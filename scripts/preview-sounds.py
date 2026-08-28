#!/usr/bin/env python3
"""Browse the open-voice earcons (and every macOS system sound) in the terminal.

Arrows/j/k move, Enter plays, Ctrl+C or q quits.
"""

import curses
import subprocess
from pathlib import Path

SOUNDS_DIR = Path("/System/Library/Sounds")
ROLES = {
    "Tink": "mic started capturing",
    "Pop": "utterance captured",
    "Ping": "prompt accepted, cancel window open",
    "Glass": "message sent / Enter",
    "Bottle": "discarded as ambient speech",
    "Basso": "cancelled / dictation off",
}


def main(screen) -> None:
    curses.curs_set(0)
    names = sorted(
        (p.stem for p in SOUNDS_DIR.glob("*.aiff")),
        key=lambda n: (n not in ROLES, n),
    )
    selected = 0
    while True:
        screen.erase()
        screen.addstr(0, 0, "open-voice sounds — Enter plays, q/Ctrl+C quits", curses.A_BOLD)
        for i, name in enumerate(names):
            role = f"  — {ROLES[name]}" if name in ROLES else ""
            attr = curses.A_REVERSE if i == selected else curses.A_NORMAL
            screen.addstr(i + 2, 0, f"  {name:<12}{role}", attr)
        screen.refresh()
        key = screen.getch()
        if key in (curses.KEY_UP, ord("k")):
            selected = (selected - 1) % len(names)
        elif key in (curses.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(names)
        elif key in (curses.KEY_ENTER, 10, 13):
            subprocess.Popen(
                ["afplay", str(SOUNDS_DIR / f"{names[selected]}.aiff")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif key == ord("q"):
            return


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
