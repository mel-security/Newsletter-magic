#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
# Cyber News Agent — Uninstaller
# ══════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${RED}════════════════════════════════════════════════════════${NC}"
echo -e "${RED}  Cyber News Agent — Uninstaller${NC}"
echo -e "${RED}════════════════════════════════════════════════════════${NC}"
echo ""
echo "This will:"
echo "  1. Stop and remove all containers"
echo "  2. Remove Docker volumes (database, redis, ollama models)"
echo "  3. Remove generated output files"
echo ""
read -rp "Are you sure? (y/N): " confirm
if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

cd "${PROJECT_DIR}"

info "Stopping containers..."
docker compose --profile mailhog down --remove-orphans 2>/dev/null || true
ok "Containers stopped."

read -rp "Remove Docker volumes (database, models)? (y/N): " remove_vols
if [[ "${remove_vols}" == "y" || "${remove_vols}" == "Y" ]]; then
    docker compose --profile mailhog down -v 2>/dev/null || true
    ok "Volumes removed."
else
    info "Volumes preserved."
fi

read -rp "Remove output files? (y/N): " remove_out
if [[ "${remove_out}" == "y" || "${remove_out}" == "Y" ]]; then
    rm -rf "${PROJECT_DIR}/out"
    ok "Output files removed."
fi

echo ""
ok "Uninstall complete. The project directory remains at ${PROJECT_DIR}."
echo "To fully remove, delete the directory: rm -rf ${PROJECT_DIR}"
