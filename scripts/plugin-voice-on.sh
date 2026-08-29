#!/bin/sh
# /open-voice:on backend: bootstraps the runtime on first use, then
# turns voice mode on. Prints machine-readable-ish status lines the command
# prompt relays to the user.
set -eu

export PATH="$HOME/.local/bin:$PATH"

if ! command -v open-voice-on >/dev/null 2>&1; then
    echo "FIRST RUN: open-voice runtime not installed yet."
    echo "Installing now (uv package + model downloads, a few GB) — this can take several minutes..."
    curl -fsSL https://raw.githubusercontent.com/nandoolle/open-voice/main/scripts/install.sh \
        | sh -s -- --plugin --router-model "${OPEN_VOICE_ROUTER:-1.5b}" --multiplexer "${OPEN_VOICE_MUX:-herdr}" --whisper-model "${OPEN_VOICE_WHISPER:-large-v3-turbo}"
    echo "runtime installed."
fi

exec open-voice-on
