#!/usr/bin/env python3
"""
Touch Respond — Mini Pupper

Reads the 4-zone touch panel and performs robot actions on press.
Runs as a background daemon alongside the main operator app.

Touch zones (GPIO):
  Front (6)  → greet
  Back  (2)  → dance2
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

# Debounce: ignore rapid re-triggers within this many seconds
DEBOUNCE_S = 1.0

# Action map: (gpio_name, robot_command)
# When a touch zone goes LOW (pressed), run the corresponding command.
TOUCH_ACTIONS = {
    TOUCH_FRONT: "squat",
    TOUCH_BACK:  "disco",
    TOUCH_LEFT:  "look-left",
    TOUCH_RIGHT: "look-right",
}

# Track last press time for debounce
_last_press: dict[int, float] = {}


def run_robot(cmd: str) -> None:
    """Run a robot_control.py command."""
    try:
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
