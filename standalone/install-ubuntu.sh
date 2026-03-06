#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
# Standalone Newsletter Agent — Ubuntu/Debian Installer
# ══════════════════════════════════════════════════════════
# Installs: Python 3.11+, pip, venv, Ollama, pulls LLM model
# Idempotent — safe to run multiple times.
set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Standalone Newsletter Agent — Ubuntu Installer${NC}"
echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
echo ""

# ── 1. System dependencies ───────────────────────────────
info "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv curl git > /dev/null 2>&1

PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [[ "$MAJOR" -lt 3 ]] || { [[ "$MAJOR" -eq 3 ]] && [[ "$MINOR" -lt 11 ]]; }; then
    die "Python 3.11+ required. Found: Python ${PYTHON_VERSION}"
fi
ok "Python ${PYTHON_VERSION} found."

# ── 2. Python virtual environment ────────────────────────
info "Setting up Python virtual environment..."
if [[ ! -d "${SCRIPT_DIR}/.venv" ]]; then
    python3 -m venv "${SCRIPT_DIR}/.venv"
    ok "Virtual environment created."
else
    ok "Virtual environment already exists."
fi

source "${SCRIPT_DIR}/.venv/bin/activate"

# ── 3. Python dependencies ───────────────────────────────
info "Installing Python packages..."
pip install --upgrade pip -q
pip install -q \
    httpx>=0.28.0 \
    feedparser>=6.0.11 \
    trafilatura>=2.0.0 \
    pyyaml>=6.0.2 \
    jinja2>=3.1.4 \
    beautifulsoup4>=4.12.0

ok "Python packages installed."

# ── 4. Ollama ────────────────────────────────────────────
info "Installing Ollama..."
if command -v ollama &> /dev/null; then
    ok "Ollama already installed."
else
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama installed."
fi

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null 2>&1; then
    info "Starting Ollama..."
    ollama serve &> /dev/null &
    sleep 3
    ok "Ollama started."
else
    ok "Ollama already running."
fi

# ── 5. Pull LLM models ──────────────────────────────────
# Default models: mistral (writer) + deepseek-r1:7b (reviewer)
WRITER_MODEL="mistral"
REVIEWER_MODEL="deepseek-r1:7b"

# Override from config if present
if [[ -f "${SCRIPT_DIR}/config/context.yml" ]]; then
    CFG_MODEL=$(grep -oP '^\s*model:\s*"\K[^"]+' "${SCRIPT_DIR}/config/context.yml" 2>/dev/null || true)
    CFG_REVIEWER=$(grep -oP '^\s*reviewer_model:\s*"\K[^"]+' "${SCRIPT_DIR}/config/context.yml" 2>/dev/null || true)
    [[ -n "${CFG_MODEL}" ]] && WRITER_MODEL="${CFG_MODEL}"
    [[ -n "${CFG_REVIEWER}" ]] && REVIEWER_MODEL="${CFG_REVIEWER}"
fi

info "Pulling writer model: ${WRITER_MODEL}..."
ollama pull "${WRITER_MODEL}"
ok "Writer model ${WRITER_MODEL} ready."

info "Pulling reviewer model: ${REVIEWER_MODEL}..."
ollama pull "${REVIEWER_MODEL}"
ok "Reviewer model ${REVIEWER_MODEL} ready."

# ── 6. Config ────────────────────────────────────────────
if [[ ! -f "${SCRIPT_DIR}/config/context.yml" ]]; then
    cp "${SCRIPT_DIR}/config/context.yml.example" "${SCRIPT_DIR}/config/context.yml"
    ok "Created config/context.yml from example. Edit it to customize."
else
    ok "config/context.yml already exists."
fi

mkdir -p "${SCRIPT_DIR}/output"

# ── Done ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  To run the newsletter agent:"
echo ""
echo "    cd ${SCRIPT_DIR}"
echo "    source .venv/bin/activate"
echo "    python run.py"
echo ""
echo "  With custom LLMs:"
echo ""
echo "    python run.py --llmwriter mistral --reviewer deepseek-r1:7b"
echo ""
echo "  Output will be saved to: ${SCRIPT_DIR}/output/"
echo ""
echo "  Edit config/context.yml to change topic & search queries."
echo ""
