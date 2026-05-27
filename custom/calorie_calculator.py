#!/usr/bin/env python3
"""
Calorie Calculator — Mini Pupper

Captures food photo, analyzes with Gemini Vision, outputs estimated calories.

Usage:
    python3 custom/calorie_calculator.py               # capture + analyze
    python3 custom/calorie_calculator.py --file /tmp/photo.jpg  # analyze existing
"""

import argparse, io, os, subprocess, sys
from PIL import Image
import vertexai
from vertexai.generative_models import GenerativeModel, Part

CREDS = "/home/ubuntu/apps-md-robots/20250923.json"
PROJECT = "modern-rex-420404"
CAPTURE = "/home/ubuntu/minipupper-app/scripts/capture_and_show.py"

PROMPT = (
    "You are a nutritional analysis AI. Analyze the food in this image.\n"
    "For each distinct food item visible, state its name and approximate calorie count.\n"
    "Then suggest which is the healthiest option.\n"
    "Output in this exact format:\n"
    "<food name>: ~<number> cal\n"
    "<food name>: ~<number> cal\n"
    "Suggest you to eat --> <food name>\n"
    "Use common serving sizes."
)

def capture(path):
    r = subprocess.run(["python3", CAPTURE, "--save", path], capture_output=True, text=True, timeout=50)
    return r.returncode == 0 and os.path.exists(path)

def analyze(path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDS
    vertexai.init(project=PROJECT, location="us-central1")
    
    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    
    try:
        model = GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            [PROMPT, Part.from_data(mime_type="image/jpeg", data=buf.getvalue())]
        )
        return response.text.strip()
    except Exception as e:
        return f"Error: {e}"

def main():
    parser = argparse.ArgumentParser(description="Mini Pupper Calorie Calculator")
    parser.add_argument("--file", help="Analyze existing image instead of capturing")
    args = parser.parse_args()

    path = args.file or "/tmp/calorie_photo.jpg"

    if not args.file:
        if not capture(path):
            print("Error: Capture failed")
            return 1

    print(analyze(path))

if __name__ == "__main__":
    main()