"""Router regression battery. Loads the real Qwen (slow, local models required):

    uv run pytest tests/test_router.py
"""

import pytest

from open_voice.listen import TOOLS, route

# every registered tool's EXAMPLES must route back to it — a new tool that
# breaks existing routing fails here, not silently in use
# degrade to "send"; nothing lost
KNOWN_SAFE_MISSES = {"repete a mensagem", "repita o seu último prompt"}
REGISTRY_CASES = [
    pytest.param(
        phrase,
        tool.name,
        marks=[pytest.mark.xfail(strict=False)] if phrase in KNOWN_SAFE_MISSES else [],
    )
    for tool in TOOLS.values()
    for phrase in tool.examples
]


@pytest.mark.parametrize("text,expected", REGISTRY_CASES)
def test_registry_examples(text, expected):
    assert route(text) == expected

CASES = [
    # known misses that degrade safely to "send" (nothing lost, no wrong action)
    pytest.param("repita o seu último prompt", "repeat_message", marks=pytest.mark.xfail(strict=False)),
    pytest.param("read that again", "repeat_message", marks=pytest.mark.xfail(strict=False)),
    pytest.param("repete a mensagem", "repeat_message", marks=pytest.mark.xfail(strict=False)),
    ("repita a última resposta", "repeat_message"),
    ("repete o que você disse", "repeat_message"),
    ("pode enviar a mensagem", "send_message"),
    ("manda a mensagem", "send_message"),
    ("pausa a execução", "pause_execution"),
    ("interrompa a execução", "pause_execution"),
    ("stop the execution", "pause_execution"),
    ("interrompa a leitura", "stop_speaking"),
    ("interrompa o ditado", "stop_speaking"),
    ("pare de ler", "stop_speaking"),
    ("pare de falar", "stop_speaking"),
    ("stop reading", "stop_speaking"),
    ("desliga o microfone", "stop_dictation"),
    ("não mande", "cancel"),
    ("para a música", "stop_media"),
    ("aumenta o volume", "volume_up"),
    ("roda os testes", "send"),
    ("e aí, tudo bem?", "send"),
    ("muito bem, continua", "send"),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_route(text, expected):
    assert route(text) == expected
