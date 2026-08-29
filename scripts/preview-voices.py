#!/usr/bin/env python3
"""Browse and audition the Kokoro voices in the terminal.

Arrows/j/k move, Enter synthesizes and plays a sample in the voice's language,
s saves the voice (tts_voice + matching tts_lang) to the open-voice config,
q or Ctrl+C quits. First play per language loads a pipeline (a few seconds);
voices not yet cached are downloaded on demand.
"""

import curses
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from open_voice import config as ov_config  # noqa: E402

KOKORO_REPO = "hexgrad/Kokoro-82M"
# kokoro lang_code per voice prefix, with a sample sentence to audition
LANGS = {
    "a": ("American English", "Hello! This is how I sound as your coding voice."),
    "b": ("British English", "Hello! This is how I sound as your coding voice."),
    "e": ("Spanish", "¡Hola! Así sueno como tu voz de programación."),
    "f": ("French", "Bonjour ! Voici comment je sonne comme votre voix."),
    "h": ("Hindi", "नमस्ते! मैं आपकी कोडिंग आवाज़ हूँ।"),
    "i": ("Italian", "Ciao! Ecco come suono come la tua voce."),
    "j": ("Japanese", "こんにちは！これが私の声です。"),
    "p": ("pt-BR", "Olá! É assim que eu soo como a sua voz de programação."),
    "z": ("Mandarin", "你好！这就是我的声音。"),
}

_pipelines: dict[str, object] = {}


def list_voices() -> list[str]:
    from huggingface_hub import HfApi

    files = HfApi().list_repo_files(KOKORO_REPO)
    return sorted(
        Path(f).stem for f in files if f.startswith("voices/") and f.endswith(".pt")
    )


def play(voice: str) -> None:
    import numpy as np
    import sounddevice as sd

    lang = voice[0]
    if lang not in _pipelines:
        from kokoro import KPipeline

        _pipelines[lang] = KPipeline(lang_code=lang)
    sd.stop()
    for _, _, audio in _pipelines[lang](LANGS[lang][1], voice=voice):
        sd.play(np.asarray(audio), 24_000)
        sd.wait()


def save(voice: str) -> None:
    cfg = ov_config.load()
    cfg["tts_voice"], cfg["tts_lang"] = voice, voice[0]
    ov_config.save(cfg)


def main(screen) -> None:
    curses.curs_set(0)
    screen.addstr(0, 0, "loading voice list from Hugging Face...")
    screen.refresh()
    voices = list_voices()
    current = ov_config.load()["tts_voice"]
    selected = voices.index(current) if current in voices else 0
    status = ""
    while True:
        screen.erase()
        height = screen.getmaxyx()[0]
        screen.addstr(0, 0, "kokoro voices — Enter plays, s saves to config, q quits", curses.A_BOLD)
        top = max(0, min(selected - (height - 4) // 2, len(voices) - (height - 4)))
        for row, voice in enumerate(voices[top : top + height - 4]):
            lang = LANGS.get(voice[0], ("?",))[0]
            mark = " *" if voice == current else ""
            attr = curses.A_REVERSE if top + row == selected else curses.A_NORMAL
            screen.addstr(row + 2, 0, f"  {voice:<16} {lang}{mark}", attr)
        screen.addstr(height - 1, 0, status[: screen.getmaxyx()[1] - 1])
        screen.refresh()
        key = screen.getch()
        if key in (curses.KEY_UP, ord("k")):
            selected = (selected - 1) % len(voices)
        elif key in (curses.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(voices)
        elif key in (curses.KEY_ENTER, 10, 13):
            status = f"synthesizing {voices[selected]}..."
            screen.addstr(height - 1, 0, status)
            screen.refresh()
            try:
                play(voices[selected])
                status = f"played {voices[selected]}"
            except Exception as exc:
                status = f"failed: {exc}"
        elif key == ord("s"):
            save(voices[selected])
            current = voices[selected]
            status = f"saved tts_voice={current} tts_lang={current[0]} — restart voice mode to apply"
        elif key == ord("q"):
            return


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
