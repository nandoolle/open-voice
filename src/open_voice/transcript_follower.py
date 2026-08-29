"""Transcript follower: speak marked assistant text as the turn unfolds.

Tails the session JSONL and sends every assistant text block that starts with
the speak marker to the TTS daemon as soon as it lands, so long-running turns
give audible progress before the final reply.
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from open_voice.mux import get_mux
from open_voice.stop_hook import DAEMON_URL, SPEAK_MARKER, strip_markdown

POLL_SECONDS = 0.3
RESOLVE_SECONDS = 5.0


def _transcript_path(pane_id: str) -> Path | None:
    return get_mux().transcript_path(pane_id)


def _say(text: str) -> None:
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        f"{DAEMON_URL}/say", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=2)
    except (urllib.error.URLError, OSError):
        pass


def _marked_texts(entry: dict) -> list[str]:
    if entry.get("type") != "assistant":
        return []
    content = entry.get("message", {}).get("content", [])
    return [
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and SPEAK_MARKER in block.get("text", "")
    ]


def follow(pane_id: str) -> None:
    """Tail the pane's session transcript forever, speaking marked blocks."""
    path: Path | None = None
    fh = None
    pending = ""
    last_resolve = 0.0
    while True:
        now = time.monotonic()
        if fh is None or now - last_resolve >= RESOLVE_SECONDS:
            last_resolve = now
            new_path = _transcript_path(pane_id)
            if new_path and new_path != path:
                if fh:
                    fh.close()
                path, pending = new_path, ""
                fh = open(path, encoding="utf-8")
                fh.seek(0, 2)  # only speak what arrives from now on
        if fh is None:
            time.sleep(1)
            continue
        chunk = fh.readline()
        if not chunk:
            time.sleep(POLL_SECONDS)
            continue
        pending += chunk
        if not pending.endswith("\n"):
            continue  # partial line still being written
        line, pending = pending, ""
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        for text in _marked_texts(entry):
            spoken = strip_markdown(text.replace(SPEAK_MARKER, ""))
            if spoken:
                _say(spoken)
