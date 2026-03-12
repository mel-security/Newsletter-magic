# Asset Populator — Arabic Letters & Quran Audio/Images

All-in-one command to populate `public/assets/` with Arabic letter audio, Quran recitation audio, and letter images — fully autonomous, no manual downloads needed.

## What It Does

| Asset | Source | Format |
|-------|--------|--------|
| Arabic letter audio (28) | Edge TTS / Google TTS | MP3 |
| Quran verse audio (6236) | EveryAyah.com (Al-Afasy) | MP3 |
| Quran surah audio (114) | EveryAyah.com | MP3 |
| Arabic letter images (28) | Generated SVG | SVG/PNG |
| Database SQL | Auto-generated | SQL |
| Asset manifest | Auto-generated | JSON |

All sources are **free and open** — no API keys, no accounts, no rate limits.

## Quick Start

```bash
cd tools/populate-assets/

# Install dependencies
pip install -r requirements.txt

# Run everything (letters + quran + images + SQL)
python populate.py
```

That's it. The script will:
1. Generate 28 Arabic letter pronunciation audio via TTS
2. Generate 28 letter SVG images
3. Download 6236 verse-by-verse Quran audio files (Al-Afasy)
4. Generate `populate.sql` with all `INSERT` statements
5. Write `manifest.json` listing every asset

## Output Structure

```
public/assets/
├── audio/
│   ├── letters/
│   │   ├── alif.mp3
│   │   ├── ba.mp3
│   │   ├── ta.mp3
│   │   └── ... (28 files)
│   └── quran/
│       ├── 001.mp3           # Al-Fatiha (full surah)
│       ├── 001_001.mp3       # Al-Fatiha verse 1
│       ├── 001_002.mp3       # Al-Fatiha verse 2
│       └── ... (6236+ files)
├── images/
│   └── letters/
│       ├── alif.svg
│       ├── ba.svg
│       └── ... (28 files)
├── manifest.json
└── populate.sql
```

## Usage Examples

```bash
# Full run — everything
python populate.py

# Only Arabic letter assets (audio + images)
python populate.py --letters-only

# Only Quran audio
python populate.py --quran-only

# Only specific surahs (great for testing)
python populate.py --surahs 1,36,67,112,113,114

# Only Al-Fatiha (7 verses — fast test)
python populate.py --quran-only --surahs 1

# Only generate images (no audio download)
python populate.py --images-only

# Only generate SQL (no downloads at all)
python populate.py --sql-only

# Use Google TTS instead of Edge TTS
python populate.py --tts-engine gtts

# Choose a different Quran reciter
python populate.py --reciter husary

# Generate PNG images (requires cairosvg)
python populate.py --image-format png

# Custom output directory
python populate.py --output-dir /var/www/myapp/public/assets
```

## Available Reciters

| ID | Reciter | Quality |
|----|---------|---------|
| `alafasy` | Mishary Rashid Al-Afasy | 128kbps (default) |
| `husary` | Mahmoud Khalil Al-Husary | 128kbps |
| `minshawi` | Mohamed Siddiq Al-Minshawi | 128kbps |
| `sudais` | Abdurrahman As-Sudais | 192kbps |
| `shuraym` | Saud Ash-Shuraym | 128kbps |
| `ajamy` | Ahmed ibn Ali Al-Ajamy | 128kbps |

## Applying the SQL

After running the populator, apply the generated SQL to your database:

```bash
# PostgreSQL
psql -U your_user -d your_db -f public/assets/populate.sql

# SQLite
sqlite3 your.db < public/assets/populate.sql

# Docker PostgreSQL
docker compose exec -T postgres psql -U cyberagent < public/assets/populate.sql
```

The SQL creates three tables (`letters`, `surahs`, `verses`) and uses `ON CONFLICT ... DO UPDATE` so it's safe to run multiple times (idempotent).

## Resumable Downloads

The script **skips files that already exist** on disk. If the download is interrupted (network issue, Ctrl+C), just run the same command again — it will pick up where it left off.

## Disk Space Estimates

| Content | Size |
|---------|------|
| 28 letter audio files | ~2 MB |
| 28 letter SVG images | ~200 KB |
| Al-Fatiha only (7 verses) | ~1 MB |
| Juz Amma (surahs 78-114) | ~150 MB |
| Full Quran (114 surahs) | ~2.5 GB |

## Dependencies

```
gTTS>=2.5.0          # Google Text-to-Speech (fallback)
edge-tts>=6.1.0      # Microsoft Edge TTS (primary, higher quality)
httpx>=0.27.0        # HTTP client for downloads
Pillow>=10.0.0       # Image processing
cairosvg>=2.7.0      # SVG→PNG conversion (optional)
rich>=13.0.0         # Pretty terminal output (optional)
```

## Sources & Attribution

- **Quran audio**: [EveryAyah.com](https://everyayah.com/) — free verse-by-verse recitations
- **Letter audio**: [Edge TTS](https://github.com/rany2/edge-tts) (Microsoft) / [gTTS](https://gtts.readthedocs.io/) (Google)
- **Letter images**: Generated programmatically (SVG)
- **Surah metadata**: Standard Quran structure (114 surahs, 6236 verses)
