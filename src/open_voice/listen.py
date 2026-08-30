"""Hands-free STT loop: mic + VAD -> local whisper -> semantic router -> Claude Code.

Cycle: listen to the mic until speech followed by silence (silero VAD),
transcribe with mlx-whisper, route the utterance (local command, prompt for
the agent, or ambient speech to discard) and inject prompts into the Claude
Code pane via the configured multiplexer backend. Earcons mark every transition:

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
from open_voice.config import daemon_url, load, router_model_repo, whisper_model_repo
from open_voice.mux import get_mux
from open_voice.tools import Ctx, load_tools

MUX = get_mux()
_CFG = load()

VAD_SAMPLE_RATE = 16_000
VAD_CHUNK = 512  # samples per silero call @16k
SILENCE_SECONDS = 2.5
MIN_SPEECH_SECONDS = 0.6
PREROLL_SECONDS = 1.0  # audio kept before the VAD "start" so leading syllables survive
CANCEL_WINDOW_SECONDS = 3.0
STALL_SECONDS = 5.0  # no audio callbacks for this long = input stream is dead
# tunables live in ~/.config/open-voice/config.json (open-voice-config to change)
VAD_THRESHOLD = _CFG["vad_threshold"]  # silero speech probability; higher rejects faint audio
RMS_GATE_RATIO = _CFG["rms_gate_ratio"]  # onset must be this many times louder than the noise floor
RMS_BARGE_RATIO = _CFG["rms_barge_ratio"]  # stricter gate while TTS speaks; passing it barges in
WHISPER_MODEL = whisper_model_repo()
WHISPER_LANGUAGE = _CFG["whisper_language"]
EARCONS = _CFG["earcons"]
TTS_DAEMON_URL = daemon_url()


def log(msg: str) -> None:
    print(f"[open-voice] {msg}", flush=True)


def _beep(sound: str) -> None:
    if not EARCONS:
        return
    from open_voice import earcons

    earcons.play(sound)


def find_claude_pane() -> str:
    pane = MUX.find_claude_pane()
    if pane is None:
        sys.exit(f"No pane running Claude Code found in {MUX.name} — use --pane.")
    if pane == "AMBIGUOUS":
        sys.exit("Multiple Claude panes active and none focused — use --pane.")
    return pane


def _output_is_builtin_speakers() -> bool:
    """True when the default output is the Mac's own speakers — TTS then reaches
    the mic as loud as direct voice, so barge-in cannot be trusted."""
    try:
        name = sd.query_devices(sd.default.device[1])["name"].lower()
    except Exception:
        return False
    return "speaker" in name or "alto-falante" in name


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

    vad = VADIterator(vad_model, sampling_rate=VAD_SAMPLE_RATE, threshold=VAD_THRESHOLD)
    noise_rms = 0.003  # EMA of the ambient noise floor, seeded conservatively
    audio_q: queue.Queue[np.ndarray] = queue.Queue()
    tts_client = httpx.Client(timeout=2)
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

    last_data = time.monotonic()
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
                # watchdog: on macOS, losing the input device (e.g. AirPods
                # disconnecting) kills the callbacks without raising — the
                # stream goes silently orphaned
                if time.monotonic() - last_data > STALL_SECONDS:
                    tts_client.close()
                    raise sd.PortAudioError("input stream stalled — device lost?")
                continue
            last_data = time.monotonic()
            buffer = np.concatenate([buffer, data])
            while len(buffer) >= VAD_CHUNK:
                chunk, buffer = buffer[:VAD_CHUNK], buffer[VAD_CHUNK:]
                if speaking:
                    chunks.append(chunk)
                else:
                    preroll.append(chunk)
                    chunk_rms = float(np.sqrt(np.mean(chunk**2)))
                    noise_rms = 0.98 * noise_rms + 0.02 * chunk_rms
                event = vad(chunk)
                if event and "start" in event:
                    if not speaking:
                        # energy gate: direct voice is far louder at the mic than
                        # TTS echo leaking from the headphones; while the TTS is
                        # speaking the bar is higher and passing it interrupts it
                        # (barge-in)
                        onset_rms = float(np.sqrt(np.mean(chunk**2)))
                        busy = _tts_busy(tts_client)
                        if busy and _output_is_builtin_speakers():
                            # speaker echo reaches the mic as loud as direct
                            # voice: no barge-in, discard until TTS finishes
                            vad.reset_states()
                            continue
                        ratio = RMS_BARGE_RATIO if busy else RMS_GATE_RATIO
                        if onset_rms < noise_rms * ratio:
                            log(
                                f"start rejected by energy gate "
                                f"(rms {onset_rms:.4f} < {ratio}x floor {noise_rms:.4f})"
                            )
                            vad.reset_states()
                            continue
                        if busy:
                            _stop_tts()
                            log("barge-in: TTS interrupted")
                        log(f"recording... (rms {onset_rms:.4f}, floor {noise_rms:.4f})")
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


def trim_repetition(text: str) -> str:
    """Collapse whisper hallucination loops (a phrase repeated 3+ times in a row)."""
    return re.sub(r"(?i)(\b.{3,80}?)(?:[\s,.!?…-]+\1){2,}", r"\1", text)


_whisper = None


def transcribe(audio: np.ndarray) -> str:
    if sys.platform == "darwin":
        import mlx_whisper

        result = mlx_whisper.transcribe(
            audio, path_or_hf_repo=WHISPER_MODEL, language=WHISPER_LANGUAGE
        )
        text = result["text"]
    else:
        global _whisper
        if _whisper is None:
            from faster_whisper import WhisperModel

            _whisper = WhisperModel(WHISPER_MODEL, device="auto", compute_type="int8")
        segments, _ = _whisper.transcribe(audio, language=WHISPER_LANGUAGE)
        text = "".join(segment.text for segment in segments)
    return trim_repetition(text.strip())


def composer_draft(pane_id: str) -> str:
    """Text currently typed in the Claude Code composer ("" if empty or unreadable).

    The detection snapshot renders the composer as a `❯` line between two
    horizontal-rule lines; anything after the `❯` (including wrapped lines
    up to the bottom rule) is user draft.
    """
    screen = MUX.read_screen(pane_id, 20)
    if not screen:
        return ""
    lines = screen.splitlines()
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
    MUX.send_text(pane_id, f" {text}")


def _stop_tts() -> None:
    try:
        httpx.post(f"{TTS_DAEMON_URL}/stop", timeout=2)
    except httpx.HTTPError:
        pass


ROUTE_HEADER = """Classify one voice utterance (any language) with exactly one label:
send = a message for the coding agent (questions, requests, feedback, anything conversational)
cancel = explicitly asks NOT to send the pending message
"""

HEAD_EXAMPLES = [
    ("oi tudo bem?", "send"),
    ("muito bem.", "send"),
    ("roda os testes de novo", "send"),
    ("não mande isso", "cancel"),
]
TAIL_EXAMPLES = [
    ("manda ver", "send"),
    ("muito bem, continua", "send"),
]

ROUTE_RULES = """
Commands require explicit wording; anything vague or conversational is send.
Interrupting the reading/speech (leitura, fala, ditado) is stop_speaking; interrupting the execution/work is pause_execution.
"""


def _build_route_prompt(tools: dict) -> str:
    """Assemble the classifier prompt from the tool registry: each tool
    contributes its label line and its few-shot examples."""
    labels = "".join(f"{t.name} = {t.description}\n" for t in tools.values())
    examples = [*HEAD_EXAMPLES]
    for tool in tools.values():
        examples.extend((phrase, tool.name) for phrase in tool.examples)
    examples.extend(TAIL_EXAMPLES)
    shots = "".join(f'"{phrase}" -> {label}\n' for phrase, label in examples)
    return f"{ROUTE_HEADER}{labels}\nExamples:\n{shots}{ROUTE_RULES}"


TOOLS = load_tools()
ROUTE_PROMPT = _build_route_prompt(TOOLS)
ROUTE_LABELS = {"send", "cancel", *TOOLS}
COMMAND_MAX_WORDS = 8
# small local model: ~100ms per classification, no network, no credentials;
# size (0.5B/1.5B) chosen at setup time via ~/.config/open-voice/config.json
ROUTER_MODEL = router_model_repo()
_router_model = None


def _router():
    global _router_model
    if _router_model is None:
        if sys.platform == "darwin":
            from mlx_lm import load

            _router_model = load(ROUTER_MODEL)
        else:
            from open_voice import router_llamacpp

            _router_model = router_llamacpp._load(*ROUTER_MODEL)
    return _router_model


def route(text: str) -> str:
    """Everything is a message unless the router labels it an explicit command.
    Long utterances are dictation and skip the LLM entirely; short ones are
    classified by the local Qwen (~0.3s), language-agnostic."""
    if len(text.split()) > COMMAND_MAX_WORDS:
        return "send"
    try:
        return _classify(text)
    except Exception:
        return "send"


def _classify(text: str) -> str:
    """Pick the label whose full sequence (label + newline terminator) has the
    highest joint log-probability, instead of free generation: deterministic,
    always a valid label, no parsing. The terminator matters — without it,
    P("send") absorbs P("send_message") through the shared prefix. Remaining
    misclassifications degrade to "send", which loses nothing."""
    if sys.platform != "darwin":
        from open_voice import router_llamacpp

        _router()  # ensure the model is downloaded/loaded
        return router_llamacpp.classify(*ROUTER_MODEL, ROUTE_PROMPT, ROUTE_LABELS, text)

    import mlx.core as mx
    from mlx_lm.models.cache import make_prompt_cache, trim_prompt_cache

    model, tokenizer = _router()
    prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": f'{ROUTE_PROMPT}"{text}" ->'}],
        add_generation_prompt=True,
    )
    cache = make_prompt_cache(model)
    prompt_logits = model(mx.array([prompt]), cache=cache)[:, -1, :]
    best_label, best_score = "send", -float("inf")
    for label in ROUTE_LABELS:
        tokens = tokenizer.encode(label + "\n", add_special_tokens=False)
        logprob, logits = 0.0, prompt_logits
        for token in tokens:
            logprob += float((logits[0] - mx.logsumexp(logits[0]))[token])
            logits = model(mx.array([[token]]), cache=cache)[:, -1, :]
        trim_prompt_cache(cache, len(tokens))
        if logprob > best_score:
            best_label, best_score = label, logprob
    return best_label


def send_to_claude(pane_id: str, text: str) -> bool:
    ok, err = MUX.prompt(pane_id, text)
    if not ok:
        log(f"{MUX.name} rejected the prompt for {pane_id}: {err[:300]}")
    return ok


def run_tool(intent: str, ctx: Ctx, text: str) -> None:
    log(f"command: {intent}")
    try:
        TOOLS[intent].run(ctx, text)
    except SystemExit:
        raise
    except Exception as exc:
        log(f"tool {intent} failed: {exc}")
        _beep("Basso")


def collect_prompt(vad_model, ctx: Ctx, pane_id: str, text: str) -> str | None:
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
        if intent in TOOLS:
            run_tool(intent, ctx, more)
            continue
        return text


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _restart_tts_daemon() -> None:
    """Relaunch the TTS daemon detached, logging to the usual file."""
    from pathlib import Path

    daemon = Path(sys.executable).parent / "open-voice-tts-daemon"
    logfile = open(Path.home() / ".claude" / "open-voice-tts.log", "a")
    subprocess.Popen(
        [str(daemon)], stdout=logfile, stderr=logfile, start_new_session=True
    )


def _watch_pane(pane_id: str) -> None:
    """Shut everything down when the target pane closes — closing the session
    in the multiplexer is the intentional 'voice off' gesture. Also restarts
    the TTS daemon if it dies (device changes and memory pressure kill it)."""
    import os

    failures = 0
    daemon_failures = 0
    while True:
        time.sleep(10)
        try:
            httpx.get(f"{TTS_DAEMON_URL}/health", timeout=2)
            daemon_failures = 0
        except httpx.HTTPError:
            daemon_failures += 1
            if daemon_failures >= 2 and not subprocess.run(
                ["pgrep", "-f", "open-voice-tts-daemon"], capture_output=True
            ).returncode == 0:
                log("TTS daemon down — restarting it")
                _restart_tts_daemon()
                daemon_failures = 0
        # the check fails both when the pane closed and when the claude process
        # exited (e.g. Ctrl+C) while the shell stayed — either way, voice off
        if MUX.agent_alive(pane_id):
            failures = 0
        else:
            failures += 1
            # detection windows fail transiently; require a sustained outage
            # (~40s) before concluding the session is really gone
            log(f"agent check failed ({failures}/4)")
        if failures >= 4:
            log("claude session gone — shutting voice mode down")
            from open_voice.flag import disable

            disable()
            subprocess.run(["pkill", "-f", "open-voice-tts-daemon"], capture_output=True)
            os._exit(0)


def route_cli() -> None:
    """open-voice-route "phrase" — print the label a phrase routes to. Used by
    /voice-tool to validate a freshly written tool's EXAMPLES."""
    if len(sys.argv) < 2:
        sys.exit('usage: open-voice-route "phrase" [...]')
    for phrase in sys.argv[1:]:
        print(f"{phrase!r} -> {route(phrase)}")


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
    ctx = Ctx(MUX, pane_id)

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

    appended_orphan: str | None = None
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
            if intent in TOOLS:
                run_tool(intent, ctx, text)
                continue
            log(f"-> {text}")
            try:
                final = collect_prompt(vad_model, ctx, pane_id, text)
            except sd.PortAudioError:
                # stream died during the cancel window: recover and send what
                # was already accepted instead of dropping it
                log("audio unavailable — reinitializing PortAudio...")
                reset_portaudio()
                time.sleep(2)
                final = text
            if final is None:
                continue
            draft = composer_draft(pane_id)
            if draft and _normalize(draft) == _normalize(appended_orphan or ""):
                # the "draft" is our own previously appended text (user typed
                # nothing since): append the new utterance and flush with Enter
                append_to_composer(pane_id, final)
                time.sleep(0.3)
                MUX.send_enter(pane_id)
                log("flushed orphaned composer text with Enter")
                appended_orphan = None
                _beep("Glass")
                continue
            if draft:
                # user is mid-typing: append the transcription without sending
                append_to_composer(pane_id, final)
                appended_orphan = f"{draft} {final}"
                log(f"draft in composer — appended, not sent (draft: {draft[:60]!r})")
                continue
            appended_orphan = None
            _beep("Glass")
            if not send_to_claude(pane_id, final):
                # pane may have changed (new session, closed pane); re-resolve and retry
                pane_id = args.pane or find_claude_pane()
                ctx.pane = pane_id
                send_to_claude(pane_id, final)
    except KeyboardInterrupt:
        print()
        raise SystemExit(0)


if __name__ == "__main__":
    main()
