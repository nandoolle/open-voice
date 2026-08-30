#!/bin/sh
# open-voice bootstrap: ensures uv, installs the package as a uv tool and
# runs open-voice-setup. Any arguments are forwarded to open-voice-setup
# (e.g. --router-model 0.5b --multiplexer tmux --skip-models).
#
#   curl -fsSL https://raw.githubusercontent.com/nandoolle/open-voice/main/scripts/install.sh | sh
set -eu

# published package once on PyPI; the git URL is the pre-release source
PACKAGE="${OPEN_VOICE_PACKAGE:-git+https://github.com/nandoolle/open-voice}"

# Linux: system libraries and build tools the Python deps need (PortAudio for
# sounddevice, compiler+cmake for llama-cpp-python, git for the source install,
# procps for pgrep/pkill). The multiplexer is NOT installed here — the herdr
# fallback below covers Linux too (linux/x86_64 and linux/aarch64 builds).
if [ "$(uname -s)" = "Linux" ]; then
    NEEDED=""
    command -v git >/dev/null 2>&1 || NEEDED="$NEEDED git"
    command -v cc >/dev/null 2>&1 || NEEDED="$NEEDED build-essential"
    command -v cmake >/dev/null 2>&1 || NEEDED="$NEEDED cmake"
    command -v pgrep >/dev/null 2>&1 || NEEDED="$NEEDED procps"
    if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
        NEEDED="$NEEDED libportaudio2"
    fi
    if [ -n "$NEEDED" ]; then
        if command -v apt-get >/dev/null 2>&1; then
            SUDO=""
            [ "$(id -u)" -ne 0 ] && SUDO="sudo"
            echo "==> installing system packages:$NEEDED"
            $SUDO apt-get update -qq
            # shellcheck disable=SC2086
            $SUDO apt-get install -y -qq $NEEDED
        else
            echo "ERROR: missing system packages:$NEEDED" >&2
            echo "install them with your package manager and rerun this script." >&2
            exit 1
        fi
    fi
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "==> installing uv (https://astral.sh/uv)"
    curl -fsSL https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# at least one supported multiplexer must exist; herdr is the default when
# none is present (setup lets the user pick among the installed ones)
if ! command -v herdr >/dev/null 2>&1 \
    && ! command -v tmux >/dev/null 2>&1 \
    && ! command -v zellij >/dev/null 2>&1; then
    echo "==> no multiplexer found (herdr/tmux/zellij) — installing herdr (default)"
    curl -fsSL https://herdr.dev/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "==> installing open-voice ($PACKAGE)"
# en_core_web_sm baked in: kokoro's G2P (misaki→spacy) otherwise tries to
# download it at runtime, which fails inside a pip-less uv tool env
SPACY_MODEL="en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
uv tool install --force --with "$SPACY_MODEL" "$PACKAGE"

echo "==> running open-voice-setup"
export PATH="$HOME/.local/bin:$PATH"
# under `curl | sh` stdin is the pipe; reattach the terminal so the setup
# questions (router model, multiplexer) stay interactive. `-r /dev/tty` is not
# enough: in a session without a controlling terminal the open itself fails,
# so probe with an actual read redirection
if [ ! -t 0 ] && (: </dev/tty) 2>/dev/null; then
    open-voice-setup "$@" </dev/tty
else
    open-voice-setup "$@"
fi
