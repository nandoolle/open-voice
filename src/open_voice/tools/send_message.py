NAME = "send_message"
DESCRIPTION = "explicitly asks to submit/send the drafted message"
EXAMPLES = ["pode enviar a mensagem", "manda a mensagem", "send the message"]


def run(ctx, text):
    if ctx.pane:
        ctx.mux.send_enter(ctx.pane)
        ctx.beep("Glass")
    else:
        ctx.say("No Claude session to send to.")
