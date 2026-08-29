NAME = "pause_execution"
DESCRIPTION = "explicitly asks to pause/interrupt the agent's execution or work (not its voice)"
EXAMPLES = ["pausa a execução", "interrompa a execução", "stop the execution"]


def run(ctx, text):
    ctx.stop_tts()
    if ctx.pane:
        ctx.mux.send_esc(ctx.pane)
