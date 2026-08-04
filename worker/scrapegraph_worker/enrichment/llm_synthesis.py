"""Turns crawled site text + detected signals into a short company summary
and an AI-maturity read, via the same OpenAI-compatible LLM backend
Conversation Intelligence uses (`conversation/llm_client.py`).

Degrades gracefully: if no LLM is configured (`LLMSettings.is_configured`
is False, same check `api.py` uses to gate /conversation/analyze), this
module falls back to a purely heuristic summary/maturity read instead of
failing the whole enrichment run -- consistent with this pipeline's
"never require a paid dependency to produce something" scope.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from ..config import LLMSettings
from .models import AIMaturityLevel, CrawledPage, TechStackHit

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a B2B sales research analyst. You will be given raw text scraped \
from a company's own public website (homepage, about page, careers page) \
and a list of technologies detected on their site. Respond with ONLY a \
single JSON object (no markdown fences, no commentary) with exactly these \
keys:

{
  "summary": a neutral 2-4 sentence description of what the company \
appears to do, based ONLY on the provided text -- do not invent facts, \
funding amounts, customer names, or numbers not present in the text,
  "ai_maturity": one of "NONE_OBSERVED" | "EXPLORING" | "ADOPTING" | \
"ADVANCED" -- how AI-forward the company appears from its own public site \
(e.g. AI-related job postings, AI mentioned as part of their product, an \
AI/ML team) -- use NONE_OBSERVED if there's no evidence either way,
  "ai_maturity_reasoning": one short sentence citing what in the text (if \
anything) supports the ai_maturity classification,
  "confidence": your confidence in the summary as a number between 0 and 1
}

If the provided text is too sparse or generic to say anything meaningful, \
set confidence low (below 0.3) rather than inventing detail to compensate.
"""

_MAX_TEXT_CHARS = 6000


def _build_user_prompt(pages: list[CrawledPage], tech_stack: list[TechStackHit]) -> str:
    combined = []
    for page in pages:
        if page.ok and page.text:
            combined.append(f"[{page.url}]\n{page.text}")
    text_blob = "\n\n".join(combined)[:_MAX_TEXT_CHARS]

    tech_names = ", ".join(hit.name for hit in tech_stack) or "(none detected)"

    return f"Detected technologies: {tech_names}\n\nCrawled site text:\n{text_blob}"


class SynthesisResult:
    def __init__(self, summary: Optional[str], ai_maturity: AIMaturityLevel, reasoning: Optional[str], confidence: float):
        self.summary = summary
        self.ai_maturity = ai_maturity
        self.reasoning = reasoning
        self.confidence = confidence


def synthesize(
    pages: list[CrawledPage],
    tech_stack: list[TechStackHit],
    *,
    llm_settings: LLMSettings,
) -> SynthesisResult:
    if llm_settings.is_configured:
        try:
            return _synthesize_with_llm(pages, tech_stack, llm_settings)
        except Exception as exc:  # noqa: BLE001 - fall back rather than fail the whole run
            logger.warning("LLM synthesis failed, falling back to heuristic summary: %s", exc)

    return _synthesize_heuristically(pages, tech_stack)


def _synthesize_with_llm(
    pages: list[CrawledPage], tech_stack: list[TechStackHit], llm_settings: LLMSettings
) -> SynthesisResult:
    # Imported here (not at module top) to avoid a hard import-time
    # dependency on httpx for callers that only need the heuristic path,
    # mirroring how api.py only imports LLMClient where it's actually used.
    from ..conversation.llm_client import LLMClient

    with LLMClient(llm_settings) as client:
        raw = client.complete_json(system_prompt=SYSTEM_PROMPT, user_prompt=_build_user_prompt(pages, tech_stack))

    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned)

    maturity_raw = str(data.get("ai_maturity", "NONE_OBSERVED")).upper()
    try:
        maturity = AIMaturityLevel(maturity_raw)
    except ValueError:
        maturity = AIMaturityLevel.UNKNOWN

    confidence = data.get("confidence", 0.5)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.5

    return SynthesisResult(
        summary=(data.get("summary") or "").strip() or None,
        ai_maturity=maturity,
        reasoning=(data.get("ai_maturity_reasoning") or "").strip() or None,
        confidence=min(1.0, max(0.0, confidence)),
    )


_AI_KEYWORDS = ["artificial intelligence", "machine learning", " ai ", "ai-powered", "ai powered", "llm", "generative ai"]


def _synthesize_heuristically(pages: list[CrawledPage], tech_stack: list[TechStackHit]) -> SynthesisResult:
    """No-LLM fallback: use the homepage's <title>/meta description as a
    summary, and a plain keyword count for AI-maturity, rather than
    fabricating either.
    """
    homepage = next((p for p in pages if p.url.rstrip("/").count("/") <= 2 and p.ok), None)
    summary = None
    if homepage and homepage.html:
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", homepage.html, re.I)
        desc_match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', homepage.html, re.I
        )
        title = title_match.group(1).strip() if title_match else None
        description = desc_match.group(1).strip() if desc_match else None
        if title and description:
            summary = f"{title}. {description}"
        elif description:
            summary = description
        elif title:
            summary = title

    combined_text = " ".join(p.text.lower() for p in pages if p.ok)
    ai_mentions = sum(combined_text.count(kw) for kw in _AI_KEYWORDS)
    if ai_mentions == 0:
        maturity = AIMaturityLevel.NONE_OBSERVED
        reasoning = "No AI/ML-related keywords found on crawled pages."
    elif ai_mentions < 3:
        maturity = AIMaturityLevel.EXPLORING
        reasoning = f"AI/ML keywords mentioned {ai_mentions}x across crawled pages."
    else:
        maturity = AIMaturityLevel.ADOPTING
        reasoning = f"AI/ML keywords mentioned {ai_mentions}x across crawled pages -- appears to be a stated focus."

    # Heuristic path never claims high confidence -- it's a title/meta-tag
    # summary and a keyword count, not analysis.
    confidence = 0.35 if summary else 0.15

    return SynthesisResult(summary=summary, ai_maturity=maturity, reasoning=reasoning, confidence=confidence)
