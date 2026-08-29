"""UserPromptSubmit hook: remind Claude of the 🔊 marker while voice mode is on."""

import json

from open_voice.flag import voice_enabled

REMINDER = (
    "Voice mode is ON. Prefix mid-turn text (between tool calls) worth speaking in "
    "real time with 🔊 — e.g. a warning before a long operation or an important "
    "finding mid-work. The transcript follower speaks 🔊 blocks immediately; the "
    "final reply of the turn is spoken automatically and must NOT carry the marker. "
    "Use sparingly: only what the user needs to hear before the turn ends."
)


def main() -> None:
    if not voice_enabled():
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": REMINDER,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
