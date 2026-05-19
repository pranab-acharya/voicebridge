"""
Copies the latest transcript to the system clipboard after each update.
Recruiter pastes it into the ATS text field.

Linux:  requires xclip or xsel
macOS:  uses pbcopy
"""
import subprocess
import sys
from .base import Plugin


class ClipboardPlugin(Plugin):
    name = "clipboard"

    def on_call_start(self, _: dict) -> None:
        self._copy("")

    def on_transcript(self, data: dict) -> None:
        self._copy(data.get("text", ""))

    def _copy(self, text: str) -> None:
        try:
            if sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=text.encode(), check=True)
            else:
                try:
                    subprocess.run(["xclip", "-selection", "clipboard"],
                                   input=text.encode(), check=True,
                                   capture_output=True)
                except FileNotFoundError:
                    subprocess.run(["xsel", "--clipboard", "--input"],
                                   input=text.encode(), check=True,
                                   capture_output=True)
        except Exception:
            pass
