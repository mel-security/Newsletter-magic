"""Render newsletter JSON to HTML using Jinja2."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger("render")


def render_newsletter(newsletter_data: dict, is_fallback: bool = False) -> str:
    """Render newsletter dict to HTML string."""
    template_dir = Path(settings.config_dir)
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template("newsletter_template.html")

    newsletter = newsletter_data.get("newsletter", newsletter_data)

    html = template.render(
        newsletter=newsletter,
        is_fallback=is_fallback,
    )

    log.info("render.complete", length=len(html), is_fallback=is_fallback)
    return html


def save_newsletter(html: str, filename: str = "latest.html") -> Path:
    """Save rendered HTML to output directory."""
    out_dir = Path(settings.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename
    out_path.write_text(html, encoding="utf-8")
    log.info("render.saved", path=str(out_path))
    return out_path
