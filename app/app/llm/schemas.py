"""Strict Pydantic schemas for LLM JSON outputs."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ── Writer output ────────────────────────────────────────
class NewsletterStory(BaseModel):
    headline: str
    severity: str = Field(pattern=r"^(critical|high|medium|low)$")
    summary: str
    cves: list[str] = Field(default_factory=list)
    iocs: list[str] = Field(default_factory=list)
    sources: list[str] = Field(min_length=1)
    recommendations: str | None = None


class NewsletterSection(BaseModel):
    section_title: str
    stories: list[NewsletterStory]


class IOCTableEntry(BaseModel):
    type: str
    value: str
    context: str
    sources: list[str] = Field(default_factory=list)


class Newsletter(BaseModel):
    date: str
    lang: str
    title: str
    intro: str
    sections: list[NewsletterSection]
    ioc_table: list[IOCTableEntry] = Field(default_factory=list)
    closing: str


class WriterOutput(BaseModel):
    newsletter: Newsletter


# ── Critic output ────────────────────────────────────────
class CriticIssue(BaseModel):
    severity: str = Field(pattern=r"^(critical|warning|info)$")
    location: str
    description: str
    fix: str


class CriticPatch(BaseModel):
    action: str = Field(pattern=r"^(replace|remove|add)$")
    path: str
    old_value: str | None = None
    new_value: str | None = None
    reason: str


class MissingItem(BaseModel):
    description: str
    suggested_section: str


class CriticReview(BaseModel):
    verdict: str = Field(pattern=r"^(PASS|FAIL)$")
    score: int = Field(ge=0, le=100)
    issues: list[CriticIssue] = Field(default_factory=list)
    patches: list[CriticPatch] = Field(default_factory=list)
    missing_items: list[MissingItem] = Field(default_factory=list)
    notes: str | None = None


class CriticOutput(BaseModel):
    review: CriticReview


# ── Extraction output ───────────────────────────────────
class ExtractedIOC(BaseModel):
    type: str
    value: str
    confidence: str = Field(pattern=r"^(high|medium|low)$")
    context: str


class ExtractedCVE(BaseModel):
    id: str
    confidence: str = Field(pattern=r"^(high|medium|low)$")
    context: str


class ExtractionOutput(BaseModel):
    iocs: list[ExtractedIOC] = Field(default_factory=list)
    cves: list[ExtractedCVE] = Field(default_factory=list)
