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
    # not open-voice deps: Claude Code's own Bash sandbox needs these on Linux,
    # and its absence surfaces as an error inside our slash commands
    command -v socat >/dev/null 2>&1 || NEEDED="$NEEDED socat"
    command -v bwrap >/dev/null 2>&1 || NEEDED="$NEEDED bubblewrap"
    if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
        NEEDED="$NEEDED libportaudio2"
    fi
    if [ -n "$NEEDED" ]; then
        if command -v apt-get >/dev/null 2>&1; then
            SUDO=""
            [ "$(id -u)" -ne 0 ] && SUDO="sudo"
            echo "==> installing system packages:$NEEDED"
            # shellcheck disable=SC2086
            if ! $SUDO apt-get update -qq || ! $SUDO apt-get install -y -qq $NEEDED; then
                # sudo cannot run inside Claude Code's Bash sandbox
                # (no_new_privileges), and may be unavailable elsewhere too
                echo "ERROR: could not install system packages automatically." >&2
                echo "Run this in a regular terminal, then retry:" >&2
                echo "  sudo apt-get install -y$NEEDED" >&2
                exit 1
            fi
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
# Linux: PyPI's torch is the CUDA build (~3GB of nvidia wheels); use the CPU
# index unless the user opts into CUDA with OPEN_VOICE_CUDA=1
TORCH_ARGS=""
if [ "$(uname -s)" = "Linux" ] && [ "${OPEN_VOICE_CUDA:-0}" != "1" ]; then
    TORCH_ARGS="--index https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match"
fi
# pytorch's CDN intermittently drops TLS handshakes under uv; each attempt
# makes progress through uv's cache, so a short retry loop converges
n=1
until
    # shellcheck disable=SC2086
    uv tool install --force --with "$SPACY_MODEL" $TORCH_ARGS "$PACKAGE"
do
    [ "$n" -ge 3 ] && { echo "ERROR: install failed after $n attempts." >&2; exit 1; }
    n=$((n + 1))
    echo "==> transient download failure, retrying ($n/3)..."
    sleep 2
done

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
