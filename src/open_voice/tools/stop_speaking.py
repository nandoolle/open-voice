NAME = "stop_speaking"
DESCRIPTION = "explicitly asks the voice to stop talking/reading aloud (leitura, fala, ditado do assistente)"
EXAMPLES = [
    "fica quieto",
    "pare de ler",
    "pare de falar",
    "interrompa a leitura",
    "interrompa o ditado",
    "stop reading",
]


def run(ctx, text):
    ctx.stop_tts()
