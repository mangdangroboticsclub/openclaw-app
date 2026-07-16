# Onboarding — Minipupper Operator Setup

This guide walks you through setting up the Minipupper Operator on a fresh Raspberry Pi. The automated setup script handles the heavy lifting; you just need to configure credentials and connect the node.

---

## Prerequisites

- Mini Pupper v2 robot (Raspberry Pi 4 / CM4)
- Microphone + speaker connected
- 64 GB microSD (UHS-I recommended)
- Ubuntu installed on the Pi
- Google Cloud project with Speech-to-Text, TTS, and Vertex AI APIs enabled
- Tailscale account (for cloud Gateway connectivity)

**Have ready before starting:**
- Your Gateway server's Tailscale address
- Your Google Cloud service account key (`api_key.json`)
- The `OPENCLAW_GATEWAY_TOKEN` from your Gateway config

---

## 1. Automated Setup

Run the setup script on the Pi. It handles Node.js, OpenClaw, Tailscale, Python deps, and config files interactively.

```bash
git clone https://github.com/mangdangroboticsclub/openclaw-app.git
cd openclaw-app
./scripts/setup.sh
```

**What the script does:**
1. Installs Node.js 22
2. Installs OpenClaw (2026.7.1)
3. Installs & connects Tailscale
4. Installs Python dependencies (webrtcvad, websocket-client)
5. Copies config files (`config.yaml`, system prompts, `api_key.json` template)

**After the script finishes, continue with the steps below.**

---

## 2. Environment Setup

### 2.1 Place your Google Cloud service account key

```bash
cat > ~/openclaw-app/config/api_key.json
# Paste your JSON key, then Ctrl+D
```

### 2.2 Configure `.env`

```bash
cd ~/openclaw-app
cp config/.env.sample config/.env
```

Edit `config/.env` with your credentials:

| Variable | Example Value | Description |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | `/home/ubuntu/openclaw-app/config/api_key.json` | Path to your service account key |
| `GOOGLE_CLOUD_PROJECT_ID` | `my-project-123` | Your Google Cloud project ID |
| `OPENCLAW_GATEWAY_URL` | `wss://instance-xxxxx.tailXXXXX.ts.net:443/ws` | Your Gateway WebSocket URL |

---

## 3. Connect as an OpenClaw Node

The node connection gives the Gateway `exec` access to the Pi — required for task processing.

### 3.1 Start the node connection on the Pi

```bash
openclaw node run --host <GATEWAY_HOST> --port 443 --tls
```

Replace `<GATEWAY_HOST>` with your Gateway's Tailscale address (e.g., `instance-20260506-083731.tail2df607.ts.net`).

### 3.2 Approve the device on the Gateway VM

```bash
openclaw devices list                # Find the request ID
openclaw devices approve --latest
```

### 3.3 (One-time) Add an allowlist entry

```bash
openclaw approvals allowlist add --node minipupperv2 "*"
```

### 3.4 Verify the connection

```bash
openclaw nodes status
# Expected: minipupperv2 — connected
```

> **First-time pairing:** Node connects → Gateway sees new device → pending approval → you approve → node reconnects → connected. This only happens once (or after a Pi reboot if metadata changes).

---

## 4. Run the Operator

```bash
cd ~/openclaw-app
python minipupper_operator.py
```

Expected startup output:
```
✓ Google Cloud Speech-to-Text initialized
✓ Google Cloud TTS initialized
✓ Gemini Vertex AI ready (model: gemini-2.5-flash)
✓ Minipupper Operator running. Listening for speech...
```

---

## 5. Test the Pipeline

```bash
# End-to-end test (ASR → LLM → TTS)
PYTHONPATH=. python3 scripts/test_pipeline.py --duration 5

# Barge-in test
python -m src.audio.barge_in_detector

# AEC calibration
python3 scripts/calibrate_aec.py
```

---

## Directory Layout After Setup

```
~/openclaw-app/
├── minipupper_operator.py      # Main entry point
├── config/
│   ├── config.yaml             # Main configuration
│   ├── .env                    # Your credentials
│   ├── system_prompt_phase2.txt
│   └── api_key.json            # Your Google Cloud service account key
├── tasks.json                  # Shared task file (app ↔ Gateway agent)
├── tasks_archive/              # Completed task history
├── custom/                     # Vision, music, touch, etc.
├── scripts/                    # Utility scripts
├── knowledge/                  # Robot capability reference
├── docs/                       # Full documentation
├── gateway/                    # Gateway-side config
└── explore/                    # Exploration results
```

---

## Troubleshooting

| Issue | Symptom | Check / Fix |
|-------|---------|-------------|
| **Node won't connect** | `openclaw node run` fails with "pending approval" | On the Gateway: `openclaw devices list` → `openclaw devices approve <ID>` |
| **Node re-pair after reboot** | Pi reboots, node says "metadata change pending approval" | Re-approve via `openclaw devices approve <ID>` on Gateway |
| **cron.run not working** | Task sits in `tasks.json` as `pending` forever | App device needs `operator.admin` scope: update `SCOPES` in `src/openclaw/client.py` to include `'operator.admin'`, restart app, approve upgrade |
| **No audio input** | Robot doesn't hear anything | `arecord -l` — verify mic device is detected. Check `config.yaml` for correct `MIC_DEVICE_INDEX` |
| **No audio output** | Robot doesn't speak | `aplay -l` — verify speaker device. Check `config.yaml` for correct `SPEAKER_DEVICE_INDEX` |
| **Google Cloud auth fails** | "Permission denied" or "Not found" | Verify `api_key.json` is valid: `gcloud auth application-default print-access-token` |
| **Barge-in not working** | Robot doesn't stop speaking when interrupted | Run `scripts/calibrate_aec.py` to tune AEC settings for your room |
| **Tailscale disconnected** | `openclaw node run` hangs | `tailscale status` — should show connected. Re-run `sudo tailscale up` if not |
| **Task never completes** | Status stuck on `running` | Check `openclaw nodes status` — node may be disconnected. Check cron on Gateway: `openclaw cron list --include-disabled` |
| **Operator fails to start** | Python import errors | Ensure you're in the virtual env: `source venv/bin/activate`. Run `pip install -r requirements.txt` |

For detailed troubleshooting, see [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md).