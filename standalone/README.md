# Standalone Newsletter Agent — Portable One-Shot Edition

A lightweight, portable version of the Cyber News Agent that runs **locally with a single command** — no Docker, no databases, no background services. Just install, configure, and run.

## How It Works

```
run.py → Search (Google News + Bing) → Extract articles → Sanitize
       → Score & rank → Pick headline story
       → Writer LLM generates newsletter → Reviewer LLM feedback loop
       → Render HTML → Save to output/
```

## Quick Start

```bash
# 1. Install (pick your OS)
./install-ubuntu.sh    # Ubuntu/Debian
./install-mac.sh       # macOS
# or: install-windows.bat  # Windows

# 2. Edit config
cp config/context.yml.example config/context.yml
# Edit context.yml to set your topic focus

# 3. Run
source .venv/bin/activate
python run.py

# Output is in output/newsletter_YYYY-MM-DD.html
```

## Platform Support

| Platform | Script | Python | Ollama | Default Models |
|----------|--------|--------|--------|----------------|
| Ubuntu/Debian | `install-ubuntu.sh` | System + venv | Auto-installed | mistral + deepseek-r1:7b |
| macOS | `install-mac.sh` | Homebrew + venv | Auto-installed | mistral + deepseek-r1:7b |
| Windows | `install-windows.bat` | winget/python.org + venv | Manual download | mistral + deepseek-r1:7b |

## Configuration

### Context File (`config/context.yml`)

This is the **key file** that makes the agent multi-purpose. Change the topic and queries to generate newsletters about anything:

```yaml
topic: "Cybersecurity"           # or "AI", "Cloud", "Finance", anything
model: "mistral"                 # Writer LLM
reviewer_model: "deepseek-r1:7b" # Reviewer LLM for feedback loop
queries:
  - "cybersecurity vulnerability news"
  - "ransomware attack today"
```

See `config/context.yml.example` for all options.

### Newsletter Structure

Each generated newsletter contains:

1. **Headline Story** — The most important story of the period with:
   - Full context and background
   - Detailed description of what happened
   - Key takeaways (bullet points)
   - Actionable recommendations

2. **Noteworthy News** — 5-10 other important stories, each with a brief summary and source link

3. **Weekly Reflection** — AI-generated analysis of trends, patterns, and what to watch for

### Dual-LLM Architecture

The agent uses two LLM roles:

- **Writer** (`--llmwriter`, default: `mistral`) — Generates all newsletter content
- **Reviewer** (`--reviewer`, default: `deepseek-r1:7b`) — Reviews and provides feedback on the writer's output. If not specified, uses the same model as the writer (single-LLM mode).

When both models are different, the reviewer checks the headline story and noteworthy summaries, requesting improvements if needed. Models are unloaded after each call (`keep_alive=0`) so both can share limited RAM.

## CLI Options

```bash
python run.py                                          # Full run with defaults
python run.py --dry-run                                # Search + score only, no LLM
python run.py --config config/ai.yml                   # Use custom context file
python run.py --llmwriter mistral                      # Override writer model
python run.py --reviewer deepseek-r1:7b                # Override reviewer model
python run.py --llmwriter mistral --reviewer mistral   # Same model, no review loop
```

## Requirements

- Python 3.11+
- Ollama (installed automatically by install scripts)
- Internet connection (for web search)
- ~8GB disk for both LLM models (mistral ~4GB + deepseek-r1:7b ~4GB)
- 8GB+ RAM recommended (models are unloaded between calls)
