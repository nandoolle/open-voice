# open-voice

Hands-free voice loop for [Claude Code](https://claude.com/claude-code), fully local: your mic is transcribed and injected into a Claude Code session, and Claude's replies are spoken back. No audio ever leaves your machine.

```
mic ──▶ silero VAD ──▶ whisper ──▶ Qwen router ──▶ multiplexer ──▶ Claude Code
                                                                       │
speakers ◀── Kokoro TTS daemon ◀── Stop hook / transcript follower ◀───┘
```

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/nandoolle/open-voice/main/scripts/install.sh | sh
```

Installs [uv](https://docs.astral.sh/uv/) and open-voice, ensures a multiplexer (installs [herdr](https://github.com/ogulcancelik/herdr) if none of herdr/tmux/zellij is present) and runs `open-voice-setup`, which asks three questions — RAM-based recommendations preselected:

| Choice | Options | Default (≥ 16 GB / less) |
|---|---|---|
| Qwen router | `0.5b` `1.5b` | `1.5b` / `0.5b` |
| whisper (STT) | `small` `large-v3-turbo` | `large-v3-turbo` / `small` |
| multiplexer | `herdr` `tmux` `zellij` | `herdr` |

Answers persist in `~/.config/open-voice/config.json`; flags (`--router-model`, `--whisper-model`, `--multiplexer`, `--skip-models`) skip the questions. Setup also writes the `/voice-on` and `/voice-off` slash commands, registers the Claude Code hooks, and pre-downloads the models.

Requires macOS on Apple Silicon (mlx), Python ≥ 3.12, and microphone permission for your terminal app.

## Usage

Inside a Claude Code session running under your multiplexer:

```
/voice-on    # flag + TTS daemon + listener (one session at a time)
/voice-off   # stops speech and shuts every open-voice process down
```

Speak; 2.5 s of silence sends. No wake word: a local Qwen router classifies each utterance — speech for the agent is sent, ambient talk is discarded, and short commands ("envie a mensagem", "pare de falar", "pause a execução", "pare o ditado", "não mande") trigger local actions. After a prompt is accepted there is a 3 s cancel window ("não mande" drops it, more dictation extends it). A typed draft in the composer is appended to, never auto-sent. Earcons mark transitions: Blow (recording), Frog (captured), Purr (cancel window), Glass (sent), Basso (cancelled/off).

The final reply of each turn is spoken automatically; mid-turn text prefixed with 🔊 is spoken live as it arrives. Voice mode shuts itself down when the Claude session exits.

## Notes

- **herdr** is the reference backend (turn tracking, session-aware). **tmux** and **zellij** are best-effort keystroke injection; zellij actions only reach the focused pane.
- Defaults are pt-BR: Kokoro voice `pf_dora` (`--voice`, `--lang` on the daemon; `--engine chatterbox` for Chatterbox TTS) and whisper language `pt`.
- Logs: `~/.claude/open-voice-tts.log`, `~/.claude/open-voice-listen.log`.
