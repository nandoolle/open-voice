"""Hands-free STT loop: mic + VAD -> local whisper -> semantic router -> Claude Code.

Cycle: listen to the mic until speech followed by silence (silero VAD),
transcribe with mlx-whisper, route the utterance (local command, prompt for
the agent, or ambient speech to discard) and inject prompts into the Claude
Code pane via `herdr agent prompt`. Earcons mark every transition:

    Blow   mic started capturing        Purr   prompt accepted, cancel window open
    Frog   utterance captured           Glass  message sent / Enter
    Basso  cancelled / dictation off
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
CANCEL_WINDOW_SECONDS = 3.0
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
WHISPER_LANGUAGE = "pt"
TTS_DAEMON_URL = "http://127.0.0.1:8765"


def log(msg: str) -> None:
    print(f"[open-voice] {msg}", flush=True)


def _beep(sound: str) -> None:
    subprocess.Popen(
        ["afplay", f"/System/Library/Sounds/{sound}.aiff"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


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


def _tts_busy(client: httpx.Client) -> bool:
    try:
        return client.get(f"{TTS_DAEMON_URL}/busy").json()["busy"]
    except httpx.HTTPError:
        return False


def record_utterance(
    vad_model, first_speech_timeout: float | None = None
) -> np.ndarray | None:
    """Record until speech + SILENCE_SECONDS of silence.

    None if nothing (or too little) was said — or, when first_speech_timeout is
    given, if no speech started within that many seconds. Audio captured while
    the TTS daemon is speaking is discarded (mic echo of the spoken replies).
    """
    from collections import deque

    from silero_vad import VADIterator

    vad = VADIterator(vad_model, sampling_rate=VAD_SAMPLE_RATE)
    audio_q: queue.Queue[np.ndarray] = queue.Queue()
    tts_client = httpx.Client(timeout=2)
    last_busy_check = 0.0
    deadline = (
        time.monotonic() + first_speech_timeout if first_speech_timeout else None
    )

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
            try:
                data = audio_q.get(timeout=0.2)
            except queue.Empty:
                data = None
            if not speaking and deadline is not None and time.monotonic() > deadline:
                tts_client.close()
                return None
            if data is None:
                continue
            buffer = np.concatenate([buffer, data])
            now = time.monotonic()
            if now - last_busy_check >= 0.5:
                last_busy_check = now
                if _tts_busy(tts_client):
                    if speaking:
                        log("TTS speaking — discarding echo capture")
                    vad.reset_states()
                    chunks = []
                    preroll.clear()
                    speaking, silence_start = False, None
                    buffer = np.empty(0, dtype=np.float32)
                    while not audio_q.empty():
                        audio_q.get_nowait()
                    continue
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
                        _beep("Blow")
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
                    tts_client.close()
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
    text = "\n".join(draft).strip()
    # Claude Code renders placeholder hints inside the composer; they are not
    # user drafts (e.g. "Press up to edit queued messages", 'Try "fix lint..."')
    if re.match(r"^(Press up to edit|Try \"|\? for shortcuts)", text):
        return ""
    return text


def append_to_composer(pane_id: str, text: str) -> None:
    subprocess.run(
        ["herdr", "pane", "send-text", pane_id, f" {text}"],
        capture_output=True,
        text=True,
    )


def _stop_tts() -> None:
    try:
        httpx.post(f"{TTS_DAEMON_URL}/stop", timeout=2)
    except httpx.HTTPError:
        pass


def _act_send_message(pane_id: str) -> None:
    subprocess.run(
        ["herdr", "pane", "send-keys", pane_id, "enter"], capture_output=True
    )
    _beep("Glass")


def _act_pause_execution(pane_id: str) -> None:
    _stop_tts()
    subprocess.run(
        ["herdr", "agent", "send-keys", pane_id, "esc"], capture_output=True
    )


def _act_stop_media(pane_id: str) -> None:
    # best effort: pause the media apps that expose an AppleScript pause
    for app in ("Spotify", "Music"):
        subprocess.run(
            ["osascript", "-e", f'tell application "{app}" to pause'],
            capture_output=True,
        )


def _act_stop_speaking(pane_id: str) -> None:
    _stop_tts()


def _act_stop_dictation(pane_id: str) -> None:
    _stop_tts()
    from open_voice.flag import disable

    disable()
    _beep("Basso")
    raise SystemExit(0)


INTENT_ACTIONS = {
    "send_message": _act_send_message,
    "pause_execution": _act_pause_execution,
    "stop_media": _act_stop_media,
    "stop_speaking": _act_stop_speaking,
    "stop_dictation": _act_stop_dictation,
}

# zero-latency fast path for common phrasings; the LLM router covers the rest
FAST_PATTERNS = [
    (re.compile(r"\b(envi\w+|manda\w*)\b.*\bmensagem\b"), "send_message"),
    (re.compile(r"\b(pause?|pausar|pare?|parar)\b.*\bexecu[çc][ãa]o\b"), "pause_execution"),
    (re.compile(r"\b(pare?|parar|pause?)\b.*\bm[íi]dias?\b|\bm[úu]sica\b"), "stop_media"),
    (re.compile(r"\b(pare?|parar)\b.*\bfalar\b|\bsil[êe]ncio\b"), "stop_speaking"),
    (re.compile(r"\b(pare?|parar|deslig\w+)\b.*\b(ditado|microfone|escuta)\b"), "stop_dictation"),
    (re.compile(r"\bn[ãa]o\s+(mand\w+|envi\w+)\b|\bcancela\w*\b|\bdon'?t\s+send\b"), "cancel"),
]

ROUTE_PROMPT = """Classify one voice utterance (any language) with exactly one label:
send = a message for the coding agent (questions, requests, feedback, anything conversational)
cancel = explicitly asks NOT to send the pending message
send_message = explicitly asks to submit/send the drafted message
pause_execution = explicitly asks to pause/interrupt the agent's execution
stop_media = explicitly asks to stop music/media
stop_speaking = explicitly asks the voice to stop talking
stop_dictation = explicitly asks to turn off the microphone/dictation

Examples:
"oi tudo bem?" -> send
"muito bem." -> send
"roda os testes de novo" -> send
"não mande isso" -> cancel
"pode enviar a mensagem" -> send_message
"pausa a execução" -> pause_execution
"para a música" -> stop_media
"fica quieto" -> stop_speaking
"desliga o microfone" -> stop_dictation
"manda ver" -> send

Commands require explicit wording; anything vague or conversational is send.
"{text}" ->"""

ROUTE_LABELS = {"send", "cancel", *INTENT_ACTIONS}
COMMAND_MAX_WORDS = 8
# small local model: ~100ms per classification, no network, no credentials
ROUTER_MODEL = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
_router_model = None


def _router():
    global _router_model
    if _router_model is None:
        from mlx_lm import load

        _router_model = load(ROUTER_MODEL)
    return _router_model


def route(text: str) -> str:
    """Everything is a message unless an explicit command matches. Commands and
    cancel must be explicit (fast regex, or haiku for short utterances only);
    long utterances are dictation and skip the LLM entirely."""
    low = text.lower()
    fast = next((i for rx, i in FAST_PATTERNS if rx.search(low)), None)
    if fast:
        return fast
    if len(text.split()) > COMMAND_MAX_WORDS:
        return "send"
    try:
        from mlx_lm import generate

        model, tokenizer = _router()
        prompt = tokenizer.apply_chat_template(
            [{"role": "user", "content": ROUTE_PROMPT.format(text=text)}],
            add_generation_prompt=True,
        )
        label = generate(model, tokenizer, prompt=prompt, max_tokens=8).strip().lower()
    except Exception:
        return "send"
    return label if label in ROUTE_LABELS else "send"


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


def collect_prompt(vad_model, pane_id: str, text: str) -> str | None:
    """Cancel/continuation window: after a prompt is accepted, keep the mic open
    for CANCEL_WINDOW_SECONDS — a cancel utterance drops it, another prompt
    utterance extends it, silence confirms it."""
    while True:
        _beep("Purr")
        extra = record_utterance(vad_model, first_speech_timeout=CANCEL_WINDOW_SECONDS)
        if extra is None:
            return text
        more = transcribe(extra)
        if not more:
            return text
        intent = route(more)
        if intent == "cancel":
            log("cancelled by user")
            _beep("Basso")
            return None
        if intent == "send":
            log(f"+> {more}")
            text = f"{text} {more}"
            continue
        if intent in INTENT_ACTIONS:
            log(f"command: {intent}")
            INTENT_ACTIONS[intent](pane_id)
            continue
        return text


def _watch_pane(pane_id: str) -> None:
    """Shut everything down when the target pane closes — closing the session
    in the multiplexer is the intentional 'voice off' gesture."""
    import os

    failures = 0
    while True:
        time.sleep(10)
        result = subprocess.run(
            ["herdr", "pane", "get", pane_id], capture_output=True, text=True
        )
        failures = failures + 1 if result.returncode != 0 else 0
        if failures >= 2:
            log("target pane gone — shutting voice mode down")
            from open_voice.flag import disable

            disable()
            subprocess.run(["pkill", "-f", "open-voice-tts-daemon"], capture_output=True)
            os._exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="open-voice hands-free listener")
    parser.add_argument("--pane", help="target pane (e.g. w1:pD); default: autodetect")
    args = parser.parse_args()

    from silero_vad import load_silero_vad

    log("loading VAD, whisper and router...")
    vad_model = load_silero_vad()
    transcribe(np.zeros(VAD_SAMPLE_RATE, dtype=np.float32))  # whisper warm-up
    _router()  # router model warm-up

    pane_id = args.pane or find_claude_pane()

    import atexit
    import os
    import threading
    from pathlib import Path

    state = Path.home() / ".claude" / "open-voice-listener.json"
    state.write_text(json.dumps({"pid": os.getpid(), "pane": pane_id}))
    atexit.register(lambda: state.unlink(missing_ok=True))

    from open_voice.transcript_follower import follow

    threading.Thread(target=follow, args=(pane_id,), daemon=True).start()
    threading.Thread(target=_watch_pane, args=(pane_id,), daemon=True).start()

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
            _beep("Frog")
            text = transcribe(audio)
            if not text:
                continue
            intent = route(text)
            if intent == "cancel":
                _beep("Basso")
                continue  # nothing pending to cancel
            if intent in INTENT_ACTIONS:
                log(f"command: {intent}")
                INTENT_ACTIONS[intent](pane_id)
                continue
            log(f"-> {text}")
            final = collect_prompt(vad_model, pane_id, text)
            if final is None:
                continue
            draft = composer_draft(pane_id)
            if draft:
                # user is mid-typing: append the transcription without sending
                append_to_composer(pane_id, final)
                log(f"draft in composer — appended, not sent (draft: {draft[:60]!r})")
                continue
            _beep("Glass")
            if not send_to_claude(pane_id, final):
                # pane may have changed (new session, closed pane); re-resolve and retry
                pane_id = args.pane or find_claude_pane()
                send_to_claude(pane_id, final)
            wait_tts_idle()
    except KeyboardInterrupt:
        print()
        raise SystemExit(0)


if __name__ == "__main__":
    main()
