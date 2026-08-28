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

STATE="$HOME/.claude/open-voice-listener.json"
if pgrep -f open-voice-listen >/dev/null 2>&1; then
  ACTIVE_PANE=$(python3 -c "import json;print(json.load(open('$STATE'))['pane'])" 2>/dev/null || echo "?")
  if [ -n "${HERDR_PANE_ID:-}" ] && [ "$ACTIVE_PANE" != "$HERDR_PANE_ID" ]; then
    echo "⚠️  voice já está ativo na sessão do pane $ACTIVE_PANE — só uma sessão por vez."
    echo "   Para trocar para este pane ($HERDR_PANE_ID): rode /voice-off e depois /voice-on."
    exit 0
  fi
  echo "listener já rodando (alvo: $ACTIVE_PANE)"
else
  # sem pane/TTY: o mic vem do CoreAudio e a permissão é do app terminal
  nohup uv run --project "$REPO_DIR" open-voice-listen ${HERDR_PANE_ID:+--pane "$HERDR_PANE_ID"} \
    >"$HOME/.claude/open-voice-listen.log" 2>&1 &
  echo "listener em background (alvo: ${HERDR_PANE_ID:-autodetect}; log: ~/.claude/open-voice-listen.log)"
fi
echo "modo voz: ON"
