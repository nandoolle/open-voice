"""Daemon TTS: Kokoro warm servido via HTTP local, com fila e interrupção.

POST /say {"text": ...} enfileira; POST /stop cancela a fala atual e limpa
a fila. O modelo carrega uma vez no startup e fica residente.
"""

import argparse
import queue
import threading

import numpy as np
import sounddevice as sd
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from open_voice.audio import reset_portaudio

DEFAULT_PORT = 8765
DEFAULT_VOICE = "pf_dora"  # pt-br feminina; lang_code "p" = pt-br
DEFAULT_LANG = "p"


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

        # resemble-perth vem sem o watermarker implícito; desnecessário aqui
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
    return {"queued": bool(text)}


@app.post("/stop")
def stop():
    _drain_queue()
    _interrupt.set()
    sd.stop()
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
        try:
            for audio in _engine.synth_chunks(text):
                if _interrupt.is_set():
                    break
                _play_resilient(audio)
        except sd.PortAudioError as exc:
            # sem saída de áudio utilizável agora; descarta a fala, thread segue viva
            print(f"[tts] fala descartada, áudio indisponível: {exc}", flush=True)
        finally:
            _speaking.clear()


def _play_resilient(audio: np.ndarray) -> None:
    """Toca o áudio; se o dispositivo de saída mudou, reinicializa e re-tenta."""
    for attempt in (1, 2):
        try:
            sd.play(audio, _engine.sample_rate)
            # sd.wait() bloquearia sem enxergar o interrupt; poll barato
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
    parser.add_argument("--engine", choices=ENGINES, default="kokoro")
    args = parser.parse_args()

    _voice = args.voice
    _engine = ENGINES[args.engine](args.lang, args.voice)
    threading.Thread(target=_speak_loop, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
