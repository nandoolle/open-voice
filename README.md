# open-voice

Hands-free voice loop for [Claude Code](https://claude.com/claude-code), fully local: your microphone is transcribed and injected into a Claude Code session, and Claude's replies are spoken back. No audio ever leaves your machine.

## How it works

```
mic ──▶ silero VAD ──▶ mlx-whisper ──▶ herdr agent prompt ──▶ Claude Code
                                                                  │
speakers ◀── sounddevice ◀── Kokoro TTS daemon ◀── Stop hook ◀────┘
```

Three components:

- **`open-voice-tts-daemon`** — keeps a TTS engine (Kokoro or Chatterbox) warm behind a local HTTP API (`POST /say`, `POST /stop`, `GET /health`, `GET /busy`).
- **`open-voice-stop-hook`** — a Claude Code `Stop` hook that extracts the final reply of each turn from the transcript, strips markdown, and sends it to the daemon. It is a no-op unless the `~/.claude/voice-enabled` flag exists.
- **`open-voice-listen`** — hands-free listener: records an utterance (silero VAD with pre-roll, so leading syllables aren't clipped), transcribes it with mlx-whisper, and injects it into a Claude Code pane via [herdr](https://github.com/nandoolle/herdr). It waits for the turn to finish and TTS to go idle before reopening the mic, so the assistant never hears itself.

Both audio ends survive device changes (e.g. a bluetooth headset disconnecting): PortAudio is reinitialized and streams are reopened automatically.

## Requirements

- macOS on Apple Silicon (mlx-whisper requires it; TTS runs on MPS/CPU)
- Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/)
- [herdr](https://github.com/nandoolle/herdr) managing your Claude Code panes
- Microphone permission granted to your terminal app

## Setup

```sh
git clone https://github.com/nandoolle/open-voice && cd open-voice
uv sync
```

Register the Stop hook in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run --project /path/to/open-voice open-voice-stop-hook"
          }
        ]
      }
    ]
  }
}
```

## Usage

```sh
scripts/voice-on.sh    # flag + TTS daemon + listener (one session at a time)
scripts/voice-off.sh   # flag off, stop speech, kill listener (daemon stays warm)
```

Wire them to `/voice-on` and `/voice-off` slash commands in `~/.claude/commands/` for in-session toggling.

Speak; 2.5 s of silence sends the utterance to Claude. Replies are spoken automatically. To make Claude read a specific mid-turn message aloud, include the invisible U+2060 marker in it — otherwise only the final reply of the turn is spoken.

## Configuration

Defaults are pt-BR: Kokoro voice `pf_dora` (`--voice`, `--lang` on the daemon) and whisper language `pt` (`WHISPER_LANGUAGE` in `listen.py`). The daemon also supports `--engine chatterbox` for Chatterbox multilingual TTS.

Logs live in `~/.claude/open-voice-tts.log` and `~/.claude/open-voice-listen.log`.
