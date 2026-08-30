import sys

NAME = "volume_up"
DESCRIPTION = "explicitly asks to raise the volume"
EXAMPLES = ["aumenta o som", "aumenta o volume"]


def run(ctx, text):
    if sys.platform == "darwin":
        ctx.shell(
            "osascript",
            "-e",
            "set volume output volume ((output volume of (get volume settings)) + 15)",
        )
        return
    # PipeWire first, PulseAudio fallback
    result = ctx.shell("wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "15%+")
    if result.returncode != 0:
        ctx.shell("pactl", "set-sink-volume", "@DEFAULT_SINK@", "+15%")
