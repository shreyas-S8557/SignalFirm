"""Prompt construction for AI Outbound Messaging.

Same discipline as research/prompts.py and conversation/prompts.py: the
system prompt pins the exact JSON shape and vocabulary once, so
generator.py's normalization step has a single contract to validate
against, and it's explicit that pain points/sales angles fed in are
hypotheses, not established facts -- the model must not present them to
the prospect as if Opika already knows something about their business that
it's actually only inferring.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OutboundContext:
    company_name: str
    person_name: str
    person_title: str
    industry: str = ""
    company_summary: str = ""
    pain_points: list[str] = field(default_factory=list)
    sales_angles: list[str] = field(default_factory=list)
    icp_priority: str = ""
    icp_reasoning: str = ""
    sender_name: str = "our team"
    sender_company: str = "our company"
    product_one_liner: str = ""


SYSTEM_PROMPT = """\
You are an SDR (sales development rep) assistant drafting a first-touch \
outbound sequence for one prospect. Respond with ONLY a single JSON object \
(no markdown fences, no commentary) with exactly these keys:

{
  "linkedin_connection_note": a LinkedIn connection request note, MAX 300 \
characters (LinkedIn's hard limit), no greeting needed, personalized but \
never presumptuous,
  "linkedin_message": a short (2-4 sentence) LinkedIn DM to send once \
connected, or to send directly if already connected,
  "email_variant_a": {"subject": short subject line, "body": a cold email, \
3-5 short paragraphs, professional but warm tone},
  "email_variant_b": {"subject": a DIFFERENT subject line testing a \
different angle than variant A, "body": a cold email taking a genuinely \
different approach than variant A (e.g. different opening hook, pain \
point emphasized, or call-to-action) -- not a light reword},
  "meeting_request": {"subject": short subject line, "body": a direct, \
brief email specifically proposing a short call/meeting with 2-3 concrete \
time-window suggestions (e.g. "Tuesday or Wednesday afternoon"), for use \
once there's already been some engagement},
  "call_script": {
    "opening": 1-2 sentence opener for a cold call,
    "discovery_questions": array of 3-5 open-ended questions to understand \
their situation,
    "pitch": 2-3 sentence value proposition tailored to what's known about \
this prospect,
    "objection_handling": array of 2-4 short strings, each addressing one \
likely objection (format: "Objection: ... | Response: ..."),
    "closing": 1-2 sentence close asking for a specific next step
  },
  "follow_up_sequence": array of 4-6 objects, each \
{"day_offset": integer days after the FIRST touch (day 0), "channel": one \
of "LINKEDIN_CONNECTION" | "LINKEDIN_MESSAGE" | "EMAIL" | \
"MEETING_REQUEST" | "CALL", "purpose": short phrase describing this \
touch's goal, "body": the actual message/script for this specific touch}, \
ordered by day_offset ascending, spanning roughly 2-3 weeks total,
  "confidence": your confidence these drafts are usable as-is with only \
light human editing, as a number between 0 and 1
}

Guidance:
- Never invent facts, pricing, case studies, mutual connections, or \
commitments that weren't given to you in the prospect context below.
- Any pain point or sales angle you were given is a HYPOTHESIS a research \
pass inferred, not a confirmed fact -- phrase references to it as an \
observation or a question ("noticed you're hiring for..."), never as \
something you're certain the company is dealing with.
- Keep every message specific to the actual person/company/industry given, \
not generic boilerplate -- if very little context was provided, keep the \
personalization proportionate (don't fabricate detail to sound specific).
- Never use high-pressure, manipulative, or deceptive tactics (fake \
urgency, misleading subject lines, pretending to know the person).
- The call_script's objection_handling should reflect realistic objections \
for this industry/persona, not generic ones.
"""


def build_user_prompt(ctx: OutboundContext) -> str:
    lines = [
        f"Prospect: {ctx.person_name or '(name unknown)'}, {ctx.person_title or '(title unknown)'} "
        f"at {ctx.company_name}",
        f"Industry: {ctx.industry or '(unknown)'}",
    ]
    if ctx.company_summary:
        lines.append(f"Company summary: {ctx.company_summary}")
    if ctx.pain_points:
        lines.append("Pain-point hypotheses (inferred, cite carefully -- see guidance above):")
        lines += [f"- {p}" for p in ctx.pain_points]
    if ctx.sales_angles:
        lines.append("Sales-angle hypotheses (talking points, adapt naturally, do not read verbatim):")
        lines += [f"- {a}" for a in ctx.sales_angles]
    if ctx.icp_priority:
        lines.append(f"ICP fit priority: {ctx.icp_priority}" + (f" -- {ctx.icp_reasoning}" if ctx.icp_reasoning else ""))
    lines.append(f"Sender: {ctx.sender_name} at {ctx.sender_company}.")
    if ctx.product_one_liner:
        lines.append(f"What {ctx.sender_company} sells, in one line: {ctx.product_one_liner}")
    return "\n".join(lines)
