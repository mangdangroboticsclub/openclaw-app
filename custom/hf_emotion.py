#!/usr/bin/env python3
"""
hf_emotion.py — Face Emotion Detection via Hugging Face Inference API

Captures a photo from the camera, sends it to Hugging Face's
Inference API using dima806/facial_emotions_image_detection,
and returns detected emotions with confidence scores.

Usage:
    python3 custom/hf_emotion.py                          # capture + analyze
    python3 custom/hf_emotion.py --file /tmp/photo.jpg    # analyze existing image
    python3 custom/hf_emotion.py --save /tmp/result.json  # save result to file
    python3 custom/hf_emotion.py --token hf_xxxx          # HF API token

Output (stdout): JSON
    {
        "ok": true,
        "emotions": [
            {"label": "happy", "score": 0.953},
            {"label": "neutral", "score": 0.032},
            ...
        ],
        "dominant_emotion": "happy",
        "top_score": 0.953,
        "face_detected": true
    }

Environment variable:
    HF_TOKEN — Hugging Face API token (or pass via --token)
    Get one at: https://huggingface.co/settings/tokens
"""

import argparse
import json
import os
import sys
import time

import cv2
import requests

# -- Config -----------------------------------------------------------

MODEL = "dima806/facial_emotions_image_detection"
API_URL = f"https://router.huggingface.co/hf-inference/models/{MODEL}"


# -- Camera -----------------------------------------------------------

def capture_photo(output_path=None) -> bytes:
    """Capture a photo from the MIPI camera at /dev/video0.

    Returns raw JPEG bytes, or exits on failure.
    If output_path is given, also saves the file.
    """
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print(json.dumps({"ok": False, "error": "Could not open camera /dev/video0"}))
        sys.exit(1)

    time.sleep(0.5)  # Camera warm-up

    for attempt in range(3):
        ret, frame = cap.read()
        if ret and frame is not None:
            break
        time.sleep(0.2)
    else:
        cap.release()
        print(json.dumps({"ok": False, "error": "Failed to capture frame after 3 attempts"}))
        sys.exit(1)

    cap.release()

    # Encode as JPEG
    ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ret:
        print(json.dumps({"ok": False, "error": "Failed to encode JPEG"}))
        sys.exit(1)

    if output_path:
        with open(output_path, "wb") as f:
            f.write(jpeg.tobytes())

    return jpeg.tobytes()



# -- Display -------------------------------------------------------------

def show_on_display(image_path: str):
    """Display an image on the ST7789 LCD screen."""
    try:
        from PIL import Image
        from MangDang.mini_pupper.display import Display
        img = Image.open(image_path)
        disp = Display()
        display_img = img.resize((320, 240))
        disp.disp.display(display_img)
        return True
    except ImportError:
        return False
    except Exception as e:
        if 'capture_photo' in dir():
            pass  # silent
        return False


# -- Hugging Face API ------------------------------------------------

def analyze_emotion(image_bytes: bytes, token: str) -> dict:
    """Send image to HF Inference API and return emotion predictions.

    Returns:
        dict with "ok" and either "emotions" list or "error".
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"}

    try:
        response = requests.post(
            API_URL,
            headers=headers,
            data=image_bytes,
            timeout=30,
        )
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "HF API request timed out after 30s"}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "Could not connect to HF API"}
    except Exception as e:
        return {"ok": False, "error": f"Request failed: {str(e)}"}

    if response.status_code == 401:
        return {"ok": False, "error": "Invalid HF token. Get one at https://huggingface.co/settings/tokens"}
    elif response.status_code == 503:
        return {"ok": False, "error": "HF model is loading (cold start). Try again in a few seconds."}
    elif response.status_code != 200:
        return {"ok": False, "error": f"HF API returned {response.status_code}: {response.text[:200]}"}

    try:
        data = response.json()
    except json.JSONDecodeError:
        return {"ok": False, "error": "HF returned invalid JSON"}

    # The model returns a list of lists: [[{"label": "happy", "score": 0.95}, ...]]
    # Each inner list is per detected face
    if not isinstance(data, list) or len(data) == 0:
        return {"ok": False, "error": "No face detected in the image", "face_detected": False}

    # Take the first face's results (most prominent face)
    emotions = data[0] if isinstance(data[0], list) else data

    # Sort by score descending
    emotions = sorted(emotions, key=lambda x: x.get("score", 0), reverse=True)

    return {
        "ok": True,
        "emotions": emotions,
        "dominant_emotion": emotions[0]["label"] if emotions else "unknown",
        "top_score": emotions[0]["score"] if emotions else 0,
        "face_detected": True,
    }


# -- CLI ---------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Face Emotion Detection via Hugging Face"
    )
    parser.add_argument("--file", help="Path to existing image file (skip camera capture)")
    parser.add_argument("--save", help="Save result JSON to file")
    parser.add_argument("--token", help="Hugging Face API token (or set HF_TOKEN env var)")

    args = parser.parse_args()

    # Get API token
    token = args.token or os.environ.get("HF_TOKEN")
    if not token:
        print(json.dumps({
            "ok": False,
            "error": "No HF token provided. Use --token or set HF_TOKEN env var. "
                     "Get one at: https://huggingface.co/settings/tokens"
        }))
        sys.exit(1)

    # Capture or load image
    if args.file:
        try:
            with open(args.file, "rb") as f:
                image_bytes = f.read()
        except OSError as e:
            print(json.dumps({"ok": False, "error": f"Cannot read file: {e}"}))
            sys.exit(1)
    else:
        image_bytes = capture_photo(output_path=args.save)
        # Display captured photo on LCD
        display_path = args.save or "/tmp/emotion_photo.jpg"
        if not args.save:
            try:
                with open(display_path, "wb") as f:
                    f.write(image_bytes)
            except OSError:
                pass
        show_on_display(display_path)

    # Analyze
    result = analyze_emotion(image_bytes, token)

    # Output
    output = json.dumps(result, indent=2)
    print(output)

    # Save if requested
    if args.save and not args.file:
        pass  # already saved via capture_photo
    elif args.save and result.get("ok"):
        try:
            with open(args.save, "w") as f:
                f.write(output)
        except OSError:
            pass

    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
