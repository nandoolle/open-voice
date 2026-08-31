#!/bin/sh
# /open-voice:on backend. The runtime is NOT installed from inside a Claude
# session: the Bash sandbox blocks sudo, filesystem writes and long-lived
# daemons, so first use hands the user the one-liner to run in a terminal.
set -eu

export PATH="$HOME/.local/bin:$PATH"

if ! command -v open-voice-on >/dev/null 2>&1; then
    # the plugin snapshot ships the whole repo: installing script and package
    # from HERE keeps runtime and plugin at the exact same version
    ROOT="$(cd "$(dirname "$0")/.." && pwd)"
    echo "FIRST RUN: the open-voice runtime is not installed yet."
    echo "It cannot be installed from inside a Claude session (sandboxed shell)."
    echo "ACTION REQUIRED — tell the user to run this in a regular terminal:"
    echo "  OPEN_VOICE_PACKAGE=\"$ROOT\" sh \"$ROOT/scripts/install.sh\""
    echo "and then run /open-voice:on again."
    exit 0
fi

if out=$(open-voice-on 2>&1); then
    printf '%s\n' "$out"
else
    printf '%s\n' "$out"
    echo "open-voice-on failed. If the error above mentions a read-only file"
    echo "system or a sandbox, the Claude Code Bash sandbox is blocking it —"
    echo "tell the user to run 'open-voice-on' in a regular terminal instead."
fi
