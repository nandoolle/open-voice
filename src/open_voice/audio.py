"""Audio utilities shared by the TTS daemon and the listener."""

import sounddevice as sd


def reset_portaudio() -> None:
    """Reinitialize PortAudio to re-enumerate devices.

    After a device connects/disconnects (e.g. bluetooth headset), PortAudio's
    internal device list goes stale and every stream open fails with
    PaErrorCode -9986 until the library is terminated and initialized again.
    """
    sd._terminate()
    sd._initialize()
