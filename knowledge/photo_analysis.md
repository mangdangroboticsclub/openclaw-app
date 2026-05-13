# Photo Analysis — Capability

## Summary
Custom implementation that captures a photo from the MIPI CSI camera and analyzes it using Gemini 2.5 Flash (Vertex AI) vision capabilities. Runs on the Mini Pupper Raspberry Pi.

## Files
- `custom/photo_analysis/main.py` — Standalone CLI module

## Usage
```
python3 custom/photo_analysis/main.py                              # capture + analyze
python3 custom/photo_analysis/main.py --file /tmp/photo.jpg        # analyze existing image
python3 custom/photo_analysis/main.py --prompt "What do you see?"  # custom prompt
python3 custom/photo_analysis/main.py --save /tmp/analysis.txt     # save analysis
python3 custom/photo_analysis/main.py --json                       # JSON output
python3 custom/photo_analysis/main.py --display                    # show on LCD screen too
python3 custom/photo_analysis/main.py --test                       # self-test camera + config
```

## Dependencies
- `opencv-python` (camera capture)
- `Pillow` (image processing)
- `vertexai` (Gemini via Vertex AI)
- Service account at `/home/ubuntu/apps-md-robots/20250923.json`

## Model
- Default: `gemini-2.5-flash` (supports vision, fast)
- Overrideable with `--model gemini-1.5-flash` or `gemini-1.5-pro`

## Capabilities
- Captures 640x480 from `/dev/video0` with retry logic
- Send image to Gemini via `Part.from_data()` with JPEG encoding
- Configurable prompt for different analysis types
- Optional LCD display of captured image
- JSON output for programmatic consumption
- Self-test mode to verify camera and config

## Tested
- Camera capture: 640x480, RGB, works on first attempt
- Gemini vision: Detailed scene description returned in ~3-4 seconds
- Service account auth: Verified via GOOGLE_APPLICATION_CREDENTIALS env var
