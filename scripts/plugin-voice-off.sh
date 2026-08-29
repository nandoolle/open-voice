#!/bin/sh
set -eu
export PATH="$HOME/.local/bin:$PATH"
if command -v open-voice-off >/dev/null 2>&1; then
    exec open-voice-off
fi
echo "open-voice runtime not installed — nothing to turn off. Run /open-voice:on to install."
