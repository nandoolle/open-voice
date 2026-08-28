#!/bin/bash
# Liga o modo voz: flag + daemon TTS + listener num pane do herdr.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
touch "$HOME/.claude/voice-enabled"

if ! curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then
  nohup uv run --project "$REPO_DIR" open-voice-tts-daemon \
    >"$HOME/.claude/open-voice-tts.log" 2>&1 &
  echo "daemon TTS iniciando (log: ~/.claude/open-voice-tts.log)"
else
  echo "daemon TTS já rodando"
fi

if pgrep -f open-voice-listen >/dev/null 2>&1; then
  echo "listener já rodando"
else
  # sem pane/TTY: o mic vem do CoreAudio e a permissão é do app terminal
  nohup uv run --project "$REPO_DIR" open-voice-listen ${HERDR_PANE_ID:+--pane "$HERDR_PANE_ID"} \
    >"$HOME/.claude/open-voice-listen.log" 2>&1 &
  echo "listener em background (alvo: ${HERDR_PANE_ID:-autodetect}; log: ~/.claude/open-voice-listen.log)"
fi
echo "modo voz: ON"
