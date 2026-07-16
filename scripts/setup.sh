#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────
# Minipupper + OpenClaw Setup Script  (setup.sh)
#
# Run on a fresh Pi:
#   git clone https://github.com/mangdangroboticsclub/openclaw-app.git
#   cd openclaw-app
#   ./scripts/setup.sh
#
# Installs: Node.js, OpenClaw, Tailscale, Python deps,
# copies configs, connects as node, launches operator.
# ──────────────────────────────────────────────────────

BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
SEP="────────────────────────────────────────────────────"

info()  { echo -e "${GREEN}→${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠ $1${NC}"; }
step()  { echo -e "\n${CYAN}${SEP}${NC}\n${BOLD}Step $1${NC}: $2\n${CYAN}${SEP}${NC}"; }
pause() { echo -e "${DIM}Press Enter to continue (or Ctrl+C to abort)...${NC}" && read -r; }

echo -e "${BOLD}
╔══════════════════════════════════════════╗
║   Minipupper + OpenClaw Setup Script    ║
╚══════════════════════════════════════════╝${NC}"
echo ""
echo "Run this entirely on the Pi."
echo "Keep the gateway VM terminal open nearby for 2 quick approvals."
echo ""

# ──────────────────────────────────────────────────────
# 0 — Pre-flight
# ──────────────────────────────────────────────────────
step 0 "Pre-flight checks"

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
info "Repo directory: $REPO_DIR"

if [ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ]; then
    warn "OPENCLAW_GATEWAY_TOKEN not set — will try config.yaml later."
fi
pause

# ──────────────────────────────────────────────────────
# 1 — System deps (Node.js)
# ──────────────────────────────────────────────────────
step 1 "Install system dependencies (Node.js)"

info "Installing Node.js 22..."
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

mkdir -p ~/.npm-global
npm config set prefix "$HOME/.npm-global"
if ! grep -q '\.npm-global/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
fi
export PATH="$HOME/.npm-global/bin:$PATH"

info "Node.js $(node --version) · npm $(npm --version)"
pause

# ──────────────────────────────────────────────────────
# 2 — OpenClaw
# ──────────────────────────────────────────────────────
step 2 "Install OpenClaw"

info "Installing openclaw@2026.7.1..."
npm install -g openclaw@2026.7.1
info "Verified: $(openclaw --version)"
pause

# ──────────────────────────────────────────────────────
# 3 — Tailscale
# ──────────────────────────────────────────────────────
step 3 "Install & connect Tailscale"

if command -v tailscale &>/dev/null; then
    info "Tailscale already installed ($(tailscale --version | head -1))"
else
    info "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

if tailscale status 2>/dev/null | grep -q '^100\.'; then
    info "Tailscale already connected"
else
    echo ""
    warn "Run sudo tailscale up, log in via the browser link, then come back."
    echo ""
    sudo tailscale up
    for i in {1..15}; do
        if tailscale status 2>/dev/null | grep -q '^100\.'; then
            info "✅ Tailscale connected"
            tailscale status | head -3
            break
        fi
        echo "  Waiting... ($i/15)"
        sleep 2
    done
    if ! tailscale status 2>/dev/null | grep -q '^100\.'; then
        warn "Tailscale didn't connect. Run 'sudo tailscale up' manually."
        exit 1
    fi
fi
pause

# ──────────────────────────────────────────────────────
# 4 — Python deps
# ──────────────────────────────────────────────────────
step 4 "Install Python dependencies"

pip install webrtcvad websocket-client
info "Python packages installed."
pause

# ──────────────────────────────────────────────────────
# 5 — Copy configs
# ──────────────────────────────────────────────────────
step 5 "Copy config files from repo"

# YAML config
if [ -f "$REPO_DIR/config/config.yaml" ]; then
    mkdir -p ~/openclaw-app/config
    cp "$REPO_DIR/config/config.yaml" ~/openclaw-app/config/config.yaml
    info "✅ config/config.yaml"
fi

# System prompt
if [ -f "$REPO_DIR/config/system_prompt_phase2.txt" ]; then
    mkdir -p ~/openclaw-app/config
    cp "$REPO_DIR/config/system_prompt_phase2.txt" ~/openclaw-app/config/system_prompt_phase2.txt
    info "✅ config/system_prompt_phase2.txt"
fi

# API key template
if [ -f "$REPO_DIR/config/api_key.json" ]; then
    mkdir -p ~/openclaw-app/config
    cp "$REPO_DIR/config/api_key.json" ~/openclaw-app/config/
    info "✅ config/api_key.json (place real key later)"
fi

# Custom / dance scripts
if [ -d "$REPO_DIR/custom" ]; then
    mkdir -p ~/openclaw-app/custom
    cp -r "$REPO_DIR/custom/"* ~/openclaw-app/custom/ 2>/dev/null || true
    info "✅ custom/"
fi

if [ -d "$REPO_DIR/scripts" ]; then
    mkdir -p ~/openclaw-app/scripts
    cp -r "$REPO_DIR/scripts/"* ~/openclaw-app/scripts/ 2>/dev/null || true
    info "✅ scripts/"
fi

info "All configs copied."
pause

# ──────────────────────────────────────────────────────
# Setup complete
# ──────────────────────────────────────────────────────
echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Place your Google Cloud service account key:"
echo "       cat > ~/openclaw-app/config/api_key.json"
echo "       (paste JSON, then Ctrl+D)"
echo ""