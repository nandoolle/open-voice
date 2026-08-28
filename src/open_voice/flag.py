"""Flag file que liga/desliga o modo voz (toggle via /voice-on e /voice-off)."""

from pathlib import Path

FLAG_PATH = Path.home() / ".claude" / "voice-enabled"


def voice_enabled() -> bool:
    return FLAG_PATH.exists()


def enable() -> None:
    FLAG_PATH.touch()


def disable() -> None:
    FLAG_PATH.unlink(missing_ok=True)
