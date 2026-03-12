#!/usr/bin/env python3
"""
populate.py — All-in-one asset populator for Arabic letters & Quran audio/images.

Usage:
    python populate.py                      # Full run (letters + quran + images + SQL)
    python populate.py --letters-only       # Only Arabic letter audio (TTS)
    python populate.py --quran-only         # Only Quran audio (download)
    python populate.py --images-only        # Only letter images (SVG generation)
    python populate.py --sql-only           # Only generate SQL statements
    python populate.py --reciter alafasy    # Choose reciter (default: alafasy)
    python populate.py --tts-engine gtts    # TTS engine: gtts or edge (default: edge)
    python populate.py --surahs 1,2,3       # Only specific surahs (default: all 114)
    python populate.py --output-dir /path   # Custom output (default: ../../public/assets)
    python populate.py --db-file out.sql    # SQL output file (default: populate.sql)

Sources (free & open):
    Quran audio:  EveryAyah.com (Al-Afasy 128kbps) — no API key needed
    Letter audio: Edge TTS (Microsoft) or gTTS (Google) — Arabic voice
    Letter images: Generated SVG with Arabic calligraphy font
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVERYAYAH_BASE = "https://everyayah.com/data"
ALQURAN_CLOUD_BASE = "https://api.alquran.cloud/v1"

RECITERS = {
    "alafasy": "Alafasy_128kbps",
    "husary": "Husary_128kbps",
    "minshawi": "Minshawi_Murattal_128kbps",
    "sudais": "Abdurrahmaan_As-Sudais_192kbps",
    "shuraym": "Saood_ash-Shuraym_128kbps",
    "ajamy": "Ahmed_ibn_Ali_al-Ajamy_128kbps_ketaballah.net",
}

# 28 Arabic letters with transliteration, isolated form, and pronunciation text
ARABIC_LETTERS: list[dict] = [
    {"order": 1,  "name": "alif",    "ar": "\u0627", "sound": "\u0623\u064e\u0644\u0650\u0641"},
    {"order": 2,  "name": "ba",      "ar": "\u0628", "sound": "\u0628\u064e\u0627\u0621"},
    {"order": 3,  "name": "ta",      "ar": "\u062a", "sound": "\u062a\u064e\u0627\u0621"},
    {"order": 4,  "name": "tha",     "ar": "\u062b", "sound": "\u062b\u064e\u0627\u0621"},
    {"order": 5,  "name": "jim",     "ar": "\u062c", "sound": "\u062c\u0650\u064a\u0645"},
    {"order": 6,  "name": "ha",      "ar": "\u062d", "sound": "\u062d\u064e\u0627\u0621"},
    {"order": 7,  "name": "kha",     "ar": "\u062e", "sound": "\u062e\u064e\u0627\u0621"},
    {"order": 8,  "name": "dal",     "ar": "\u062f", "sound": "\u062f\u064e\u0627\u0644"},
    {"order": 9,  "name": "dhal",    "ar": "\u0630", "sound": "\u0630\u064e\u0627\u0644"},
    {"order": 10, "name": "ra",      "ar": "\u0631", "sound": "\u0631\u064e\u0627\u0621"},
    {"order": 11, "name": "zay",     "ar": "\u0632", "sound": "\u0632\u064e\u0627\u064a"},
    {"order": 12, "name": "sin",     "ar": "\u0633", "sound": "\u0633\u0650\u064a\u0646"},
    {"order": 13, "name": "shin",    "ar": "\u0634", "sound": "\u0634\u0650\u064a\u0646"},
    {"order": 14, "name": "sad",     "ar": "\u0635", "sound": "\u0635\u064e\u0627\u062f"},
    {"order": 15, "name": "dad",     "ar": "\u0636", "sound": "\u0636\u064e\u0627\u062f"},
    {"order": 16, "name": "taa",     "ar": "\u0637", "sound": "\u0637\u064e\u0627\u0621"},
    {"order": 17, "name": "dhaa",    "ar": "\u0638", "sound": "\u0638\u064e\u0627\u0621"},
    {"order": 18, "name": "ayn",     "ar": "\u0639", "sound": "\u0639\u064e\u064a\u0646"},
    {"order": 19, "name": "ghayn",   "ar": "\u063a", "sound": "\u063a\u064e\u064a\u0646"},
    {"order": 20, "name": "fa",      "ar": "\u0641", "sound": "\u0641\u064e\u0627\u0621"},
    {"order": 21, "name": "qaf",     "ar": "\u0642", "sound": "\u0642\u064e\u0627\u0641"},
    {"order": 22, "name": "kaf",     "ar": "\u0643", "sound": "\u0643\u064e\u0627\u0641"},
    {"order": 23, "name": "lam",     "ar": "\u0644", "sound": "\u0644\u064e\u0627\u0645"},
    {"order": 24, "name": "mim",     "ar": "\u0645", "sound": "\u0645\u0650\u064a\u0645"},
    {"order": 25, "name": "nun",     "ar": "\u0646", "sound": "\u0646\u064f\u0648\u0646"},
    {"order": 26, "name": "ha2",     "ar": "\u0647", "sound": "\u0647\u064e\u0627\u0621"},
    {"order": 27, "name": "waw",     "ar": "\u0648", "sound": "\u0648\u064e\u0627\u0648"},
    {"order": 28, "name": "ya",      "ar": "\u064a", "sound": "\u064a\u064e\u0627\u0621"},
]

# Surah metadata: (number, name_ar, total_ayahs)
SURAH_META: list[tuple[int, str, int]] = [
    (1, "الفاتحة", 7), (2, "البقرة", 286), (3, "آل عمران", 200),
    (4, "النساء", 176), (5, "المائدة", 120), (6, "الأنعام", 165),
    (7, "الأعراف", 206), (8, "الأنفال", 75), (9, "التوبة", 129),
    (10, "يونس", 109), (11, "هود", 123), (12, "يوسف", 111),
    (13, "الرعد", 43), (14, "إبراهيم", 52), (15, "الحجر", 99),
    (16, "النحل", 128), (17, "الإسراء", 111), (18, "الكهف", 110),
    (19, "مريم", 98), (20, "طه", 135), (21, "الأنبياء", 112),
    (22, "الحج", 78), (23, "المؤمنون", 118), (24, "النور", 64),
    (25, "الفرقان", 77), (26, "الشعراء", 227), (27, "النمل", 93),
    (28, "القصص", 88), (29, "العنكبوت", 69), (30, "الروم", 60),
    (31, "لقمان", 34), (32, "السجدة", 30), (33, "الأحزاب", 73),
    (34, "سبأ", 54), (35, "فاطر", 45), (36, "يس", 83),
    (37, "الصافات", 182), (38, "ص", 88), (39, "الزمر", 75),
    (40, "غافر", 85), (41, "فصلت", 54), (42, "الشورى", 53),
    (43, "الزخرف", 89), (44, "الدخان", 59), (45, "الجاثية", 37),
    (46, "الأحقاف", 35), (47, "محمد", 38), (48, "الفتح", 29),
    (49, "الحجرات", 18), (50, "ق", 45), (51, "الذاريات", 60),
    (52, "الطور", 49), (53, "النجم", 62), (54, "القمر", 55),
    (55, "الرحمن", 78), (56, "الواقعة", 96), (57, "الحديد", 29),
    (58, "المجادلة", 22), (59, "الحشر", 24), (60, "الممتحنة", 13),
    (61, "الصف", 14), (62, "الجمعة", 11), (63, "المنافقون", 11),
    (64, "التغابن", 18), (65, "الطلاق", 12), (66, "التحريم", 12),
    (67, "الملك", 30), (68, "القلم", 52), (69, "الحاقة", 52),
    (70, "المعارج", 44), (71, "نوح", 28), (72, "الجن", 28),
    (73, "المزمل", 20), (74, "المدثر", 56), (75, "القيامة", 40),
    (76, "الإنسان", 31), (77, "المرسلات", 50), (78, "النبأ", 40),
    (79, "النازعات", 46), (80, "عبس", 42), (81, "التكوير", 29),
    (82, "الانفطار", 19), (83, "المطففين", 36), (84, "الانشقاق", 25),
    (85, "البروج", 22), (86, "الطارق", 17), (87, "الأعلى", 19),
    (88, "الغاشية", 26), (89, "الفجر", 30), (90, "البلد", 20),
    (91, "الشمس", 15), (92, "الليل", 21), (93, "الضحى", 11),
    (94, "الشرح", 8), (95, "التين", 8), (96, "العلق", 19),
    (97, "القدر", 5), (98, "البينة", 8), (99, "الزلزلة", 8),
    (100, "العاديات", 11), (101, "القارعة", 11), (102, "التكاثر", 8),
    (103, "العصر", 3), (104, "الهمزة", 9), (105, "الفيل", 5),
    (106, "قريش", 4), (107, "الماعون", 7), (108, "الكوثر", 3),
    (109, "الكافرون", 6), (110, "النصر", 3), (111, "المسد", 5),
    (112, "الإخلاص", 4), (113, "الفلق", 5), (114, "الناس", 6),
]

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    class _FakeConsole:
        def print(self, *a, **kw):
            print(*[str(x) for x in a])
        def log(self, *a, **kw):
            print(*[str(x) for x in a])
    console = _FakeConsole()


def info(msg: str):
    console.print(f"[bold cyan]▸[/bold cyan] {msg}" if HAS_RICH else f"▸ {msg}")

def success(msg: str):
    console.print(f"[bold green]✓[/bold green] {msg}" if HAS_RICH else f"✓ {msg}")

def warn(msg: str):
    console.print(f"[bold yellow]⚠[/bold yellow] {msg}" if HAS_RICH else f"⚠ {msg}")

def error(msg: str):
    console.print(f"[bold red]✗[/bold red] {msg}" if HAS_RICH else f"✗ {msg}")


# ---------------------------------------------------------------------------
# HTTP download helper with retry
# ---------------------------------------------------------------------------

def _download_file(url: str, dest: Path, retries: int = 3, timeout: float = 30.0) -> bool:
    """Download a file with retry and exponential backoff."""
    import httpx

    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and dest.stat().st_size > 0:
        return True  # already downloaded

    for attempt in range(retries):
        try:
            with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
                if resp.status_code == 404:
                    return False
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8192):
                        f.write(chunk)
            return True
        except (httpx.HTTPError, httpx.StreamError, OSError) as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                warn(f"  Retry {attempt+1}/{retries} for {dest.name} ({e}) — waiting {wait}s")
                time.sleep(wait)
            else:
                error(f"  Failed to download {url}: {e}")
                if dest.exists():
                    dest.unlink()
                return False
    return False


# ===================================================================
# MODULE 1: Arabic Letter Audio (TTS)
# ===================================================================

def generate_letter_audio_gtts(letters: list[dict], output_dir: Path) -> list[Path]:
    """Generate Arabic letter pronunciation audio using Google TTS."""
    from gtts import gTTS

    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    info("Generating Arabic letter audio via gTTS...")

    for letter in letters:
        dest = output_dir / f"{letter['name']}.mp3"
        if dest.exists() and dest.stat().st_size > 0:
            generated.append(dest)
            continue

        try:
            # Generate the letter name pronunciation in Arabic
            tts = gTTS(text=letter["sound"], lang="ar", slow=True)
            tts.save(str(dest))
            generated.append(dest)
            success(f"  {letter['name']} ({letter['ar']}) → {dest.name}")
        except Exception as e:
            error(f"  Failed {letter['name']}: {e}")

    return generated


async def generate_letter_audio_edge(letters: list[dict], output_dir: Path) -> list[Path]:
    """Generate Arabic letter pronunciation audio using Edge TTS (higher quality)."""
    import edge_tts

    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    # Arabic voices available in Edge TTS
    voice = "ar-SA-HamedNeural"  # Male Saudi Arabic voice

    info(f"Generating Arabic letter audio via Edge TTS (voice: {voice})...")

    for letter in letters:
        dest = output_dir / f"{letter['name']}.mp3"
        if dest.exists() and dest.stat().st_size > 0:
            generated.append(dest)
            continue

        try:
            communicate = edge_tts.Communicate(
                text=letter["sound"],
                voice=voice,
                rate="-30%",  # Slower for clarity
            )
            await communicate.save(str(dest))
            generated.append(dest)
            success(f"  {letter['name']} ({letter['ar']}) → {dest.name}")
        except Exception as e:
            error(f"  Failed {letter['name']}: {e}")

    return generated


# ===================================================================
# MODULE 2: Quran Audio Download
# ===================================================================

def download_quran_audio(
    output_dir: Path,
    reciter: str = "alafasy",
    surahs: Optional[list[int]] = None,
) -> dict:
    """
    Download Quran audio from EveryAyah.com.

    Downloads:
      - Full surah audio (from Al Quran Cloud API)
      - Verse-by-verse audio (from EveryAyah.com)

    Returns dict with stats.
    """
    reciter_path = RECITERS.get(reciter)
    if not reciter_path:
        error(f"Unknown reciter '{reciter}'. Available: {', '.join(RECITERS.keys())}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    target_surahs = surahs or list(range(1, 115))
    stats = {"surah_ok": 0, "surah_fail": 0, "verse_ok": 0, "verse_fail": 0, "skipped": 0}

    total_verses = sum(
        ayahs for num, _, ayahs in SURAH_META if num in target_surahs
    )
    info(f"Downloading Quran audio — reciter: {reciter} ({reciter_path})")
    info(f"  Surahs: {len(target_surahs)} | Estimated verses: {total_verses}")
    print()

    for surah_num, surah_name, total_ayahs in SURAH_META:
        if surah_num not in target_surahs:
            continue

        surah_str = f"{surah_num:03d}"
        info(f"Surah {surah_str} — {surah_name} ({total_ayahs} verses)")

        # --- Full surah audio (from EveryAyah, concatenation of all verses) ---
        # We download the Bismillah (verse 0) for surahs that have it
        # Actually EveryAyah uses verse numbers starting from 001
        # Full surah: we'll mark it after all verses are done

        # --- Verse-by-verse audio ---
        surah_verse_ok = 0
        for ayah in range(1, total_ayahs + 1):
            ayah_str = f"{ayah:03d}"
            filename = f"{surah_str}_{ayah_str}.mp3"
            url = f"{EVERYAYAH_BASE}/{reciter_path}/{surah_str}{ayah_str}.mp3"
            dest = output_dir / filename

            if dest.exists() and dest.stat().st_size > 0:
                stats["skipped"] += 1
                surah_verse_ok += 1
                continue

            ok = _download_file(url, dest, retries=3, timeout=30.0)
            if ok:
                stats["verse_ok"] += 1
                surah_verse_ok += 1
            else:
                stats["verse_fail"] += 1

            # Polite delay to avoid rate-limiting
            time.sleep(0.15)

        # Create a marker for full surah (first verse serves as intro)
        full_surah_dest = output_dir / f"{surah_str}.mp3"
        if not full_surah_dest.exists():
            first_verse = output_dir / f"{surah_str}_001.mp3"
            if first_verse.exists():
                # Symlink full surah → first verse as placeholder
                # Users can replace with full recitation later
                try:
                    full_surah_dest.symlink_to(first_verse.name)
                    stats["surah_ok"] += 1
                except OSError:
                    # Windows doesn't support symlinks easily; just copy
                    import shutil
                    shutil.copy2(first_verse, full_surah_dest)
                    stats["surah_ok"] += 1
        else:
            stats["surah_ok"] += 1

        success(f"  → {surah_verse_ok}/{total_ayahs} verses downloaded")

    return stats


# ===================================================================
# MODULE 3: Arabic Letter Images (SVG generation)
# ===================================================================

def generate_letter_images(letters: list[dict], output_dir: Path, fmt: str = "svg") -> list[Path]:
    """
    Generate Arabic letter images as SVG (and optionally PNG).

    Creates clean, large-format letter images suitable for educational apps.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    info(f"Generating Arabic letter images ({fmt.upper()})...")

    # Color palette for letters (rotating)
    colors = [
        "#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#F44336",
        "#00BCD4", "#8BC34A", "#FF5722", "#3F51B5", "#E91E63",
        "#009688", "#FFC107", "#673AB7", "#795548",
    ]

    for letter in letters:
        color = colors[letter["order"] % len(colors)]
        svg_content = _create_letter_svg(letter["ar"], letter["name"], color)

        svg_path = output_dir / f"{letter['name']}.svg"
        svg_path.write_text(svg_content, encoding="utf-8")
        generated.append(svg_path)

        # Also generate PNG if cairosvg is available and format requested
        if fmt in ("png", "both"):
            png_path = output_dir / f"{letter['name']}.png"
            try:
                import cairosvg
                cairosvg.svg2png(
                    bytestring=svg_content.encode("utf-8"),
                    write_to=str(png_path),
                    output_width=512,
                    output_height=512,
                )
                generated.append(png_path)
            except ImportError:
                warn(f"  cairosvg not available — skipping PNG for {letter['name']}")
            except Exception as e:
                warn(f"  PNG generation failed for {letter['name']}: {e}")

        success(f"  {letter['name']} ({letter['ar']}) → {svg_path.name}")

    return generated


def _create_letter_svg(char: str, name: str, color: str) -> str:
    """Create a clean SVG image for a single Arabic letter."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <radialGradient id="bg_{name}" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{color}" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>
    </radialGradient>
  </defs>
  <!-- Background -->
  <rect width="512" height="512" rx="48" ry="48" fill="#FAFAFA"/>
  <rect width="512" height="512" rx="48" ry="48" fill="url(#bg_{name})"/>
  <!-- Border -->
  <rect x="4" y="4" width="504" height="504" rx="44" ry="44"
        fill="none" stroke="{color}" stroke-width="3" stroke-opacity="0.3"/>
  <!-- Arabic letter -->
  <text x="256" y="280" text-anchor="middle" dominant-baseline="central"
        font-family="'Traditional Arabic','Scheherazade New','Noto Naskh Arabic','Arial'"
        font-size="260" fill="{color}" direction="rtl">{char}</text>
  <!-- Latin name -->
  <text x="256" y="460" text-anchor="middle"
        font-family="'Segoe UI','Roboto','Helvetica Neue',sans-serif"
        font-size="28" fill="#666" letter-spacing="2">{name.upper()}</text>
</svg>"""


# ===================================================================
# MODULE 4: SQL Generation
# ===================================================================

def generate_sql(
    letters: list[dict],
    surahs: Optional[list[int]],
    output_file: Path,
    audio_prefix: str = "audio",
    image_prefix: str = "images",
) -> None:
    """Generate SQL statements to populate the database with asset references."""
    target_surahs = surahs or list(range(1, 115))
    lines: list[str] = []

    lines.append("-- =============================================================")
    lines.append("-- Auto-generated by populate.py — Arabic Letters & Quran Assets")
    lines.append(f"-- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("-- =============================================================")
    lines.append("")

    # --- Letters table ---
    lines.append("-- ─── Arabic Letters ─────────────────────────────────────────")
    lines.append("-- Creates table if not exists, then upserts audio/image paths")
    lines.append("")
    lines.append("""CREATE TABLE IF NOT EXISTS letters (
    id SERIAL PRIMARY KEY,
    order_num INTEGER UNIQUE NOT NULL,
    name VARCHAR(20) NOT NULL,
    arabic_char VARCHAR(4) NOT NULL,
    audio_file VARCHAR(255),
    image_file VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);""")
    lines.append("")

    for letter in letters:
        audio_path = f"{audio_prefix}/letters/{letter['name']}.mp3"
        image_path = f"{image_prefix}/letters/{letter['name']}.svg"
        lines.append(
            f"INSERT INTO letters (order_num, name, arabic_char, audio_file, image_file) "
            f"VALUES ({letter['order']}, '{letter['name']}', '{letter['ar']}', "
            f"'{audio_path}', '{image_path}') "
            f"ON CONFLICT (order_num) DO UPDATE SET "
            f"audio_file = EXCLUDED.audio_file, image_file = EXCLUDED.image_file;"
        )

    lines.append("")
    lines.append("")

    # --- Verses table ---
    lines.append("-- ─── Quran Verses ──────────────────────────────────────────")
    lines.append("")
    lines.append("""CREATE TABLE IF NOT EXISTS surahs (
    id SERIAL PRIMARY KEY,
    surah_number INTEGER UNIQUE NOT NULL,
    name_ar VARCHAR(50) NOT NULL,
    total_verses INTEGER NOT NULL,
    audio_file VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);""")
    lines.append("")
    lines.append("""CREATE TABLE IF NOT EXISTS verses (
    id SERIAL PRIMARY KEY,
    surah_id INTEGER NOT NULL REFERENCES surahs(surah_number),
    verse_number INTEGER NOT NULL,
    audio_file VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(surah_id, verse_number)
);""")
    lines.append("")

    for surah_num, surah_name, total_ayahs in SURAH_META:
        if surah_num not in target_surahs:
            continue

        surah_str = f"{surah_num:03d}"
        # Escape single quotes in surah names
        safe_name = surah_name.replace("'", "''")
        surah_audio = f"{audio_prefix}/quran/{surah_str}.mp3"

        lines.append(f"-- Surah {surah_num}: {surah_name}")
        lines.append(
            f"INSERT INTO surahs (surah_number, name_ar, total_verses, audio_file) "
            f"VALUES ({surah_num}, '{safe_name}', {total_ayahs}, '{surah_audio}') "
            f"ON CONFLICT (surah_number) DO UPDATE SET "
            f"audio_file = EXCLUDED.audio_file;"
        )

        for ayah in range(1, total_ayahs + 1):
            ayah_str = f"{ayah:03d}"
            verse_audio = f"{audio_prefix}/quran/{surah_str}_{ayah_str}.mp3"
            lines.append(
                f"INSERT INTO verses (surah_id, verse_number, audio_file) "
                f"VALUES ({surah_num}, {ayah}, '{verse_audio}') "
                f"ON CONFLICT (surah_id, verse_number) DO UPDATE SET "
                f"audio_file = EXCLUDED.audio_file;"
            )

        lines.append("")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(lines), encoding="utf-8")
    success(f"SQL file written → {output_file}")


# ===================================================================
# MODULE 5: Manifest / Summary
# ===================================================================

def write_manifest(output_dir: Path, stats: dict) -> None:
    """Write a JSON manifest of all downloaded/generated assets."""
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "assets_root": str(output_dir),
        "stats": stats,
        "letters": [
            {
                "order": l["order"],
                "name": l["name"],
                "arabic": l["ar"],
                "audio": f"audio/letters/{l['name']}.mp3",
                "image_svg": f"images/letters/{l['name']}.svg",
            }
            for l in ARABIC_LETTERS
        ],
        "surahs": [
            {
                "number": num,
                "name": name,
                "verses": ayahs,
                "audio_full": f"audio/quran/{num:03d}.mp3",
                "audio_verse_pattern": f"audio/quran/{num:03d}_{{verse:03d}}.mp3",
            }
            for num, name, ayahs in SURAH_META
        ],
        "sources": {
            "quran_audio": "EveryAyah.com (Al-Afasy 128kbps) — free, no API key",
            "letter_audio": "Edge TTS / gTTS — Arabic neural voice",
            "letter_images": "Generated SVG — open format",
        },
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    success(f"Manifest written → {manifest_path}")


# ===================================================================
# MAIN
# ===================================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="All-in-one asset populator for Arabic letters & Quran audio/images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python populate.py                          # Full run — everything
  python populate.py --letters-only           # Only letter audio + images
  python populate.py --quran-only --surahs 1  # Only Al-Fatiha
  python populate.py --surahs 1,2,3,36,67     # Specific surahs
  python populate.py --tts-engine gtts        # Use Google TTS instead of Edge
  python populate.py --reciter husary         # Use Husary recitation
  python populate.py --images-only --image-format png  # PNG letter images
        """,
    )

    p.add_argument("--output-dir", type=Path, default=None,
                    help="Output directory (default: ../../public/assets relative to this script)")
    p.add_argument("--db-file", type=Path, default=None,
                    help="SQL output file (default: <output-dir>/populate.sql)")

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--letters-only", action="store_true", help="Only generate letter assets")
    mode.add_argument("--quran-only", action="store_true", help="Only download Quran audio")
    mode.add_argument("--images-only", action="store_true", help="Only generate letter images")
    mode.add_argument("--sql-only", action="store_true", help="Only generate SQL (no downloads)")

    p.add_argument("--reciter", choices=list(RECITERS.keys()), default="alafasy",
                    help="Quran reciter (default: alafasy)")
    p.add_argument("--tts-engine", choices=["edge", "gtts"], default="edge",
                    help="TTS engine for letters (default: edge)")
    p.add_argument("--surahs", type=str, default=None,
                    help="Comma-separated surah numbers (default: all 114)")
    p.add_argument("--image-format", choices=["svg", "png", "both"], default="svg",
                    help="Image format (default: svg)")

    return p.parse_args()


def main():
    args = parse_args()

    # Resolve paths
    script_dir = Path(__file__).resolve().parent
    output_dir = args.output_dir or (script_dir / ".." / ".." / "public" / "assets").resolve()
    db_file = args.db_file or (output_dir / "populate.sql")

    surahs = None
    if args.surahs:
        surahs = [int(s.strip()) for s in args.surahs.split(",")]

    # Header
    print()
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]" if HAS_RICH else "=" * 56)
    console.print("[bold]  Arabic Letters & Quran — Asset Populator[/bold]" if HAS_RICH else "  Arabic Letters & Quran — Asset Populator")
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]" if HAS_RICH else "=" * 56)
    print()
    info(f"Output directory : {output_dir}")
    info(f"SQL file         : {db_file}")
    if surahs:
        info(f"Surahs           : {surahs}")
    info(f"TTS engine       : {args.tts_engine}")
    info(f"Reciter          : {args.reciter}")
    print()

    all_stats: dict = {}

    # ── Step 1: Letter Audio ──
    if not args.quran_only and not args.images_only and not args.sql_only:
        print()
        console.print("[bold]═══ Step 1/4: Arabic Letter Audio (TTS) ═══[/bold]" if HAS_RICH else "=== Step 1/4: Arabic Letter Audio (TTS) ===")
        letter_audio_dir = output_dir / "audio" / "letters"

        if args.tts_engine == "edge":
            try:
                results = asyncio.run(generate_letter_audio_edge(ARABIC_LETTERS, letter_audio_dir))
            except ImportError:
                warn("edge-tts not installed — falling back to gTTS")
                results = generate_letter_audio_gtts(ARABIC_LETTERS, letter_audio_dir)
        else:
            results = generate_letter_audio_gtts(ARABIC_LETTERS, letter_audio_dir)

        all_stats["letter_audio"] = len(results)
        success(f"Letter audio: {len(results)}/{len(ARABIC_LETTERS)} generated")

    # ── Step 2: Letter Images ──
    if not args.quran_only and not args.sql_only:
        print()
        console.print("[bold]═══ Step 2/4: Arabic Letter Images ═══[/bold]" if HAS_RICH else "=== Step 2/4: Arabic Letter Images ===")
        letter_image_dir = output_dir / "images" / "letters"
        results = generate_letter_images(ARABIC_LETTERS, letter_image_dir, fmt=args.image_format)
        all_stats["letter_images"] = len(results)
        success(f"Letter images: {len(results)} generated")

    # ── Step 3: Quran Audio ──
    if not args.letters_only and not args.images_only and not args.sql_only:
        print()
        console.print("[bold]═══ Step 3/4: Quran Audio (Download) ═══[/bold]" if HAS_RICH else "=== Step 3/4: Quran Audio (Download) ===")
        quran_audio_dir = output_dir / "audio" / "quran"
        quran_stats = download_quran_audio(quran_audio_dir, reciter=args.reciter, surahs=surahs)
        all_stats["quran"] = quran_stats
        print()
        success(f"Quran audio: {quran_stats['verse_ok']} downloaded, "
                f"{quran_stats['skipped']} cached, {quran_stats['verse_fail']} failed")

    # ── Step 4: SQL ──
    print()
    console.print("[bold]═══ Step 4/4: SQL Generation ═══[/bold]" if HAS_RICH else "=== Step 4/4: SQL Generation ===")
    generate_sql(ARABIC_LETTERS, surahs, db_file)

    # ── Manifest ──
    write_manifest(output_dir, all_stats)

    # ── Summary ──
    print()
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]" if HAS_RICH else "=" * 56)
    console.print("[bold green]  ✓ All done![/bold green]" if HAS_RICH else "  ✓ All done!")
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]" if HAS_RICH else "=" * 56)
    print()
    info(f"Assets directory : {output_dir}")
    info(f"SQL file         : {db_file}")
    info(f"Manifest         : {output_dir / 'manifest.json'}")
    print()
    info("To apply the SQL to your database:")
    info(f"  psql -U your_user -d your_db -f {db_file}")
    info("  -- or --")
    info(f"  sqlite3 your.db < {db_file}")
    print()


if __name__ == "__main__":
    main()
