#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
# Ubuntu 24.04 Hardening Script for Cyber News Agent VM
# ══════════════════════════════════════════════════════════
# Run as root: sudo ./hardening/harden.sh
#
# IMPORTANT: Ensure SSH key-based auth works BEFORE running.
# This script disables password authentication.
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
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root."
    exit 1
fi

echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Ubuntu 24.04 Hardening — Cyber News Agent VM${NC}"
echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
echo ""

# ── 1. System updates ────────────────────────────────────
info "Applying system updates..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq > /dev/null 2>&1
ok "System updated."

# ── 2. Install security packages ─────────────────────────
info "Installing security packages..."
apt-get install -y -qq \
    ufw \
    fail2ban \
    auditd \
    audispd-plugins \
    unattended-upgrades \
    apt-listchanges \
    libpam-pwquality \
    rkhunter \
    lynis \
    aide \
    > /dev/null 2>&1
ok "Security packages installed."

# ── 3. Automatic security updates ────────────────────────
info "Configuring unattended-upgrades..."
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'AUTOCONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Download-Upgradeable-Packages "1";
AUTOCONF

# Enable only security updates
cat > /etc/apt/apt.conf.d/50unattended-upgrades <<'UUCONF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::SyslogEnable "true";
UUCONF
ok "Unattended upgrades configured."

# ── 4. SSH hardening ─────────────────────────────────────
info "Hardening SSH..."
cp "${SCRIPT_DIR}/sshd_hardened.conf" /etc/ssh/sshd_config.d/99-hardened.conf
chmod 644 /etc/ssh/sshd_config.d/99-hardened.conf

# Test SSH config before reloading
if sshd -t 2>/dev/null; then
    systemctl reload sshd 2>/dev/null || systemctl reload ssh 2>/dev/null || true
    ok "SSH hardened."
else
    warn "SSH config test failed — skipping reload. Check /etc/ssh/sshd_config.d/99-hardened.conf"
fi

# ── 5. Kernel hardening (sysctl) ─────────────────────────
info "Applying kernel hardening parameters..."
cp "${SCRIPT_DIR}/sysctl_hardened.conf" /etc/sysctl.d/99-hardened.conf
sysctl --system > /dev/null 2>&1
ok "Kernel parameters hardened."

# ── 6. Firewall (UFW) ───────────────────────────────────
info "Configuring firewall..."
bash "${SCRIPT_DIR}/firewall.sh"
ok "Firewall configured."

# ── 7. Fail2ban ──────────────────────────────────────────
info "Configuring fail2ban..."
cp "${SCRIPT_DIR}/fail2ban_jail.local" /etc/fail2ban/jail.local
systemctl enable fail2ban
systemctl restart fail2ban
ok "Fail2ban configured."

# ── 8. File permissions ──────────────────────────────────
info "Tightening file permissions..."

# Restrict cron access
chmod 600 /etc/crontab
chmod 700 /etc/cron.d /etc/cron.daily /etc/cron.hourly /etc/cron.monthly /etc/cron.weekly 2>/dev/null || true

# Restrict at access
if [[ -f /etc/at.deny ]]; then chmod 600 /etc/at.deny; fi

# SSH directory permissions
chmod 700 /root/.ssh 2>/dev/null || true
chmod 600 /root/.ssh/authorized_keys 2>/dev/null || true

# Shadow and password files
chmod 640 /etc/shadow
chmod 644 /etc/passwd
chmod 644 /etc/group

# Boot loader config
chmod 600 /boot/grub/grub.cfg 2>/dev/null || true

ok "File permissions tightened."

# ── 9. Disable unnecessary services ─────────────────────
info "Disabling unnecessary services..."
for svc in avahi-daemon cups bluetooth whoopsie apport; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        systemctl stop "$svc"
        systemctl disable "$svc"
        info "  Disabled: $svc"
    fi
done
ok "Unnecessary services disabled."

# ── 10. Audit logging ───────────────────────────────────
info "Configuring audit logging..."
systemctl enable auditd
systemctl start auditd

# Add basic audit rules
cat > /etc/audit/rules.d/cyber-agent.rules <<'AUDITRULES'
# Monitor authentication events
-w /etc/passwd -p wa -k identity
-w /etc/group -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/gshadow -p wa -k identity
-w /etc/sudoers -p wa -k sudoers
-w /etc/sudoers.d/ -p wa -k sudoers

# Monitor SSH config changes
-w /etc/ssh/sshd_config -p wa -k sshd_config
-w /etc/ssh/sshd_config.d/ -p wa -k sshd_config

# Monitor Docker config
-w /etc/docker/ -p wa -k docker_config
-w /var/lib/docker/ -p wa -k docker_files

# Monitor cron changes
-w /etc/crontab -p wa -k cron
-w /etc/cron.d/ -p wa -k cron

# Monitor login/logout
-w /var/log/auth.log -p wa -k auth_log
-w /var/log/faillog -p wa -k login_failures
-w /var/log/lastlog -p wa -k login

# Monitor privileged commands
-a always,exit -F arch=b64 -S execve -C uid!=euid -F euid=0 -k priv_escalation
AUDITRULES

augenrules --load > /dev/null 2>&1 || true
ok "Audit logging configured."

# ── 11. Password policy ─────────────────────────────────
info "Configuring password policy..."
# Only if PAM pwquality is available
if [[ -f /etc/pam.d/common-password ]]; then
    cat > /etc/security/pwquality.conf <<'PWQUAL'
minlen = 12
dcredit = -1
ucredit = -1
lcredit = -1
ocredit = -1
maxrepeat = 3
maxclassrepeat = 4
PWQUAL
    ok "Password policy configured."
fi

# ── 12. Docker hardening ────────────────────────────────
info "Hardening Docker daemon..."
mkdir -p /etc/docker
# Only write if not already customized
if [[ ! -f /etc/docker/daemon.json ]] || ! grep -q "no-new-privileges" /etc/docker/daemon.json 2>/dev/null; then
    cat > /etc/docker/daemon.json <<'DOCKERCONF'
{
    "no-new-privileges": true,
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "50m",
        "max-file": "3"
    },
    "live-restore": true,
    "userns-remap": "",
    "icc": false,
    "default-ulimits": {
        "nofile": {
            "Name": "nofile",
            "Hard": 65536,
            "Soft": 32768
        }
    }
}
DOCKERCONF
    systemctl restart docker 2>/dev/null || true
    ok "Docker daemon hardened."
else
    ok "Docker daemon.json already customized — skipping."
fi

# ── 13. Login banner ────────────────────────────────────
cat > /etc/issue.net <<'BANNER'
*******************************************************************
*  AUTHORIZED ACCESS ONLY — This system is monitored.            *
*  Unauthorized access attempts will be logged and reported.      *
*******************************************************************
BANNER
ok "Login banner set."

# ── Summary ──────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Hardening Complete!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Applied:"
echo "  1.  System updates"
echo "  2.  Unattended security upgrades"
echo "  3.  SSH hardening (key-only, no root login)"
echo "  4.  Kernel sysctl hardening"
echo "  5.  UFW firewall (deny all incoming, allow SSH)"
echo "  6.  Fail2ban (SSH + HTTP protection)"
echo "  7.  File permission tightening"
echo "  8.  Disabled unnecessary services"
echo "  9.  Audit logging (auditd)"
echo "  10. Password policy (pwquality)"
echo "  11. Docker daemon hardening"
echo "  12. Login banner"
echo ""
echo "Next steps:"
echo "  - Run: sudo ./hardening/audit.sh  (to verify)"
echo "  - Run: sudo lynis audit system     (full CIS audit)"
echo "  - Review: /var/log/audit/audit.log"
echo ""
warn "IMPORTANT: Verify SSH key auth works before disconnecting!"
