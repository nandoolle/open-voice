#!/bin/sh
# e2e: install.sh from scratch (BLOCKING if it fails), then the voice pipeline
# against a virtual PulseAudio mic fed with kokoro-generated WAVs.
set -eu

# harness only: the docker cache volume mounts root-owned
sudo chown -R dev:dev "$HOME/.cache" 2>/dev/null || true

echo "=========== STAGE 1: install.sh (single entry point) ==========="
sh /opt/open-voice/scripts/install.sh \
    --router-model 0.5b --whisper-model small --multiplexer tmux
export PATH="$HOME/.local/bin:$PATH"

echo "=========== STAGE 2: virtual audio (PulseAudio null sink) ==========="
pulseaudio --start --exit-idle-time=-1
pactl load-module module-null-sink sink_name=vmic sink_properties=device.description=vmic
pactl set-default-sink vmic
pactl set-default-source vmic.monitor
pactl info | grep -E 'Default (Sink|Source)'

echo "=========== STAGE 3: pipeline checks ==========="
TOOLENV_PY="$(ls -d "$HOME"/.local/share/uv/tools/open-voice/bin/python)"
"$TOOLENV_PY" /opt/e2e_checks.py

echo "=========== STAGE 4: tmux mux backend ==========="
tmux new-session -d -s ov -x 120 -y 30 'exec sh'
tmux send-keys -t ov 'echo mux-roundtrip-ok' Enter
sleep 1
tmux capture-pane -t ov -p | grep -q 'mux-roundtrip-ok'
echo "tmux send/read roundtrip: ok"
tmux kill-server

echo "=========== ALL STAGES PASSED ==========="
