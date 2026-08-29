NAME = "volume_up"
DESCRIPTION = "explicitly asks to raise the volume"
EXAMPLES = ["aumenta o som", "aumenta o volume"]


def run(ctx, text):
    ctx.shell(
        "osascript",
        "-e",
        "set volume output volume ((output volume of (get volume settings)) + 15)",
    )
