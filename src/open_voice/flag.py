"""Voice-mode flag (via /voice-on and /voice-off).

State is the file's CONTENT ("on"/"off"), not its existence: setup creates
the file once, so toggling only ever writes to an existing path — the only
capability a sandboxed shell needs when granted write access to the dir.
Lives next to the user config (~/.config/open-voice/), NOT under ~/.claude,
which is a protected path of Claude Code's Bash sandbox on Linux.
"""

from pathlib import Path

FLAG_PATH = Path.home() / ".config" / "open-voice" / "voice-enabled"
# TODO(remove after 2026-09-30): legacy flag migration (~7 users on the old
# path as of 2026-08-31) — delete _LEGACY_PATH and every reference to it
_LEGACY_PATH = Path.home() / ".claude" / "voice-enabled"


def voice_enabled() -> bool:
    try:
        return FLAG_PATH.read_text().strip() == "on"
    except OSError:
        # pre-content installs: bare existence (either location) meant enabled
        return _LEGACY_PATH.exists()


def ensure_flag() -> None:
    """Create the flag file (off) so later toggles only write, never create."""
    if not FLAG_PATH.exists():
        FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        FLAG_PATH.write_text("off\n")


def enable() -> None:
    FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    FLAG_PATH.write_text("on\n")
    _LEGACY_PATH.unlink(missing_ok=True)


def disable() -> None:
    FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    FLAG_PATH.write_text("off\n")
    _LEGACY_PATH.unlink(missing_ok=True)
