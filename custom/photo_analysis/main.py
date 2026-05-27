#!/usr/bin/env python3
"""
Photo Analysis Module — Mini Pupper

Captures a photo from the MIPI CSI camera and analyzes it using
Gemini 2.5 Flash (Vertex AI) vision capabilities.

Usage:
    python3 main.py                              # capture + analyze
    python3 main.py --file /tmp/photo.jpg        # analyze existing image
    python3 main.py --prompt "What do you see?"  # custom prompt
    python3 main.py --save /tmp/analysis.txt     # save analysis to file
"""

import argparse
import json
import os
import sys
import time
import cv2
from PIL import Image
import io
import vertexai
from vertexai.generative_models import GenerativeModel, Part, SafetySetting


# ── Config ─────────────────────────────────────────────────────

DEFAULT_PROMPT = "Describe this image in detail. What objects, people, text, colors, and environment do you see?"
DEFAULT_MODEL = "gemini-2.5-flash"


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

    # Let camera warm up
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

    # BGR to RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(frame_rgb)

    if output_path:
        pil_img.save(output_path)
        print(f"Photo saved to {output_path}")

    return pil_img


def load_image(image_path):
    """Load an existing image file as PIL Image (RGB)."""
    try:
        pil_img = Image.open(image_path).convert("RGB")
        return pil_img
    except Exception as e:
        print(f"ERROR: Could not open {image_path}: {e}", file=sys.stderr)
        return None


# ── Gemini Vision ──────────────────────────────────────────────

def _get_project_id():
    """Get GCP project ID from env."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    if project:
        return project
    # Fallback: try reading from ADC
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if creds_path and os.path.exists(creds_path):
        with open(creds_path) as f:
            data = json.load(f)
        return data.get("project_id")
    return None


def _init_vertex():
    """Initialize Vertex AI SDK."""
    project = _get_project_id()
    if not project:
        print("ERROR: GOOGLE_CLOUD_PROJECT_ID not set and service account not found", file=sys.stderr)
        return False
    vertexai.init(project=project, location="us-central1")
    return True


def analyze_image(image, prompt=None, model_name=None):
    """Send an image to Gemini for analysis.
    
    Args:
        image: PIL Image (RGB)
        prompt: Optional custom prompt string
        model_name: Optional model name override
        
    Returns:
        Analysis text string, or None on failure.
    """
    if not _init_vertex():
        return None

    model = GenerativeModel(model_name or DEFAULT_MODEL)

    # Convert PIL image to JPEG bytes
    img_bytes = io.BytesIO()
    image.save(img_bytes, format="JPEG", quality=85)
    img_data = img_bytes.getvalue()

    prompt_text = prompt or DEFAULT_PROMPT

    safety_settings = [
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

    image_part = Part.from_data(
        mime_type="image/jpeg",
        data=img_data,
    )

    try:
        response = model.generate_content(
            [prompt_text, image_part],
            safety_settings=safety_settings,
        )
        return response.text
    except Exception as e:
        print(f"ERROR: Gemini vision analysis failed: {e}", file=sys.stderr)
        return None


# ── Display (Optional) ─────────────────────────────────────────

def show_on_display(image):
    """Show image on ST7789 LCD (if available)."""
    try:
        from MangDang.mini_pupper.display import Display
        disp = Display()
        display_img = image.resize((320, 240))
        disp.disp.display(display_img)
        return True
    except ImportError:
        return False
    except Exception as e:
        print(f"WARN: Display failed: {e}", file=sys.stderr)
        return False


# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mini Pupper Photo Analysis")
    parser.add_argument("--file", type=str, default=None,
                        help="Analyze an existing image file instead of capturing")
    parser.add_argument("--prompt", type=str, default=None,
                        help="Custom analysis prompt (default: detailed scene description)")
    parser.add_argument("--save", type=str, default=None,
                        help="Save analysis result to a text file")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help=f"Gemini model (default: {DEFAULT_MODEL})")
    parser.add_argument("--display", action="store_true",
                        help="Show the captured/loaded image on the LCD screen")
    parser.add_argument("--json", action="store_true",
                        help="Output result as JSON")
    parser.add_argument("--test", action="store_true",
                        help="Run a quick self-test (capture only, no analysis)")

    args = parser.parse_args()

    # ── Self-test mode ──
    if args.test:
        print("Photo Analysis self-test...")
        img = capture_photo()
        if img is None:
            print("FAIL: Camera capture failed", file=sys.stderr)
            return 1
        print(f"OK: Captured {img.size[0]}x{img.size[1]} photo")
        print(f"OK: Image mode = {img.mode}")
        print(f"OK: Gemini config - model={args.model}, project={_get_project_id()}")
        return 0

    # ── Load image ──
    if args.file:
        image = load_image(args.file)
        source = args.file
    else:
        print("Capturing photo from camera...")
        image = capture_photo()
        source = "camera"

    if image is None:
        return 1

    print(f"Loaded image: {image.size[0]}x{image.size[1]}, mode={image.mode}")
    
    # Optional display
    if args.display:
        show_on_display(image)
        print("Image shown on LCD screen")

    # ── Analyze ──
    print(f"Analyzing with Gemini ({args.model})...")
    prompt = args.prompt or DEFAULT_PROMPT
    analysis = analyze_image(image, prompt=prompt, model_name=args.model)

    if analysis is None:
        print("FAIL: Analysis failed", file=sys.stderr)
        return 1

    # ── Output ──
    if args.json:
        result = {
            "source": source,
            "image_size": {"width": image.size[0], "height": image.size[1]},
            "model": args.model,
            "prompt": prompt,
            "analysis": analysis,
        }
        print(json.dumps(result, indent=2))
    else:
        print("\n" + "=" * 60)
        print("ANALYSIS RESULT")
        print("=" * 60)
        print(analysis)
        print("=" * 60)

    if args.save:
        with open(args.save, "w") as f:
            if args.json:
                json.dump(result, f, indent=2)
            else:
                f.write(analysis)
        print(f"Analysis saved to {args.save}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
