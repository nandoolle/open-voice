---
description: Turn open-voice on (first run prints the terminal install command)
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-voice-on.sh")
---

Result: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-voice-on.sh"`

Interpret the result above for the user:

- **FIRST RUN / ACTION REQUIRED**: relay the exact install command printed above — it must be run in a regular terminal (outside this session); afterwards rerun /open-voice:on. Mention the install downloads models (a few GB, several minutes).
- **Sandbox failed to initialize (socat/bubblewrap not installed)**: this is a Claude Code sandbox dependency, not open-voice. Tell the user to run `sudo apt install socat bubblewrap` in a terminal and restart Claude Code.
- **`bwrap: setting up uid map: Permission denied`**: Ubuntu 23.10+ AppArmor restriction. Tell the user to run `echo 'kernel.apparmor_restrict_unprivileged_userns = 0' | sudo tee /etc/sysctl.d/99-userns.conf && sudo sysctl --system` (note: relaxes a kernel hardening) or switch the sandbox off via /sandbox → Regular permissions.
- **Read-only file system or another sandbox write/spawn failure**: the sandbox blocks starting the daemons. Tell the user to either run `open-voice-on` in a regular terminal, or switch the sandbox off via /sandbox → Regular permissions.
- **Otherwise**: confirm in one line that voice mode is on (or report exactly what failed).
