#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
# Security Audit Script — Check hardening status
# ══════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
WARN=0
FAIL=0

pass() { echo -e "  ${GREEN}[PASS]${NC} $*"; ((PASS++)); }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $*"; ((WARN++)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $*"; ((FAIL++)); }

echo "══════════════════════════════════════════════════════════"
echo "  Security Audit — $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════════════════"
echo ""

# ── SSH ──────────────────────────────────────────────────
echo "SSH Configuration:"
if sshd -T 2>/dev/null | grep -qi "permitrootlogin no"; then
    pass "Root login disabled"
else
    fail "Root login NOT disabled"
fi

if sshd -T 2>/dev/null | grep -qi "passwordauthentication no"; then
    pass "Password authentication disabled"
else
    warn "Password authentication is enabled"
fi

if sshd -T 2>/dev/null | grep -qi "x11forwarding no"; then
    pass "X11 forwarding disabled"
else
    warn "X11 forwarding is enabled"
fi
echo ""

# ── Firewall ─────────────────────────────────────────────
echo "Firewall:"
if ufw status 2>/dev/null | grep -q "Status: active"; then
    pass "UFW is active"
else
    fail "UFW is NOT active"
fi
echo ""

# ── Fail2ban ─────────────────────────────────────────────
echo "Fail2ban:"
if systemctl is-active --quiet fail2ban 2>/dev/null; then
    pass "Fail2ban is running"
    JAILS=$(fail2ban-client status 2>/dev/null | grep "Jail list" | sed 's/.*:\s*//')
    pass "Active jails: ${JAILS}"
else
    fail "Fail2ban is NOT running"
fi
echo ""

# ── Kernel hardening ─────────────────────────────────────
echo "Kernel Security:"
if [[ "$(sysctl -n net.ipv4.conf.all.rp_filter 2>/dev/null)" == "1" ]]; then
    pass "IP spoofing protection (rp_filter)"
else
    fail "IP spoofing protection NOT enabled"
fi

if [[ "$(sysctl -n net.ipv4.tcp_syncookies 2>/dev/null)" == "1" ]]; then
    pass "SYN flood protection (syncookies)"
else
    fail "SYN flood protection NOT enabled"
fi

if [[ "$(sysctl -n kernel.randomize_va_space 2>/dev/null)" == "2" ]]; then
    pass "ASLR enabled"
else
    fail "ASLR NOT fully enabled"
fi

if [[ "$(sysctl -n kernel.kptr_restrict 2>/dev/null)" == "2" ]]; then
    pass "Kernel pointer restriction"
else
    warn "Kernel pointers may be exposed"
fi
echo ""

# ── Auto-updates ─────────────────────────────────────────
echo "Automatic Updates:"
if dpkg -l | grep -q unattended-upgrades 2>/dev/null; then
    pass "unattended-upgrades installed"
else
    fail "unattended-upgrades NOT installed"
fi
echo ""

# ── Docker ───────────────────────────────────────────────
echo "Docker Security:"
if docker info 2>/dev/null | grep -q "no-new-privileges: true"; then
    pass "Docker no-new-privileges enabled"
else
    warn "Docker no-new-privileges NOT set"
fi

# Check if any containers expose ports on 0.0.0.0
EXPOSED=$(docker ps --format '{{.Ports}}' 2>/dev/null | grep "0.0.0.0" || true)
if [[ -z "${EXPOSED}" ]]; then
    pass "No containers expose ports on 0.0.0.0"
else
    warn "Containers with public port bindings: ${EXPOSED}"
fi
echo ""

# ── Audit daemon ─────────────────────────────────────────
echo "Audit Logging:"
if systemctl is-active --quiet auditd 2>/dev/null; then
    pass "auditd is running"
else
    warn "auditd is NOT running"
fi
echo ""

# ── File permissions ─────────────────────────────────────
echo "File Permissions:"
SHADOW_PERMS=$(stat -c %a /etc/shadow 2>/dev/null || echo "000")
if [[ "${SHADOW_PERMS}" == "640" || "${SHADOW_PERMS}" == "600" ]]; then
    pass "/etc/shadow permissions: ${SHADOW_PERMS}"
else
    fail "/etc/shadow permissions too open: ${SHADOW_PERMS}"
fi

CRONTAB_PERMS=$(stat -c %a /etc/crontab 2>/dev/null || echo "000")
if [[ "${CRONTAB_PERMS}" == "600" ]]; then
    pass "/etc/crontab permissions: ${CRONTAB_PERMS}"
else
    warn "/etc/crontab permissions: ${CRONTAB_PERMS} (should be 600)"
fi
echo ""

# ── Listening ports ──────────────────────────────────────
echo "Listening Ports:"
ss -tlnp 2>/dev/null | grep LISTEN | while read -r line; do
    if echo "$line" | grep -q "0.0.0.0\|:::"; then
        PORT=$(echo "$line" | awk '{print $4}')
        PROC=$(echo "$line" | awk '{print $6}')
        if echo "$PORT" | grep -qE "(:22$|\*:22$)"; then
            pass "SSH on ${PORT}"
        else
            warn "Public listener: ${PORT} (${PROC})"
        fi
    fi
done
echo ""

# ── Summary ──────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════"
echo -e "  Results: ${GREEN}${PASS} PASS${NC}  ${YELLOW}${WARN} WARN${NC}  ${RED}${FAIL} FAIL${NC}"
echo "══════════════════════════════════════════════════════════"

if [[ ${FAIL} -gt 0 ]]; then
    echo ""
    echo "Run ./hardening/harden.sh to fix failing checks."
    exit 1
fi
