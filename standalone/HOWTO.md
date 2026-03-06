# How to Use the Standalone Newsletter Agent

A step-by-step guide to installing, configuring, and running the portable newsletter agent on your local machine.

---

## Step 1: Install Prerequisites

Pick the script for your operating system:

### Ubuntu / Debian

```bash
cd standalone/
chmod +x install-ubuntu.sh
./install-ubuntu.sh
```

This will:
- Install Python 3.11+ and system dependencies via `apt`
- Create a Python virtual environment (`.venv/`)
- Install required Python packages (httpx, feedparser, trafilatura, etc.)
- Install Ollama (local LLM runtime)
- Pull `mistral` (writer) and `deepseek-r1:7b` (reviewer) models
- Create `config/context.yml` from the example template

### macOS

```bash
cd standalone/
chmod +x install-mac.sh
./install-mac.sh
```

This will:
- Install Homebrew (if not present)
- Install Python 3.12 via Homebrew
- Create a Python virtual environment
- Install Ollama via Homebrew
- Pull both LLM models

### Windows

```
cd standalone
install-windows.bat
```

This will:
- Install Python 3.12 via winget (or prompt manual install)
- Create a Python virtual environment
- Check for Ollama (must be installed manually from https://ollama.com)
- Pull both LLM models

---

## Step 2: Configure Your Newsletter

Edit `config/context.yml` to customize your newsletter topic:

```bash
# The installer creates this from the example template
# Edit it to match your interests
nano config/context.yml     # Linux/Mac
notepad config\context.yml  # Windows
```

### Key Settings

**Topic and identity:**
```yaml
topic: "Cybersecurity"                    # Your newsletter's focus area
tagline: "Weekly threat intelligence digest"  # Subtitle
lang: en                                  # Language (en, fr, etc.)
```

**LLM models:**
```yaml
model: "mistral"                # Writer LLM — generates content
reviewer_model: "deepseek-r1:7b"  # Reviewer LLM — provides feedback
temperature: 0.4                # Lower = more focused, higher = more creative
```

**Search queries** — these determine what the agent looks for:
```yaml
queries:
  - "cybersecurity vulnerability exploit news"
  - "ransomware attack today"
  - "zero-day vulnerability CVE"
  # Add or remove queries to shift focus
```

**Scoring keywords** — control which articles rank highest:
```yaml
scoring_keywords:
  critical:      # weight 5 — highest priority
    - zero-day
    - ransomware
    - data breach
  high:          # weight 3
    - CVE-
    - malware
    - phishing
  medium:        # weight 1
    - patch
    - vulnerability
```

### Example: AI/ML Newsletter

```yaml
topic: "Artificial Intelligence"
tagline: "Weekly AI and machine learning digest"
queries:
  - "artificial intelligence breakthrough news"
  - "large language model research"
  - "AI regulation policy"
  - "machine learning production deployment"
scoring_keywords:
  critical:
    - breakthrough
    - GPT
    - state-of-the-art
  high:
    - transformer
    - fine-tuning
    - benchmark
  medium:
    - dataset
    - training
    - inference
```

### Example: Cloud Infrastructure Newsletter

```yaml
topic: "Cloud Infrastructure"
tagline: "Weekly cloud and DevOps digest"
queries:
  - "AWS Azure GCP outage incident"
  - "Kubernetes security vulnerability"
  - "cloud infrastructure news"
  - "DevOps platform update"
scoring_keywords:
  critical:
    - outage
    - data loss
    - security breach
  high:
    - Kubernetes
    - zero-day
    - CVE
  medium:
    - migration
    - deployment
    - scaling
```

---

## Step 3: Run the Agent

Activate the virtual environment and run:

```bash
# Linux/Mac
source .venv/bin/activate
python run.py

# Windows
.venv\Scripts\activate.bat
python run.py
```

### What Happens

The agent runs through 7 steps:

```
[1/7] Loading configuration...       # Reads context.yml
[2/7] Searching the internet...      # Queries Google News, Google, Bing
[3/7] Extracting article content...  # Fetches full text from URLs
[4/7] Scoring and ranking articles...# Ranks by keyword relevance
[5/7] Generating headline story...   # Writer LLM + Reviewer feedback
[6/7] Generating noteworthy news...  # Summarizes remaining top stories
[7/7] Weekly reflection + render...  # Trend analysis + HTML output
```

Total runtime: 5-15 minutes depending on internet speed and LLM performance.

### Output

The newsletter is saved to the `output/` folder:
- `output/newsletter_2025-03-06.html` — Rendered HTML newsletter (open in any browser)
- `output/newsletter_2025-03-06.json` — Raw structured data

---

## Step 4: Customize LLM Models

### Using CLI Arguments

```bash
# Use specific writer model
python run.py --llmwriter mistral

# Use specific reviewer model
python run.py --reviewer deepseek-r1:7b

# Use both (recommended for best quality)
python run.py --llmwriter mistral --reviewer deepseek-r1:7b

# Use same model for both (faster, no review loop)
python run.py --llmwriter mistral --reviewer mistral
```

### How the Dual-LLM Works

1. **Writer LLM** generates the headline story, noteworthy summaries, and weekly reflection
2. **Reviewer LLM** (if different from writer) reviews the output and suggests improvements
3. If the reviewer requests changes, the writer's output is updated with the improvements

When both `--llmwriter` and `--reviewer` use the same model, the review step is skipped (single-LLM mode).

### Available Models

Any Ollama model works. Popular choices:

| Model | Size | Best For |
|-------|------|----------|
| `mistral` | ~4GB | Fast, good quality writing (default writer) |
| `deepseek-r1:7b` | ~4GB | Strong reasoning and review (default reviewer) |
| `llama3.1:8b` | ~4.7GB | Good all-around performance |
| `phi3:mini` | ~2.3GB | Lightweight, lower RAM usage |
| `gemma2:9b` | ~5.4GB | Strong instruction following |

Pull any model first:
```bash
ollama pull llama3.1:8b
python run.py --llmwriter llama3.1:8b
```

---

## Step 5: Dry Run (Test Without LLM)

To test search and scoring without calling the LLM:

```bash
python run.py --dry-run
```

This runs steps 1-4 (search, extract, score) and shows the top articles with their scores. Useful for:
- Checking if your search queries return good results
- Tuning scoring keywords before generating the full newsletter
- Verifying internet connectivity

---

## Troubleshooting

### "Ollama not found" or connection errors

Make sure Ollama is running:
```bash
# Check if running
ollama list

# Start Ollama
ollama serve    # Foreground (see logs)
# or
ollama serve &  # Background
```

### "No search results found"

- Check your internet connection
- Some search engines may rate-limit. The agent adds polite delays between requests.
- Try different/simpler search queries in `context.yml`

### "Could not extract any article content"

- Some websites block automated access. This is normal — the agent skips those and continues with the rest.
- If most sites block you, try using a different set of search queries

### LLM returns poor quality output

- Try a different model: `python run.py --llmwriter llama3.1:8b`
- Lower the temperature in `context.yml` for more focused output
- Improve your search queries to get higher quality source articles

### Out of memory

Both models use `keep_alive=0` to unload after each call, so they don't need to be in RAM simultaneously. If you still run out:
- Use smaller models (`phi3:mini` is ~2.3GB)
- Close other applications
- Ensure you have at least 8GB RAM available

### Using a custom config file

```bash
python run.py --config config/my-topic.yml
```

You can maintain multiple config files for different newsletter topics and switch between them.

---

## Automation (Optional)

### Linux/Mac — Run Weekly via Cron

```bash
crontab -e
# Add this line (runs every Monday at 8:00 AM):
0 8 * * 1 cd /path/to/standalone && .venv/bin/python run.py >> output/cron.log 2>&1
```

### Windows — Run Weekly via Task Scheduler

1. Open Task Scheduler
2. Create a new task
3. Set trigger: Weekly, Monday at 8:00 AM
4. Set action: Start a program
   - Program: `C:\path\to\standalone\.venv\Scripts\python.exe`
   - Arguments: `run.py`
   - Start in: `C:\path\to\standalone\`
