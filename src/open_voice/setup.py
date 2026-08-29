"""open-voice-setup: one-command install of the voice loop for Claude Code.

Installs the /voice-on and /voice-off slash commands, the Claude Code hooks
(Stop TTS + 🔊 reminder), the anti-hint setting, checks herdr and microphone
access, and pre-downloads the models.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"


def _bin(name: str) -> str:
    return str(Path(sys.executable).parent / name)


def _step(msg: str) -> None:
    print(f"\n==> {msg}")


def install_commands() -> None:
    _step("slash commands (/voice-on, /voice-off)")
    commands = CLAUDE_DIR / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    on, off = _bin("open-voice-on"), _bin("open-voice-off")
    (commands / "voice-on.md").write_text(
        f"""---
description: Turn open-voice on (flag + TTS daemon + listener)
allowed-tools: Bash({on})
---

Result: !`{on}`

Confirm to the user in one line that voice mode is on (or what failed above).
"""
    )
    (commands / "voice-off.md").write_text(
        f"""---
description: Turn open-voice off (flag, speech and all processes)
allowed-tools: Bash({off})
---

Result: !`{off}`

Confirm to the user in one line that voice mode is off.
"""
    )
    print(f"    written to {commands}")


def install_settings() -> None:
    _step("Claude Code settings (hooks + composer hints off)")
    path = CLAUDE_DIR / "settings.json"
    settings = json.loads(path.read_text()) if path.exists() else {}

    hooks = settings.setdefault("hooks", {})

    def replace(event: str, command: str) -> None:
        entries = [
            e
            for e in hooks.get(event, [])
            if not any("open-voice" in h.get("command", "") for h in e.get("hooks", []))
        ]
        entries.append({"hooks": [{"type": "command", "command": command}]})
        hooks[event] = entries

    replace("Stop", _bin("open-voice-stop-hook"))
    replace("UserPromptSubmit", _bin("open-voice-prompt-hook"))
    # composer placeholder suggestions are a confirmed source of false positives
    # in the draft detector
    settings["promptSuggestionEnabled"] = False

    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    print(f"    merged into {path}")


def check_herdr() -> bool:
    _step("herdr")
    if shutil.which("herdr"):
        print("    found in PATH")
        return True
    print("    NOT FOUND — open-voice requires herdr (https://herdr.dev).")
    return False


def check_microphone() -> bool:
    _step("microphone access (a permission prompt may appear)")
    try:
        import numpy as np
        import sounddevice as sd

        recording = sd.rec(int(0.3 * 16_000), samplerate=16_000, channels=1)
        sd.wait()
        level = float(np.abs(recording).max())
        print(f"    capture ok (peak {level:.4f})")
        return True
    except Exception as exc:
        print(f"    FAILED: {exc}")
        print("    grant microphone access to your terminal in System Settings →")
        print("    Privacy & Security → Microphone, then rerun open-voice-setup.")
        return False


def download_models() -> None:
    _step("models (first run downloads a few GB — grab a coffee)")
    import numpy as np

    print("    silero VAD...")
    from silero_vad import load_silero_vad

    load_silero_vad()

    print("    whisper (mlx-community/whisper-large-v3-turbo)...")
    from open_voice.listen import transcribe

    transcribe(np.zeros(16_000, dtype=np.float32))

    print("    router (Qwen2.5-1.5B-Instruct-4bit)...")
    from open_voice.listen import _router

    _router()

    print("    kokoro TTS...")
    from open_voice.tts_daemon import KokoroEngine

    KokoroEngine("p", "pf_dora")
    print("    all models ready")


def main() -> None:
    parser = argparse.ArgumentParser(description="open-voice installer")
    parser.add_argument(
        "--skip-models", action="store_true", help="skip pre-downloading the models"
    )
    args = parser.parse_args()

    print("open-voice setup")
    install_commands()
    install_settings()
    herdr_ok = check_herdr()
    mic_ok = check_microphone()
    if not args.skip_models:
        download_models()

    _step("done")
    if herdr_ok and mic_ok:
        print("    start a Claude Code session inside herdr and run /voice-on.")
    else:
        print("    fix the items marked FAILED/NOT FOUND above, then rerun setup.")


if __name__ == "__main__":
    main()
