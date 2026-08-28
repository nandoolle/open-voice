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
from kokoro import KPipeline
from pydantic import BaseModel

SAMPLE_RATE = 24_000
DEFAULT_PORT = 8765
DEFAULT_VOICE = "pf_dora"  # pt-br feminina; lang_code "p" = pt-br
DEFAULT_LANG = "p"

app = FastAPI()
_say_queue: queue.Queue[str] = queue.Queue()
_interrupt = threading.Event()
_speaking = threading.Event()
_pipeline: KPipeline | None = None
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
    assert _pipeline is not None
    while True:
        text = _say_queue.get()
        _interrupt.clear()
        _speaking.set()
        try:
            for _, _, audio in _pipeline(text, voice=_voice):
                if _interrupt.is_set():
                    break
                sd.play(np.asarray(audio), SAMPLE_RATE)
                # sd.wait() bloquearia sem enxergar o interrupt; poll barato
                while sd.get_stream().active:
                    if _interrupt.wait(0.05):
                        sd.stop()
                        break
        finally:
            _speaking.clear()


def main() -> None:
    global _pipeline, _voice
    parser = argparse.ArgumentParser(description="open-voice TTS daemon (Kokoro)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--lang", default=DEFAULT_LANG)
    args = parser.parse_args()

    _voice = args.voice
    _pipeline = KPipeline(lang_code=args.lang)
    threading.Thread(target=_speak_loop, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
