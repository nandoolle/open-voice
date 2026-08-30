import sys

NAME = "volume_down"
DESCRIPTION = "explicitly asks to lower the volume"
EXAMPLES = ["fala mais baixo", "diminui o volume", "mais baixo"]


def run(ctx, text):
    if sys.platform == "darwin":
        ctx.shell(
            "osascript",
            "-e",
            "set volume output volume ((output volume of (get volume settings)) - 15)",
        )
        return
    result = ctx.shell("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "15%-")
    if result.returncode != 0:
        ctx.shell("pactl", "set-sink-volume", "@DEFAULT_SINK@", "-15%")
