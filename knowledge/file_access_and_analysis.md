# Photo Analysis Module -- `custom/photo_analysis/main.py`

## Purpose
A vision analysis module for the Mini Pupper robot that captures photos from the MIPI CSI camera and analyzes them using Google Gemini 2.5 Flash (Vertex AI). It can also analyze existing image files and optionally display images on the robot's ST7789 LCD screen.

## Key Features

### Camera Capture
- Uses OpenCV (`cv2.VideoCapture(0)`) to access `/dev/video0` (the MIPI CSI camera)
- Captures at 640x480 resolution after a 0.5s warmup
- Retries up to 3 times on failed frames
- Converts BGR to RGB and returns a PIL Image

### Gemini Vision Analysis
- Initializes Vertex AI with GOOGLE_CLOUD_PROJECT_ID env var (or reads GCP project from the service account JSON file)
- Location: us-central1 (hardcoded)
- Uses gemini-2.5-flash model (configurable via --model)
- Sends image as JPEG bytes (85% quality) with safety settings (block only HIGH for harassment/hate/sexual)
- Default prompt: Describe this image in detail. What objects, people, text, colors, and environment do you see?
- Custom prompts supported via --prompt

### Command-Line Interface
Flags: --file <path> (analyze existing image), --prompt <text> (custom prompt), --save <path> (save analysis to file), --model <name> (override Gemini model), --display (show on LCD), --json (JSON output), --test (self-test only)

### Output Formats
- Text mode (default): Prints analysis with separator lines
- JSON mode (--json): {source, image_size, model, prompt, analysis}

### Display Support
- Uses MangDang.mini_pupper.display.Display for the robot's ST7789 LCD
- Resizes image to 320x240 before displaying
- Gracefully handles ImportError (display not available)

## Dependencies
- opencv-python (cv2)
- Pillow (PIL)
- google-cloud-aiplatform / vertexai
- MangDang.mini_pupper.display (optional, for LCD)

## Integration Points
- Called by the task processor for vision_analyze_image actions
- Authenticates via GOOGLE_APPLICATION_CREDENTIALS service account + GOOGLE_CLOUD_PROJECT_ID
- Credential path: /home/ubuntu/apps-md-robots/20250923.json
- GCP Project: modern-rex-420404

## File Location
/home/ubuntu/minipupper-app/custom/photo_analysis/main.py (single file, 8772 bytes)
