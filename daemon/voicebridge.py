#!/usr/bin/env python3
"""
VoiceBridge laptop daemon.

Usage examples
--------------
# Test mode — phone connected via USB, ADB forward in place:
    adb forward tcp:7654 tcp:7654
    python voicebridge.py

# Events only, no Whisper (instant start, good for protocol testing):
    python voicebridge.py --no-transcribe

# Production AOAv2 USB:
    python voicebridge.py --transport aoa

# Custom triggers:
    python voicebridge.py --trigger "offer:offer letter" --trigger "start:start date"

# Larger Whisper model for better accuracy:
    python voicebridge.py --model small
"""
import argparse
import struct
import sys
import time

from rich.console import Console

from core.event_bus import EventBus
from core.packet import (
    HEADER_SIZE, MAGIC,
    TYPE_AUDIO_FRAME, TYPE_CALL_START, TYPE_CALL_END,
    TYPE_HEARTBEAT, TYPE_METADATA,
    parse_packet,
)
from core.session import CallSession
from plugins.console import ConsolePlugin
from plugins.triggers import TriggerPlugin, KeywordTrigger
from plugins.transcript_log import TranscriptLogPlugin
from plugins.clipboard import ClipboardPlugin

con = Console(highlight=False)


# ── Default triggers ─────────────────────────────────────────────────────────

DEFAULT_TRIGGERS = [
    KeywordTrigger("salary",     [r"\$[\d,]+", r"salary", r"compensation", r"pay range"]),
    KeywordTrigger("timeline",   [r"start date", r"notice period", r"available", r"join"]),
    KeywordTrigger("next_steps", [r"next steps?", r"follow.?up", r"get back to you",
                                   r"schedule.*interview"]),
    KeywordTrigger("remote",     [r"remote", r"work from home", r"on.?site", r"hybrid"]),
    KeywordTrigger("benefits",   [r"benefits", r"health insurance", r"401k", r"PTO"]),
]


# ── Packet dispatch loop ─────────────────────────────────────────────────────

def _run(transport, bus: EventBus, session: CallSession,
         decoder, transcriber) -> None:
    buf = b""

    while True:
        # ── reconnect ────────────────────────────────────────────────────────
        if not transport.is_connected:
            con.print(f"[yellow]Connecting via {transport.name} …[/]")
            while not transport.connect():
                time.sleep(2)
            bus.publish("transport_connected", {"name": transport.name})

        # ── read ─────────────────────────────────────────────────────────────
        chunk = transport.read(4096)
        if chunk is None:
            bus.publish("transport_disconnected", {})
            transport.disconnect()
            continue
        buf += chunk

        # ── parse packets ────────────────────────────────────────────────────
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

            _dispatch(pkt, bus, session, decoder, transcriber, transport)


def _dispatch(pkt, bus, session, decoder, transcriber, transport) -> None:
    if pkt.type == TYPE_CALL_START:
        number = pkt.payload.decode("utf-8", errors="replace")
        session.start(number)
        decoder.reset()
        transcriber.clear()
        transcriber.start()
        bus.publish("call_start", {"number": number, "seq_id": pkt.seq_id})

    elif pkt.type == TYPE_CALL_END:
        dur = session.duration_s
        session.end()
        transcriber.stop()
        bus.publish("call_end", {"seq_id": pkt.seq_id, "duration_s": dur})

    elif pkt.type == TYPE_HEARTBEAT:
        bus.publish("heartbeat", {"seq_id": pkt.seq_id})

    elif pkt.type == TYPE_AUDIO_FRAME:
        session.record_frame(len(pkt.payload))
        bus.publish("audio_frame", {
            "seq_id":        pkt.seq_id,
            "encoded_bytes": len(pkt.payload),
            "total_frames":  session.frames_received,
            "total_bytes":   session.bytes_received,
        })
        if session.is_active:
            pcm = decoder.decode(pkt.payload)
            if pcm is not None:
                transcriber.push(pcm)

    elif pkt.type == TYPE_METADATA:
        bus.publish("metadata", {
            "seq_id":  pkt.seq_id,
            "payload": pkt.payload,
        })


# ── Null transcriber (--no-transcribe) ───────────────────────────────────────

class _NoopTranscriber:
    def start(self):  pass
    def stop(self):   pass
    def push(self, _): pass
    def clear(self):  pass


# ── Decoder with reset ────────────────────────────────────────────────────────

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

def main() -> None:
    p = argparse.ArgumentParser(
        description="VoiceBridge laptop daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--transport", choices=["tcp", "aoa"], default="tcp",
                   help="tcp = ADB forward (default)  |  aoa = AOAv2 USB")
    p.add_argument("--host",  default="127.0.0.1", help="TCP host (tcp mode)")
    p.add_argument("--port",  type=int, default=7654, help="TCP port (tcp mode)")
    p.add_argument("--model", default="base",
                   choices=["tiny", "base", "small", "medium", "large"],
                   help="Whisper model size (default: base)")
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda"],
                   help="Whisper inference device")
    p.add_argument("--no-transcribe", action="store_true",
                   help="Disable Whisper — events and audio stats only")
    p.add_argument("--no-clipboard", action="store_true",
                   help="Disable clipboard output")
    p.add_argument("--no-log", action="store_true",
                   help="Disable per-call transcript file logging")
    p.add_argument("--log-dir", default="logs",
                   help="Directory for call transcript logs")
    p.add_argument("--trigger", action="append", metavar="NAME:PATTERN",
                   help="Extra trigger, e.g.  --trigger offer:\"offer letter\"")
    p.add_argument("--no-default-triggers", action="store_true",
                   help="Skip the built-in salary/timeline/remote/… triggers")
    args = p.parse_args()

    # ── transport ─────────────────────────────────────────────────────────────
    if args.transport == "tcp":
        from transport.tcp import TcpTransport
        transport = TcpTransport(args.host, args.port)
        con.print(f"[cyan]Transport :[/] TCP {args.host}:{args.port}")
        con.print(f"[dim]            Run first:  adb forward tcp:{args.port} tcp:{args.port}[/dim]")
    else:
        from transport.aoa import AoaTransport
        transport = AoaTransport()
        con.print("[cyan]Transport :[/] AOAv2 USB")

    # ── event bus ─────────────────────────────────────────────────────────────
    bus     = EventBus()
    session = CallSession()
    decoder = _ResettableDecoder()

    # ── transcriber ───────────────────────────────────────────────────────────
    if args.no_transcribe:
        transcriber = _NoopTranscriber()
        con.print("[cyan]Transcription :[/] disabled")
    else:
        con.print(f"[cyan]Whisper model :[/] {args.model} on {args.device}  (loading…)")
        from audio.transcriber import StreamingTranscriber
        transcriber = StreamingTranscriber(
            model_size=args.model,
            device=args.device,
            on_transcript=lambda t: bus.publish("transcript", {"text": t}),
        )
        con.print("[green]Whisper ready[/]")

    # ── plugins ───────────────────────────────────────────────────────────────
    ConsolePlugin().register(bus)

    if not args.no_log:
        TranscriptLogPlugin(log_dir=args.log_dir).register(bus)

    if not args.no_clipboard:
        ClipboardPlugin().register(bus)

    trigger_plugin = TriggerPlugin()
    if not args.no_default_triggers:
        for t in DEFAULT_TRIGGERS:
            trigger_plugin.add(t)
    if args.trigger:
        for spec in args.trigger:
            name, _, pattern = spec.partition(":")
            trigger_plugin.add(KeywordTrigger(name.strip(), [pattern.strip()]))
    trigger_plugin.register(bus)

    con.rule("[bold green]VoiceBridge daemon ready[/bold green]")

    try:
        _run(transport, bus, session, decoder, transcriber)
    except KeyboardInterrupt:
        con.print("\n[yellow]Shutting down…[/]")
        try:
            transcriber.stop()
        except Exception:
            pass
        transport.disconnect()


if __name__ == "__main__":
    main()
