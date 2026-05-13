#!/usr/bin/env python3
"""
Mini Pupper — Person Following with Live Video Display

Combines HOG-based person tracking with real-time ST7789 LCD video feed.
Detects people via OpenCV HOG descriptor, tracks with PID steering,
and simultaneously displays the camera feed on the onboard screen.

Hardware:
  - MIPI CSI camera /dev/video0 (640x480 capture → 320x240 display)
  - ST7789 SPI LCD (320x240)
  - ContinuousController (FPC API, direct servo control)

Usage:
  python3 custom/camera_person_follow_with_live_video/main.py
  python3 custom/camera_person_follow_with_live_video/main.py --duration 60
  python3 custom/camera_person_follow_with_live_video/main.py --no-display
  python3 custom/camera_person_follow_with_live_video/main.py --test
"""

import sys
import os
import time
import signal
import argparse

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.expanduser("~/minipupper-app"))
from robot.continuous_control import ContinuousController

# ── Config ─────────────────────────────────────────────────────
CAMERA_ID = 0
CAMERA_W = 640
CAMERA_H = 480
DISPLAY_W = 320
DISPLAY_H = 240
CONTROL_DT = 0.015       # ~66 Hz on continuous_controller tick()

# Detection
HOG_WINSTRIDE = (4, 4)
HOG_PADDING = (8, 8)
HOG_SCALE = 1.05

# PID (steering)
KP_DEFAULT = 1.2
KI_DEFAULT = 0.5
KD_DEFAULT = 0.3

# Follower
MAX_SPEED_DEFAULT = 0.35
FOLLOW_DISTANCE_DEFAULT = 0.35
LOST_FRAMES_MAX = 30
LOST_FRAMES_EXIT = 60

# Display
DISPLAY_EVERY_N = 2       # Show every Nth frame (less SPI contention)

# ── Globals ────────────────────────────────────────────────────
RUNNING = True


def signal_handler(sig, frame):
    global RUNNING
    RUNNING = False


# ── Display helpers (ST7789) ───────────────────────────────────
def get_display():
    try:
        from MangDang.mini_pupper.display import Display
        return Display()
    except ImportError:
        return None
    except Exception as e:
        print(f"[follow+live] Display init failed: {e}", file=sys.stderr)
        return None


def frame_to_display_img(frame_bgr):
    """BGR frame → 320x240 RGB PIL Image."""
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb).resize((DISPLAY_W, DISPLAY_H))


def show_frame(disp, pil_img):
    try:
        disp.disp.display(pil_img)
        return True
    except Exception:
        return False


# ── Main Loop ──────────────────────────────────────────────────
def run_follow_with_live_video(
    duration=None,
    max_speed=MAX_SPEED_DEFAULT,
    steer_gain=KP_DEFAULT,
    follow_distance=FOLLOW_DISTANCE_DEFAULT,
    show_display=True,
    debug=False,
):
    global RUNNING
    RUNNING = True

    print("[follow+live] Initializing...")

    # ── Camera ──
    cap = cv2.VideoCapture(CAMERA_ID)
    if not cap.isOpened():
        print("[follow+live] ERROR: Cannot open camera", file=sys.stderr)
        return 1
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_H)
    for _ in range(5):
        cap.read()
        time.sleep(0.1)

    # ── HOG detector ──
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    # ── Display ──
    disp = None
    if show_display:
        disp = get_display()
        if disp is None:
            print("[follow+live] Display unavailable, continuing without LCD")
            show_display = False

    # ── Robot controller ──
    ctrl = ContinuousController()
    print("[follow+live] Activating robot...")
    ctrl.activate()
    print("[follow+live] Robot ready. Starting follow loop.")

    # ── PID state ──
    integral = 0.0
    prev_error = 0.0
    dt = CONTROL_DT
    lost_counter = 0
    frame_count = 0
    start_time = time.time()

    # ── Main loop ──
    while RUNNING:
        # Check duration
        if duration and (time.time() - start_time) >= duration:
            print(f"[follow+live] Duration reached ({duration}s). Stopping.")
            break

        # Capture
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue
        frame_count += 1
        h, w = frame.shape[:2]

        # ── Detect people (HOG on half-resolution) ──
        scale = 0.5
        small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        sh, sw = small.shape[:2]

        (rects, _weights) = hog.detectMultiScale(
            small, winStride=HOG_WINSTRIDE, padding=HOG_PADDING, scale=HOG_SCALE
        )

        # Pick largest person
        best_rect = None
        best_area = 0
        for (x, y, rw, rh) in rects:
            area = rw * rh
            if area > best_area:
                best_area = area
                best_rect = (x, y, rw, rh)

        if best_rect is not None:
            lost_counter = 0
            bx, by, bw, bh = best_rect

            # Normalize
            cx = (bx + bw / 2) / sw   # 0=left, 1=right
            cy = (by + bh / 2) / sh   # 0=top, 1=bottom
            person_height_ratio = bh / sh

            # Steering PID
            error_x = cx - 0.5
            integral += error_x * dt
            integral = np.clip(integral, -0.5, 0.5)
            derivative = (error_x - prev_error) / dt if dt > 0 else 0
            steer_cmd = steer_gain * error_x + KI_DEFAULT * integral + KD_DEFAULT * derivative
            steer_cmd = np.clip(steer_cmd, -1.0, 1.0)
            prev_error = error_x

            # Forward/back (person height = distance proxy)
            dist_error = -(person_height_ratio - follow_distance)
            forward_cmd = np.clip(dist_error * 1.5, -max_speed, max_speed)

            # Apply control
            # vx=ly (forward), vy=steer (lateral)
            ctrl.set_velocity(vx=forward_cmd, vy=0)
            ctrl.set_yaw_rate(rate=-steer_cmd * 1.5)  # steer via yaw

            # Log every 20 frames
            if frame_count % 20 == 0:
                print(
                    f"[follow+live] Person at ({cx:.2f},{cy:.2f}) "
                    f"ht={person_height_ratio:.2f} "
                    f"fwd={forward_cmd:.2f} steer={steer_cmd:.2f}"
                )

            # Draw bounding box on display frame (scaled up)
            if show_display and frame_count % DISPLAY_EVERY_N == 0:
                fx, fy, fw, fh = [int(v / scale) for v in (bx, by, bw, bh)]
                cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (0, 255, 0), 2)
                cv2.putText(
                    frame,
                    f"fwd={forward_cmd:.2f}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
                )

        else:
            lost_counter += 1
            if lost_counter >= LOST_FRAMES_MAX:
                ctrl.stop()
                if lost_counter == LOST_FRAMES_MAX:
                    print(f"[follow+live] Person lost. Stopped.")
                if lost_counter >= LOST_FRAMES_EXIT:
                    print("[follow+live] Person not found. Exiting.")
                    break
            elif lost_counter == 1:
                ctrl.stop()

        # ── Advance control tick ──
        ctrl.tick()

        # ── Display frame (every Nth frame to reduce SPI load) ──
        if show_display and frame_count % DISPLAY_EVERY_N == 0:
            disp_img = frame_to_display_img(frame)
            show_frame(disp, disp_img)

    # ── Cleanup ──
    print("[follow+live] Stopping robot...")
    ctrl.stop()
    ctrl.deactivate()

    cap.release()

    # Clear display
    if disp:
        try:
            blank = Image.new("RGB", (DISPLAY_W, DISPLAY_H), (0, 0, 0))
            show_frame(disp, blank)
        except Exception:
            pass

    print(f"[follow+live] Done. {frame_count} frames processed.")
    return 0


def test():
    """
    Quick self-test: verify camera, display, and a short 8-second run.
    """
    print("=== Person Follow + Live Video Self-Test ===")

    # 1. Camera
    cap = cv2.VideoCapture(CAMERA_ID)
    if not cap.isOpened():
        print("FAIL: Camera not available")
        return 1
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        print("FAIL: Cannot capture frame")
        return 1
    print(f"  Camera: OK ({frame.shape[1]}x{frame.shape[0]})")

    # 2. Display
    disp = get_display()
    if disp:
        print("  Display: OK (module loaded)")
    else:
        print("  Display: N/A (headless mode)")

    # 3. Image pipeline
    img = frame_to_display_img(frame)
    assert img.size == (DISPLAY_W, DISPLAY_H), f"Size mismatch: {img.size}"
    print(f"  Image pipeline: OK ({img.size[0]}x{img.size[1]})")

    # 4. HOG
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    print(f"  HOG detector: OK ({hog.getDescriptorSize()} features)")

    # 5. Short run (8s with display)
    print("  Running 8-second follow+live test...")
    ret = run_follow_with_live_video(duration=8, show_display=True)
    if ret != 0:
        print(f"FAIL: run returned {ret}")
        return 1
    print("  Short run: OK")

    print("=== Self-test PASSED ===")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Mini Pupper — Person Following with Live Video Display"
    )
    parser.add_argument("--duration", type=float, default=None,
                        help="Run for N seconds (default: unlimited)")
    parser.add_argument("--max-speed", type=float, default=MAX_SPEED_DEFAULT,
                        help=f"Max forward speed (0-1, default {MAX_SPEED_DEFAULT})")
    parser.add_argument("--steer-gain", type=float, default=KP_DEFAULT,
                        help=f"Steering PID gain (default {KP_DEFAULT})")
    parser.add_argument("--follow-distance", type=float, default=FOLLOW_DISTANCE_DEFAULT,
                        help=f"Target person height ratio (default {FOLLOW_DISTANCE_DEFAULT})")
    parser.add_argument("--no-display", action="store_true",
                        help="Skip LCD display output (headless follow only)")
    parser.add_argument("--test", action="store_true",
                        help="Run quick self-test")
    parser.add_argument("--debug", action="store_true",
                        help="Verbose debug output")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.test:
        return test()

    return run_follow_with_live_video(
        duration=args.duration,
        max_speed=args.max_speed,
        steer_gain=args.steer_gain,
        follow_distance=args.follow_distance,
        show_display=not args.no_display,
        debug=args.debug,
    )


if __name__ == "__main__":
    sys.exit(main())
