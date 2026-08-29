---
description: Create a new open-voice voice tool (voice command for the local voice loop)
allowed-tools: Write, Read, Bash(open-voice-route:*), Bash(sh -c PATH*)
---

Create a new voice tool for open-voice from this request: $ARGUMENTS

A voice tool is one Python file in `~/.config/open-voice/tools/` with this exact contract:

```python
NAME = "lock_screen"                                  # unique label, snake_case; "send" and "cancel" are reserved
DESCRIPTION = "explicitly asks to lock the screen"    # one line, English, starts with "explicitly asks"
EXAMPLES = ["trava a tela", "lock the screen"]        # 2-5 spoken phrasings (include the user's language)

def run(ctx, text):                                   # text = full transcription; ignore it for fixed intents
    ctx.shell("pmset", "displaysleepnow")
```

`ctx` provides: `say(text)` speak via TTS · `beep(sound)` macOS earcon · `stop_tts()` ·
`shell(*args)` run a command · `pane` Claude pane id or None · `mux` pane control
(`send_enter`/`send_esc`/`send_text`) · `config` open-voice config dict · `shutdown()` stop voice mode.
A tool that needs the pane must handle `ctx.pane is None` (e.g. `ctx.say` an error).

Steps:
1. Write the file to `~/.config/open-voice/tools/<name>.py`.
2. Validate routing: run `sh -c 'PATH="$HOME/.local/bin:$PATH" open-voice-route "<each example phrase>"'` and confirm each prints the new NAME. If a phrase misroutes, reword DESCRIPTION/EXAMPLES and retry.
3. Tell the user the tool is ready and that /open-voice:off + /open-voice:on reloads it.
