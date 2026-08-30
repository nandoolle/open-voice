"""Original synthesized earcons, played via sounddevice on every platform.

The five cues keep the names the codebase already uses (Basso, Purr, Glass,
Frog, Blow) but the audio is generated here — sine partials, filtered noise
and exponential envelopes — so nothing OS-owned is played or shipped.
"""

import numpy as np

SR = 44100
_cache: dict[str, np.ndarray] = {}


def _t(dur: float) -> np.ndarray:
    return np.arange(int(SR * dur)) / SR


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    a = max(1, int(SR * attack))
    e = np.empty(n)
    e[:a] = np.linspace(0.0, 1.0, a)
    e[a:] = np.exp(-np.arange(n - a) / (SR * decay / 5))
    return e


def _basso() -> np.ndarray:  # dark low thud (cancelled / dictation off)
    x = _t(0.45)
    sig = (
        np.sin(2 * np.pi * 238 * x)
        + 0.8 * np.sin(2 * np.pi * 252 * x)
        + 0.5 * np.sin(2 * np.pi * 640 * x) * np.exp(-x * 18)
    )
    return sig * _env(len(x), 0.003, 0.28)


def _purr() -> np.ndarray:  # soft mid trill (cancel window open)
    x = _t(0.28)
    cluster = sum(np.sin(2 * np.pi * f * x) for f in (760, 800, 840))
    tremolo = 0.6 + 0.4 * np.sin(2 * np.pi * 25 * x)
    return cluster * tremolo * _env(len(x), 0.008, 0.16)


def _glass() -> np.ndarray:  # bright ding with a tail (message sent)
    x = _t(0.6)
    sig = (
        np.sin(2 * np.pi * 396 * x)
        + 0.35 * np.sin(2 * np.pi * 2340 * x) * np.exp(-x * 6)
        + 0.25 * np.sin(2 * np.pi * 3135 * x) * np.exp(-x * 5)
    )
    return sig * _env(len(x), 0.002, 0.45)


def _frog() -> np.ndarray:  # two rising croak pulses (utterance captured)
    def croak(dur: float, f0: float, amp: float) -> np.ndarray:
        x = _t(dur)
        noise = np.random.default_rng(7).normal(0, 1, len(x)) * np.exp(-x * 60)
        tone = np.sin(2 * np.pi * (f0 + 40 * np.exp(-x * 30)) * x)
        return amp * (0.3 * noise + tone) * _env(len(x), 0.004, dur * 0.6)

    gap = np.zeros(int(SR * 0.05))
    return np.concatenate([croak(0.09, 470, 0.6), gap, croak(0.12, 500, 1.0)])


def _blow() -> np.ndarray:  # breathy 400Hz band (mic started capturing)
    x = _t(0.5)
    noise = np.random.default_rng(3).normal(0, 1, len(x))
    spec = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    spec *= np.exp(-(((freqs - 400) / 180) ** 2))
    band = np.fft.irfft(spec, len(x))
    sig = band / np.abs(band).max() + 0.4 * np.sin(2 * np.pi * 400 * x)
    return sig * _env(len(x), 0.02, 0.35)


_SYNTHS = {"Basso": _basso, "Purr": _purr, "Glass": _glass, "Frog": _frog, "Blow": _blow}


def play(name: str) -> None:
    """Non-blocking playback of one cue; unknown names and audio errors are silent."""
    synth = _SYNTHS.get(name)
    if synth is None:
        return
    sig = _cache.get(name)
    if sig is None:
        sig = synth()
        sig = (sig / max(1e-9, float(np.abs(sig).max())) * 0.5).astype(np.float32)
        _cache[name] = sig
    try:
        import sounddevice as sd

        sd.play(sig, SR)
    except Exception:
        pass
