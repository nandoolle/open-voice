NAME = "stop_dictation"
DESCRIPTION = "explicitly asks to turn off the microphone/dictation"
EXAMPLES = ["desliga o microfone", "turn off the mic"]


def run(ctx, text):
    ctx.shutdown()
