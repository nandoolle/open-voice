#!/bin/sh
# SessionStart hook (runs OUTSIDE the Bash sandbox): on Linux, detect the
# sandbox prerequisites that make /open-voice:on die before Claude can even
# read the command markdown, and surface the fix as session context.
# Silent everywhere else — context is only emitted when something is wrong.
set -eu

[ "$(uname -s)" = "Linux" ] || exit 0

missing=""
command -v socat >/dev/null 2>&1 || missing="$missing socat"
command -v bwrap >/dev/null 2>&1 || missing="$missing bubblewrap"

userns_restricted=0
if [ "$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null)" = "1" ]; then
    userns_restricted=1
fi

[ -z "$missing" ] && [ "$userns_restricted" = "0" ] && exit 0

echo "[open-voice] Claude Code's Bash sandbox is not functional on this Linux machine,"
echo "so /open-voice:on (and any Bash slash command) will fail with a sandbox error."
echo "If the user asks about open-voice or hits a sandbox error, instruct them to run:"
[ -n "$missing" ] && echo "  sudo apt install -y$missing"
if [ "$userns_restricted" = "1" ]; then
    echo "  echo 'kernel.apparmor_restrict_unprivileged_userns = 0' | sudo tee /etc/sysctl.d/99-userns.conf && sudo sysctl --system"
    echo "  (relaxes an Ubuntu kernel hardening; alternative: /sandbox -> Regular permissions)"
fi
echo "then restart Claude Code."
exit 0
