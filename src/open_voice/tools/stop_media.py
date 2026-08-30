NAME = "stop_media"
DESCRIPTION = "explicitly asks to stop music/media"
EXAMPLES = ["para a música", "pare as mídias", "stop the music"]


def _press_play_pause():
    """Press the system Play/Pause media key — macOS routes it to whatever is
    Now Playing (browser video included)."""
    import Quartz
    from AppKit import NSEvent

    NX_KEYTYPE_PLAY = 16
    for down in (True, False):
        flags = 0xA00 if down else 0xB00
        data1 = (NX_KEYTYPE_PLAY << 16) | ((0x0A if down else 0x0B) << 8)
        event = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            14, (0, 0), flags, 0, 0, None, 8, data1, -1
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event.CGEvent())


def run(ctx, text):
    import sys

    if sys.platform != "darwin":
        # MPRIS covers Spotify, browsers and most Linux players
        ctx.shell("playerctl", "--all-players", "pause")
        return
    try:
        _press_play_pause()
        return
    except Exception:
        pass
    for app in ("Spotify", "Music"):
        ctx.shell("osascript", "-e", f'tell application "{app}" to pause')
