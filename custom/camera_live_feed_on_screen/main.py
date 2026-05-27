#!/usr/bin/env python3
"""
Mini Pupper - Live Camera Feed on ST7789 LCD

Captures a continuous live video stream from the MIPI CSI camera
(/dev/video0) and displays it on the onboard ST7789 LCD (320x240).

Features:
- Continuous live feed at ~10-15 FPS
- Graceful shutdown on Ctrl+C, 'q' key, or timeout
- Optional duration limit
- Low-latency single-threaded loop (SPI is the bottleneck, not CPU)
- Signal-safe cleanup

Usage:
  python main.py                    # run indefinitely until Ctrl+C or 'q'
  python main.py --duration 30      # run for 30 seconds then stop
  python main.py --test             # quick 5-second test
  python main.py --record /tmp/feed.mp4  # record while displaying
"""

import argparse
import signal
import sys
import time

import cv2
from PIL import Image

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CAMERA_DEVICE = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
DISPLAY_WIDTH = 320
DISPLAY_HEIGHT = 240

_running = True

def _signal_handler(sig, frame):
    global _running
    _running = False

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

def _check_quit_key():
    if not _running:
        return True
    try:
        return cv2.waitKey(1) & 0xFF == ord('q')
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
def open_camera():
    cap = cv2.VideoCapture(CAMERA_DEVICE)
    if not cap.isOpened():
        print("ERROR: Could not open camera", file=sys.stderr)
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    # Warm up
    for _ in range(5):
        cap.read()
    return cap

def capture_frame(cap):
    ret, frame = cap.read()
    return frame if ret else None

def frame_to_display_image(frame_bgr):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(frame_rgb).resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
def get_display():
    try:
        from MangDang.mini_pupper.display import Display
        return Display()
    except (ImportError, Exception) as e:
        print(f"ERROR: Display init failed: {e}", file=sys.stderr)
        return None

def show_frame(disp, pil_img):
    try:
        disp.disp.display(pil_img)
        return True
    except Exception as e:
        print(f"WARN: Display write failed: {e}", file=sys.stderr)
        return False

# ---------------------------------------------------------------------------
# Video recording
# ---------------------------------------------------------------------------
def setup_recorder(output_path, fps=15.0):
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    if not writer.isOpened():
        print(f"WARN: Could not open video writer", file=sys.stderr)
        return None
    return writer

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run_live_feed(duration=None, record_path=None):
    global _running
    _running = True

    cap = open_camera()
    if cap is None:
        return 1

    disp = get_display()
    if disp is None:
        cap.release()
        return 1

    writer = None
    if record_path:
        writer = setup_recorder(record_path)

    start_time = time.time()
    frame_count = 0
    last_fps_report = start_time

    print("Live feed started. Press Ctrl+C or 'q' to stop.")
    if duration:
        print(f"Auto-stopping after {duration:.0f} seconds.")

    try:
        while _running:
            if duration and (time.time() - start_time) >= duration:
                break

            frame = capture_frame(cap)
            if frame is None:
                time.sleep(0.05)
                continue

            show_frame(disp, frame_to_display_image(frame))

            if writer:
                writer.write(cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT)))

            frame_count += 1

            if time.time() - last_fps_report >= 5.0:
                print(f"  ~{frame_count / 5.0:.1f} FPS, {frame_count} frames")
                last_fps_report = time.time()
                frame_count = 0

            if _check_quit_key():
                break

    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
    finally:
        cap.release()
        if writer:
            writer.release()
        try:
            show_frame(disp, Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0)))
        except Exception:
            pass
        print("Feed stopped.")

    return 0

def test_feed_quick():
    print("=== Self-Test (5 seconds) ===")

    cap = open_camera()
    if cap is None:
        print("FAIL: Camera not available")
        return 1
    frame = capture_frame(cap)
    cap.release()
    if frame is None:
        print("FAIL: Cannot capture frame")
        return 1
    print(f"  Camera: OK ({frame.shape[1]}x{frame.shape[0]})")

    if get_display() is None:
        print("  Display: NOT AVAILABLE (non-fatal)")
    else:
        print("  Display: OK")

    display_img = frame_to_display_image(frame)
    if display_img.size == (DISPLAY_WIDTH, DISPLAY_HEIGHT):
        print(f"  Image pipeline: OK ({display_img.size[0]}x{display_img.size[1]})")
    else:
        print(f"  Image pipeline: FAIL - size mismatch")
        return 1

    if run_live_feed(duration=5.0) != 0:
        print("FAIL: Feed test failed")
        return 1

    print("=== Self-Test PASSED ===")
    return 0

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Mini Pupper Live Camera Feed")
    parser.add_argument('--duration', type=float, help='Run for N seconds')
    parser.add_argument('--record', type=str, help='Record video to file')
    parser.add_argument('--test', action='store_true', help='Run 5-second test')
    args = parser.parse_args()

    if args.test:
        return test_feed_quick()
    return run_live_feed(duration=args.duration, record_path=args.record)

if __name__ == "__main__":
    sys.exit(main())