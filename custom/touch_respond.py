#!/usr/bin/env python3
"""
Touch Respond — Mini Pupper

Reads the 4-zone touch panel and performs robot actions on press.
Runs as a background daemon alongside the main operator app.

Touch zones (GPIO):
  Front (6)  → squat
  Back  (2)  → toggle mute (0% / restore)
  Left  (3)  → look left
  Right (16) → look right

Usage:
    python3 custom/touch_respond.py              # foreground
    python3 custom/touch_respond.py --daemon     # background (nohup)
"""

import os
import subprocess
import sys
import time

import RPi.GPIO as GPIO

# GPIO mapping
TOUCH_FRONT = 6
TOUCH_LEFT  = 3
TOUCH_RIGHT = 16
TOUCH_BACK  = 2

# Robot control script
ROBOT_CTRL = os.path.expanduser("~/minipupper-app/robot/robot_control.py")

# File used to store previous volume before muting (mute toggle state)
MUTE_STATE_FILE = os.path.expanduser("~/.local/state/touch_aec_mute")

# Debounce: ignore rapid re-triggers within this many seconds
DEBOUNCE_S = 1.0

# Action map: (gpio_name, action_command)
TOUCH_ACTIONS = {
    TOUCH_FRONT: "squat",
    TOUCH_BACK:  "aec_mute",
    TOUCH_LEFT:  "look-left",
    TOUCH_RIGHT: "look-right",
}

# Track last press time for debounce
_last_press: dict[int, float] = {}


def _ensure_audio_util():
    """Import audio_util, inserting path if needed."""
    if "audio_util" not in sys.modules:
        sys.path.insert(0, "/home/ubuntu/minipupper-app")
    from src.audio.audio_util import get_current_volume, set_volume, set_mute
    return get_current_volume, set_volume, set_mute


def toggle_mute() -> str:
    """Toggle speaker mute: mute to 0% or restore previous volume."""
    get_vol, set_vol, mute = _ensure_audio_util()

    muted = os.path.exists(MUTE_STATE_FILE)
    if muted:
        # Unmute — restore saved level
        try:
            with open(MUTE_STATE_FILE) as f:
                pct = f.read().strip() or "98%"
        except Exception:
            pct = "98%"
        os.remove(MUTE_STATE_FILE)
        set_vol(pct)
        mute(False)
        return f"Unmuted -> {pct}"
    else:
        # Mute — save current level, then set to 0%
        current = get_vol()
        os.makedirs(os.path.dirname(MUTE_STATE_FILE), exist_ok=True)
        with open(MUTE_STATE_FILE, "w") as f:
            f.write(current)
        set_vol("0%")
        mute(True)
        return f"Muted (was {current})"


def run_robot(cmd: str) -> None:
    """Run a robot_control.py command or handle special actions."""
    try:
        if cmd == "aec_mute":
            result = toggle_mute()
            print(f"[touch_respond] {result}")
            return
        subprocess.run(
            [sys.executable, ROBOT_CTRL, cmd], timeout=10,
        )
    except Exception:
        pass


def main():
    GPIO.setmode(GPIO.BCM)
    for pin in (TOUCH_FRONT, TOUCH_LEFT, TOUCH_RIGHT, TOUCH_BACK):
        GPIO.setup(pin, GPIO.IN)

    # Initial state: read all pins once
    prev = {pin: GPIO.input(pin) for pin in TOUCH_ACTIONS}

    while True:
        for pin, cmd in TOUCH_ACTIONS.items():
            val = GPIO.input(pin)
            now = time.time()
            # Detect falling edge: was HIGH, now LOW (touch pressed)
            if prev[pin] == GPIO.HIGH and val == GPIO.LOW:
                # Debounce
                last = _last_press.get(pin, 0.0)
                if now - last >= DEBOUNCE_S:
                    _last_press[pin] = now
                    run_robot(cmd)
            prev[pin] = val
        time.sleep(0.05)  # 50ms poll


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        pid = os.fork()
        if pid > 0:
            print(f"Touch responder started (PID {pid})")
            sys.exit(0)
    try:
        main()
    except KeyboardInterrupt:
        GPIO.cleanup()
    except Exception:
        GPIO.cleanup()
