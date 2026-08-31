"""open-voice-uninstall: remove everything the standalone setup installed.

Stops the processes, removes the slash commands, the hooks from
~/.claude/settings.json and the state/flag files. Keeps the config and user
tools unless --purge is given. The uv package itself is removed last, by the
printed `uv tool uninstall` command (a process cannot remove itself).
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
CONFIG_DIR = Path.home() / ".config" / "open-voice"


def _step(msg: str) -> None:
    print(f"\n==> {msg}")


def stop_processes() -> None:
    _step("processes")
    for pattern in ("open-voice-listen", "open-voice-tts-daemon"):
        if subprocess.run(["pkill", "-f", pattern], capture_output=True).returncode == 0:
            print(f"    stopped {pattern}")


def remove_commands() -> None:
    _step("slash commands")
    # current namespaced layout plus the flat legacy names
    namespace = CLAUDE_DIR / "commands" / "open-voice"
    if namespace.exists():
        shutil.rmtree(namespace)
        print(f"    removed {namespace}")
    for name in ("voice-on.md", "voice-off.md", "voice-tool.md"):
        path = CLAUDE_DIR / "commands" / name
        if path.exists():
            path.unlink()
            print(f"    removed {path}")


def remove_hooks() -> None:
    _step("hooks in ~/.claude/settings.json")
    path = CLAUDE_DIR / "settings.json"
    if not path.exists():
        return
    settings = json.loads(path.read_text())
    hooks = settings.get("hooks", {})
    removed = 0
    for event in list(hooks):
        kept = [
            e
            for e in hooks[event]
            if not any("open-voice" in h.get("command", "") for h in e.get("hooks", []))
        ]
        removed += len(hooks[event]) - len(kept)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    print(f"    removed {removed} hook entries")


def remove_state() -> None:
    _step("state and flag files")
    from open_voice.config import LISTEN_LOG, STATE_PATH, TTS_LOG
    from open_voice.flag import FLAG_PATH, _LEGACY_PATH

    legacy = [
        CLAUDE_DIR / name
        for name in (
            "open-voice-listener.json",
            "open-voice-tts.log",
            "open-voice-listen.log",
        )
    ]
    candidates = [FLAG_PATH, _LEGACY_PATH, STATE_PATH, TTS_LOG, LISTEN_LOG, *legacy]
    for path in candidates:
        if path.exists():
            path.unlink()
            print(f"    removed {path}")


def purge_config() -> None:
    _step("config and user tools (--purge)")
    if CONFIG_DIR.exists():
        shutil.rmtree(CONFIG_DIR)
        print(f"    removed {CONFIG_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description="open-voice uninstaller")
    parser.add_argument(
        "--purge",
        action="store_true",
        help="also remove ~/.config/open-voice (config and user tools)",
    )
    args = parser.parse_args()

    print("open-voice uninstall")
    stop_processes()
    remove_commands()
    remove_hooks()
    remove_state()
    if args.purge:
        purge_config()

    _step("done")
    print("    to remove the package itself: uv tool uninstall open-voice")
    print("    if installed as a Claude Code plugin: /plugin uninstall open-voice")


if __name__ == "__main__":
    main()
