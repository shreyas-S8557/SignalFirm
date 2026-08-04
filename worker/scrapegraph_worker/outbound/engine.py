"""Orchestrates one drafting run: gather company/person/research/ICP
context -> generate.py -> persist as a Note attached to the Company (and
the chosen Person, if any).

Deliberately writes to the existing Note object rather than adding a new
Twenty custom object for outbound drafts. Two reasons: (1) it means this
milestone ships without needing a twenty-app schema migration reviewed and
applied first (same tolerant-write posture EnrichmentJob/ResearchJob use
when their custom object isn't installed yet -- see `_write_*` functions
throughout this codebase), and (2) Notes already show up natively in a
Company/Person's timeline in the Twenty UI, which is exactly where a human
reviewing a draft before sending it would look.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..config import LLMSettings
from ..conversation.llm_client import LLMClient
from .models import MessageChannel, OutboundMessageSet, OutboundStatus, SequenceStep
from .prompts import OutboundContext
from .generator import generate_messages

logger = logging.getLogger(__name__)

_SENIORITY_HINTS = ["chief", "cxo", "founder", "president", "vp", "vice president", "head of", "director"]


def draft_outreach_for_company(client, company_id: str, *, llm_settings: LLMSettings) -> OutboundMessageSet:
    try:
        return _draft_outreach_inner(client, company_id, llm_settings=llm_settings)
    except Exception as exc:  # noqa: BLE001 - a bad company must not kill a batch run
        logger.exception("Unexpected error drafting outreach for company %s", company_id)
        return OutboundMessageSet(company_id=company_id, status=OutboundStatus.FAILED, error_message=str(exc))


def _draft_outreach_inner(client, company_id: str, *, llm_settings: LLMSettings) -> OutboundMessageSet:
    if not llm_settings.is_configured:
        return OutboundMessageSet(
            company_id=company_id,
            status=OutboundStatus.FAILED,
            error_message=(
                "LLM_BASE_URL / LLM_MODEL are not configured -- outreach drafting requires an LLM, same "
                "as Research (see research/engine.py)."
            ),
        )

    company = client.get_record("companies", company_id, depth=0)
    if company is None:
        return OutboundMessageSet(company_id=company_id, status=OutboundStatus.FAILED, error_message="Company not found.")

    person = _pick_top_person(client, company_id)
    research = _latest_researched(client, company_id)
    icp_score = _latest_icp_score(client, company_id)

    ctx = OutboundContext(
        company_name=company.get("name") or "this company",
        person_name=_person_full_name(person),
        person_title=(person or {}).get("jobTitle") or "",
        industry=company.get("industry") or "",
        company_summary=_latest_enrichment_summary(client, company_id),
        pain_points=_extract_hypotheses(research.get("painPoints") if research else None),
        sales_angles=_extract_hypotheses(research.get("salesAngles") if research else None),
        icp_priority=(icp_score or {}).get("priority") or "",
        icp_reasoning=(icp_score or {}).get("reasoning") or "",
    )
    # OutboundContext's sender_name/sender_company/product_one_liner come
    # from OutboundSettings, not LLMSettings -- callers that only have
    # llm_settings (workflow/engine.py) still get the config-driven
    # identity via load_settings() here rather than threading a second
    # settings object through every call site.
    from ..config import load_settings

    outbound_settings = load_settings().outbound
    ctx.sender_name = outbound_settings.sender_name
    ctx.sender_company = outbound_settings.sender_company
    ctx.product_one_liner = outbound_settings.product_one_liner

    with LLMClient(llm_settings) as llm:
        result = generate_messages(
            ctx,
            company_id=company_id,
            person_id=(person or {}).get("id"),
            llm=llm,
            model_name=llm_settings.model,
        )

    result.person_email = ((person or {}).get("emails") or {}).get("primaryEmail")

    if result.status == OutboundStatus.DRAFTED:
        result.note_id = _write_draft_note(client, result, company=company, person=person)
        _schedule_follow_up_sequence(result)

    return result


def _schedule_follow_up_sequence(result: OutboundMessageSet) -> None:
    """Best-effort -- a company/person without a usable email on file still
    gets its sequence scheduled (LinkedIn/call steps don't need one), and a
    sequencing failure must never turn a successful draft into a FAILED
    result.
    """
    if not result.person_id or not result.follow_up_sequence:
        return
    try:
        from ..config import load_settings
        from .sequence import SequenceStore

        settings = load_settings()
        store = SequenceStore(settings.job_store_url.replace("sqlite:///", ""))
        store.schedule_from_message_set(result, recipient_email=result.person_email)
    except Exception:  # noqa: BLE001 - scheduling must not fail the drafting run
        logger.warning("Could not schedule follow-up sequence for person %s", result.person_id, exc_info=True)


def _person_full_name(person: Optional[dict]) -> str:
    if not person:
        return ""
    name = person.get("name") or {}
    return f"{name.get('firstName') or ''} {name.get('lastName') or ''}".strip()


def _pick_top_person(client, company_id: str) -> Optional[dict]:
    people = client.find_records("people", filter_query=f"company.id[eq]:{company_id}", limit=200, depth=0)
    if not people:
        return None
    for person in people:
        title = (person.get("jobTitle") or "").lower()
        if any(hint in title for hint in _SENIORITY_HINTS):
            return person
    return people[0]


def _latest_researched(client, company_id: str) -> Optional[dict]:
    records = client.find_records(
        "researchJobs",
        filter_query=f"company.id[eq]:{company_id}",
        limit=20,
        depth=0,
        order_by="createdAt[DescNullsLast]",
    )
    for record in records:
        if record.get("status") == "RESEARCHED":
            return record
    return None


def _latest_icp_score(client, company_id: str) -> Optional[dict]:
    records = client.find_records(
        "icpScores", filter_query=f"company.id[eq]:{company_id}", limit=1, depth=0, order_by="createdAt[DescNullsLast]"
    )
    return records[0] if records else None


def _latest_enrichment_summary(client, company_id: str) -> str:
    records = client.find_records(
        "enrichmentJobs",
        filter_query=f"company.id[eq]:{company_id}",
        limit=5,
        depth=0,
        order_by="createdAt[DescNullsLast]",
    )
    for record in records:
        if record.get("summary"):
            return record["summary"]
    return ""


def _extract_hypotheses(rendered: Optional[str]) -> list[str]:
    """Inverse of research/engine.py's `_render_pain_points`/
    `_render_sales_angles`: pulls just the hypothesis sentence back out of
    each "- <hypothesis>\\n  (derived from: ...)" block, dropping the
    leading explanatory line and the citation. Outbound drafting wants the
    hypothesis text to weave into a message, not the citation trail --
    that stays in the ICPScore/ResearchJob records for a human to audit.
    """
    if not rendered:
        return []
    hypotheses = []
    for line in rendered.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            hypotheses.append(stripped[2:].split(" (addresses:")[0].strip())
    return hypotheses[:6]


def _write_draft_note(client, result: OutboundMessageSet, *, company: dict, person: Optional[dict]) -> Optional[str]:
    from ..twenty_client import TwentyAPIError

    company_name = company.get("name") or "Unknown Company"
    body = _render_draft_markdown(result)
    title = f"AI Outreach Draft - {company_name}"

    try:
        note = client.create_record("notes", {"title": title, "body": body})
        note_id = note["id"]
        client.create_record("noteTargets", {"noteId": note_id, "companyId": company["id"]})
        if person:
            client.create_record("noteTargets", {"noteId": note_id, "personId": person["id"]})
        return note_id
    except TwentyAPIError:
        logger.warning("Could not write outreach draft Note for company %s", result.company_id)
        return None


def _render_draft_markdown(result: OutboundMessageSet) -> str:
    lines = [
        f"AI-drafted outreach for {result.person_name or '(no named contact)'} "
        f"({result.person_title or 'title unknown'}). Confidence: {result.confidence:.2f}. "
        "Review before sending -- nothing here has been sent automatically.",
        "",
    ]

    if result.linkedin_connection_note:
        lines += ["## LinkedIn connection note", result.linkedin_connection_note, ""]
    if result.linkedin_message:
        lines += ["## LinkedIn message", result.linkedin_message, ""]
    for variant in result.email_variants:
        lines += [f"## Cold email -- variant {variant.label}", f"Subject: {variant.subject or '(none)'}", "", variant.body, ""]
    if result.meeting_request:
        lines += [
            "## Meeting request email",
            f"Subject: {result.meeting_request.subject or '(none)'}",
            "",
            result.meeting_request.body,
            "",
        ]
    if result.call_script:
        cs = result.call_script
        lines += ["## Call script", f"**Opening:** {cs.opening}", ""]
        if cs.discovery_questions:
            lines += ["**Discovery questions:**"] + [f"- {q}" for q in cs.discovery_questions] + [""]
        lines += [f"**Pitch:** {cs.pitch}", ""]
        if cs.objection_handling:
            lines += ["**Objection handling:**"] + [f"- {o}" for o in cs.objection_handling] + [""]
        lines += [f"**Closing:** {cs.closing}", ""]
    if result.follow_up_sequence:
        lines += ["## Follow-up sequence"]
        for step in result.follow_up_sequence:
            lines += [f"**Day {step.day_offset} -- {step.channel.value} ({step.purpose}):**", step.body, ""]

    lines.append(f"<!-- outbound-message-set: {json.dumps(result.model_dump(mode='json'), default=str)} -->")
    return "\n".join(lines)


def parse_sequence_from_note(note_body: str) -> list[SequenceStep]:
    """Round-trips the follow-up sequence back out of a Note's body (see
    the HTML-comment payload `_render_draft_markdown` appends) -- used by
    `sequence.py` when scheduling a sequence from an already-drafted Note
    rather than re-generating one.
    """
    marker = "<!-- outbound-message-set: "
    idx = note_body.find(marker)
    if idx == -1:
        return []
    payload = note_body[idx + len(marker) :].rsplit("-->", 1)[0]
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    steps = []
    for item in data.get("follow_up_sequence", []):
        try:
            steps.append(
                SequenceStep(
                    step_number=item["step_number"],
                    day_offset=item["day_offset"],
                    channel=MessageChannel(item["channel"]),
                    purpose=item.get("purpose", ""),
                    body=item.get("body", ""),
                )
            )
        except (KeyError, ValueError):
            continue
    return steps
