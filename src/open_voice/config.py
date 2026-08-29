"""User configuration: ~/.config/open-voice/config.json, written by setup."""

import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "open-voice" / "config.json"

ROUTER_MODELS = {
    "0.5b": "mlx-community/Qwen2.5-0.5B-Instruct-4bit",
    "1.5b": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
}
WHISPER_MODELS = {
    "small": "mlx-community/whisper-small-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}
MULTIPLEXERS = ("herdr", "tmux", "zellij")

DEFAULTS = {
    "router_model": "1.5b",
    "whisper_model": "large-v3-turbo",
    "multiplexer": "herdr",
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
    except (OSError, ValueError):
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
