#!/bin/bash
# Liga o modo voz: cria a flag e sobe o daemon TTS se não estiver rodando.
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
echo "modo voz: ON"
