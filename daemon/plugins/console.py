"""
Rich terminal display plugin.

Shows a live event feed:
  ✓ USB connected
  ━━━ CALL STARTED — +1 (555) 000-1234
  ▶ audio  seq=42  38 B encoded  [12 frames | 2.1 kB total]
  📝 TRANSCRIPT: Hello, I'm calling about the position...
  ⚡ TRIGGER [salary] → "$120,000"
  ━━━ CALL ENDED  (duration 3m 42s)
"""
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from .base import Plugin

_con = Console(highlight=False)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class ConsolePlugin(Plugin):
    name = "console"

    # ── connection ────────────────────────────────────────────────────────────

    def on_transport_connected(self, data: dict) -> None:
        _con.print(f"[{_ts()}] [bold green]✓ Connected[/]  {data.get('name', '')}")

    def on_transport_disconnected(self, data: dict) -> None:
        _con.print(f"[{_ts()}] [bold red]✗ Disconnected[/]")

    # ── call lifecycle ────────────────────────────────────────────────────────

    def on_call_start(self, data: dict) -> None:
        number = data.get("number") or "unknown"
        _con.print(Panel(
            f"[bold green]CALL STARTED[/]  [white]{number}[/]",
            border_style="green", padding=(0, 2)
        ))

    def on_call_end(self, data: dict) -> None:
        dur = data.get("duration_s")
        dur_str = f"  duration {int(dur // 60)}m {int(dur % 60)}s" if dur else ""
        _con.print(Panel(
            f"[bold red]CALL ENDED[/]{dur_str}",
            border_style="red", padding=(0, 2)
        ))

    # ── packets ───────────────────────────────────────────────────────────────

    def on_heartbeat(self, data: dict) -> None:
        _con.print(
            f"[{_ts()}] [dim]♥  heartbeat  seq={data.get('seq_id', '?')}[/dim]"
        )

    def on_audio_frame(self, data: dict) -> None:
        _con.print(
            f"[{_ts()}] [blue]▶  audio[/]"
            f"  seq={data.get('seq_id', '?')}"
            f"  {data.get('encoded_bytes', 0)} B"
            f"  [dim]frames={data.get('total_frames', '?')}"
            f"  total={data.get('total_bytes', 0)//1024:.1f} kB[/dim]"
        )

    # ── transcription & triggers ──────────────────────────────────────────────

    def on_transcript(self, data: dict) -> None:
        text = data.get("text", "")
        _con.print(f"\n[{_ts()}] [bold yellow]📝  TRANSCRIPT[/]\n   {text}\n")

    def on_trigger_fired(self, data: dict) -> None:
        _con.print(
            f"[{_ts()}] [bold magenta]⚡  TRIGGER [{data.get('trigger')}][/]"
            f"  → \"{data.get('matched_text')}\""
        )
