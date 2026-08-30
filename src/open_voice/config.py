"""User configuration: ~/.config/open-voice/config.json, written by setup."""

import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "open-voice" / "config.json"

IS_MAC = sys.platform == "darwin"

# same size keys everywhere; the artifact per platform differs (MLX vs GGUF/CT2)
if IS_MAC:
    ROUTER_MODELS = {
        "0.5b": "mlx-community/Qwen2.5-0.5B-Instruct-4bit",
        "1.5b": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    }
    WHISPER_MODELS = {
        "small": "mlx-community/whisper-small-mlx",
        "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    }
else:
    ROUTER_MODELS = {
        "0.5b": ("Qwen/Qwen2.5-0.5B-Instruct-GGUF", "qwen2.5-0.5b-instruct-q4_k_m.gguf"),
        "1.5b": ("Qwen/Qwen2.5-1.5B-Instruct-GGUF", "qwen2.5-1.5b-instruct-q4_k_m.gguf"),
    }
    # faster-whisper model aliases (resolved to CTranslate2 repos by the lib)
    WHISPER_MODELS = {
        "small": "small",
        "large-v3-turbo": "large-v3-turbo",
    }
MULTIPLEXERS = ("herdr", "tmux", "zellij")

DEFAULTS = {
    # setup-time choices
    "router_model": "1.5b",
    "whisper_model": "large-v3-turbo",
    "multiplexer": "herdr" if IS_MAC else "tmux",
    # runtime tuning (open-voice-config to inspect/change)
    "whisper_language": "en",
    "tts_engine": "kokoro",
    "tts_voice": "af_heart",  # en-US female; lang_code "a" = American English
    "tts_lang": "a",
    "daemon_port": 8765,
    "vad_threshold": 0.7,
    "rms_gate_ratio": 4.0,
    "rms_barge_ratio": 8.0,
    "earcons": True,
}

RAM_CUT_BYTES = 16 * 1024**3


def _total_ram() -> int | None:
    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True
            )
            return int(out.stdout.strip())
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (OSError, ValueError, AttributeError):
        return None


def recommended_router_model() -> str:
    """1.5b needs headroom next to whisper+kokoro: 16 GB of RAM is the cut."""
    total = _total_ram()
    if total is None:
        return DEFAULTS["router_model"]
    return "1.5b" if total >= RAM_CUT_BYTES else "0.5b"


def recommended_whisper_model() -> str:
    """large-v3-turbo alongside kokoro+router wants 16 GB; below that, small."""
    total = _total_ram()
    if total is None:
        return DEFAULTS["whisper_model"]
    return "large-v3-turbo" if total >= RAM_CUT_BYTES else "small"


def load() -> dict:
    try:
        return {**DEFAULTS, **json.loads(CONFIG_PATH.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


def router_model_repo() -> str:
    return ROUTER_MODELS[load()["router_model"]]


def whisper_model_repo() -> str:
    return WHISPER_MODELS[load()["whisper_model"]]


def daemon_url() -> str:
    return f"http://127.0.0.1:{load()['daemon_port']}"


def cli() -> None:
    """open-voice-config: no args prints the config; `KEY VALUE` sets one key."""
    args = sys.argv[1:]
    config = load()
    if not args:
        print(f"# {CONFIG_PATH}")
        for key, value in config.items():
            print(f"{key} = {json.dumps(value)}")
        return
    if len(args) != 2:
        sys.exit("usage: open-voice-config [KEY VALUE]")
    key, raw = args
    if key not in DEFAULTS:
        sys.exit(f"unknown key {key!r} — known: {', '.join(DEFAULTS)}")
    try:
        value = json.loads(raw)
    except ValueError:
        value = raw  # bare strings arrive unquoted
    if type(value) is not type(DEFAULTS[key]) and not (
        isinstance(value, (int, float)) and isinstance(DEFAULTS[key], (int, float))
    ):
        sys.exit(f"{key} expects {type(DEFAULTS[key]).__name__}, got {value!r}")
    valid = {
        "router_model": ROUTER_MODELS,
        "whisper_model": WHISPER_MODELS,
        "multiplexer": MULTIPLEXERS,
        "tts_engine": ("kokoro", "chatterbox"),
    }
    if key in valid and value not in valid[key]:
        sys.exit(f"{key} must be one of: {', '.join(valid[key])}")
    config[key] = value
    save(config)
    print(f"{key} = {json.dumps(value)} (restart voice mode to apply)")
