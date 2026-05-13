# Camera Person Follow with Live Video Display

Merges HOG-based person tracking with real-time ST7789 LCD video feed.

## Location
- **Implementation:** `custom/camera_person_follow_with_live_video/main.py`
- **Knowledge:** Alias for `camera_person_follow_with_live_video`

## Summary
Person following with simultaneous live video display on ST7789 LCD.
Uses OpenCV HOG people detector + PID steering controller, displayed on the onboard LCD at ~16 FPS.

## Capabilities
- OpenCV HOG people detector (CPU-based, no ML frameworks required)
- PID controller for smooth steering & speed (KP=1.2, KI=0.5, KD=0.3)
- Real-time ST7789 LCD video feed (320x240, every 2nd frame)
- ContinuousController (FPC API, direct servo control at ~66 Hz)
- Configurable follow distance, max speed, steer gain
- Person-lost handling (stops after 30 frames, exits after 60)
- Self-test mode (--test)
- Duration-limited mode (--duration N)
- No-display headless mode (--no-display)

## Hardware
- MIPI CSI camera /dev/video0, 640x480 capture
- ST7789 SPI LCD, 320x240 display
- ContinuousController (FPC API) for direct servo control

## Usage
```bash
python3 custom/camera_person_follow_with_live_video/main.py
python3 custom/camera_person_follow_with_live_video/main.py --duration 60
python3 custom/camera_person_follow_with_live_video/main.py --no-display
python3 custom/camera_person_follow_with_live_video/main.py --test
```

## Related
- `camera_person_follow` - headless person following (UDP joystick based)
- `camera_live_feed_on_screen` - LCD video feed only
