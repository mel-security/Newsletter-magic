#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
# UFW Firewall Configuration for Cyber News Agent VM
# ══════════════════════════════════════════════════════════
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root." >&2
    exit 1
fi

echo "[INFO] Configuring UFW firewall..."

# Reset to defaults (idempotent)
ufw --force reset > /dev/null 2>&1

# Default policies
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (adjust port if needed)
ufw allow 22/tcp comment "SSH"

# NOTE: API (8000) and MailHog (8025) bind to 127.0.0.1 only.
# They do NOT need firewall rules since they never listen on
# external interfaces. This is security-by-design.

# Optionally allow SSH from specific IP only (uncomment and edit):
# ufw delete allow 22/tcp
# ufw allow from 192.168.1.0/24 to any port 22 proto tcp comment "SSH from LAN only"

# Rate limit SSH to prevent brute-force
ufw limit 22/tcp comment "Rate-limit SSH"

# Enable
ufw --force enable

echo "[OK] UFW firewall active."
ufw status verbose
