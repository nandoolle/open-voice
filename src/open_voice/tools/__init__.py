"""Voice tool framework: registry, loading and the ctx handed to every tool.

A tool is a Python file exporting NAME, DESCRIPTION, EXAMPLES and run(ctx, text).
Built-in tools live in this package; user tools in ~/.config/open-voice/tools/
(a user tool with the same NAME overrides the built-in). A broken file is
logged and skipped — it never takes the listener down.
"""

import importlib.util
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from open_voice import config as ov_config

USER_TOOLS_DIR = Path.home() / ".config" / "open-voice" / "tools"
RESERVED = {"send", "cancel"}  # flow control, owned by the router core

# few-shot POSITION shifts the 1.5B classifier: this builtin order is the one
# the router regression battery was validated against — keep it stable
BUILTIN_ORDER = [
    "send_message",
    "pause_execution",
    "stop_media",
    "stop_speaking",
    "stop_dictation",
    "volume_up",
    "volume_down",
    "repeat_message",
]


class Ctx:
    """Capabilities a tool can use. `pane` is None when no Claude pane exists."""

    def __init__(self, mux, pane: str | None):
        self.mux = mux
        self.pane = pane
        self.config = ov_config.load()

    def say(self, text: str) -> None:
        body = json.dumps({"text": text}).encode()
        req = urllib.request.Request(
            f"{ov_config.daemon_url()}/say",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=2)
        except (urllib.error.URLError, OSError):
            pass

    def stop_tts(self) -> None:
        try:
            urllib.request.urlopen(
                urllib.request.Request(f"{ov_config.daemon_url()}/stop", method="POST"),
                timeout=2,
            )
        except (urllib.error.URLError, OSError):
            pass

    def beep(self, sound: str) -> None:
        if not self.config.get("earcons", True):
            return
        from open_voice import earcons

        earcons.play(sound)

    def shell(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(list(args), capture_output=True, text=True)

    def shutdown(self) -> None:
        """Turn voice mode off and exit the listener."""
        from open_voice.flag import disable

        self.stop_tts()
        disable()
        self.beep("Basso")
        raise SystemExit(0)


@dataclass
class Tool:
    name: str
    description: str
    examples: list[str]
    run: Callable


def _load_file(path: Path) -> Tool | None:
    spec = importlib.util.spec_from_file_location(f"open_voice_tool_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    name = module.NAME
    if name in RESERVED:
        raise ValueError(f"NAME {name!r} is reserved")
    return Tool(name, module.DESCRIPTION, list(module.EXAMPLES), module.run)


def load_tools() -> dict[str, Tool]:
    tools: dict[str, Tool] = {}
    here = Path(__file__).parent
    known = [here / f"{n}.py" for n in BUILTIN_ORDER]
    extra = sorted(
        p for p in here.glob("*.py") if p.stem != "__init__" and p.stem not in BUILTIN_ORDER
    )
    builtin = [p for p in known if p.exists()] + extra
    user = sorted(USER_TOOLS_DIR.glob("*.py")) if USER_TOOLS_DIR.exists() else []
    for path in [*builtin, *user]:
        try:
            tool = _load_file(path)
            tools[tool.name] = tool
        except Exception as exc:
            print(f"[open-voice] tool {path} skipped: {exc}", file=sys.stderr, flush=True)
    return tools
