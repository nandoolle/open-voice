#!/bin/bash
# Desliga o modo voz: remove a flag e interrompe a fala atual (daemon fica de pé).
set -euo pipefail

rm -f "$HOME/.claude/voice-enabled"
curl -sf -X POST http://127.0.0.1:8765/stop >/dev/null 2>&1 || true
echo "modo voz: OFF"
