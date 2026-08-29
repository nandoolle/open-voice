NAME = "volume_down"
DESCRIPTION = "explicitly asks to lower the volume"
EXAMPLES = ["fala mais baixo", "diminui o volume", "mais baixo"]


def run(ctx, text):
    ctx.shell(
        "osascript",
        "-e",
        "set volume output volume ((output volume of (get volume settings)) - 15)",
    )
