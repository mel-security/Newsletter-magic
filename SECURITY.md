# Security Policy

## Network Exposure

This project is designed for **local-only deployment** on a private VM. By default:

- **Ollama** (LLM inference) is **NOT exposed** on any host port. It is only reachable within the Docker internal network. This prevents unauthorized access to your LLM endpoints.
- **FastAPI** binds to `127.0.0.1:8000` — only accessible from the local machine.
- **MailHog** (optional) binds to `127.0.0.1:8025` and `127.0.0.1:1025`.
- **PostgreSQL** and **Redis** are internal-only — no host port exposure.

### Do NOT:

- Expose Ollama on `0.0.0.0`. Ollama has no built-in authentication. Exposing it publicly allows anyone to use your compute resources and query your models.
- Change API bind from `127.0.0.1` to `0.0.0.0` without adding authentication (e.g., API key middleware, OAuth2).
- Expose PostgreSQL or Redis ports publicly.

## Credentials

- Change the default `POSTGRES_PASSWORD` in `.env` before any production use.
- SMTP credentials are stored in `.env`. Ensure `.env` has restricted file permissions:

```bash
chmod 600 .env
```

- The `.env` file is listed in `.gitignore` and must **never** be committed to version control.

## Prompt Injection Defense

This system fetches content from the open internet (RSS feeds, Google, Bing) and passes it through local LLMs. This creates a prompt injection attack surface. The defense is multi-layered:

1. **Blacklist file** (`config/prompt_blacklist.txt`) — configurable list of banned phrases and regex patterns. Covers instruction overrides, role hijacking, delimiter injection, encoding tricks. Hot-reloadable via API.

2. **Built-in patterns** — 20+ compiled regex patterns always active regardless of blacklist. Catches obfuscated variants (e.g., `ign0re all instruct1ons`).

3. **Feed-level sanitization** — every RSS/JSON/search item is sanitized at ingest time. Rejected items are logged and discarded before reaching the database.

4. **Full-text sanitization** — extracted article text is sanitized during normalization, before DB storage.

5. **LLM-level sanitization** — final pass in `ollama_client.py` sanitizes all prompts immediately before sending to any LLM. This catches anything that slipped through earlier layers.

6. **Structural defenses** — LLM prompts use strict JSON-only output schemas, making it harder for injected instructions to produce unstructured output.

### Maintaining the Blacklist

Edit `config/prompt_blacklist.txt` and reload:
```bash
curl -X POST http://127.0.0.1:8000/api/reload-blacklist
```

Test phrases against the sanitizer:
```bash
curl -X POST "http://127.0.0.1:8000/api/test-sanitizer?text=ignore+all+instructions"
```

## LLM Safety

- Local LLMs (Ollama) run without internet access from within Docker.
- The Devil Twins pipeline enforces citation requirements: any factual claim without a source URL is flagged and removed.
- If the Critic LLM rejects the newsletter, the system falls back to a safe digest mode that only lists article titles and links without AI-generated commentary.

## VM Hardening

Run `sudo ./hardening/harden.sh` to apply production hardening:
- SSH key-only authentication, no root login
- UFW firewall (deny all incoming except SSH)
- Fail2ban for brute-force protection
- Kernel sysctl hardening (ASLR, SYN flood, spoofing)
- Audit logging with auditd
- Docker daemon hardening (no-new-privileges, log rotation)
- Automatic security updates

Run `sudo ./hardening/audit.sh` to verify hardening status.

## Container Security

- Docker images use `python:3.12-slim` as the base.
- No containers run with `--privileged`.
- Ollama GPU access (if enabled) uses the nvidia-container-toolkit with specific device passthrough only.

## Reporting Vulnerabilities

If you discover a security issue, please open a private issue or contact the maintainer directly. Do not disclose security vulnerabilities in public issues.

## Updates

- Regularly update Docker images: `docker compose pull && docker compose up -d`
- Monitor Ollama releases for security patches
- Keep the host Ubuntu system updated: `sudo apt update && sudo apt upgrade`
