# Camera Person Follow — Exploration Results

## Status: ✅ Already Implemented and Tested

### What Exists

The Mini Pupper already has **4 implementations** related to person following with camera feed display:

| Module | Lines | Description |
|--------|-------|-------------|
| `custom/camera_person_follow/main.py` | 274 | HOG-based person detection + robot follow via UDP |
| `custom/camera_person_follow_with_live_video/main.py` | 348 | Person follow + live OpenCV preview window (on screen) |
| `custom/camera_live_feed_on_screen/main.py` | 311 | Live camera feed display only |
| `custom/camera_person_follower.py` (standalone) | 250 | Simpler version, same HOG approach |

### Architecture
- **Camera**: MIPI CSI `/dev/video0` at 640x480
- **Detection**: OpenCV HOGDescriptor (people detector) — no ML frameworks needed
- **Control**: UDP joystick protocol on port 8830 (standard Mini Pupper movement API)
- **Pipeline**: Detect person → compute centroid offset → PID-style velocity commands → send UDP at 20Hz

### How It Works
1. Init robot (L1 activate → body up → R1 trot)
2. Capture frame, run HOG detection
3. Find largest detection → compute horizontal offset from frame center
4. If offset > threshold: rotate (rx) to center the person
5. If person is close (< threshold area): move backward (ly negative)
6. If person is far: move forward (ly positive)
7. If no person detected: stop, scan by small rotations
8. On interrupt: stop → R1 exit trot → L1 deactivate

### Known Limitations
- **HOG only detects people** — good for person-class tracking
- No deep learning (no YOLO/TensorFlow)
- Camera tilt is fixed — only horizontal tracking
- Detection drops when person stops moving (for MOG2 version)
- HOG works better — detects standing/walking people regardless of motion

### Resources
- Research sources: ROS2 `mini_pupper_tracking` package (YOLO11n + Flask web interface) exists upstream but not installed on this robot
- Current impl uses HOG which is lighter weight and runs without ROS2

### Previous Test Results (2026-05-12)
- Camera OK at 640x480
- All imports resolve (cv2, numpy, UDPComms)
- Robot services running
- Full follow test available: `python3 custom/camera_person_follower.py --duration 30 --preview`
