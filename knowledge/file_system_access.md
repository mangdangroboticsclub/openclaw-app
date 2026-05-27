# File System Access — Agent Capability

## Summary

The OpenClaw agent running on the Gateway host has **full read-only (and controlled exec) access** to the Mini Pupper robot's filesystem via the `exec` tool using `host="node"` and `node="minipupper-deepseek"`. The agent can:

- **Read any file** — using `cat`, `head`, `tail`, `less` etc.
- **List directories** — using `ls`, `find`, `stat`
- **Check file existence** — using `test -f`, `ls`, `stat`
- **Execute Python scripts** — using `python3` (with access to all robot libraries: MangDang BSP, OpenCV, etc.)
- **Run shell commands** — including compound pipelines

## What the Agent Cannot Do (natively)

- Browse the filesystem interactively (no real-time terminal UI)
- Mount additional filesystems
- Modify files unless explicitly programmed to (e.g., via `python3 -c` write operations)

## Specific File: `mini_pupper_bsp/touch_test.py`

**Actual location:** `/home/ubuntu/mini_pupper_bsp/demos/touch_test.py`
*(Not at `/home/ubuntu/mini_pupper_bsp/touch_test.py` as queried)*

**Content:** A GPIO-based test script for the Mini Pupper touch panel. It monitors 4 touch zones (Front, Back, Left, Right) using RPi.GPIO on BCM pins 6, 2, 3, 16 respectively, printing which zone is touched every 0.5 seconds.

## File System Layout (key directories)

| Path | Contents |
|------|----------|
| `/home/ubuntu/mini_pupper_bsp/` | Board Support Package — hardware libraries (LCD, GPIO, ESP32, IMU, camera) |
| `/home/ubuntu/mini_pupper_bsp/demos/` | Test/demo scripts (touch, audio, camera, IMU, servo position, display) |
| `/home/ubuntu/StanfordQuadruped/` | Robot control code (movement, gait, joystick interface) |
| `/home/ubuntu/PupperCommand/` | UDP joystick service |
| `/home/ubuntu/minipupper-app/` | App layer — scripts, custom modules, tasks.json, knowledge base |
| `/home/ubuntu/minipupper-app/scripts/` | Utility scripts (capture, display, AEC calibration) |
| `/home/ubuntu/minipupper-app/custom/` | Custom feature modules (photo analysis, pointing tracker, person follow) |
| `/home/ubuntu/apps-md-robots/` | Movement API, robot control Python files |

## How to Read a File

```python
# Via exec tool on node:
# host="node", node="minipupper-deepseek"
# cat /path/to/file
```

The agent can access, parse, and return any text file's contents.
