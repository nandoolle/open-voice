"""Voice mode toggles, installed as the open-voice-on / open-voice-off commands."""

import json
import subprocess
import sys
from pathlib import Path

import httpx

from open_voice.flag import disable, enable

DAEMON_URL = "http://127.0.0.1:8765"
STATE_PATH = Path.home() / ".claude" / "open-voice-listener.json"
LOG_DIR = Path.home() / ".claude"


def _bin(name: str) -> str:
    return str(Path(sys.executable).parent / name)


def _running(pattern: str) -> bool:
    return (
        subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0
    )


def _spawn(name: str, args: list[str], logfile: str) -> None:
    log = open(LOG_DIR / logfile, "a")
    subprocess.Popen(
        [_bin(name), *args], stdout=log, stderr=log, start_new_session=True
    )


def voice_on() -> None:
    enable()
    if _running("open-voice-tts-daemon"):
        print("TTS daemon already running")
    else:
        _spawn("open-voice-tts-daemon", [], "open-voice-tts.log")
        print("TTS daemon starting (log: ~/.claude/open-voice-tts.log)")

    from open_voice.mux import current_pane_from_env, get_mux

    pane = current_pane_from_env(get_mux())
    if _running("open-voice-listen"):
        try:
            active = json.loads(STATE_PATH.read_text())["pane"]
        except (OSError, ValueError, KeyError):
            active = "?"
        if pane and active != pane:
            print(f"⚠️  voice is already active on pane {active} — one session at a time.")
            print(f"   To switch to this pane ({pane}): run /voice-off, then /voice-on.")
            return
        print(f"listener already running (target: {active})")
    else:
        _spawn(
            "open-voice-listen",
            ["--pane", pane] if pane else [],
            "open-voice-listen.log",
        )
        print(f"listener in background (target: {pane or 'autodetect'}; log: ~/.claude/open-voice-listen.log)")
    print("voice mode: ON")


def voice_off() -> None:
    disable()
    try:
        httpx.post(f"{DAEMON_URL}/stop", timeout=2)
    except httpx.HTTPError:
        pass
    if subprocess.run(["pkill", "-f", "open-voice-listen"], capture_output=True).returncode == 0:
        print("listener stopped")
    if subprocess.run(["pkill", "-f", "open-voice-tts-daemon"], capture_output=True).returncode == 0:
        print("TTS daemon stopped")
    print("voice mode: OFF")
