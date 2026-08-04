"""Prompt construction for the research pass.

Same pattern as `conversation/prompts.py`: the system prompt pins the exact
JSON shape once, in one place, so `agent.py`'s parsing/normalization step
has a single contract to validate against -- and the model is still
free-text underneath, which is exactly why `normalize_result` never trusts
its output verbatim.

The prompt is unusually insistent about grounding because this is the one
place in the pipeline where the model is asked to *infer* rather than
summarize, and the output lands on a real company's CRM record.
"""

from __future__ import annotations

from ..enrichment.models import EnrichmentResult

SYSTEM_PROMPT = """\
You are a B2B sales researcher. You will be given structured enrichment \
data gathered from a company's own public website. Produce a research \
brief for a sales rep preparing for first contact.

Respond with ONLY a single JSON object (no markdown fences, no commentary) \
with exactly these keys:

{
  "summary": 2-4 sentences on what this company does and who they appear \
to sell to, based ONLY on the provided data,
  "pain_points": array of objects, each { "hypothesis": string, \
"derived_from": string } -- plausible operational or business problems \
this company MAY have,
  "sales_angles": array of objects, each { "angle": string, \
"addresses_pain_point": string, "derived_from": string } -- how a rep \
might open a conversation,
  "buying_signals": array of objects, each { "excerpt": string, \
"source_url": string, "interpretation": string } -- for each buying-signal \
excerpt provided in the input, what it plausibly indicates. Copy `excerpt` \
and `source_url` through EXACTLY as given; only `interpretation` is yours
}

Rules you must follow:

- NEVER invent facts not present in the provided data. No customer names, \
headcounts, revenue figures, funding amounts, technologies, or executive \
names unless they appear verbatim in the input. If the input is thin, \
return fewer items -- an empty array is a correct answer.
- `pain_points` and `sales_angles` are HYPOTHESES, not findings. Phrase \
them as such ("may be", "could suggest", "worth asking whether"). Never \
phrase an inference as an established fact about the company.
- `derived_from` is REQUIRED on every item and must point at something \
actually in the input (e.g. "careers page lists 3 open Engineering roles", \
"tech stack includes HubSpot but no CRM"). Items without a real \
`derived_from` will be discarded, so do not pad the list.
- Do not speculate about a company's finances, internal politics, or the \
competence of named individuals.
- Do not write outreach copy here. Angles are talking points for a human \
to adapt, not messages to send.
- Return at most 5 pain points and at most 5 sales angles. Quality over \
volume.
"""


def build_user_prompt(enrichment: EnrichmentResult, *, company_name: str) -> str:
    """Renders the enrichment record into the model's input. Only fields
    that actually have content are included -- an absent section is
    omitted entirely rather than sent as "none", so the model isn't
    nudged into filling a conspicuous blank.
    """
    parts: list[str] = [f"Company: {company_name or '(name unknown)'}"]

    if enrichment.summary:
        parts.append(f"\nSite summary:\n{enrichment.summary}")

    if enrichment.tech_stack:
        tech = ", ".join(f"{hit.name} ({hit.category})" for hit in enrichment.tech_stack)
        parts.append(f"\nDetected technologies:\n{tech}")

    if enrichment.hiring_signals:
        hiring = "\n".join(
            f"- {signal.department}: {signal.mention_count} mention(s) on {signal.source_url}"
            for signal in enrichment.hiring_signals
        )
        parts.append(f"\nHiring signals:\n{hiring}")

    if enrichment.buying_signals:
        buying = "\n".join(
            f'- keyword "{hit.keyword}" | excerpt: "{hit.excerpt}" | source_url: {hit.source_url}'
            for hit in enrichment.buying_signals[:10]
        )
        parts.append(f"\nBuying-signal excerpts (copy excerpt/source_url through exactly):\n{buying}")

    if enrichment.growth_indicators:
        growth = enrichment.growth_indicators
        parts.append(
            f"\nGrowth indicators:\n- People synced for this company: {growth.synced_people_count}"
            f"\n- Open-role keyword mentions: {growth.open_role_mentions}"
        )

    if enrichment.linkedin_signals and enrichment.linkedin_signals.seniority_mix:
        mix = ", ".join(f"{k}: {v}" for k, v in enrichment.linkedin_signals.seniority_mix.items())
        parts.append(f"\nContacts on file by seniority:\n{mix}")

    if enrichment.ai_maturity:
        parts.append(f"\nApparent AI maturity: {enrichment.ai_maturity.value}")

    return "\n".join(parts)
