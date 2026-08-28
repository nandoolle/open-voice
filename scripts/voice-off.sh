#!/bin/bash
# Desliga o modo voz: remove a flag, para a fala e derruba o listener (daemon TTS fica).
set -euo pipefail

rm -f "$HOME/.claude/voice-enabled"
curl -sf -X POST http://127.0.0.1:8765/stop >/dev/null 2>&1 || true
pkill -f open-voice-listen 2>/dev/null && echo "listener parado" || true
echo "modo voz: OFF"
