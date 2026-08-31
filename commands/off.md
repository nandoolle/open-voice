---
description: Turn open-voice off (flag, speech and all processes)
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-voice-off.sh")
---

Result: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-voice-off.sh"`

Confirm to the user in one line that voice mode is off. If the result is a sandbox
initialization error instead, tell the user to run `open-voice-off` in a regular
terminal (and see /open-voice:on for the sandbox prerequisites on Linux).
