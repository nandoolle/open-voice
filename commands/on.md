---
description: Turn open-voice on (first run installs the runtime — may take several minutes)
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-voice-on.sh")
---

Result: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-voice-on.sh"`

If the output above says FIRST RUN, tell the user the runtime was installed now and that the very first listener start still downloads models, so voice may take a few minutes to become responsive. Otherwise confirm in one line that voice mode is on (or what failed above).
