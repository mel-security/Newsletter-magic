# Ubuntu 24.04 Hardening for Cyber News Agent

Scripts and configurations to secure the Ubuntu VM hosting the Cyber News Agent.

## Scripts

| Script | Purpose |
|--------|---------|
| `harden.sh` | Main hardening script — run once after OS install |
| `audit.sh` | Security audit — checks current hardening status |
| `firewall.sh` | UFW firewall configuration |
| `sshd_hardened.conf` | Hardened SSH daemon configuration |
| `sysctl_hardened.conf` | Kernel security parameters |
| `fail2ban_jail.local` | Fail2ban configuration for SSH and API |

## Usage

```bash
# Run full hardening (as root)
sudo ./hardening/harden.sh

# Audit current security posture
sudo ./hardening/audit.sh

# Apply firewall rules only
sudo ./hardening/firewall.sh
```

## What harden.sh Does

1. **System updates** — Applies all security patches
2. **Automatic updates** — Enables unattended-upgrades for security
3. **SSH hardening** — Disables root login, password auth, enforces key-only
4. **Firewall (UFW)** — Blocks all incoming except SSH (configurable)
5. **Kernel hardening** — Sysctl parameters to mitigate common attacks
6. **Fail2ban** — Intrusion prevention for SSH and HTTP
7. **File permissions** — Locks down sensitive files
8. **Unnecessary services** — Disables what's not needed
9. **Audit logging** — Installs and configures auditd
10. **Docker hardening** — Restricts Docker daemon settings

## Important Notes

- Review each script before running — customize for your environment
- SSH key-based auth is REQUIRED before running (password auth gets disabled)
- The firewall blocks ALL incoming by default except SSH (port 22)
- API (8000) and MailHog (8025) remain on localhost only — no firewall rule needed
