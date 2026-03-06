#!/usr/bin/env python3
"""
Standalone Newsletter Agent — One-shot runner.

Usage:
    python run.py
    python run.py --config config/context.yml
    python run.py --dry-run
    python run.py --llmwriter mistral --reviewer deepseek-r1:7b

The script:
  1. Loads context.yml (topic, queries, scoring keywords)
  2. Searches the internet (Google News, Google, Bing)
  3. Extracts article content
  4. Scores and ranks articles
  5. Picks headline story + noteworthy items
  6. Calls local Ollama LLM to generate newsletter content
  7. Renders HTML newsletter to output/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

# Ensure standalone/ is on sys.path for local imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from search import run_searches
from extractor import extract_articles
from scorer import score_articles
from llm import generate_headline_story, generate_noteworthy_summaries, generate_reflection, call_ollama


def load_config(config_path: str) -> dict:
    """Load context.yml configuration."""
    path = Path(config_path)
    if not path.exists():
        # Try relative to script dir
        path = SCRIPT_DIR / config_path
    if not path.exists():
        print(f"[ERROR] Config file not found: {config_path}")
        print("        Run: cp config/context.yml.example config/context.yml")
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def render_newsletter(data: dict, template_dir: str | None = None) -> str:
    """Render newsletter data to HTML using Jinja2 template."""
    if template_dir is None:
        template_dir = str(SCRIPT_DIR / "templates")
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
    template = env.get_template("newsletter.html")
    return template.render(**data)


def save_output(html: str, config: dict) -> Path:
    """Save newsletter HTML (and JSON) to output directory."""
    output_dir = Path(config.get("output_dir", "./output"))
    if not output_dir.is_absolute():
        output_dir = SCRIPT_DIR / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    pattern = config.get("filename_pattern", "newsletter_{date}")
    basename = pattern.replace("{date}", date_str)

    html_path = output_dir / f"{basename}.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


def run(config_path: str = "config/context.yml", dry_run: bool = False,
        llmwriter: str | None = None, reviewer: str | None = None):
    """Execute the full one-shot newsletter pipeline."""

    print("=" * 60)
    print("  Standalone Newsletter Agent")
    print("=" * 60)
    print()

    # ── 1. Load config ──────────────────────────────────────
    print("[1/7] Loading configuration...")
    config = load_config(config_path)
    topic = config.get("topic", "General")
    tagline = config.get("tagline", "Weekly digest")
    lang = config.get("lang", "en")
    writer_model = llmwriter or config.get("model", "mistral")
    reviewer_model = reviewer or config.get("reviewer_model", writer_model)
    temperature = config.get("temperature", 0.4)
    ollama_url = config.get("ollama_url", "http://localhost:11434")
    print(f"       Topic: {topic}")
    print(f"       Writer LLM: {writer_model}")
    print(f"       Reviewer LLM: {reviewer_model}")
    print(f"       Ollama: {ollama_url}")
    print()

    # ── 2. Search the internet ──────────────────────────────
    print("[2/7] Searching the internet...")
    queries = config.get("queries", [])
    engines = config.get("engines", ["google_news", "bing"])
    results_per_query = config.get("results_per_query", 8)
    search_results = run_searches(queries, engines, results_per_query=results_per_query, lang=lang)
    print()

    if not search_results:
        print("[ERROR] No search results found. Check your internet connection and queries.")
        sys.exit(1)

    # ── 3. Extract article content ──────────────────────────
    print("[3/7] Extracting article content...")
    max_articles = config.get("max_articles", 50)
    articles = extract_articles(search_results, max_articles=max_articles)
    print()

    if not articles:
        print("[ERROR] Could not extract any article content.")
        sys.exit(1)

    # ── 4. Score and rank ───────────────────────────────────
    print("[4/7] Scoring and ranking articles...")
    scoring_keywords = config.get("scoring_keywords", {})
    articles = score_articles(articles, scoring_keywords)
    print(f"       Top score: {articles[0]['score']} — {articles[0]['title'][:60]}")
    print()

    if dry_run:
        print("[DRY RUN] Skipping LLM calls. Top articles:")
        for i, a in enumerate(articles[:10]):
            print(f"  {i+1}. [{a['score']}] {a['title'][:70]}")
        return

    # ── 5. Generate headline story (Writer LLM) ────────────
    print("[5/7] Generating headline story...")
    headline_min_score = config.get("headline_min_score", 30)
    headline_article = articles[0]
    headline_data = generate_headline_story(
        headline_article,
        topic=topic,
        model=writer_model,
        temperature=temperature,
        ollama_url=ollama_url,
    )

    # ── 5b. Reviewer feedback loop ─────────────────────────
    if headline_data and reviewer_model != writer_model:
        print(f"       Running reviewer ({reviewer_model}) feedback loop...")
        review_prompt = f"""You are a critical reviewer for a {topic} newsletter.

Review this headline story draft and provide specific improvements.

Draft:
{json.dumps(headline_data, indent=2)}

Respond with a JSON object:
{{
    "approved": true/false,
    "feedback": "specific feedback if not approved",
    "improved_headline": "better headline if you have one",
    "improved_context": "better context if needed",
    "improved_description": "better description if needed"
}}

If the draft is good, set approved=true. Otherwise provide improvements."""

        review = call_ollama(
            review_prompt,
            model=reviewer_model,
            temperature=0.3,
            ollama_url=ollama_url,
            expect_json=True,
        )

        if isinstance(review, dict) and not review.get("approved", True):
            print("       Reviewer requested improvements, revising...")
            if review.get("improved_headline"):
                headline_data["headline"] = review["improved_headline"]
            if review.get("improved_context"):
                headline_data["context"] = review["improved_context"]
            if review.get("improved_description"):
                headline_data["description"] = review["improved_description"]

    if headline_data:
        print(f"       Headline: {headline_data.get('headline', 'N/A')[:60]}")
    else:
        print("       [WARN] LLM failed to generate headline, using fallback")
        headline_data = {
            "headline": headline_article["title"],
            "context": "",
            "description": headline_article.get("text", "")[:500],
            "key_takeaways": [],
            "recommendations": [],
            "source_url": headline_article["url"],
            "source_title": headline_article["title"],
        }
    print()

    # ── 6. Generate noteworthy summaries ────────────────────
    print("[6/7] Generating noteworthy news summaries...")
    max_noteworthy = config.get("max_noteworthy", 8)
    noteworthy_articles = articles[1:max_noteworthy + 1]
    noteworthy_data = generate_noteworthy_summaries(
        noteworthy_articles,
        topic=topic,
        max_items=max_noteworthy,
        model=writer_model,
        temperature=temperature,
        ollama_url=ollama_url,
    )

    # ── 6b. Reviewer check on noteworthy ───────────────────
    if noteworthy_data and reviewer_model != writer_model:
        print(f"       Running reviewer ({reviewer_model}) on noteworthy items...")
        review_prompt = f"""You are a critical reviewer for a {topic} newsletter.

Review these noteworthy news summaries. Check for accuracy, clarity, and relevance.

{json.dumps(noteworthy_data, indent=2)}

Respond with a JSON object:
{{
    "approved": true/false,
    "feedback": "overall feedback",
    "items": [improved items if needed, same structure]
}}

If the summaries are good, set approved=true and omit items."""

        review = call_ollama(
            review_prompt,
            model=reviewer_model,
            temperature=0.3,
            ollama_url=ollama_url,
            expect_json=True,
        )

        if isinstance(review, dict) and not review.get("approved", True):
            improved_items = review.get("items")
            if improved_items and len(improved_items) > 0:
                # Preserve original URLs
                for i, item in enumerate(improved_items):
                    if i < len(noteworthy_articles):
                        item["url"] = noteworthy_articles[i]["url"]
                noteworthy_data = improved_items

    print(f"       {len(noteworthy_data)} noteworthy items generated")
    print()

    # ── 7. Generate reflection + render ─────────────────────
    print("[7/7] Generating weekly reflection and rendering...")
    reflection = generate_reflection(
        topic=topic,
        headline=headline_data,
        noteworthy=noteworthy_data,
        model=writer_model,
        temperature=temperature,
        ollama_url=ollama_url,
    )

    # Build template data
    date_str = datetime.now().strftime("%B %d, %Y")
    template_data = {
        "topic": topic,
        "tagline": tagline,
        "date": date_str,
        "lang": lang,
        "headline": headline_data,
        "noteworthy": noteworthy_data,
        "reflection": reflection,
        "articles_searched": len(search_results),
        "articles_extracted": len(articles),
        "noteworthy_count": len(noteworthy_data) + 1,  # +1 for headline
    }

    # Render HTML
    html = render_newsletter(template_data)

    # Save
    html_path = save_output(html, config)

    # Also save raw JSON
    json_path = html_path.with_suffix(".json")
    json_path.write_text(json.dumps(template_data, indent=2, default=str), encoding="utf-8")

    print()
    print("=" * 60)
    print("  Newsletter Generated Successfully!")
    print("=" * 60)
    print(f"  HTML: {html_path}")
    print(f"  JSON: {json_path}")
    print(f"  Topic: {topic}")
    print(f"  Headline: {headline_data.get('headline', 'N/A')[:50]}")
    print(f"  Noteworthy items: {len(noteworthy_data)}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Standalone Newsletter Agent — generates a newsletter from internet sources using local AI",
    )
    parser.add_argument(
        "--config", "-c",
        default="config/context.yml",
        help="Path to context.yml config file (default: config/context.yml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and score only, skip LLM generation",
    )
    parser.add_argument(
        "--llmwriter",
        default=None,
        help="Ollama model for writing (default: from config, typically mistral)",
    )
    parser.add_argument(
        "--reviewer",
        default=None,
        help="Ollama model for review/feedback loop (default: same as writer)",
    )
    args = parser.parse_args()
    run(
        config_path=args.config,
        dry_run=args.dry_run,
        llmwriter=args.llmwriter,
        reviewer=args.reviewer,
    )


if __name__ == "__main__":
    main()
