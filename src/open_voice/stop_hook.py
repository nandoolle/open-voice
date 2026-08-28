"""Stop hook do Claude Code: extrai a última resposta do transcript e manda ao daemon TTS.

Recebe o payload do hook via stdin (JSON com transcript_path). Sai cedo e em
silêncio se a flag voice-enabled não existir ou se o daemon estiver fora do ar.
Só stdlib — o hook roda a cada resposta e precisa ser barato.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DAEMON_URL = "http://127.0.0.1:8765"
# U+2060 (word joiner): invisível; presença numa mensagem = "leia esta em voz alta"
SPEAK_MARKER = "⁠"
FLAG_PATH = Path.home() / ".claude" / "voice-enabled"
MAX_CHARS = 1500


def _is_human_message(entry: dict) -> bool:
    """Mensagem digitada pelo usuário — tool_results também chegam como type user."""
    if entry.get("type") != "user":
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") == "text" for b in content
        )
    return False


def last_assistant_text(transcript_path: str) -> str:
    """Texto assistant do último turno (tudo após a última mensagem humana)."""
    texts: list[str] = []
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _is_human_message(entry):
                texts = []
                continue
            if entry.get("type") != "assistant":
                continue
            content = entry.get("message", {}).get("content", [])
            chunk = "\n".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ).strip()
            if chunk:
                texts.append(chunk)
    marked = [t for t in texts if SPEAK_MARKER in t]
    if marked:
        return "\n".join(t.replace(SPEAK_MARKER, "") for t in marked)
    # sem marcador: só a resposta final, não os textos entre tool calls
    return texts[-1] if texts else ""


def strip_markdown(text: str) -> str:
    """Remove ruído de markdown que soa mal em TTS."""
    text = re.sub(r"```.*?```", " Bloco de código omitido. ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
    text = re.sub(r"https?://\S+", "link", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def main() -> None:
    if not FLAG_PATH.exists():
        return
    payload = json.load(sys.stdin)
    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return
    text = strip_markdown(last_assistant_text(transcript_path))
    if not text:
        return
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + " ... resposta longa, resto no terminal."
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        f"{DAEMON_URL}/say", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=2)
    except (urllib.error.URLError, OSError):
        pass  # daemon fora do ar: modo voz efetivamente desligado


if __name__ == "__main__":
    main()
