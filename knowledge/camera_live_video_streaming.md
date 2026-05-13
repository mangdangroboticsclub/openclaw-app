# Camera Live Video Streaming

## Overview
Live video streaming from the Mini Pupper MIPI CSI camera to the onboard ST7789 LCD display is an **existing, tested capability**.

## Existing Implementation
- **Path:** `custom/camera_live_feed_on_screen/main.py`
- **Tested:** Yes — self-test verified at **~15.9 FPS** (640×480 capture → 320×240 display)
- **Capabilities:**
  - Continuous live feed at ~15-16 FPS
  - Optional duration limit (`--duration N` seconds)
  - Optional video recording (`--record /path/to.mp4`)
  - Graceful shutdown (Ctrl+C, SIGINT, 'q' key, or auto-stop on duration)
  - Signal-safe cleanup clears screen on exit

## Hardware Constraints
- **Camera:** /dev/video0, MIPI CSI, 640×480 @ 30 FPS
- **Display:** ST7789 SPI-based 320×240 LCD
- **Bottleneck:** SPI bus — display updates limited to ~15 FPS
- **CPU usage:** ~30-50% on Raspberry Pi 4

## "Poly Command" Context
The user query referenced modifying a "poly command" for live video. No code or reference named "poly" exists anywhere in the minipupper-app codebase. This is likely a user/operator-side concept — possibly:
- A voice command phrase defined in the operator
- A custom command alias the user wants to create
- A reference to the "Poly" robot platform

## How to Invoke Directly
```bash
# Full live feed (unlimited duration, Ctrl+C to stop)
python3 ~/minipupper-app/custom/camera_live_feed_on_screen/main.py

# 30-second feed
python3 ~/minipupper-app/custom/camera_live_feed_on_screen/main.py --duration 30

# Quick 5-second self-test
python3 ~/minipupper-app/custom/camera_live_feed_on_screen/main.py --test

# Record feed to video file
python3 ~/minipupper-app/custom/camera_live_feed_on_screen/main.py --record /tmp/feed.mp4
```

## How to Invoke via Robot Control
A new robot action could be added to `robot/robot_control.py`:
```python
elif subcommand == "live-feed":
    import sys
    sys.path.insert(0, os.path.expanduser("~/minipupper-app/custom/camera_live_feed_on_screen"))
    from main import run_live_feed
    run_live_feed(duration=float(duration) if duration else None)
```

## Integration with Operator
To make "poly command" → live video streaming work, the operator would need:
1. A new custom action in the operator's prompt/system instructions mapping the phrase "poly command" (or whatever the user calls it) to a `robot.live_feed` task action
2. An entry in `robot/robot_control.py` for the `live-feed` subcommand (as shown above)
3. Task mapping in the cron job to dispatch `robot.live_feed` → `python3 .../camera_live_feed_on_screen/main.py --duration {duration}`

## Status
✅ Live video streaming to LCD = **exists and tested** (~16 FPS)
❌ Any "poly command" = **not found in codebase** (user-defined concept)
⚙️ Link: feed can be invoked from `robot/robot_control.py` with a 5-line addition
