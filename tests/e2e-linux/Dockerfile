# e2e Linux test: simulates a minimal user machine. Only curl + a desktop
# audio stack (PulseAudio, which a real desktop/WSLg already has) come
# preinstalled — EVERYTHING the plugin needs must come from install.sh.
FROM ubuntu:24.04

RUN apt-get update -qq && apt-get install -y -qq \
    curl ca-certificates sudo \
    pulseaudio pulseaudio-utils libasound2-plugins \
    && rm -rf /var/lib/apt/lists/*

# route ALSA (PortAudio's backend) to PulseAudio, like a desktop distro does
RUN printf 'pcm.!default pulse\nctl.!default pulse\n' > /etc/asound.conf

# non-root user with passwordless sudo — like a real dev machine; also lets
# install.sh exercise its sudo path and PulseAudio run per-user
RUN useradd -m -s /bin/bash dev && echo 'dev ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/dev

COPY open-voice /opt/open-voice
COPY test_wavs /opt/test_wavs
COPY e2e.sh /opt/e2e.sh
COPY e2e_checks.py /opt/e2e_checks.py

USER dev
WORKDIR /home/dev
ENV OPEN_VOICE_PACKAGE=/opt/open-voice
CMD ["sh", "/opt/e2e.sh"]
