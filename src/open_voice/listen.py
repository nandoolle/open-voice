"""Loop STT hands-free: mic + VAD → whisper local → herdr agent prompt.

Ciclo: escuta o mic até detectar fala seguida de 2.5s de silêncio (silero VAD),
transcreve com mlx-whisper (large-v3-turbo, pt), injeta no pane do Claude Code
via `herdr agent prompt` e espera o turno terminar (herdr wait + TTS ocioso)
antes de reabrir o mic.
"""

import argparse
import json
import queue
import subprocess
import sys
import time

import httpx
import numpy as np
import sounddevice as sd

VAD_SAMPLE_RATE = 16_000
VAD_CHUNK = 512  # amostras por chamada do silero @16k
SILENCE_SECONDS = 2.5
MIN_SPEECH_SECONDS = 0.6
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
TTS_DAEMON_URL = "http://127.0.0.1:8765"


def log(msg: str) -> None:
    print(f"[open-voice] {msg}", flush=True)


def find_claude_pane() -> str:
    out = subprocess.run(
        ["herdr", "pane", "list"], capture_output=True, text=True, check=True
    ).stdout
    panes = json.loads(out)["result"]["panes"]
    claude = [p for p in panes if p.get("agent") == "claude"]
    if not claude:
        sys.exit("Nenhum pane com Claude Code encontrado no herdr.")
    focused = [p for p in claude if p.get("focused")]
    if focused:
        return focused[0]["pane_id"]
    if len(claude) == 1:
        return claude[0]["pane_id"]
    ids = ", ".join(p["pane_id"] for p in claude)
    sys.exit(f"Vários Claudes ativos ({ids}) e nenhum focado — use --pane.")


def record_utterance(vad_model) -> np.ndarray | None:
    """Grava até fala + SILENCE_SECONDS de silêncio. None se nada foi falado."""
    from silero_vad import VADIterator

    vad = VADIterator(vad_model, sampling_rate=VAD_SAMPLE_RATE)
    audio_q: queue.Queue[np.ndarray] = queue.Queue()

    def callback(indata, frames, time_info, status):
        audio_q.put(indata[:, 0].copy())

    chunks: list[np.ndarray] = []
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
                event = vad(chunk)
                if event and "start" in event:
                    if not speaking:
                        log("🎤 gravando...")
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
        audio, path_or_hf_repo=WHISPER_MODEL, language="pt"
    )
    return result["text"].strip()


def send_to_claude(pane_id: str, text: str) -> None:
    subprocess.run(
        ["herdr", "agent", "prompt", pane_id, text, "--wait", "--timeout", "600000"],
        capture_output=True,
        text=True,
    )


def wait_tts_idle() -> None:
    with httpx.Client(timeout=2) as client:
        while True:
            try:
                if not client.get(f"{TTS_DAEMON_URL}/busy").json()["busy"]:
                    return
            except httpx.HTTPError:
                return  # daemon fora do ar: nada a esperar
            time.sleep(0.3)


def main() -> None:
    parser = argparse.ArgumentParser(description="open-voice hands-free listener")
    parser.add_argument("--pane", help="pane alvo (ex.: w1:pD); default: autodetect")
    args = parser.parse_args()

    from silero_vad import load_silero_vad

    log("carregando VAD e whisper...")
    vad_model = load_silero_vad()
    transcribe(np.zeros(VAD_SAMPLE_RATE, dtype=np.float32))  # warm-up do whisper

    pane_id = args.pane or find_claude_pane()
    log(f"pronto — alvo: {pane_id}. Fale; {SILENCE_SECONDS}s de silêncio envia.")

    while True:
        audio = record_utterance(vad_model)
        if audio is None:
            continue
        text = transcribe(audio)
        if not text:
            continue
        log(f"→ {text}")
        send_to_claude(pane_id, text)
        wait_tts_idle()
        log("turno concluído — escutando de novo.")


if __name__ == "__main__":
    main()
