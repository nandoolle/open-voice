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
elif [ "${HERDR_ENV:-}" = "1" ] && [ -n "${HERDR_PANE_ID:-}" ]; then
  # o listener detecta o pane alvo sozinho; --no-focus mantém o usuário onde está
  NEW_PANE=$(herdr pane split --pane "$HERDR_PANE_ID" --direction down --ratio 0.2 \
    --cwd "$REPO_DIR" --no-focus | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['pane']['pane_id'])")
  herdr pane run "$NEW_PANE" "uv run open-voice-listen --pane $HERDR_PANE_ID" >/dev/null
  echo "listener iniciado no pane $NEW_PANE (alvo: $HERDR_PANE_ID)"
else
  echo "fora do herdr: rode 'uv run open-voice-listen' num terminal separado"
fi
echo "modo voz: ON"
