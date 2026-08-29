NAME = "repeat_message"
DESCRIPTION = "explicitly asks to repeat the last reply"
EXAMPLES = [
    "repete o que você disse",
    "repita a última resposta",
    "repita o seu último prompt",
    "repete a mensagem",
    "read that again",
]


def run(ctx, text):
    """Re-speak the last assistant reply from the session transcript."""
    from open_voice.stop_hook import last_assistant_text, strip_markdown

    path = ctx.mux.transcript_path(ctx.pane) if ctx.pane else None
    reply = strip_markdown(last_assistant_text(str(path))) if path else ""
    if reply:
        ctx.say(reply)
    else:
        ctx.beep("Basso")
