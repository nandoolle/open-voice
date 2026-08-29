"""TTS daemon: warm engine served over local HTTP, with a queue and interruption.

POST /say {"text": ...} enqueues; POST /stop cancels the current speech and
drains the queue. The model loads once at startup and stays resident.
"""

import argparse
import queue
import threading
import time


def _log(msg: str) -> None:
    print(f"[tts {time.strftime('%H:%M:%S')}] {msg}", flush=True)

import numpy as np
import sounddevice as sd
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from open_voice.audio import reset_portaudio
from open_voice.config import load as load_config

# defaults come from ~/.config/open-voice/config.json; CLI flags override
_CFG = load_config()
DEFAULT_PORT = _CFG["daemon_port"]
DEFAULT_VOICE = _CFG["tts_voice"]
DEFAULT_LANG = _CFG["tts_lang"]
DEFAULT_ENGINE = _CFG["tts_engine"]


class KokoroEngine:
    sample_rate = 24_000

    def __init__(self, lang: str, voice: str):
        from kokoro import KPipeline

        self._pipe = KPipeline(lang_code=lang)
        self._voice = voice

    def synth_chunks(self, text: str):
        for _, _, audio in self._pipe(text, voice=self._voice):
            yield np.asarray(audio)


class ChatterboxEngine:
    def __init__(self, lang: str, voice: str):
        import torch
        import perth

        # resemble-perth ships without the implicit watermarker; not needed here
        if getattr(perth, "PerthImplicitWatermarker", None) is None:
            perth.PerthImplicitWatermarker = perth.DummyWatermarker
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._model = ChatterboxMultilingualTTS.from_pretrained(device=device)
        self._lang = "pt" if lang == "p" else lang
        self.sample_rate = self._model.sr

    def synth_chunks(self, text: str):
        yield self._model.generate(text, language_id=self._lang).squeeze(0).cpu().numpy()


ENGINES = {"kokoro": KokoroEngine, "chatterbox": ChatterboxEngine}

app = FastAPI()
_say_queue: queue.Queue[str] = queue.Queue()
_interrupt = threading.Event()
_speaking = threading.Event()
_engine = None
_voice = DEFAULT_VOICE


class SayRequest(BaseModel):
    text: str


@app.post("/say")
def say(req: SayRequest):
    text = req.text.strip()
    if text:
        _say_queue.put(text)
        _log(f"queued: {text[:60]!r}")
    return {"queued": bool(text)}


@app.post("/stop")
def stop():
    _drain_queue()
    _interrupt.set()
    sd.stop()
    _log("stop requested (queue drained)")
    return {"stopped": True}


@app.get("/health")
def health():
    return {"ok": True, "voice": _voice}


@app.get("/busy")
def busy():
    return {"busy": _speaking.is_set() or not _say_queue.empty()}


def _drain_queue() -> None:
    try:
        while True:
            _say_queue.get_nowait()
    except queue.Empty:
        pass


def _speak_loop() -> None:
    assert _engine is not None
    while True:
        text = _say_queue.get()
        _interrupt.clear()
        _speaking.set()
        # follow the CURRENT system default output: PortAudio freezes the device
        # list at init, so a headset connected later would never receive audio
        try:
            reset_portaudio()
        except Exception:
            pass
        try:
            _log(f"speaking: {text[:60]!r}")
            for audio in _engine.synth_chunks(text):
                if _interrupt.is_set():
                    _log("interrupted mid-speech")
                    break
                _play_resilient(audio)
            else:
                _log("finished")
        except sd.PortAudioError as exc:
            # no usable audio output right now; drop the utterance, keep the thread alive
            _log(f"speech DROPPED, audio unavailable: {exc}")
        finally:
            _speaking.clear()


def _play_resilient(audio: np.ndarray) -> None:
    """Play audio; if the output device changed, reinitialize and retry once."""
    for attempt in (1, 2):
        try:
            sd.play(audio, _engine.sample_rate)
            # sd.wait() would block without seeing the interrupt; cheap polling
            while sd.get_stream().active:
                if _interrupt.wait(0.05):
                    sd.stop()
                    break
            return
        except sd.PortAudioError:
            if attempt == 2:
                raise
            reset_portaudio()


def main() -> None:
    global _engine, _voice
    parser = argparse.ArgumentParser(description="open-voice TTS daemon")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--lang", default=DEFAULT_LANG)
    parser.add_argument("--engine", choices=ENGINES, default=DEFAULT_ENGINE)
    args = parser.parse_args()

    _voice = args.voice
    _engine = ENGINES[args.engine](args.lang, args.voice)
    threading.Thread(target=_speak_loop, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
