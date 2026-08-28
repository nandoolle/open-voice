#!/bin/bash
# Turn voice mode off: remove the flag, stop speech and kill listener + TTS daemon.
set -euo pipefail

rm -f "$HOME/.claude/voice-enabled"
curl -sf -X POST http://127.0.0.1:8765/stop >/dev/null 2>&1 || true
pkill -f open-voice-listen 2>/dev/null && echo "listener stopped" || true
pkill -f open-voice-tts-daemon 2>/dev/null && echo "TTS daemon stopped" || true
echo "voice mode: OFF"
