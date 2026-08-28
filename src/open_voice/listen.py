"""Hands-free STT loop: mic + VAD -> local whisper -> herdr agent prompt.

Cycle: listen to the mic until speech followed by silence (silero VAD),
transcribe with mlx-whisper, inject into the Claude Code pane via
`herdr agent prompt` and wait for the turn to finish (herdr wait + idle TTS)
before reopening the mic.
"""

import argparse
import json
import queue
import re
import subprocess
import sys
import time

import httpx
import numpy as np
import sounddevice as sd

from open_voice.audio import reset_portaudio

VAD_SAMPLE_RATE = 16_000
VAD_CHUNK = 512  # samples per silero call @16k
SILENCE_SECONDS = 2.5
MIN_SPEECH_SECONDS = 0.6
PREROLL_SECONDS = 1.0  # audio kept before the VAD "start" so leading syllables survive
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
WHISPER_LANGUAGE = "pt"
TTS_DAEMON_URL = "http://127.0.0.1:8765"
# wake word "Jarvis": proper noun whisper transcribes stably in pt speech;
# tolerate one short junk token before it (whisper sometimes prefixes syllables)
WAKE_WORD_RE = re.compile(
    r"^(?:[\s,.!?…\"'-]*\w{1,3}[\s,.!?…-]+)?[\s,.!?…\"'-]*jarvis\b[\s,.!?…:-]*",
    re.IGNORECASE,
)


def log(msg: str) -> None:
    print(f"[open-voice] {msg}", flush=True)


def find_claude_pane() -> str:
    out = subprocess.run(
        ["herdr", "pane", "list"], capture_output=True, text=True, check=True
    ).stdout
    panes = json.loads(out)["result"]["panes"]
    claude = [p for p in panes if p.get("agent") == "claude"]
    if not claude:
        sys.exit("No pane running Claude Code found in herdr.")
    focused = [p for p in claude if p.get("focused")]
    if focused:
        return focused[0]["pane_id"]
    if len(claude) == 1:
        return claude[0]["pane_id"]
    ids = ", ".join(p["pane_id"] for p in claude)
    sys.exit(f"Multiple Claude panes active ({ids}) and none focused — use --pane.")


def record_utterance(vad_model) -> np.ndarray | None:
    """Record until speech + SILENCE_SECONDS of silence. None if nothing was said."""
    from collections import deque

    from silero_vad import VADIterator

    vad = VADIterator(vad_model, sampling_rate=VAD_SAMPLE_RATE)
    audio_q: queue.Queue[np.ndarray] = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_q.put(indata[:, 0].copy())

    chunks: list[np.ndarray] = []
    preroll: deque[np.ndarray] = deque(
        maxlen=int(PREROLL_SECONDS * VAD_SAMPLE_RATE / VAD_CHUNK)
    )
    speaking = False
    silence_start: float | None = None
    buffer = np.empty(0, dtype=np.float32)

    with sd.InputStream(
        samplerate=VAD_SAMPLE_RATE, channels=1, dtype="float32", callback=callback
    ):
        while True:
            buffer = np.concatenate([buffer, audio_q.get()])
            while len(buffer) >= VAD_CHUNK:
                chunk, buffer = buffer[:VAD_CHUNK], buffer[VAD_CHUNK:]
                if speaking:
                    chunks.append(chunk)
                else:
                    preroll.append(chunk)
                event = vad(chunk)
                if event and "start" in event:
                    if not speaking:
                        log("recording...")
                        chunks = [*preroll, chunk]
                        preroll.clear()
                    speaking = True
                    silence_start = None
                elif event and "end" in event and speaking:
                    silence_start = time.monotonic()
                if (
                    speaking
                    and silence_start is not None
                    and time.monotonic() - silence_start >= SILENCE_SECONDS
                ):
                    vad.reset_states()
                    audio = np.concatenate(chunks)
                    if len(audio) < MIN_SPEECH_SECONDS * VAD_SAMPLE_RATE:
                        return None
                    return audio


def transcribe(audio: np.ndarray) -> str:
    import mlx_whisper

    result = mlx_whisper.transcribe(
        audio, path_or_hf_repo=WHISPER_MODEL, language=WHISPER_LANGUAGE
    )
    return result["text"].strip()


def composer_draft(pane_id: str) -> str:
    """Text currently typed in the Claude Code composer ("" if empty or unreadable).

    The detection snapshot renders the composer as a `❯` line between two
    horizontal-rule lines; anything after the `❯` (including wrapped lines
    up to the bottom rule) is user draft.
    """
    result = subprocess.run(
        ["herdr", "pane", "read", pane_id, "--source", "detection", "--lines", "20"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    lines = result.stdout.splitlines()
    starts = [i for i, line in enumerate(lines) if line.lstrip().startswith("❯")]
    if not starts:
        return ""
    start = starts[-1]
    draft = [lines[start].lstrip().removeprefix("❯")]
    for line in lines[start + 1 :]:
        if line.strip().startswith("─"):
            break
        draft.append(line)
    return "\n".join(draft).strip()


def append_to_composer(pane_id: str, text: str) -> None:
    subprocess.run(
        ["herdr", "pane", "send-text", pane_id, f" {text}"],
        capture_output=True,
        text=True,
    )


def handle_command(pane_id: str, text: str) -> bool:
    """Local voice commands, resolved without touching the Claude session."""
    low = text.lower()
    if re.search(r"\b(envi\w+|manda\w*)\b.*\bmensagem\b", low):
        subprocess.run(
            ["herdr", "pane", "send-keys", pane_id, "enter"], capture_output=True
        )
        log("command: send message")
        return True
    if re.search(r"\b(pare?|parar)\b.*\bfalar\b|\bsil[êe]ncio\b", low):
        try:
            httpx.post(f"{TTS_DAEMON_URL}/stop", timeout=2)
        except httpx.HTTPError:
            pass
        log("command: stop speaking")
        return True
    if re.search(r"\b(pare?|parar|deslig\w+)\b.*\b(ditado|microfone|escuta)\b", low):
        log("command: stop dictation — exiting")
        try:
            httpx.post(f"{TTS_DAEMON_URL}/stop", timeout=2)
        except httpx.HTTPError:
            pass
        from open_voice.flag import disable

        disable()
        raise SystemExit(0)
    return False


def send_to_claude(pane_id: str, text: str) -> bool:
    result = subprocess.run(
        ["herdr", "agent", "prompt", pane_id, text, "--wait", "--timeout", "600000"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        log(f"herdr rejected the prompt for {pane_id}: {err[:300]}")
        return False
    return True


def wait_tts_idle() -> None:
    with httpx.Client(timeout=2) as client:
        while True:
            try:
                if not client.get(f"{TTS_DAEMON_URL}/busy").json()["busy"]:
                    return
            except httpx.HTTPError:
                return  # daemon down: nothing to wait for
            time.sleep(0.3)


def main() -> None:
    parser = argparse.ArgumentParser(description="open-voice hands-free listener")
    parser.add_argument("--pane", help="target pane (e.g. w1:pD); default: autodetect")
    args = parser.parse_args()

    from silero_vad import load_silero_vad

    log("loading VAD and whisper...")
    vad_model = load_silero_vad()
    transcribe(np.zeros(VAD_SAMPLE_RATE, dtype=np.float32))  # whisper warm-up

    pane_id = args.pane or find_claude_pane()

    import atexit
    import os
    from pathlib import Path

    state = Path.home() / ".claude" / "open-voice-listener.json"
    state.write_text(json.dumps({"pid": os.getpid(), "pane": pane_id}))
    atexit.register(lambda: state.unlink(missing_ok=True))

    import threading

    from open_voice.transcript_follower import follow

    threading.Thread(target=follow, args=(pane_id,), daemon=True).start()

    log(f"ready — target: {pane_id}. Speak; {SILENCE_SECONDS}s of silence sends.")

    try:
        while True:
            try:
                audio = record_utterance(vad_model)
            except sd.PortAudioError:
                # input device changed (headset connected/disconnected)
                log("audio unavailable — reinitializing PortAudio...")
                reset_portaudio()
                time.sleep(2)
                continue
            if audio is None:
                continue
            text = transcribe(audio)
            if not text:
                continue
            stripped = WAKE_WORD_RE.sub("", text, count=1).strip()
            if stripped == text.strip():
                log(f"no wake word — ignored: {text[:60]!r}")
                continue
            if not stripped:
                continue
            text = stripped
            log(f"-> {text}")
            if handle_command(pane_id, text):
                continue
            draft = composer_draft(pane_id)
            if draft:
                # user is mid-typing: append the transcription without sending
                append_to_composer(pane_id, text)
                log(f"draft in composer — appended, not sent (draft: {draft[:60]!r})")
                continue
            if not send_to_claude(pane_id, text):
                # pane may have changed (new session, closed pane); re-resolve and retry
                pane_id = args.pane or find_claude_pane()
                send_to_claude(pane_id, text)
            wait_tts_idle()
    except KeyboardInterrupt:
        print()
        raise SystemExit(0)


if __name__ == "__main__":
    main()
