# Cyber News Agent

Autonomous cybersecurity newsletter agent powered by local LLMs using the **Devil Twins** architecture — a Writer LLM drafts the newsletter while a Critic LLM reviews, flags issues, and enforces citation standards.

## Architecture

```
┌─────────────┐
│  RSS/JSON   │──┐
│  Sources    │  │   ┌──────────┐   ┌──────────┐   ┌──────────┐
├─────────────┤  ├──▸│  Ingest  │──▸│ Sanitize │──▸│  Dedup   │
│Google Search│  │   │ +Search  │   │+Normalize│   │ (simhash)│
│Google News  │──┘   └──────────┘   └──────────┘   └────┬─────┘
│Bing Search  │           │                              │
└─────────────┘           ▼                              ▼
              ┌──────────────────┐              ┌──────────────┐
              │  Prompt Inject.  │              │   Extract    │
              │  Blacklist       │              │   IOC/CVE    │
              │  Sanitizer       │              └──────┬───────┘
              └──────────────────┘                     ▼
                                                ┌──────────┐
    ┌──────────┐   ┌──────────┐                 │  Score   │
    │  Email   │◂──│  Render  │                 └────┬─────┘
    │(SMTP/MH) │   │ (Jinja2) │                      ▼
    └──────────┘   └────┬─────┘                 ┌──────────┐
                        │                       │ Cluster  │
                   ┌────┴─────┐                 │→ Stories │
                   │Newsletter│◂────────────────└──────────┘
                   │Devil Twin│
                   └────┬─────┘
                        │
               ┌────────┴───────┐
               │    Ollama       │
               │ Writer + Critic │
               └────────────────┘
```

## Requirements

- **OS**: Ubuntu Server 24.04 LTS (amd64)
- **RAM**: 16GB recommended (12GB minimum)
- **CPU**: 6-8 vCPU recommended
- **Disk**: 80GB+ recommended (30GB minimum free)
- **GPU**: Optional — NVIDIA GPU with CUDA support auto-detected

## Quick Start

```bash
# Clone the repository
git clone <repo-url> /opt/cyber-news-agent
cd /opt/cyber-news-agent

# Run the installer (as root)
sudo ./install.sh

# Harden the VM (recommended)
sudo ./hardening/harden.sh
```

That's it. The installer will:
1. Install Docker Engine + Compose
2. Detect GPU and configure nvidia-container-toolkit if available
3. Start all services (Postgres, Redis, Ollama, API, Worker, Scheduler)
4. Run database migrations
5. Pull LLM models (mistral + deepseek-r1:7b)
6. Run smoke tests

## Services

| Service    | Port              | Description                          |
|-----------|-------------------|--------------------------------------|
| API       | 127.0.0.1:8000    | FastAPI — health, runs, trigger      |
| MailHog   | 127.0.0.1:8025    | Email testing UI (optional)          |
| Postgres  | internal only     | Database                             |
| Redis     | internal only     | Celery broker + backend              |
| Ollama    | internal only     | LLM inference (never exposed)        |

## Configuration

### Environment Variables (.env)

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Key settings:
- `MODEL_WRITER` / `MODEL_CRITIC` — Ollama model names
- `DAILY_RUN_TIME` — Cron time for daily newsletter (default: 06:30)
- `TZ` — Timezone (default: Africa/Tunis)
- `SMTP_*` — Email delivery settings
- `MAILHOG_ENABLED` — Enable MailHog for local testing
- `LANG` — Newsletter language (fr/en)
- `MAX_STORIES` — Max stories per newsletter
- `OLLAMA_KEEP_ALIVE=0` — Unload models after each call (saves RAM)
- `SEARCH_ENABLED` — Enable autonomous web search (Google/Bing)

### Sources (config/sources.yml)

Add or remove RSS/JSON feeds. Each source has:
- `name` — Display name
- `url` — Feed URL
- `type` — `rss` or `json`
- `reliability` — 0.0 to 1.0 (used in scoring)

### Search Engines (config/search_queries.yml)

Configure autonomous web search beyond RSS feeds:
- `enabled_engines` — List of engines: `google`, `google_news`, `bing`
- `queries` — Cybersecurity search queries (customizable)
- `results_per_query` — Max results per query per engine

Search results are automatically ingested alongside RSS feeds, deduplicated, and scored the same way.

### Scoring (config/scoring.yml)

Configure weights for article prioritization: recency, source reliability, keyword matches, CVE/IOC presence, exploit hints.

### Prompt Injection Blacklist (config/prompt_blacklist.txt)

The sanitizer uses this file to detect and block prompt injection attempts in fetched content. Supports:
- Plain text phrases (case-insensitive substring match)
- Regex patterns (lines starting with `regex:`)
- Comments (lines starting with `#`)

Hot-reload without restart:
```bash
curl -X POST http://127.0.0.1:8000/api/reload-blacklist
```

## Usage

### Manual Pipeline Run

```bash
# Dry run (no email sent)
docker compose exec worker python -m app.pipeline.run_daily --dry-run

# Full run
docker compose exec worker python -m app.pipeline.run_daily
```

### API Endpoints

```bash
# Health check
curl http://127.0.0.1:8000/health

# Trigger pipeline via API
curl -X POST http://127.0.0.1:8000/api/trigger
curl -X POST "http://127.0.0.1:8000/api/trigger?dry_run=true"

# List recent runs
curl http://127.0.0.1:8000/api/runs

# List top stories
curl http://127.0.0.1:8000/api/stories

# Reload prompt injection blacklist
curl -X POST http://127.0.0.1:8000/api/reload-blacklist

# Test sanitizer
curl -X POST "http://127.0.0.1:8000/api/test-sanitizer?text=ignore+all+instructions"
```

### View Logs

```bash
docker compose logs -f worker      # Pipeline execution
docker compose logs -f api         # API server
docker compose logs -f scheduler   # Celery beat
docker compose logs -f ollama      # LLM inference
```

### Output Files

- `out/latest.html` — Rendered HTML newsletter
- `out/latest.json` — Structured JSON output

## Prompt Injection Defense

All content from the internet passes through a multi-layer sanitizer before reaching the DB or any LLM:

1. **Blacklist matching** (`config/prompt_blacklist.txt`) — blocks known injection phrases
2. **Built-in pattern detection** — 20+ regex patterns catch instruction overrides, role hijacking, delimiter injection, encoding tricks
3. **Marker stripping** — removes `<system>`, `[INST]`, `<<SYS>>` style delimiters
4. **LLM-level defense** — final sanitization pass right before sending any text to Ollama
5. **Length truncation** — prevents resource abuse via extremely long injected text

Pipeline stats track `sanitizer_rejected` counts per run. Review in `/api/runs`.

To test the sanitizer:
```bash
curl -X POST "http://127.0.0.1:8000/api/test-sanitizer?text=ignore+all+previous+instructions"
# Returns: {"cleaned_text": "", "report": {"action": "rejected", ...}}
```

## Devil Twins Pipeline

The newsletter generation uses two competing LLMs:

1. **Writer** (mistral) generates a structured JSON newsletter draft
2. **Critic** (deepseek-r1:7b) reviews the draft:
   - Flags unsourced claims
   - Checks for inconsistencies and duplicates
   - Proposes fixes as structured patches
3. **Writer** revises based on critic feedback (v2)
4. **Critic** verifies v2 → PASS or FAIL
5. If FAIL → **safe fallback digest** (links only, no AI claims)

Memory management: `OLLAMA_KEEP_ALIVE=0` ensures each model is unloaded immediately after use, so both models can share 16GB RAM.

## Ubuntu Hardening

The `hardening/` folder contains production hardening scripts for the VM:

```bash
sudo ./hardening/harden.sh    # Full hardening (SSH, firewall, kernel, fail2ban, audit)
sudo ./hardening/audit.sh     # Security posture audit
sudo ./hardening/firewall.sh  # UFW firewall only
```

See `hardening/README.md` for details on what each script does.

## GPU Support

GPU support is auto-detected during installation. If an NVIDIA GPU is available:

```bash
# Verify GPU is detected
nvidia-smi

# The installer automatically uses the GPU overlay
# To manually start with GPU:
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

## Upgrade

```bash
sudo ./upgrade.sh
```

## Uninstall

```bash
sudo ./uninstall.sh
```

## Troubleshooting

### Ollama models not loading
```bash
# Check Ollama logs
docker compose logs ollama

# Manually pull models
docker compose exec ollama ollama pull mistral
docker compose exec ollama ollama pull deepseek-r1:7b

# List available models
docker compose exec ollama ollama list
```

### Pipeline failures
```bash
# Check run history
curl http://127.0.0.1:8000/api/runs | jq .

# Check worker logs
docker compose logs --tail=100 worker
```

### Database issues
```bash
# Connect to Postgres
docker compose exec postgres psql -U cyberagent

# Re-run migrations
docker compose exec api alembic -c /opt/app/alembic.ini upgrade head
```

### Sanitizer too aggressive
Edit `config/prompt_blacklist.txt` to remove false-positive entries, then:
```bash
curl -X POST http://127.0.0.1:8000/api/reload-blacklist
```

### Out of memory
- Ensure `OLLAMA_KEEP_ALIVE=0` is set in `.env`
- Reduce `MAX_STORIES` and `MAX_ARTICLES_PER_RUN`
- Consider using smaller models (e.g., `phi3:mini` as critic)

## License

MIT
