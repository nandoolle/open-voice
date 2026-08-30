# open-voice

Hands-free voice loop for [Claude Code](https://claude.com/claude-code), fully local: your mic is transcribed and injected into a Claude Code session, and Claude's replies are spoken back. No audio ever leaves your machine.

```
mic ──▶ silero VAD ──▶ whisper ──▶ Qwen router ──▶ multiplexer ──▶ Claude Code
                                                                       │
speakers ◀── Kokoro TTS daemon ◀── Stop hook / transcript follower ◀───┘
```

## Install

**As a Claude Code plugin (preferred):**

```
/plugin marketplace add nandoolle/open-voice
/plugin install open-voice@open-voice
```

Then run `/open-voice:on` to finish the installation — the first run installs the runtime and downloads the models (a few GB), so it may take several minutes. The plugin ships the slash commands and hooks; nothing is written to your settings besides `promptSuggestionEnabled`.

**Standalone (`curl | sh`, if you prefer not to use the plugin system):**

```sh
curl -fsSL https://raw.githubusercontent.com/nandoolle/open-voice/main/scripts/install.sh | sh
```

Installs [uv](https://docs.astral.sh/uv/) and open-voice, ensures a multiplexer (installs [herdr](https://github.com/ogulcancelik/herdr) if none of herdr/tmux/zellij is present) and runs `open-voice-setup`, which asks three questions — RAM-based recommendations preselected:

| Choice | Options | Default (≥ 16 GB / less) |
|---|---|---|
| Qwen router | `0.5b` `1.5b` | `1.5b` / `0.5b` |
| whisper (STT) | `small` `large-v3-turbo` | `large-v3-turbo` / `small` |
| multiplexer | `herdr` `tmux` `zellij` | `herdr` (macOS) / `tmux` (Linux) |

Answers persist in `~/.config/open-voice/config.json`; flags (`--router-model`, `--whisper-model`, `--multiplexer`, `--skip-models`) skip the questions. Setup also writes the same `/open-voice:on`, `/open-voice:off` and `/open-voice:tool` slash commands the plugin ships, registers the Claude Code hooks, and pre-downloads the models.

Requires Python ≥ 3.12 and microphone access for your terminal app.

- **macOS (Apple Silicon)**: STT and routing run on the GPU via MLX. Grant mic permission in System Settings → Privacy & Security → Microphone.
- **Linux (beta)**: STT via faster-whisper and routing via llama.cpp, CPU (CUDA planned). `install.sh` installs the system packages it needs (Debian/Ubuntu via apt; other distros: install `git build-essential cmake tmux libportaudio2` first). Voice command routing is currently less accurate than on macOS — commands may land in the chat as text instead of firing; a fine-tuned router is in progress.
- **Windows**: supported via WSL2 — needs WSLg (Windows 11) for microphone passthrough; follow the Linux path inside WSL.

## Usage

Inside a Claude Code session running under your multiplexer:

```
/open-voice:on    # flag + TTS daemon + listener (one session at a time)
/open-voice:off   # stops speech and shuts every open-voice process down
```

Speak; 2.5 s of silence sends. No wake word: a local Qwen router classifies each utterance — speech for the agent is sent, ambient talk is discarded, and short commands ("envie a mensagem", "pare de falar", "pause a execução", "pare o ditado", "não mande") trigger local actions. After a prompt is accepted there is a 3 s cancel window ("não mande" drops it, more dictation extends it). A typed draft in the composer is appended to, never auto-sent. Earcons mark transitions: Blow (recording), Frog (captured), Purr (cancel window), Glass (sent), Basso (cancelled/off).

The final reply of each turn is spoken automatically; mid-turn text prefixed with 🔊 is spoken live as it arrives. Voice mode shuts itself down when the Claude session exits.

## Custom voice tools

Every voice command is a tool: one Python file exporting `NAME`, `DESCRIPTION`, `EXAMPLES` and `run(ctx, text)`. The built-ins live in `src/open_voice/tools/`; drop your own in `~/.config/open-voice/tools/` (same `NAME` overrides a built-in) and restart voice mode. The router picks them up automatically — labels and few-shots are built from the registry. Ask Claude Code to write one for you with `/open-voice:tool`, and validate phrases with `open-voice-route "your phrase"`.

## Notes

- **herdr** is the reference backend (turn tracking, session-aware). **tmux** and **zellij** are best-effort keystroke injection; zellij actions only reach the focused pane.
- Runtime tuning lives in `~/.config/open-voice/config.json` — inspect with `open-voice-config`, change with `open-voice-config KEY VALUE`: whisper language, TTS engine/voice/lang (Kokoro or Chatterbox), daemon port, VAD threshold, energy-gate ratios, earcons on/off. Defaults are en-US (Kokoro `af_heart`, whisper `en`); for pt-BR set `whisper_language pt`, `tts_lang p`, `tts_voice pf_dora`.
- Logs: `~/.claude/open-voice-tts.log`, `~/.claude/open-voice-listen.log`.
