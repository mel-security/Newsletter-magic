"""Standalone LLM client — talks to local Ollama instance."""
from __future__ import annotations

import json
import re

import httpx


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from deepseek-r1 style models."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> dict | None:
    """Extract JSON object from LLM response text."""
    text = _strip_think_tags(text)
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding first { ... }
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def call_ollama(
    prompt: str,
    model: str = "mistral",
    temperature: float = 0.4,
    ollama_url: str = "http://localhost:11434",
    expect_json: bool = False,
) -> str | dict | None:
    """Call Ollama generate endpoint. Returns text or parsed JSON."""
    url = f"{ollama_url}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
        "keep_alive": 0,  # Unload model after use to save RAM
    }

    try:
        resp = httpx.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        response_text = data.get("response", "")
        response_text = _strip_think_tags(response_text)

        if expect_json:
            parsed = _extract_json(response_text)
            if parsed:
                return parsed
            print("  [WARN] LLM did not return valid JSON, returning raw text")

        return response_text
    except Exception as e:
        print(f"  [ERROR] Ollama call failed: {e}")
        return None


def generate_headline_story(article: dict, topic: str, model: str = "mistral", **kwargs) -> dict | None:
    """Generate the headline story section using LLM."""
    prompt = f"""You are an expert {topic} analyst writing a newsletter.

Analyze this article and produce a detailed headline story section.

Article title: {article['title']}
Article URL: {article['url']}
Article content:
{article['text'][:4000]}

Write a JSON response with this exact structure:
{{
    "headline": "A compelling headline for this story",
    "context": "2-3 sentences providing background context for this story",
    "description": "3-5 sentences describing what happened, with specific details",
    "key_takeaways": ["takeaway 1", "takeaway 2", "takeaway 3"],
    "recommendations": ["actionable recommendation 1", "actionable recommendation 2", "actionable recommendation 3"],
    "source_url": "{article['url']}",
    "source_title": "{article['title']}"
}}

Respond ONLY with the JSON object. No other text."""

    result = call_ollama(prompt, model=model, expect_json=True, **kwargs)
    if isinstance(result, dict):
        result["source_url"] = article["url"]
        result["source_title"] = article["title"]
        return result
    return None


def generate_noteworthy_summaries(articles: list[dict], topic: str, max_items: int = 8, model: str = "mistral", **kwargs) -> list[dict]:
    """Generate short summaries for noteworthy articles."""
    if not articles:
        return []

    articles_text = ""
    for i, a in enumerate(articles[:max_items]):
        articles_text += f"\n--- Article {i+1} ---\nTitle: {a['title']}\nURL: {a['url']}\nContent: {a['text'][:800]}\n"

    prompt = f"""You are an expert {topic} analyst writing a newsletter section called "Other Noteworthy News".

For each article below, write a 1-2 sentence summary highlighting why it matters.

{articles_text}

Write a JSON response with this exact structure:
{{
    "items": [
        {{
            "title": "Short title",
            "summary": "1-2 sentence summary of why this matters",
            "url": "the article URL"
        }}
    ]
}}

Include all {min(len(articles), max_items)} articles. Respond ONLY with JSON."""

    result = call_ollama(prompt, model=model, expect_json=True, **kwargs)
    if isinstance(result, dict) and "items" in result:
        # Ensure URLs are preserved from originals
        items = result["items"]
        for i, item in enumerate(items):
            if i < len(articles):
                item["url"] = articles[i]["url"]
                item["original_title"] = articles[i]["title"]
        return items
    # Fallback: return basic info without LLM summaries
    return [
        {"title": a["title"], "summary": a.get("snippet", ""), "url": a["url"]}
        for a in articles[:max_items]
    ]


def generate_reflection(topic: str, headline: dict | None, noteworthy: list[dict], model: str = "mistral", **kwargs) -> str:
    """Generate a weekly self-reflection section."""
    context_parts = []
    if headline:
        context_parts.append(f"Headline story: {headline.get('headline', '')}")
    for item in noteworthy[:5]:
        context_parts.append(f"- {item.get('title', '')}")
    context = "\n".join(context_parts)

    prompt = f"""You are an expert {topic} analyst writing the closing section of a weekly newsletter.

This week's coverage included:
{context}

Write a thoughtful "Weekly Reflection" paragraph (4-6 sentences) that:
1. Identifies the overarching theme or trend from this week's news
2. Puts it in broader context (industry direction, recurring patterns)
3. Offers a forward-looking thought about what to watch next week
4. Ends with an encouraging or thought-provoking closing line

Write ONLY the reflection paragraph, no headers or labels."""

    result = call_ollama(prompt, model=model, **kwargs)
    if isinstance(result, str) and len(result) > 50:
        return result.strip()
    return f"This week in {topic} highlighted both ongoing challenges and evolving trends. Stay vigilant and informed."
