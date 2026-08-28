#!/bin/bash
# UserPromptSubmit hook: when voice mode is on, remind Claude to mark
# speak-aloud mid-turn text with the 🔊 prefix.
[ -f "$HOME/.claude/voice-enabled" ] || exit 0
cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"Voice mode is ON. Prefix mid-turn text (between tool calls) worth speaking in real time with 🔊 — e.g. a warning before a long operation or an important finding mid-work. The transcript follower speaks 🔊 blocks immediately; the final reply of the turn is spoken automatically and must NOT carry the marker. Use sparingly: only what the user needs to hear before the turn ends."}}
EOF
