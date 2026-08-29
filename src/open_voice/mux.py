"""Multiplexer backends: herdr, tmux and zellij behind one interface.

herdr is the reference backend (agent-aware: turn tracking, session id).
tmux and zellij are best-effort: prompts are injected as keystrokes, the
transcript is resolved from the pane's cwd (newest session JSONL) and
liveness falls back to "the pane still runs a non-shell command".
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

SHELLS = {"zsh", "bash", "fish", "sh", "nu"}


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def _newest_transcript(cwd: str) -> Path | None:
    slug = cwd.replace("/", "-").replace(".", "-")
    project = Path.home() / ".claude" / "projects" / slug
    files = sorted(project.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


class HerdrMux:
    name = "herdr"
    pane_env = "HERDR_PANE_ID"
    # herdr tracks the agent turn itself: prompt blocks until the turn ends
    blocking_prompt = True

    def find_claude_pane(self) -> str | None:
        result = _run(["herdr", "pane", "list"])
        if result.returncode != 0:
            return None
        panes = json.loads(result.stdout)["result"]["panes"]
        claude = [p for p in panes if p.get("agent") == "claude"]
        if not claude:
            return None
        focused = [p for p in claude if p.get("focused")]
        if focused:
            return focused[0]["pane_id"]
        return claude[0]["pane_id"] if len(claude) == 1 else "AMBIGUOUS"

    def send_text(self, pane_id: str, text: str) -> None:
        _run(["herdr", "pane", "send-text", pane_id, text])

    def send_enter(self, pane_id: str) -> None:
        _run(["herdr", "pane", "send-keys", pane_id, "enter"])

    def send_esc(self, pane_id: str) -> None:
        _run(["herdr", "agent", "send-keys", pane_id, "esc"])

    def read_screen(self, pane_id: str, lines: int) -> str:
        result = _run(
            ["herdr", "pane", "read", pane_id, "--source", "detection", "--lines", str(lines)]
        )
        return result.stdout if result.returncode == 0 else ""

    def prompt(self, pane_id: str, text: str) -> tuple[bool, str]:
        result = _run(
            ["herdr", "agent", "prompt", pane_id, text, "--wait", "--timeout", "600000"]
        )
        return result.returncode == 0, (result.stderr or result.stdout).strip()

    def agent_alive(self, pane_id: str) -> bool:
        result = _run(["herdr", "agent", "get", pane_id])
        return (
            result.returncode == 0
            and '"agent":"claude"' in result.stdout.replace(" ", "")
        )

    def transcript_path(self, pane_id: str) -> Path | None:
        result = _run(["herdr", "agent", "get", pane_id])
        if result.returncode != 0:
            return None
        agent = json.loads(result.stdout)["result"]["agent"]
        session = agent.get("agent_session") or {}
        if session.get("kind") != "id" or not agent.get("cwd"):
            return None
        slug = agent["cwd"].replace("/", "-").replace(".", "-")
        path = Path.home() / ".claude" / "projects" / slug / f"{session['value']}.jsonl"
        return path if path.exists() else None


class TmuxMux:
    name = "tmux"
    pane_env = "TMUX_PANE"
    blocking_prompt = False

    def find_claude_pane(self) -> str | None:
        result = _run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{pane_id}\t#{pane_current_command}\t#{?pane_active,1,0}",
            ]
        )
        if result.returncode != 0:
            return None
        rows = [line.split("\t") for line in result.stdout.splitlines() if line]
        # Claude Code shows up as its own process name or as the node runtime
        claude = [r for r in rows if r[1] in ("claude", "node")]
        if not claude:
            return None
        active = [r for r in claude if r[2] == "1"]
        if active:
            return active[0][0]
        return claude[0][0] if len(claude) == 1 else "AMBIGUOUS"

    def send_text(self, pane_id: str, text: str) -> None:
        _run(["tmux", "send-keys", "-t", pane_id, "-l", "--", text])

    def send_enter(self, pane_id: str) -> None:
        _run(["tmux", "send-keys", "-t", pane_id, "Enter"])

    def send_esc(self, pane_id: str) -> None:
        _run(["tmux", "send-keys", "-t", pane_id, "Escape"])

    def read_screen(self, pane_id: str, lines: int) -> str:
        result = _run(["tmux", "capture-pane", "-p", "-t", pane_id])
        if result.returncode != 0:
            return ""
        return "\n".join(result.stdout.splitlines()[-lines:])

    def prompt(self, pane_id: str, text: str) -> tuple[bool, str]:
        if _run(["tmux", "display-message", "-p", "-t", pane_id, "ok"]).returncode != 0:
            return False, f"pane {pane_id} not found"
        self.send_text(pane_id, text)
        time.sleep(0.3)
        self.send_enter(pane_id)
        return True, ""

    def agent_alive(self, pane_id: str) -> bool:
        result = _run(
            ["tmux", "display-message", "-p", "-t", pane_id, "#{pane_current_command}"]
        )
        return result.returncode == 0 and result.stdout.strip() not in SHELLS

    def transcript_path(self, pane_id: str) -> Path | None:
        result = _run(
            ["tmux", "display-message", "-p", "-t", pane_id, "#{pane_current_path}"]
        )
        if result.returncode != 0:
            return None
        return _newest_transcript(result.stdout.strip())


class ZellijMux:
    """zellij actions target the focused pane of a session — there is no pane
    addressing. The "pane id" here is `<session>:<cwd>`, captured by /voice-on
    inside the Claude pane; injection lands on whatever pane is focused."""

    name = "zellij"
    pane_env = None  # composed by current_pane_from_env below
    blocking_prompt = False

    @staticmethod
    def current_pane_from_env() -> str | None:
        session = os.environ.get("ZELLIJ_SESSION_NAME")
        return f"{session}:{os.getcwd()}" if session else None

    @staticmethod
    def _split(pane_id: str) -> tuple[str, str]:
        session, _, cwd = pane_id.partition(":")
        return session, cwd

    def find_claude_pane(self) -> str | None:
        return None  # no autodetection: /voice-on must run inside the session

    def _action(self, pane_id: str, *args: str) -> subprocess.CompletedProcess:
        session, _ = self._split(pane_id)
        return _run(["zellij", "--session", session, "action", *args])

    def send_text(self, pane_id: str, text: str) -> None:
        self._action(pane_id, "write-chars", text)

    def send_enter(self, pane_id: str) -> None:
        self._action(pane_id, "write", "13")

    def send_esc(self, pane_id: str) -> None:
        self._action(pane_id, "write", "27")

    def read_screen(self, pane_id: str, lines: int) -> str:
        with tempfile.NamedTemporaryFile(suffix=".txt") as tmp:
            result = self._action(pane_id, "dump-screen", tmp.name)
            if result.returncode != 0:
                return ""
            content = Path(tmp.name).read_text(errors="replace")
        return "\n".join(content.splitlines()[-lines:])

    def prompt(self, pane_id: str, text: str) -> tuple[bool, str]:
        self.send_text(pane_id, text)
        time.sleep(0.3)
        self.send_enter(pane_id)
        return True, ""

    def agent_alive(self, pane_id: str) -> bool:
        session, _ = self._split(pane_id)
        result = _run(["zellij", "list-sessions", "-s"])
        return result.returncode == 0 and session in result.stdout.splitlines()

    def transcript_path(self, pane_id: str) -> Path | None:
        _, cwd = self._split(pane_id)
        return _newest_transcript(cwd) if cwd else None


BACKENDS = {m.name: m for m in (HerdrMux, TmuxMux, ZellijMux)}


def get_mux():
    from open_voice.config import load

    return BACKENDS[load()["multiplexer"]]()


def current_pane_from_env(mux) -> str | None:
    if isinstance(mux, ZellijMux):
        return ZellijMux.current_pane_from_env()
    return os.environ.get(mux.pane_env) if mux.pane_env else None
