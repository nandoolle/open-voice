"""Utilidades de áudio compartilhadas entre daemon TTS e listener."""

import sounddevice as sd


def reset_portaudio() -> None:
    """Reinicializa o PortAudio para re-enumerar dispositivos.

    Após conectar/desconectar um dispositivo (ex.: fone bluetooth), a lista
    interna do PortAudio fica obsoleta e toda abertura de stream falha com
    PaErrorCode -9986 até a lib ser terminada e inicializada de novo.
    """
    sd._terminate()
    sd._initialize()
