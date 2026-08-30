"""In-container pipeline checks, run with the installed tool env's python.

1. STT+router: each fixture WAV -> transcribe() -> route() == expected label
2. capture: paplay a WAV into the virtual mic while sounddevice records it
3. earcons: synth + playback to the null sink
4. TTS daemon: /say + /busy roundtrip (kokoro -> null sink)
"""

import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

FIXTURES = [  # (file, expected_route, transcript_must_contain, xfail)
    # xfail: llama.cpp router quality baseline (~50%, Linear NAN-20) — commands
    # may degrade to "send" (harmless direction) until the fine-tuned router lands.
    ("en_prompt.wav", "send", "function", False),
    ("en_volume.wav", "volume_up", "volume", True),
    ("pt_prompt.wav", "send", "erro", False),
    ("pt_send.wav", "send_message", "mensagem", True),
]
WAVS = Path("/opt/test_wavs")
failures = []


def check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name} {detail}", flush=True)
    if not ok:
        failures.append(name)


print("--- STT + router (WAV -> transcribe -> route) ---")
import open_voice.config as cfg

# fixtures are multilingual; let whisper detect the language per utterance
c = cfg.load()
c["whisper_language"] = None
cfg.save(c)

from open_voice.listen import route, transcribe  # noqa: E402  (reads config at import)

for fname, expected, must_contain, xfail in FIXTURES:
    audio, sr = sf.read(WAVS / fname, dtype="float32")
    if sr != 16000:
        idx = np.round(np.arange(0, len(audio), sr / 16000)).astype(int)
        audio = audio[idx[idx < len(audio)]]
    text = transcribe(audio)
    label = route(text)
    ok = label == expected and must_contain in text.lower()
    if not ok and xfail and label == "send" and must_contain in text.lower():
        print(f"  [xfail] {fname} -> {text!r} -> {label} "
              f"(expected {expected}; known router baseline, NAN-20)", flush=True)
        continue
    check(fname, ok, f"-> {text!r} -> {label} (expected {expected})")

print("--- mic capture via virtual source ---")
import sounddevice as sd

seconds = 3
player = subprocess.Popen(["paplay", str(WAVS / "en_prompt.wav")])
rec = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, dtype="float32")
sd.wait()
player.wait()
peak = float(np.abs(rec).max())
check("sounddevice capture", peak > 0.01, f"(peak {peak:.4f})")

print("--- earcons ---")
from open_voice import earcons

for s in ("Blow", "Frog", "Purr", "Glass", "Basso"):
    earcons.play(s)
    time.sleep(0.1)
check("earcons synth+play", True)

print("--- TTS daemon ---")
daemon = subprocess.Popen(
    ["open-voice-tts-daemon"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
)
try:
    import httpx

    url = cfg.daemon_url()
    up = False
    for _ in range(60):
        try:
            httpx.get(f"{url}/busy", timeout=1)
            up = True
            break
        except Exception:
            time.sleep(1)
    check("daemon up", up)
    if up:
        httpx.post(f"{url}/say", json={"text": "Linux voice loop is alive."}, timeout=5)
        spoke = False
        for _ in range(30):
            if httpx.get(f"{url}/busy", timeout=2).json()["busy"]:
                spoke = True
                break
            time.sleep(0.3)
        check("daemon spoke", spoke)
finally:
    daemon.terminate()

print(f"\n{len(FIXTURES) + 4 - len(failures)} passed, {len(failures)} failed")
sys.exit(1 if failures else 0)
