#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
# Cyber News Agent — Upgrade Script
# ══════════════════════════════════════════════════════════
set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${PROJECT_DIR}"

info "Pulling latest changes..."
git pull --ff-only 2>/dev/null || warn "Not a git repo or no remote. Skipping git pull."

info "Rebuilding containers..."
source "${PROJECT_DIR}/.env" 2>/dev/null || true

COMPOSE_PROFILES=""
if [[ "${MAILHOG_ENABLED:-false}" == "true" ]]; then
    COMPOSE_PROFILES="--profile mailhog"
fi

GPU_MODE=false
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    GPU_MODE=true
fi

COMPOSE_CMD="docker compose"
if [[ "${GPU_MODE}" == "true" ]]; then
    COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.gpu.yml"
fi

${COMPOSE_CMD} ${COMPOSE_PROFILES} build --quiet
${COMPOSE_CMD} ${COMPOSE_PROFILES} up -d

info "Running migrations..."
sleep 5
docker compose exec -T api alembic -c /opt/app/alembic.ini upgrade head
ok "Migrations complete."

ok "Upgrade complete."
echo ""
echo "Check logs: docker compose logs -f worker"
