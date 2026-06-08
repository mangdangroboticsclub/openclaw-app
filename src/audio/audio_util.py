"""Shared audio utility — robust ALSA control detection."""

import subprocess
import time

_CACHED_CARD: str | None = None
_CACHED_AT: float = 0
_CACHE_TTL = 60  # re-check every 60s


def _find_headphone_card() -> str:
    """Return the amixer card flag (e.g. '-c 0' or '') for the card
    that has a 'Headphone' playback control.

    Cached for _CACHE_TTL seconds to avoid hammering amixer.
    """
    global _CACHED_CARD, _CACHED_AT
    now = time.monotonic()
    if _CACHED_CARD is not None and now - _CACHED_AT < _CACHE_TTL:
        return _CACHED_CARD

    for card in ("", "-c 0", "-c 1"):
        try:
            args = ["amixer"]
            if card:
                args.extend(card.split())
            args.append("scontrols")
            r = subprocess.run(args, capture_output=True, text=True, timeout=3)
            if "'Headphone'" in r.stdout:
                _CACHED_CARD = card
                _CACHED_AT = now
                return card
        except Exception:
            continue

    _CACHED_CARD = ""
    _CACHED_AT = now
    return ""


def set_volume(pct: str) -> bool:
    """Set Headphone volume to pct (e.g. '85%', '0%'). Returns True on success."""
    card_flag = _find_headphone_card()
    try:
        args = ["amixer"]
        if card_flag:
            args.extend(card_flag.split())
        args.extend(["sset", "Headphone", pct])
        r = subprocess.run(args, capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


def get_current_volume() -> str:
    """Parse the current Headphone volume percentage (e.g. '85%'). Returns '85%' on failure."""
    card_flag = _find_headphone_card()
    try:
        args = ["amixer"]
        if card_flag:
            args.extend(card_flag.split())
        args.append("sget")
        args.append("Headphone")
        r = subprocess.run(args, capture_output=True, text=True, timeout=3)
        for line in r.stdout.splitlines():
            if "Mono:" in line and "Playback" in line:
                for part in line.split():
                    if part.endswith("%"):
                        return part
    except Exception:
        pass
    return "85%"


def set_mute(muted: bool) -> bool:
    """Mute (off) or unmute (on) the Headphone switch."""
    card_flag = _find_headphone_card()
    state = "off" if muted else "on"
    try:
        args = ["amixer"]
        if card_flag:
            args.extend(card_flag.split())
        args.extend(["sset", "Headphone", state])
        r = subprocess.run(args, capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False
