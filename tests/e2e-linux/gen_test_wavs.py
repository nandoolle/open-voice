"""Generate spoken test fixtures with kokoro for the container e2e test."""

from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline

OUT = Path(__file__).parent / "container" / "test_wavs"
OUT.mkdir(parents=True, exist_ok=True)

FIXTURES = [
    ("en_prompt", "a", "af_heart", "What does this function do?"),
    ("en_volume", "a", "af_heart", "Turn the volume up."),
    ("pt_prompt", "p", "pf_dora", "Explica esse erro para mim."),
    ("pt_send", "p", "pf_dora", "Pode enviar a mensagem."),
]

for name, lang, voice, text in FIXTURES:
    pipe = KPipeline(lang_code=lang)
    chunks = [audio for _, _, audio in pipe(text, voice=voice)]
    audio = np.concatenate([np.asarray(c) for c in chunks])
    pad = np.zeros(24000, dtype=np.float32)
    audio = np.concatenate([pad, audio.astype(np.float32), pad])
    sf.write(OUT / f"{name}.wav", audio, 24000, subtype="PCM_16")
    print(f"{name}.wav  {len(audio)/24000:.1f}s")
