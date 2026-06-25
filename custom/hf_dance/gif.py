#!/usr/bin/env python3
"""
gif.py — Animated GIF player for Mini Pupper ST7789 LCD.

Usage:
    python3 gif.py <path_to.gif>            # play once, then exit
    python3 gif.py <path_to.gif> --loop      # loop forever
    python3 gif.py <path_to.gif> --fps 15    # custom framerate
    python3 gif.py stop                      # stop any running animation

Supports Ctrl+C / SIGTERM / stop flag file for clean exit.
"""

import argparse
import os
import signal
import sys
import time
from PIL import Image

STOP_FLAG = "/tmp/minipupper_gif_active"


def _show_image_on_lcd(img: Image.Image):
    """Display a PIL Image on the ST7789 LCD, resized and centered."""
    from MangDang.mini_pupper.display import Display
    d = Display()
    w, h = d.disp.width, d.disp.height
    # Convert to RGB if needed
    if img.mode != "RGB":
        img = img.convert("RGB")
    # Resize to fit while maintaining aspect ratio
    thumb = img.copy()
    thumb.thumbnail((w, h), Image.LANCZOS)
    # Flip horizontally for LCD mounting orientation
    thumb = thumb.transpose(Image.FLIP_LEFT_RIGHT)
    # Center on black background
    bg = Image.new("RGB", (w, h), (0, 0, 0))
    offset = ((w - thumb.width) // 2, (h - thumb.height) // 2)
    bg.paste(thumb, offset)
    # Save to temp and display
    tmp = "/tmp/minipupper_gif_frame.png"
    bg.save(tmp)
    d.show_image(tmp)


def stop():
    """Stop any running GIF animation."""
    try:
        if os.path.exists("/tmp/minipupper_gif_pid"):
            with open("/tmp/minipupper_gif_pid") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
    except (ValueError, ProcessLookupError, OSError):
        pass
    for f in [STOP_FLAG, "/tmp/minipupper_gif_pid"]:
        try:
            os.remove(f)
        except OSError:
            pass
    print("GIF animation stopped.")
    sys.exit(0)


def play(gif_path: str, loop: bool = False, fps: float = 10.0):
    """Play animated GIF on the LCD, frame by frame."""
    if not os.path.exists(gif_path):
        print(f"Error: {gif_path} not found")
        sys.exit(1)

    # Write PID for external stop signal
    with open("/tmp/minipupper_gif_pid", "w") as f:
        f.write(str(os.getpid()))
    # Create stop flag
    open(STOP_FLAG, "w").close()

    # Register signal handler for clean exit
    def _cleanup(sig, frame):
        _stop_internal()
    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    def _stop_internal():
        for f in [STOP_FLAG, "/tmp/minipupper_gif_pid"]:
            try:
                os.remove(f)
            except OSError:
                pass
        sys.exit(0)

    try:
        gif = Image.open(gif_path)
        frame_dur = 1.0 / fps

        frame_index = 0
        while True:
            try:
                gif.seek(frame_index)
            except EOFError:
                if loop:
                    frame_index = 0
                    gif.seek(0)
                else:
                    break

            if not os.path.exists(STOP_FLAG):
                break

            _show_image_on_lcd(gif)
            frame_index += 1

            # Use GIF's native frame duration if available, otherwise our fps
            native_dur = gif.info.get("duration", 0) / 1000.0
            sleep_dur = native_dur if native_dur > 0 else frame_dur
            time.sleep(sleep_dur)

    except KeyboardInterrupt:
        pass
    finally:
        _stop_internal()


def show(image_path: str):
    """Display a single static image on the LCD (aspect-ratio preserved, centered)."""
    if not os.path.exists(image_path):
        print(f"Error: {image_path} not found")
        sys.exit(1)
    img = Image.open(image_path)
    _show_image_on_lcd(img)
    print(f"Displayed {image_path}")


def main():
    parser = argparse.ArgumentParser(description="Play animated GIF on Mini Pupper LCD")
    parser.add_argument("command", nargs="?", help="gif path, 'stop', or 'show'")
    parser.add_argument("path", nargs="?", help="image path (for 'show' command)")
    parser.add_argument("--loop", action="store_true", help="loop forever")
    parser.add_argument("--fps", type=float, default=15.0, help="framerate (default 15)")
    args = parser.parse_args()

    if args.command == "stop":
        stop()
    elif args.command == "show":
        show(args.path)
    elif args.command:
        play(args.command, loop=args.loop, fps=args.fps)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
