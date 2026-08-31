"""Flag file that toggles voice mode (via /voice-on and /voice-off).

Lives next to the user config (~/.config/open-voice/), NOT under ~/.claude:
that directory is a protected path of Claude Code's Bash sandbox on Linux.
"""

from pathlib import Path

FLAG_PATH = Path.home() / ".config" / "open-voice" / "voice-enabled"
_LEGACY_PATH = Path.home() / ".claude" / "voice-enabled"


def voice_enabled() -> bool:
    return FLAG_PATH.exists() or _LEGACY_PATH.exists()


def enable() -> None:
    FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    FLAG_PATH.touch()
    _LEGACY_PATH.unlink(missing_ok=True)


def disable() -> None:
    FLAG_PATH.unlink(missing_ok=True)
    _LEGACY_PATH.unlink(missing_ok=True)
