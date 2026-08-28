#!/bin/bash
# Turn voice mode on: flag + TTS daemon + listener bound to a herdr pane.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
touch "$HOME/.claude/voice-enabled"

if ! curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then
  nohup uv run --project "$REPO_DIR" open-voice-tts-daemon \
    >"$HOME/.claude/open-voice-tts.log" 2>&1 &
  echo "TTS daemon starting (log: ~/.claude/open-voice-tts.log)"
else
  echo "TTS daemon already running"
fi

STATE="$HOME/.claude/open-voice-listener.json"
if pgrep -f open-voice-listen >/dev/null 2>&1; then
  ACTIVE_PANE=$(python3 -c "import json;print(json.load(open('$STATE'))['pane'])" 2>/dev/null || echo "?")
  if [ -n "${HERDR_PANE_ID:-}" ] && [ "$ACTIVE_PANE" != "$HERDR_PANE_ID" ]; then
    echo "⚠️  voice is already active on pane $ACTIVE_PANE — one session at a time."
    echo "   To switch to this pane ($HERDR_PANE_ID): run /voice-off, then /voice-on."
    exit 0
  fi
  echo "listener already running (target: $ACTIVE_PANE)"
else
  # no pane/TTY needed: the mic comes from CoreAudio and the permission belongs to the terminal app
  nohup uv run --project "$REPO_DIR" open-voice-listen ${HERDR_PANE_ID:+--pane "$HERDR_PANE_ID"} \
    >"$HOME/.claude/open-voice-listen.log" 2>&1 &
  echo "listener in background (target: ${HERDR_PANE_ID:-autodetect}; log: ~/.claude/open-voice-listen.log)"
fi
echo "voice mode: ON"
