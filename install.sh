#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
# Cyber News Agent — Idempotent Installer for Ubuntu 24.04
# ══════════════════════════════════════════════════════════
set -euo pipefail

# ── Colors ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }
die()   { err "$@"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_PROFILES=""

# ══════════════════════════════════════════════════════════
# 1. Pre-flight checks
# ══════════════════════════════════════════════════════════
info "Running pre-flight checks..."

# Must run as root or with sudo
if [[ $EUID -ne 0 ]]; then
    die "This script must be run as root (or with sudo)."
fi

# Ubuntu version check
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    if [[ "${ID:-}" != "ubuntu" ]]; then
        warn "This script is designed for Ubuntu. Detected: ${ID:-unknown}"
    elif [[ "${VERSION_ID:-}" != "24.04" ]]; then
        warn "Designed for Ubuntu 24.04. Detected: ${VERSION_ID:-unknown}. Proceeding anyway."
    else
        ok "Ubuntu ${VERSION_ID} detected."
    fi
fi

# Disk space (>= 30GB free)
FREE_GB=$(df -BG --output=avail "${PROJECT_DIR}" | tail -1 | tr -dc '0-9')
if [[ "${FREE_GB}" -lt 30 ]]; then
    warn "Only ${FREE_GB}GB free disk space. 30GB+ recommended."
else
    ok "Disk space: ${FREE_GB}GB free."
fi

# RAM check (>= 12GB recommended)
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_RAM_GB=$((TOTAL_RAM_KB / 1024 / 1024))
if [[ "${TOTAL_RAM_GB}" -lt 12 ]]; then
    warn "Only ${TOTAL_RAM_GB}GB RAM detected. 12GB+ recommended for running two LLMs."
else
    ok "RAM: ${TOTAL_RAM_GB}GB detected."
fi

# ══════════════════════════════════════════════════════════
# 2. System packages
# ══════════════════════════════════════════════════════════
info "Installing system prerequisites..."
apt-get update -qq
apt-get install -y -qq curl git jq ca-certificates gnupg lsb-release > /dev/null 2>&1
ok "System packages installed."

# ══════════════════════════════════════════════════════════
# 3. Docker Engine + Compose plugin
# ══════════════════════════════════════════════════════════
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    ok "Docker and Compose plugin already installed."
else
    info "Installing Docker Engine..."
    # Remove old packages
    for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
        apt-get remove -y -qq "$pkg" 2>/dev/null || true
    done

    # Add Docker GPG key
    install -m 0755 -d /etc/apt/keyrings
    if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg
    fi

    # Add Docker repo
    ARCH=$(dpkg --print-architecture)
    CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
    echo \
      "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      ${CODENAME} stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin > /dev/null 2>&1
    systemctl enable --now docker
    ok "Docker Engine installed."
fi

# ══════════════════════════════════════════════════════════
# 4. GPU detection + nvidia-container-toolkit
# ══════════════════════════════════════════════════════════
GPU_MODE=false
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    info "NVIDIA GPU detected. Setting up GPU support..."
    GPU_MODE=true

    if ! dpkg -l | grep -q nvidia-container-toolkit; then
        # Install nvidia-container-toolkit
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
            gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null || true
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
        apt-get update -qq
        apt-get install -y -qq nvidia-container-toolkit > /dev/null 2>&1
        nvidia-ctk runtime configure --runtime=docker
        systemctl restart docker
        ok "nvidia-container-toolkit installed and configured."
    else
        ok "nvidia-container-toolkit already installed."
    fi
else
    info "No NVIDIA GPU detected (or nvidia-smi not available). Using CPU mode."
fi

# ══════════════════════════════════════════════════════════
# 5. Setup project directory + .env
# ══════════════════════════════════════════════════════════
info "Setting up project in ${PROJECT_DIR}..."

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
    cp "${PROJECT_DIR}/.env.example" "${PROJECT_DIR}/.env"
    ok "Created .env from .env.example. Review and customize it."
else
    ok ".env already exists."
fi

mkdir -p "${PROJECT_DIR}/out"

# Determine MailHog profile
source "${PROJECT_DIR}/.env"
if [[ "${MAILHOG_ENABLED:-false}" == "true" ]]; then
    COMPOSE_PROFILES="--profile mailhog"
    info "MailHog enabled."
fi

# ══════════════════════════════════════════════════════════
# 6. Build and start containers
# ══════════════════════════════════════════════════════════
info "Pulling and building Docker images..."
cd "${PROJECT_DIR}"

COMPOSE_CMD="docker compose"
if [[ "${GPU_MODE}" == "true" ]]; then
    COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.gpu.yml"
    info "Using GPU overlay for Ollama."
fi

${COMPOSE_CMD} ${COMPOSE_PROFILES} pull --ignore-pull-failures 2>/dev/null || true
${COMPOSE_CMD} ${COMPOSE_PROFILES} build --quiet
${COMPOSE_CMD} ${COMPOSE_PROFILES} up -d

ok "All containers started."

# ══════════════════════════════════════════════════════════
# 7. Bootstrap: migrations + model pulls
# ══════════════════════════════════════════════════════════
info "Waiting for PostgreSQL to be healthy..."
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-cyberagent}" &> /dev/null; then
        ok "PostgreSQL is ready."
        break
    fi
    if [[ $i -eq 30 ]]; then
        die "PostgreSQL did not become healthy in time."
    fi
    sleep 2
done

info "Running Alembic migrations..."
docker compose exec -T api alembic -c /opt/app/alembic.ini upgrade head
ok "Migrations complete."

info "Waiting for Ollama to be ready..."
for i in $(seq 1 60); do
    if docker compose exec -T ollama curl -sf http://localhost:11434/api/tags &> /dev/null; then
        ok "Ollama is ready."
        break
    fi
    if [[ $i -eq 60 ]]; then
        die "Ollama did not become healthy in time."
    fi
    sleep 5
done

WRITER_MODEL="${MODEL_WRITER:-mistral}"
CRITIC_MODEL="${MODEL_CRITIC:-deepseek-r1:7b}"

info "Pulling LLM model: ${WRITER_MODEL}..."
docker compose exec -T ollama ollama pull "${WRITER_MODEL}"
ok "Model ${WRITER_MODEL} pulled."

info "Pulling LLM model: ${CRITIC_MODEL}..."
docker compose exec -T ollama ollama pull "${CRITIC_MODEL}"
ok "Model ${CRITIC_MODEL} pulled."

# Warmup + immediate unload
info "Warming up models (with immediate unload)..."
docker compose exec -T ollama curl -sf http://localhost:11434/api/chat -d "{
  \"model\": \"${WRITER_MODEL}\",
  \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}],
  \"stream\": false,
  \"keep_alive\": \"0\"
}" > /dev/null 2>&1 && ok "Writer warmup done." || warn "Writer warmup failed (non-critical)."

docker compose exec -T ollama curl -sf http://localhost:11434/api/chat -d "{
  \"model\": \"${CRITIC_MODEL}\",
  \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}],
  \"stream\": false,
  \"keep_alive\": \"0\"
}" > /dev/null 2>&1 && ok "Critic warmup done." || warn "Critic warmup failed (non-critical)."

# ══════════════════════════════════════════════════════════
# 8. Smoke tests
# ══════════════════════════════════════════════════════════
info "Running smoke tests..."

# API health
sleep 3
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health 2>/dev/null || echo "000")
if [[ "${HTTP_CODE}" == "200" ]]; then
    ok "API health check passed."
else
    warn "API health check returned ${HTTP_CODE}. It may still be starting."
fi

# Ollama models
MODELS=$(docker compose exec -T ollama curl -sf http://localhost:11434/api/tags 2>/dev/null | jq -r '.models[].name' 2>/dev/null || echo "")
if echo "${MODELS}" | grep -q "${WRITER_MODEL}"; then
    ok "Writer model (${WRITER_MODEL}) available."
else
    warn "Writer model (${WRITER_MODEL}) not found in Ollama."
fi
if echo "${MODELS}" | grep -q "${CRITIC_MODEL}"; then
    ok "Critic model (${CRITIC_MODEL}) available."
else
    warn "Critic model (${CRITIC_MODEL}) not found in Ollama."
fi

# ══════════════════════════════════════════════════════════
# 9. Final instructions
# ══════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Cyber News Agent — Installation Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BLUE}Project directory:${NC}  ${PROJECT_DIR}"
echo -e "  ${BLUE}GPU mode:${NC}           ${GPU_MODE}"
echo ""
echo -e "  ${BLUE}View logs:${NC}"
echo "    docker compose logs -f worker"
echo "    docker compose logs -f api"
echo ""
echo -e "  ${BLUE}Trigger manual run:${NC}"
echo "    docker compose exec worker python -m app.pipeline.run_daily --dry-run"
echo ""
echo -e "  ${BLUE}API:${NC}"
echo "    curl http://127.0.0.1:8000/health"
echo "    curl http://127.0.0.1:8000/api/runs"
echo "    curl -X POST http://127.0.0.1:8000/api/trigger"
echo ""
if [[ "${MAILHOG_ENABLED:-false}" == "true" ]]; then
    echo -e "  ${BLUE}MailHog UI:${NC}"
    echo "    http://127.0.0.1:8025"
    echo ""
fi
echo -e "  ${BLUE}Newsletter output:${NC}"
echo "    ${PROJECT_DIR}/out/latest.html"
echo "    ${PROJECT_DIR}/out/latest.json"
echo ""
echo -e "  ${BLUE}Daily schedule:${NC}  ${DAILY_RUN_TIME:-06:30} (${TZ:-Africa/Tunis})"
echo ""
echo -e "  ${YELLOW}Remember to review and customize .env before production use.${NC}"
echo ""
