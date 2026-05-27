#!/usr/bin/env python3
"""
look_here.py — Mini Pupper Gesture Following


Captures 3 photos (1s apart), shows each on the LCD screen,
analyzes each for hand-pointing direction (left/right/up/down/fingergun_forward),
and moves the robot's gaze accordingly in sequence.


Usage:
    python3 custom/look_here.py                     # normal run
    python3 custom/look_here.py --json              # JSON output for agent
    python3 custom/look_here.py --test              # camera + Gemini self-test
"""


import argparse
import json
import os
import sys
import time
import io
import subprocess


import cv2
import vertexai
from PIL import Image
from vertexai.generative_models import GenerativeModel, Part, SafetySetting




# ── Config ─────────────────────────────────────────────────────


NUM_CAPTURES = 3
CAPTURE_INTERVAL = 1.0  # seconds
GEMINI_MODEL = "gemini-2.5-flash"
SAVE_DIR = "/tmp/look_here_captures"


# Service account key (same one used by calorie_calculator.py)
SA_KEY = "/home/ubuntu/apps-md-robots/20250923.json"
GCP_PROJECT = "modern-rex-420404"


POINTING_PROMPT = (
  "The user is making a hand gesture toward you (the camera).\n"
  "Reply with exactly ONE word from this list:\n"
  "- fingergun_forward: thumb up with index finger pointing towards / straight to the camera\n"
  "- up: hand/gesture pointing upward (any gesture)\n"
  "- down: hand/gesture pointing downward (any gesture)\n"
  "- left: hand/gesture pointing to viewer's left (any gesture - hand sideways, parallel to camera)\n"
  "- right: hand/gesture pointing to viewer's right (any gesture - hand sideways, parallel to camera)\n"
  "- none: no hand or unclear gesture\n"
  "\n"
  "RULES:\n"
  "1. A fingergun pointing left/right/up/down \u2192 output that direction (left/right/up/down), NOT fingergun_forward\n"
  "2. 'fingergun_forward' ONLY for a fingergun pointed directly at the camera lens (not sideways)\n"
  "3. Regular pointing hand (no fingergun) \u2192 output the direction\n"
  "Do NOT explain. Just one word."
)


# Reuseable safety settings for Gemini calls (avoids reallocating each call)
SAFETY_SETTINGS = [
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    SafetySetting(
        category=SafetySetting.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=SafetySetting.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
]





# ── Display ────────────────────────────────────────────────────


def show_on_lcd(image):
    """Display a PIL Image on the ST7789 LCD screen (320x240)."""
    try:
        from MangDang.mini_pupper.display import Display
        disp = Display()
        display_img = image.resize((320, 240))
        disp.disp.display(display_img)
        return True
    except ImportError:
        print("WARN: LCD display module not available", file=sys.stderr)
        return False
    except Exception as e:
        print(f"WARN: LCD display failed: {e}", file=sys.stderr)
        return False




# ── Camera ─────────────────────────────────────────────────────


def capture_photo(output_path=None):
    """Capture a photo from the MIPI camera at /dev/video0.


    Returns:
        PIL Image (RGB), or None on failure.
    """
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open camera /dev/video0", file=sys.stderr)
        return None


    time.sleep(0.5)


    for attempt in range(3):
        ret, frame = cap.read()
        if ret and frame is not None:
            break
        time.sleep(0.2)
    else:
        cap.release()
        print("ERROR: Failed to capture frame after 3 attempts", file=sys.stderr)
        return None


    cap.release()


    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(frame_rgb)


    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        pil_img.save(output_path, quality=90)
        print(f"Photo saved to {output_path}")


    return pil_img




# ── Gemini Vision ──────────────────────────────────────────────


def _init_vertex():
    """Initialize Vertex AI with the service account key."""
    if not os.path.exists(SA_KEY):
        print(f"ERROR: Service account key not found: {SA_KEY}", file=sys.stderr)
        return False
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SA_KEY
    vertexai.init(project=GCP_PROJECT, location="us-central1")
    return True




def analyze_direction(image, model_name=None):
    """Analyze a single image for hand-pointing direction.


    Returns:
        One of: "LEFT", "RIGHT", "UP", "DOWN", "FINGERGUN_FORWARD", "NONE", "ERROR"
    """
    if not _init_vertex():
        return "ERROR"


    model = GenerativeModel(model_name or GEMINI_MODEL)


    
    img_bytes = io.BytesIO()
    image.save(img_bytes, format="JPEG", quality=85)
    img_data = img_bytes.getvalue()


    # Use module-level SAFETY_SETTINGS to avoid reallocating this list each call


    image_part = Part.from_data(mime_type="image/jpeg", data=img_data)


    try:
        response = model.generate_content(
            [POINTING_PROMPT, image_part],
            safety_settings=SAFETY_SETTINGS,
        )
        text = response.text.strip().upper()
        for direction in ("LEFT", "RIGHT", "UP", "DOWN", "FINGERGUN_FORWARD"):
            if direction in text:
                return direction
        return "NONE"
    except Exception as e:
        print(f"ERROR: Gemini analysis failed: {e}", file=sys.stderr)
        return "ERROR"




# ── Robot Movement ─────────────────────────────────────────────


def move_gaze(direction, index):
    """Move robot gaze in the given direction."""
    cmd_map = {
        "LEFT": "look-left",
        "RIGHT": "look-right",
        "UP": "look-up",
        "DOWN": "look-down",
        
        "FINGERGUN_FORWARD": "fall",
    }


    cmd = cmd_map.get(direction)
    if not cmd:
        print(f"  capture #{index + 1}: '{direction}' \u2192 no movement needed")
        return True


    print(f"  capture #{index + 1}: '{direction}' \u2192 robot {cmd}")
    proc = subprocess.run([sys.executable, "/home/ubuntu/minipupper-app/robot/robot_control.py", cmd])
    if proc.returncode != 0:
        print(f"ERROR: robot control '{cmd}' returned {proc.returncode}", file=sys.stderr)
        return False
    return True




# ── Main ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Mini Pupper Gesture Following \u2014 look where the hand points"
    )
    parser.add_argument("--json", action="store_true",
                        help="Output result as JSON (for agent integration)")
    parser.add_argument("--test", action="store_true",
                        help="Run self-test: capture + Gemini only, no movement")
    parser.add_argument("--no-display", action="store_true",
                        help="Skip showing captures on the LCD screen")
    args = parser.parse_args()


    # ── Phase 1: Capture 3 photos ──
    os.makedirs(SAVE_DIR, exist_ok=True)


    print(f"Capturing {NUM_CAPTURES} photos ({CAPTURE_INTERVAL}s apart)...")
    photos = []
    for i in range(NUM_CAPTURES):
        if i > 0:
            print(f"  Waiting {CAPTURE_INTERVAL}s before capture #{i+1}...")
            time.sleep(CAPTURE_INTERVAL)


        path = os.path.join(SAVE_DIR, f"capture_{i+1}.jpg")
        img = capture_photo(path)
        if img is None:
            print(f"ERROR: Failed capture #{i+1}", file=sys.stderr)
            if args.json:
                result = {
                    "status": "error",
                    "summary": "Camera capture failed during capture sequence.",
                    "error": f"Failed to capture photo #{i+1}",
                }
                print(json.dumps(result, indent=2))
            return 1
        photos.append(img)


        # Display each capture on LCD right after it's taken
        if not args.no_display:
            print(f"  Displaying capture #{i+1} on LCD...")
            show_on_lcd(img)
            # Hold the image on screen for the interval between captures
            # Hold last capture a bit longer so the user can see it
            if i >= NUM_CAPTURES - 1:
                time.sleep(2.0)


    if args.test:
        print(f"\nCaptured {len(photos)} photos successfully. Testing Gemini analysis...")


    # ── Phase 2: Analyze each photo ──
    print("\nAnalyzing photos for hand-pointing directions...")
    directions = []
    for i, img in enumerate(photos):
        direction = analyze_direction(img)
        directions.append(direction)
        print(f"  capture #{i+1}: {direction}")


    if args.test:
        summary_parts = []
        for i, d in enumerate(directions):
            if d in ("LEFT", "RIGHT", "UP", "DOWN", "FINGERGUN_FORWARD"):
                summary_parts.append(f"Capture {i+1}: hand pointing {d}")
            else:
                summary_parts.append(f"Capture {i+1}: no clear hand direction")
        summary = ". ".join(summary_parts)
        result = {
            "status": "success",
            "test_mode": True,
            "captures": 3,
            "directions": directions,
            "summary": summary + " (test mode, no movement executed).",
        }
        print(json.dumps(result, indent=2))
        return 0


    # ── Phase 3: Move robot ──
    print("\nMoving robot to follow detected hand directions...")
    movements_made = []
    for i, direction in enumerate(directions):
        if direction in ("LEFT", "RIGHT", "UP", "DOWN", "FINGERGUN_FORWARD"):
            ok = move_gaze(direction, i)
            movements_made.append({
                "capture": i + 1,
                "direction": direction,
                "success": ok,
            })
            time.sleep(0.3)
        else:
            movements_made.append({
                "capture": i + 1,
                "direction": direction,
                "success": True,
                "note": "No hand detected or unclear",
            })


    # ── Summary ──
    print(f"\n{'='*50}")
    print("GESTURE FOLLOWING COMPLETE")
    print(f"{'='*50}")
    summary_parts = []
    for m in movements_made:
        if m["direction"] in ("LEFT", "RIGHT", "UP", "DOWN", "FINGERGUN_FORWARD"):
            summary_parts.append(
                f"Capture {m['capture']}: hand pointing {m['direction']} \u2192 looked {m['direction'].lower()}"
            )
        else:
            summary_parts.append(f"Capture {m['capture']}: no hand detected")
    summary = ". ".join(summary_parts)


    if args.json:
        result = {
            "status": "success",
            "captures": [
                {
                    "index": i + 1,
                    "file": os.path.join(SAVE_DIR, f"capture_{i+1}.jpg"),
                    "direction": directions[i],
                }
                for i in range(len(photos))
            ],
            "movements": movements_made,
            "summary": summary,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"\nSummary: {summary}")


    return 0




if __name__ == "__main__":
    sys.exit(main())