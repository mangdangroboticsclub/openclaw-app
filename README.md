# Minipupper Operator — Voice-First AI Assistant

**Status:** Phase 2 Active (Audio Pipeline ✅ — OpenClaw Agent Integration ✅ — Complex Tasks ✅)
**Last Updated:** 2026-07-16
**Platform:** Mini Pupper v2 Robot (Raspberry Pi CM4, Ubuntu, Debian 11)

---

## Overview

Minipupper Operator is a **voice-first conversational AI agent** running directly on your Mini Pupper robot, with **hybrid offloading** to a remote OpenClaw Gateway for complex tasks. It provides robust autonomous capabilities with **barge-in support** (user can interrupt the robot's speech at any time).

### Key Features
- 🎤 **Speech Recognition** — Google Cloud Speech-to-Text (near real-time)
- 🔊 **Text-to-Speech** — Google Cloud TTS with natural voices, barge-in interruptible
- 🤖 **AI Reasoning** — Gemini 2.5 Flash via Vertex AI (fast, capable)
- ⚡ **Barge-in Ready** — User interrupts robot speech instantly
- 🔌 **OpenClaw Gateway Integration** — File-based task protocol for complex actions (Communicating with cron gateway through json)
- 🦴 **Robot Control** — Direct FPC API movement, no UDP joystick dependency
- 🧠 **Knowledge Base** — Indexed reference for camera, motors, IMU, photo analysis
- 📸 **Vision** — Gemini Vision for photo analysis, gesture following, food detection
- 🌐 **Tailscale Connected** — Secure mesh network to cloud server
- 📊 **Queue-Based Architecture** - Scalable, decoupled components

### Models in Use

| Component | Model | Provider |
|-----------|-------|----------|
| **Speech-to-Text** | Google Cloud Speech-to-Text | Google Cloud |
| **AI Reasoning** | Gemini 2.5 Flash | Google Vertex AI |
| **Text-to-Speech** | Google Cloud TTS | Google Cloud |
| **Vision Analysis** | Gemini 2.5 Flash (multimodal) | Google Vertex AI |
| **Fallback LLM** | Mistral (local) | Ollama (optional) |

---

## Architecture

```
┌──────────────────────────────┐     Tailscale TLS      ┌──────────────────────────────┐
│   Cloud Server                │◀─────────────────────▶│   Raspberry Pi                 │
│   (Gateway)                   │                        │   (minipupperv2)               │
│                               │                        │                                │
│  OpenClaw Gateway             │                        │  openclaw node-host            │
│   ws://127.0.0.1:18789        │                        │  (exec/file access)            │
│                               │                        │                                │
│  Agent Sessions:              │  ─── cron.run (wake)   │  minipupper-app                │
│  • main (heartbeat 5s)        │  ─── tasks.json (file) │  ┌─────────────────────────┐   │
│  • minipupper-app (stable)    │                        │  │ ASR (Google Cloud)      │   │
│  • isolated cron turns        │                        │  │ TTS (Google Cloud)      │   │
│                               │                        │  │ Gemini 2.5 Flash        │   │
│  Cron: minipupper-task-       │                        │  │ Barge-in Detector       │   │
│  processor (5s isolated)      │                        │  │ OpenClaw Client         │   │
│                               │                        │  │ Task Watcher            │   │
│  Custom actions:              │                        │  │ Task Archiver           │   │
│  • web_search                 │                        │  └─────────────────────────┘   │
│  • web_fetch                  │                        │                                │
│  • robot.init / move / dance  │                        │  Robot Control:                │
│  • robot.look_here            │                        │  ┌─────────────────────────┐   │
│  • robot.take_photo_and_show  │                        │  │ FPC MovementLib        │   │
│  • vision_analyze_image       │                        │  │ ContinuousController   │   │
│  • explore / implement        │                        │  │ camera_person_follow   │   │
│  • query                      │                        │  │ look_here.py            │   │
│                               │                        │  │ photo_analysis          │   │
└──────────────────────────────┘                        └──────────────────────────────┘
```

### Data Flow (Task Offloading)

```
User Speech → ASR → Gemini LLM → [TASK] marker detected?
  │                                    │
  │ (no) ←─────────────────────→ (yes)│
  │                                    │
  ▼                                    ▼
Direct reply                      Write to tasks.json
                                  └─ Cron triggered via Gateway WebSocket
                                     └─ Agent processes task
                                        ├─ robot.* → exec on node
                                        ├─ web_search → web_search tool
                                        ├─ web_fetch → web_fetch tool
                                        ├─ vision → run custom script
                                        └─ explore/implement → build capability
                                     └─ Writes result to tasks.json
                                  TaskWatcher detects "completed"
                                  └─ Gemini generates TTS announcement
                                     └─ User hears result
```

---

## Getting Started

### One-Script Setup (Recommended)

The fastest way to set up a new Mini Pupper:

```bash
# 1. Connect to your Mini Pupper via VS Code Remote-SSH
#    (Cmd/Ctrl+Shift+P -> Remote-SSH: Connect to Host -> ubuntu@<your-pi-ip>)
#    Then open a terminal inside VS Code (Ctrl+`)

# 2. Clone the repo onto the Pi
cd ~
git clone https://github.com/mangdangroboticsclub/openclaw-app.git -b master
cd openclaw-app

# 3. Run the automated setup script
bash scripts/setup.sh
```

The script will walk you through:
1. ✅ Install Node.js 22, OpenClaw, Tailscale, Python deps
2. ✅ Copy config files to `~/openclaw-app/`
3. ✅ Connect the Pi as an OpenClaw node

**Before running**, have ready:
- Your Gateway server's Tailscale address
- Your Google Cloud service account key (`api_key.json`)
- The `OPENCLAW_GATEWAY_TOKEN` from your Gateway config

Once the setup is complete, see the detailed [Onboarding](ONBOARDING.md) to continue installation.

### Manual Setup

If you prefer to set up step by step, see the detailed [Setup Guide](docs/SETUP_GUIDE.md) or [Quick Start](QUICKSTART.md).

---

## Configuration

### `config/config.yaml` — Main Settings

```yaml
app:
  debug: true
  log_level: INFO
  version: 0.1.0

audio:
  asr:
    engine: google          # Google Cloud Speech-to-Text (primary)
    streaming: true
    language: en-US
    # Fallback: "whisper"   # Faster-Whisper local model
  tts:
    engine: google          # Google Cloud TTS
    voice: en-US-Neural2-A
    pitch: 0.0
    speed: 1.0

operator:
  llm_provider: gemini          # Google Vertex AI (Gemini)
  llm_model: gemini-2.5-flash   # Current active model
  enable_tool_execution: true
  max_context_length: 8192
  max_response_tokens: 500
  response_timeout_seconds: 30
  role: minipupper_autonomous
  movements:
    enabled: true
    max_speed: 100

barge_in:
  enabled: true
  vad_aggressiveness: 2
  aec_enabled: true
  aec_double_talk_ratio: 1.2
  aec_max_delay_ms: 180
  aec_max_gain: 1.5
  echo_suppression_threshold: 0.85
  echo_energy_ratio: 1.0
  nearend_frames_required: 8
  nearend_min_cleaned_rms: 500
  nearend_mic_to_playback_ratio: 1.5
  silence_duration_ms: 300
  detection_timeout_ms: 90
  frame_duration_ms: 30
  startup_grace_ms: 300

network:
  gateway_url: ${OPENCLAW_GATEWAY_URL}
  session_target: agent:main:dashboard:*             # Stable session key
  cron_job_id: a3dc8f0c-c459-43b2-8cde-3fa014124c0c # Task processor cron
  tailscale_enabled: true
  default_port: 8888
  local_network: true
```

### `.env` — Environment Variables

```bash
cp config/.env.sample config/.env
# Edit with your values:
GOOGLE_APPLICATION_CREDENTIALS=/home/ubuntu/apps-md-robots/api_key.json
GOOGLE_CLOUD_PROJECT_ID=your-project-id
OPENCLAW_GATEWAY_URL=wss://your-gateway:443/ws
```

### Barge-in Tuning

- Use `scripts/calibrate_aec.py` to measure echo delay/gain for your hardware
- Adjust `nearend_min_cleaned_rms` (lower = more sensitive, default 500)
- Adjust `vad_aggressiveness` (0-3, default 2)
- Test with `scripts/test_bargein.py`

---

## Key Features

### 🎤 Audio Pipeline (Phase 1 — Complete)

- **ASR:** Google Cloud Speech-to-Text primary, Faster Whisper fallback
- **TTS:** Google Cloud TTS with natural voices (en-US-Neural2-A)
- **Barge-in:** Streaming VAD with in-app Acoustic Echo Cancellation (AEC)
  - Double-talk detection, echo suppression, near-end gating
  - Calibration script: `scripts/calibrate_aec.py` → run once if changing input medium
  - Tuning via `config.yaml` `barge_in.*` section → for adjusting sensitivity

### 🤖 OpenClaw Gateway Integration (Phase 2 — Active)

- **File-based task protocol** — Shared `tasks.json` replaces session-based messaging
- **Gateway WebSocket client** — `src/openclaw/client.py` with Ed25519 signed handshake
- **Task Watcher** — `src/core/task_watcher.py` polls every 2s, announces results via TTS
- **Task Archiver** — `src/core/task_archiver.py` moves completed tasks to date-partitioned archive
- **Protocol Handler** — `src/core/protocol_handler.py` parses agent messages (e.g TTS from Task Watcher)
- **Wake Signal** — App triggers cron via `scripts/send_wake.py` (cron.run RPC)

#### Task JSON Format

```json
{
  "tasks": {
    "task-xxx": {
      "taskId": "task-xxx",
      "action": "web_search | robot.init | vision_analyze_image | ...",
      "params": { "query": "...", "duration": 2.0, ... },
      "status": "pending | running | completed | failed",
      "phase": "starting | processing | completed",
      "progress": 0-100,
      "message": "Human-readable status",
      "result": "Final result text",
      "announced": true | false,
      "createdAt": 1234567890.0,
      "updatedAt": 1234567890.0
    }
  }
}
```

#### Offloading Actions

| Action Type | Sub-actions | Handler |
|-------------|-------------|---------|
| `web_search` | — | `web_search` tool on Gateway |
| `web_fetch` | — | `web_fetch` tool on Gateway |
| `robot.init` | activate, deactivate | `robot/robot_control.py` |
| `robot.move_*` | forward, backward, strafe_left/right | `robot/robot_control.py` |
| `robot.rotate_*` | cw, ccw | `robot/robot_control.py` |
| `robot.look_*` | up, down | `robot/robot_control.py` |
| `robot.raise_body` / `robot.lower_body` | — | `robot/robot_control.py` |
| `robot.dance` | — | `robot/robot_control.py` |
| `robot.stop` | — | `robot/robot_control.py` |
| `robot.reset` | — | deactivate + activate |
| `robot.trot` | — | activate |
| `robot.take_photo_and_show` | — | `scripts/capture_and_show.py` |
| `robot.show_image` | — | `scripts/capture_and_show.py --display-only` |
| `robot.look_here` | — | `custom/look_here.py` (background, 45-90s) |
| `vision_analyze_image` | use_captured/file | `custom/photo_analysis/main.py` |
| `food.analyze` | — | `custom/calorie_calculator.py` |
| `query` | — | Answer from agent context |
| `explore` | — | Check `knowledge/INDEX.json` or run exploration |
| `implement` | — | Build capability, write to `custom/{topic}/main.py` |

### 🦴 Robot Control (FPC API)

Replaces the old buggy UDP-joystick-based control. Uses the **Flexible Programmable Choreography (FPC) API** from StanfordQuadruped:

- **`robot/robot_control.py`** — CLI-based movement commands (activate, trot, forward, dance, etc.)
- **`robot/continuous_control.py`** — Real-time velocity control for continuous tasks like person following. Keeps the hardware interface open and accepts live updates each tick.

### 📸 Vision & Custom Capabilities (Phase 3 — Active)

| Module | Path | Description |
|--------|------|-------------|
| **Photo Analysis** | `custom/photo_analysis/main.py` | Capture & analyze with Gemini Vision (scene, objects, text) |
| **Look Here** | `custom/look_here.py` | Takes 3 photos, detects pointing gestures, moves gaze accordingly (45-90s) |
| **Person Follower** | `custom/camera_person_follow/main.py` | HOG-based person detection + PID steering |
| **Person Follow + Live Video** | `custom/camera_person_follow_with_live_video/main.py` | Merges HOG + LCD feed via ContinuousController |
| **Live Camera Feed on LCD** | `custom/camera_live_feed_on_screen/main.py` | Continuous MIPI → ST7789 LCD at ~16 FPS |
| **Calorie Calculator** | `custom/calorie_calculator.py` | Food photo → Gemini Vision → calorie estimate |
| **Touch Respond** | `custom/touch_respond.py` | 4-zone touch panel → robot actions (daemon) |
| **Code Analysis** | `knowledge/code_analysis.md` | Full codebase reference for agent |

### 🧠 Knowledge Base

17 indexed knowledge files at `knowledge/` for agent reference:

- `camera.md`, `motors.md`, `imu.md`, `battery.md` — Hardware specs
- `photo_analysis.md`, `look_here.md` — Vision capabilities
- `script_invocation.md`, `file_system_access.md`, `file_access_and_analysis.md` — Agent access docs
- `camera_person_follow.md`, `camera_live_feed.md`, `camera_live_video_streaming.md` — Camera features
- `diet_food_analysis_cron_trigger.md` — Food analysis integration
- `bowling_court_activation.md` — Bowling simulation

---

## Project Structure

```
minipupper-app/
├── minipupper_operator.py      # Main entry point (operator class with workers)
├── protocol.py                 # Phase 2 protocol dataclasses
├── tasks.json                  # Shared task file (app ↔ agent)
├── tasks_archive.json          # Historical task log
├── INDEX.json                  # Robot anatomy reference
├── PHASE2.md                   # Phase 2 protocol documentation
├── QUICKSTART.md               # Quick start guide
├── ROADMAP.md                  # Development roadmap
├── README.md                   # This file
├── requirements.txt            # Python dependencies
│
├── config/
│   ├── config.yaml             # Main configuration (audio, barge-in, operator, network)
│   ├── .env                    # Environment variables (credentials)
│   ├── .env.sample             # Environment variable template
│   ├── api_key.json.example    # Google Cloud service account key template
│   ├── system_prompt.txt       # Base Gemini system prompt
│   └── system_prompt_phase2.txt# Phase 2 system prompt with [TASK] offloading
│
├── src/
│   ├── core/
│   │   ├── llm_engine.py       # LLM provider abstraction (Gemini, Ollama, fallback)
│   │   ├── task_queue.py       # Inter-component queue-based IPC
│   │   ├── task_watcher.py     # Phase 2: polls tasks.json for completed tasks
│   │   ├── task_archiver.py    # Phase 2: archives completed tasks
│   │   └── protocol_handler.py # Phase 2: parses agent protocol messages
│   ├── audio/
│   │   ├── audio_manager.py    # ASR/TTS with barge-in support
│   │   └── barge_in_detector.py# Speech detection with AEC
│   ├── openclaw/
│   │   └── client.py           # Gateway WebSocket client (Ed25519 handshake)
│   └── robot/
│       └── (reserved)
│
├── robot/
│   ├── robot_control.py        # FPC MovementLib CLI commands
│   └── continuous_control.py   # Real-time velocity control for person following
│
├── custom/
│   ├── photo_analysis/main.py           # Gemini Vision photo analysis
│   ├── look_here.py                     # Gesture following (3 photos)
│   ├── calorie_calculator.py            # Food photo → calorie estimates
│   ├── camera_person_follower.py        # Person follower (FPC API)
│   ├── camera_person_follow/            # HOG + PID person following
│   ├── camera_person_follow_with_live_video/  # Merge HOG + LCD feed
│   ├── camera_live_feed_on_screen/      # Live MIPI → LCD feed
│   ├── movement_bug/                    # Movement debugging
│   └── touch_respond.py                 # Touch panel daemon
│
├── scripts/
│   ├── setup.sh                         # 🚀 One-script automated setup
│   ├── capture_and_show.py              # Camera capture + LCD display
│   ├── send_wake.py                     # Trigger Gateway cron for task processing
│   ├── manage_archives.py               # Task archive CLI utility
│   ├── calibrate_aec.py                 # In-app AEC calibration
│   ├── test_bargein.py                  # Continuous barge-in test harness
│   ├── test_pipeline.py                 # ASR → LLM → TTS pipeline test
│   ├── display_task_info.py             # Show task status on ST7789 LCD
│   └── start_with_aec.sh                # Start with AEC enabled
│
├── knowledge/                   # 17 indexed knowledge files for agent reference
│   ├── INDEX.json               # Knowledge index with summaries
│   ├── camera.md, motors.md, imu.md, battery.md
│   ├── photo_analysis.md, look_here.md
│   ├── script_invocation.md, file_system_access.md
│   ├── camera_person_follow.md, camera_live_feed.md
│   └── ... (17 total)
│
├── explore/                 # Exploration results
│   └── INDEX.json, camera_person_follow.md, custom_command_mapping.md
│
├── gateway/                 # Gateway-side config & setup
│   ├── cron_config.json        # Cron job definition
│   └── SETUP_NEW_GATEWAY.md    # Gateway setup guide
│
├── docs/
│   ├── ARCHITECTURE.md         # System design & data flow
│   ├── OPENCLAW_INTEGRATION.md # Gateway integration details
│   ├── CURRENT_STATE.md        # Current development status
│   ├── PROGRESS.md             # Development log with dates
│   ├── SETUP_GUIDE.md          # Complete manual setup instructions
│   ├── DEPLOYMENT_GUIDE.md     # Operations guide
│   ├── TASK_ARCHIVING.md       # Task archive system documentation
│   ├── BARGE_IN_GUIDE.md       # Barge-in implementation details
│   ├── TESTING_PLAN.md         # Test strategy & checklist
│   ├── GOOGLE_CLOUD_SETUP.md   # Google Cloud credential setup
│   ├── audio-architecture.md   # Audio subsystem deep dive
│   ├── phase3-complex-tasks.md # Phase 3 complex task documentation
│   └── phase3-overhaul.md      # Phase 3 overhaul notes

└── tasks_archive/              # Date-partitioned completed tasks
    └── YYYY-MM-DD.json
```

---

## Quick Start

### Prerequisites
- Minipupper robot with Raspberry Pi 4 (4GB+ RAM)
- Microphone + speakers connected
- Python 3.9+ installed
- Google Cloud account with Speech-to-Text, TTS, and Vertex AI APIs
- Tailscale for cloud connectivity (optional for local-only)

### 🚀 Automated Setup (Recommended)

```bash
cd ~
git clone https://github.com/mangdangroboticsclub/openclaw-app.git
cd openclaw-app
./scripts/setup.sh
```

Follow the prompts. The script handles everything: Node.js, OpenClaw, Tailscale, Python deps, configs, node connection, and dashboard.

### Manual Installation

```bash
# 1. Clone repository
cd ~
git clone https://github.com/mangdangroboticsclub/openclaw-app.git
cd openclaw-app

# 2. Create Python environment
python3.10 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp config/.env.sample config/.env
# Edit config/.env with your Google Cloud credentials

# 5. Configure gateway (if using OpenClaw integration)
# See: docs/OPENCLAW_INTEGRATION.md and gateway/SETUP_NEW_GATEWAY.md

# 6. Run!
python minipupper_operator.py
```

### Google Cloud Setup

See [docs/GOOGLE_CLOUD_SETUP.md](docs/GOOGLE_CLOUD_SETUP.md) for:
- Creating Google Cloud project
- Enabling Speech-to-Text, TTS, and Vertex AI APIs
- Setting up service account credentials
- Cost estimation

### Test Pipeline

```bash
# Test ASR → LLM → TTS end-to-end
PYTHONPATH=. python3 scripts/test_pipeline.py --duration 5

# Test barge-in detection
python -m src.audio.barge_in_detector

# Test AEC calibration
python3 scripts/calibrate_aec.py
```

---

## Barge-in Feature

**What it does:** User can interrupt the robot's speech by speaking over it.

**How to test:**
```bash
# Robot speaks a response while listening for interruption
# User speaks → Robot detects speech → TTS stops immediately
# User input is processed next
```

**Configuration:**
- Adjust `barge_in.min_energy_threshold` based on ambient noise
- See [docs/BARGE_IN_GUIDE.md](docs/BARGE_IN_GUIDE.md) for details

---

## Deployment

### Run Flags

```bash
python minipupper_operator.py --help
  --config PATH     Config file path (default: config/config.yaml)
  --k               Keyboard input mode (no ASR/TTS)
  --m               Mute output (no TTS, text only)
  --v               Verbose logging
```

---

## Further Reading

- [Architecture](docs/ARCHITECTURE.md) — Complete system design
- [Setup Guide](docs/SETUP_GUIDE.md) — Step-by-step manual setup
- [Gateway Integration](docs/OPENCLAW_INTEGRATION.md) — OpenClaw protocol details
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) — Production operations
- [Barge-in Guide](docs/BARGE_IN_GUIDE.md) — AEC/VAD tuning
- [Google Cloud Setup](docs/GOOGLE_CLOUD_SETUP.md) — Credential configuration
- [Progress Log](docs/PROGRESS.md) — Development history
- [Current State](docs/CURRENT_STATE.md) — Latest status
- [ROADMAP.md](ROADMAP.md) — Future plans

---

## License

MIT