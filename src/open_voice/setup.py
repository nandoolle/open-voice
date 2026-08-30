"""open-voice-setup: one-command install of the voice loop for Claude Code.

Installs the /open-voice:on, :off and :tool slash commands, the Claude Code hooks
(Stop TTS + 🔊 reminder), the anti-hint setting, checks the multiplexer and microphone
access, and pre-downloads the models.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from open_voice import config as ov_config

CLAUDE_DIR = Path.home() / ".claude"


def _choose(label: str, options: list[str], default: str) -> str:
    if not sys.stdin.isatty():
        return default
    menu = ", ".join(f"[{o}]" if o == default else o for o in options)
    while True:
        answer = input(f"    {label} ({menu}): ").strip().lower() or default
        if answer in options:
            return answer
        print(f"    pick one of: {', '.join(options)}")


def configure(args) -> dict:
    _step("configuration (~/.config/open-voice/config.json)")
    # defaults: router size picked by available RAM, multiplexer is herdr
    router_rec = ov_config.recommended_router_model()
    whisper_rec = ov_config.recommended_whisper_model()
    cfg = {
        "router_model": args.router_model
        or _choose(
            f"router model (Qwen2.5; {router_rec} recommended for this machine's RAM)",
            list(ov_config.ROUTER_MODELS),
            router_rec,
        ),
        "whisper_model": args.whisper_model
        or _choose(
            f"whisper model (STT; {whisper_rec} recommended for this machine's RAM)",
            list(ov_config.WHISPER_MODELS),
            whisper_rec,
        ),
        "multiplexer": args.multiplexer
        or _choose("multiplexer", list(ov_config.MULTIPLEXERS), ov_config.DEFAULTS["multiplexer"]),
    }
    # merge over the full config so runtime keys survive a setup rerun
    ov_config.save({**ov_config.load(), **cfg})
    print(
        f"    saved: router {cfg['router_model']}, whisper {cfg['whisper_model']}, "
        f"multiplexer {cfg['multiplexer']}"
    )
    return cfg


def _bin(name: str) -> str:
    return str(Path(sys.executable).parent / name)


def _step(msg: str) -> None:
    print(f"\n==> {msg}")


def install_commands() -> None:
    _step("slash commands (/open-voice:on, :off, :tool)")
    # the subdirectory is the namespace — same API as the Claude Code plugin
    commands = CLAUDE_DIR / "commands" / "open-voice"
    commands.mkdir(parents=True, exist_ok=True)
    on, off = _bin("open-voice-on"), _bin("open-voice-off")
    (commands / "on.md").write_text(
        f"""---
description: Turn open-voice on (flag + TTS daemon + listener)
allowed-tools: Bash({on})
---

Result: !`{on}`

Confirm to the user in one line that voice mode is on (or what failed above).
"""
    )
    (commands / "off.md").write_text(
        f"""---
description: Turn open-voice off (flag, speech and all processes)
allowed-tools: Bash({off})
---

Result: !`{off}`

Confirm to the user in one line that voice mode is off.
"""
    )
    route_bin = _bin("open-voice-route")
    (commands / "tool.md").write_text(
        f"""---
description: Create a new open-voice voice tool (voice command for the local voice loop)
allowed-tools: Write, Read, Bash({route_bin})
---

Create a new voice tool for open-voice from this request: $ARGUMENTS

A voice tool is one Python file in `~/.config/open-voice/tools/` with this exact contract:

```python
NAME = "lock_screen"                                  # unique label, snake_case; "send" and "cancel" are reserved
DESCRIPTION = "explicitly asks to lock the screen"    # one line, English, starts with "explicitly asks"
EXAMPLES = ["trava a tela", "lock the screen"]        # 2-5 spoken phrasings (include the user's language)

def run(ctx, text):                                   # text = full transcription; ignore it for fixed intents
    ctx.shell("pmset", "displaysleepnow")
```

`ctx` provides: `say(text)` speak via TTS · `beep(sound)` macOS earcon · `stop_tts()` ·
`shell(*args)` run a command · `pane` Claude pane id or None · `mux` pane control
(`send_enter`/`send_esc`/`send_text`) · `config` open-voice config dict · `shutdown()` stop voice mode.
A tool that needs the pane must handle `ctx.pane is None` (e.g. `ctx.say` an error).

Steps:
1. Write the file to `~/.config/open-voice/tools/<name>.py`.
2. Validate routing: run `{route_bin} "<each example phrase>"` and confirm each prints the new NAME.
   If a phrase misroutes, reword DESCRIPTION/EXAMPLES and retry.
3. Tell the user the tool is ready and that /open-voice:off + /open-voice:on reloads it.
"""
    )
    print(f"    written to {commands}")


def install_settings(plugin_mode: bool) -> None:
    _step("Claude Code settings" + (" (composer hints off)" if plugin_mode else " (hooks + composer hints off)"))
    path = CLAUDE_DIR / "settings.json"
    settings = json.loads(path.read_text()) if path.exists() else {}

    if not plugin_mode:
        # in plugin mode the hooks ship with the plugin's hooks.json
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


def check_multiplexer(name: str) -> bool:
    _step(name)
    if shutil.which(name):
        print("    found in PATH")
        return True
    pkg = "brew install" if sys.platform == "darwin" else "sudo apt install"
    hint = {"herdr": "https://herdr.dev", "tmux": f"{pkg} tmux", "zellij": f"{pkg} zellij"}[name]
    print(f"    NOT FOUND — install it first ({hint}) or rerun setup with another --multiplexer.")
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
        if sys.platform == "darwin":
            print("    grant microphone access to your terminal in System Settings →")
            print("    Privacy & Security → Microphone, then rerun open-voice-setup.")
        else:
            print("    check that an audio input exists (PulseAudio/PipeWire running,")
            print("    libportaudio2 installed; on WSL2 you need WSLg for mic passthrough),")
            print("    then rerun open-voice-setup.")
        return False


def download_models() -> None:
    _step("models (first run downloads a few GB — grab a coffee)")
    import numpy as np

    print("    silero VAD...")
    from silero_vad import load_silero_vad

    load_silero_vad()

    print(f"    whisper ({ov_config.whisper_model_repo()})...")
    from open_voice.listen import transcribe

    transcribe(np.zeros(16_000, dtype=np.float32))

    print(f"    router ({ov_config.router_model_repo()})...")
    from open_voice.listen import _router

    _router()

    print("    kokoro TTS...")
    from open_voice.tts_daemon import KokoroEngine

    cfg = ov_config.load()
    KokoroEngine(cfg["tts_lang"], cfg["tts_voice"])
    print("    all models ready")


def main() -> None:
    parser = argparse.ArgumentParser(description="open-voice installer")
    parser.add_argument(
        "--skip-models", action="store_true", help="skip pre-downloading the models"
    )
    parser.add_argument(
        "--router-model",
        choices=list(ov_config.ROUTER_MODELS),
        help="Qwen router size (skips the interactive question)",
    )
    parser.add_argument(
        "--whisper-model",
        choices=list(ov_config.WHISPER_MODELS),
        help="whisper STT size (skips the interactive question)",
    )
    parser.add_argument(
        "--multiplexer",
        choices=list(ov_config.MULTIPLEXERS),
        help="terminal multiplexer backend (skips the interactive question)",
    )
    parser.add_argument(
        "--plugin",
        action="store_true",
        help="installed via the Claude Code plugin: skip commands and hooks (the plugin ships them)",
    )
    args = parser.parse_args()

    print("open-voice setup")
    cfg = configure(args)
    if not args.plugin:
        install_commands()
    install_settings(plugin_mode=args.plugin)
    mux_ok = check_multiplexer(cfg["multiplexer"])
    mic_ok = check_microphone()
    if not args.skip_models:
        download_models()

    _step("done")
    if mux_ok and mic_ok:
        print(f"    start a Claude Code session inside {cfg['multiplexer']} and run /open-voice:on.")
    else:
        print("    fix the items marked FAILED/NOT FOUND above, then rerun setup.")


if __name__ == "__main__":
    main()
