#!/bin/sh
# open-voice bootstrap: ensures uv, installs the package as a uv tool and
# runs open-voice-setup. Any arguments are forwarded to open-voice-setup
# (e.g. --router-model 0.5b --multiplexer tmux --skip-models).
#
#   curl -fsSL https://raw.githubusercontent.com/nandoolle/open-voice/main/scripts/install.sh | sh
set -eu

# published package once on PyPI; the git URL is the pre-release source
PACKAGE="${OPEN_VOICE_PACKAGE:-git+https://github.com/nandoolle/open-voice}"

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
uv tool install --force "$PACKAGE"

echo "==> running open-voice-setup"
export PATH="$HOME/.local/bin:$PATH"
# under `curl | sh` stdin is the pipe; reattach the terminal so the setup
# questions (router model, multiplexer) stay interactive
if [ ! -t 0 ] && [ -r /dev/tty ]; then
    open-voice-setup "$@" </dev/tty
else
    open-voice-setup "$@"
fi
