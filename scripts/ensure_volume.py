#!/usr/bin/env python3
"""
Boot-time failsafe: ensure speaker volume is set to 85%.

Runs as a systemd oneshot before the operator app starts.
Uses audio_util to auto-detect the correct ALSA card.
"""
import sys
sys.path.insert(0, "/home/ubuntu/minipupper-app")
from src.audio.audio_util import set_volume, set_mute

ok_vol = set_volume("85%")
ok_mute = set_mute(False)
print(f"Volume set to 85%: {ok_vol}, Mute off: {ok_mute}")
sys.exit(0 if ok_vol else 1)
