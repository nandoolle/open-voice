"""Claude Code Stop hook: extract the last reply from the transcript and send it to the TTS daemon.

Receives the hook payload via stdin (JSON with transcript_path). Exits early
and silently if the voice-enabled flag is absent or the daemon is down.
Stdlib only — the hook runs on every reply and must stay cheap.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from open_voice.config import daemon_url

DAEMON_URL = daemon_url()
# marks a mid-turn block as "speak as it arrives"; the transcript follower reads
# these in real time, so this hook skips them to avoid speaking twice
SPEAK_MARKER = "🔊"
FLAG_PATH = Path.home() / ".claude" / "voice-enabled"
MAX_CHARS = 1500


def _is_human_message(entry: dict) -> bool:
    """Message typed by the user — tool_results also arrive as type user."""
    if entry.get("type") != "user":
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") == "text" for b in content
        )
    return False


def last_assistant_text(transcript_path: str) -> str:
    """Assistant text of the last turn (everything after the last human message)."""
    texts: list[str] = []
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _is_human_message(entry):
                texts = []
                continue
            if entry.get("type") != "assistant":
                continue
            content = entry.get("message", {}).get("content", [])
            chunk = "\n".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ).strip()
            if chunk:
                texts.append(chunk)
    # marked blocks were already spoken live by the follower; speak the final
    # unmarked reply only
    texts = [t for t in texts if SPEAK_MARKER not in t]
    return texts[-1] if texts else ""


def strip_markdown(text: str) -> str:
    """Remove markdown noise that sounds bad through TTS."""
    text = re.sub(r"```.*?```", " Code block omitted. ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
    text = re.sub(r"https?://\S+", "link", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def main() -> None:
    if not FLAG_PATH.exists():
        return
    payload = json.load(sys.stdin)
    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return
    # Stop may fire before the last message is flushed to the JSONL; brief retry
    import time

    text = ""
    for _ in range(8):
        text = strip_markdown(last_assistant_text(transcript_path))
        if text:
            break
        time.sleep(0.5)
    if not text:
        return
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + " ... long reply, the rest is in the terminal."
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        f"{DAEMON_URL}/say", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=2)
    except (urllib.error.URLError, OSError):
        pass  # daemon down: voice mode effectively off


if __name__ == "__main__":
    main()
