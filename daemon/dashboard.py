#!/usr/bin/env python3
"""
VoiceBridge live TUI dashboard.

Runs the full daemon inside a Rich live layout:

  ┌─ VoiceBridge ──────────────────── status ─────────────────────────────┐
  │  Transport: TCP 127.0.0.1:7654          ● CONNECTED                   │
  │  Call: +1 (555) 000-1234                ● ACTIVE  0m 42s              │
  ├─ Event Log ──────────────────┬─ Live Transcript ──────────────────────┤
  │  10:02:01 ▶ audio  seq=120  │  Hello, I wanted to discuss the        │
  │  10:02:03 ♥ heartbeat       │  compensation package for the role...  │
  │  10:02:05 ▶ audio  seq=121  │                                        │
  │  ...                         │                                        │
  ├──────────────────────────────┴────────────────────────────────────────┤
  │  ⚡ TRIGGER [salary]  → "$120,000"   10:02:07                         │
  └───────────────────────────────────────────────────────────────────────┘

Usage:
    python dashboard.py                        # TCP, base Whisper
    python dashboard.py --no-transcribe        # events only
    python dashboard.py --transport aoa        # AOAv2 USB
    python dashboard.py --model small          # better accuracy
"""
import argparse
import struct
import sys
import time
import threading
from collections import deque
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from core.event_bus import EventBus
from core.packet import (
    HEADER_SIZE, MAGIC,
    TYPE_AUDIO_FRAME, TYPE_CALL_START, TYPE_CALL_END,
    TYPE_HEARTBEAT, TYPE_METADATA,
    parse_packet,
)
from core.session import CallSession
from plugins.triggers import TriggerPlugin, KeywordTrigger
from plugins.transcript_log import TranscriptLogPlugin
from plugins.clipboard import ClipboardPlugin

MAX_EVENTS   = 30
MAX_TRIGGERS = 8


# ── State shared between daemon thread and renderer ──────────────────────────

class DashboardState:
    def __init__(self):
        self.lock          = threading.Lock()
        self.transport_name = ""
        self.connected     = False
        self.call_active   = False
        self.call_number   = ""
        self.call_start_ts : datetime | None = None
        self.frames        = 0
        self.total_bytes   = 0
        self.transcript    = ""
        self.events: deque = deque(maxlen=MAX_EVENTS)
        self.triggers: deque = deque(maxlen=MAX_TRIGGERS)

    def log(self, icon: str, text: str, style: str = "white") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.events.appendleft((ts, icon, text, style))

    def add_trigger(self, name: str, match: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.triggers.appendleft((ts, name, match))


# ── Rich layout renderer ──────────────────────────────────────────────────────

def _render(state: DashboardState) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body"),
        Layout(name="triggers", size=min(len(state.triggers) + 2, MAX_TRIGGERS + 2)),
    )
    layout["body"].split_row(
        Layout(name="events"),
        Layout(name="transcript"),
    )

    # ── header ────────────────────────────────────────────────────────────────
    conn_str = (
        "[bold green]● CONNECTED[/]" if state.connected
        else "[bold red]● DISCONNECTED[/]"
    )
    call_str = ""
    if state.call_active and state.call_start_ts:
        dur = int((datetime.now() - state.call_start_ts).total_seconds())
        call_str = (
            f"[bold green]● ACTIVE[/]  "
            f"[cyan]{state.call_number or 'unknown'}[/]  "
            f"[dim]{dur // 60}m {dur % 60}s  "
            f"{state.frames} frames  "
            f"{state.total_bytes / 1024:.1f} kB[/dim]"
        )
    elif not state.call_active:
        call_str = "[dim]● IDLE — waiting for call[/dim]"

    header_grid = Table.grid(expand=True)
    header_grid.add_column(ratio=1)
    header_grid.add_column(ratio=1)
    header_grid.add_row(
        f"[bold white]Transport:[/]  {state.transport_name}    {conn_str}",
        call_str,
    )
    layout["header"].update(Panel(header_grid, title="[bold cyan]VoiceBridge[/]",
                                   border_style="cyan"))

    # ── event log ─────────────────────────────────────────────────────────────
    tbl = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    tbl.add_column("ts",   style="dim",   no_wrap=True, width=8)
    tbl.add_column("icon", no_wrap=True,  width=2)
    tbl.add_column("msg",  overflow="fold")
    with state.lock:
        for ts, icon, text, style in list(state.events):
            tbl.add_row(ts, icon, Text(text, style=style))
    layout["events"].update(Panel(tbl, title="Event Log", border_style="blue"))

    # ── transcript ────────────────────────────────────────────────────────────
    with state.lock:
        transcript_text = state.transcript or "[dim]Waiting for speech…[/dim]"
    layout["transcript"].update(
        Panel(Text.from_markup(transcript_text, overflow="fold"),
              title="Live Transcript", border_style="yellow")
    )

    # ── triggers ──────────────────────────────────────────────────────────────
    trig_grid = Table.grid(expand=True, padding=(0, 2))
    trig_grid.add_column("ts",    style="dim",          no_wrap=True, width=8)
    trig_grid.add_column("name",  style="bold magenta", no_wrap=True, width=14)
    trig_grid.add_column("match", style="white")
    with state.lock:
        rows = list(state.triggers)
    if rows:
        for ts, name, match in rows:
            trig_grid.add_row(ts, f"⚡ {name}", f'"{match}"')
    else:
        trig_grid.add_row("", "[dim]No triggers fired yet[/dim]", "")
    layout["triggers"].update(
        Panel(trig_grid, title="Triggers", border_style="magenta")
    )

    return layout


# ── Daemon thread ─────────────────────────────────────────────────────────────

def _run_daemon(transport, bus, session, decoder, transcriber, state):
    buf = b""

    while True:
        if not transport.is_connected:
            state.log("…", f"Connecting via {transport.name}", "yellow")
            with state.lock:
                state.connected = False
            while not transport.connect():
                time.sleep(2)
            with state.lock:
                state.connected      = True
                state.transport_name = transport.name
            bus.publish("transport_connected", {"name": transport.name})

        chunk = transport.read(4096)
        if chunk is None:
            with state.lock:
                state.connected = False
            bus.publish("transport_disconnected", {})
            transport.disconnect()
            continue

        buf += chunk

        while len(buf) >= HEADER_SIZE:
            pos = buf.find(MAGIC)
            if pos < 0:
                buf = buf[-3:]
                break
            if pos > 0:
                buf = buf[pos:]
            if len(buf) < HEADER_SIZE:
                break

            length = struct.unpack_from(">I", buf, 9)[0]
            total  = HEADER_SIZE + length
            if len(buf) < total:
                break

            pkt = parse_packet(buf[:total])
            buf = buf[total:]
            if pkt is None:
                continue

            if pkt.type == TYPE_CALL_START:
                number = pkt.payload.decode("utf-8", errors="replace")
                session.start(number)
                decoder.reset()
                transcriber.clear()
                transcriber.start()
                with state.lock:
                    state.call_active   = True
                    state.call_number   = number
                    state.call_start_ts = datetime.now()
                    state.frames        = 0
                    state.total_bytes   = 0
                    state.transcript    = ""
                state.log("📞", f"CALL STARTED  {number}", "bold green")
                bus.publish("call_start", {"number": number})

            elif pkt.type == TYPE_CALL_END:
                dur = session.duration_s
                session.end()
                transcriber.stop()
                with state.lock:
                    state.call_active = False
                state.log("📵", f"CALL ENDED  ({int(dur or 0)}s)", "bold red")
                bus.publish("call_end", {"duration_s": dur})

            elif pkt.type == TYPE_HEARTBEAT:
                state.log("♥", f"heartbeat  seq={pkt.seq_id}", "dim")
                bus.publish("heartbeat", {"seq_id": pkt.seq_id})

            elif pkt.type == TYPE_AUDIO_FRAME:
                session.record_frame(len(pkt.payload))
                with state.lock:
                    state.frames      = session.frames_received
                    state.total_bytes = session.bytes_received
                state.log("▶", f"audio  seq={pkt.seq_id}  {len(pkt.payload)}B", "blue")
                bus.publish("audio_frame", {
                    "seq_id":        pkt.seq_id,
                    "encoded_bytes": len(pkt.payload),
                })
                if session.is_active:
                    pcm = decoder.decode(pkt.payload)
                    if pcm is not None:
                        transcriber.push(pcm)


# ── Null transcriber ──────────────────────────────────────────────────────────

class _NoopTranscriber:
    def start(self):      pass
    def stop(self):       pass
    def push(self, _):    pass
    def clear(self):      pass


class _ResettableDecoder:
    def __init__(self):
        self._dec = None
        self.reset()

    def reset(self):
        from audio.decoder import OpusDecoder
        self._dec = OpusDecoder()

    def decode(self, data):
        return self._dec.decode(data)


# ── CLI ───────────────────────────────────────────────────────────────────────

DEFAULT_TRIGGERS = [
    KeywordTrigger("salary",     [r"\$[\d,]+", r"salary", r"compensation", r"pay range"]),
    KeywordTrigger("timeline",   [r"start date", r"notice period", r"available", r"join"]),
    KeywordTrigger("next_steps", [r"next steps?", r"follow.?up", r"get back to you"]),
    KeywordTrigger("remote",     [r"remote", r"work from home", r"on.?site", r"hybrid"]),
    KeywordTrigger("benefits",   [r"benefits", r"health insurance", r"401k", r"PTO"]),
]


def main():
    p = argparse.ArgumentParser(description="VoiceBridge live dashboard")
    p.add_argument("--transport", choices=["tcp", "aoa"], default="tcp")
    p.add_argument("--host",  default="127.0.0.1")
    p.add_argument("--port",  type=int, default=7654)
    p.add_argument("--model", default="base",
                   choices=["tiny", "base", "small", "medium", "large"])
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    p.add_argument("--no-transcribe", action="store_true")
    p.add_argument("--no-clipboard",  action="store_true")
    p.add_argument("--no-log",        action="store_true")
    p.add_argument("--log-dir",       default="logs")
    args = p.parse_args()

    con = Console()

    # transport
    if args.transport == "tcp":
        from transport.tcp import TcpTransport
        transport = TcpTransport(args.host, args.port)
    else:
        from transport.aoa import AoaTransport
        transport = AoaTransport()

    state = DashboardState()
    state.transport_name = transport.name

    bus     = EventBus()
    session = CallSession()
    decoder = _ResettableDecoder()

    # transcriber
    if args.no_transcribe:
        transcriber = _NoopTranscriber()
    else:
        con.print(f"[cyan]Loading Whisper [{args.model}] on {args.device}…[/]")
        from audio.transcriber import StreamingTranscriber
        def _on_transcript(text):
            with state.lock:
                state.transcript = text
            bus.publish("transcript", {"text": text})
        transcriber = StreamingTranscriber(
            model_size=args.model, device=args.device,
            on_transcript=_on_transcript,
        )
        con.print("[green]Whisper ready[/]")

    # plugins (non-display ones)
    if not args.no_log:
        TranscriptLogPlugin(log_dir=args.log_dir).register(bus)
    if not args.no_clipboard:
        ClipboardPlugin().register(bus)

    trig_plugin = TriggerPlugin()
    for t in DEFAULT_TRIGGERS:
        trig_plugin.add(t)
    trig_plugin.register(bus)

    # wire trigger_fired → dashboard state
    def _on_trigger(data):
        state.add_trigger(data.get("trigger", ""), data.get("matched_text", ""))
    bus.subscribe("trigger_fired", _on_trigger)

    # daemon thread
    daemon = threading.Thread(
        target=_run_daemon,
        args=(transport, bus, session, decoder, transcriber, state),
        name="DaemonThread",
        daemon=True,
    )
    daemon.start()

    # live dashboard
    try:
        with Live(_render(state), refresh_per_second=4, screen=True) as live:
            while True:
                live.update(_render(state))
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        con.print("\n[yellow]Shutting down…[/]")
        try:
            transcriber.stop()
        except Exception:
            pass
        transport.disconnect()


if __name__ == "__main__":
    main()
