#!/bin/sh
# Plugin hook shim: forwards to the named open-voice entry point when the
# runtime is installed, and no-ops silently when it is not (the plugin can be
# installed before /voice-on bootstraps the uv package).
set -eu

name="$1"
PATH="$HOME/.local/bin:$PATH"
if command -v "$name" >/dev/null 2>&1; then
    exec "$name"
fi
exit 0
