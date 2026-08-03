"""Turns one ScrapedLead into Company / Person / Opportunity / Note records
inside Twenty, deduplicating against what's already there and updating
existing records instead of creating duplicates on re-runs.

Mapping used throughout this file (see architecture-analysis doc §3.2):
  Company      <- the CPA firm
  Person       <- the decision maker (contact)
  Opportunity  <- stands in for "Lead" (Twenty has no separate Lead object;
                  its pipeline object is Opportunity, used here as the
                  lead/prospect record, created in Twenty's default pipeline
                  at whatever stage Twenty's default pipeline first stage is)
  Note         <- stands in for "Activity" (Notes show up in the record's
                  timeline automatically, alongside the auto-generated
                  "record created" timeline entries Twenty already produces)
  ResearchJob  <- one row per sync attempt, for progress/audit visibility in
                  the CRM itself (custom object, see twenty-app-crm-sync/)

No AI/LLM calls happen anywhere in this module.
"""

from __future__ import annotations

import logging
from typing import Optional

from . import dedup
from .models import ScrapedLead, SyncOutcome, SyncResult
from .twenty_client import TwentyAPIError, TwentyClient

logger = logging.getLogger(__name__)

# Twenty's default "won't lose the deal" first pipeline stage name varies per
# workspace config; NEW is the conventional default label shipped with a
# fresh Twenty workspace's Opportunities pipeline.
DEFAULT_OPPORTUNITY_STAGE = "NEW"


class SyncError(RuntimeError):
    pass


def sync_lead(client: TwentyClient, lead: ScrapedLead, *, source_run_id: str) -> SyncResult:
    try:
        company_id, company_outcome, matched_existing = _upsert_company(client, lead)
        person_id = _upsert_person(client, lead, company_id=company_id) if _has_person_data(lead) else None
        opportunity_id = _create_opportunity_if_new(client, lead, company_id=company_id, outcome=company_outcome)
        note_id = _create_activity_note(client, lead, company_id=company_id, person_id=person_id)
        research_job_id = _record_research_job(
            client,
            lead,
            company_id=company_id,
            outcome=company_outcome,
            source_run_id=source_run_id,
        )

        return SyncResult(
            outcome=SyncOutcome.CREATED if company_outcome == "created" else SyncOutcome.UPDATED,
            company_id=company_id,
            person_id=person_id,
            opportunity_id=opportunity_id,
            note_id=note_id,
            research_job_id=research_job_id,
            matched_existing_company_id=matched_existing,
        )
    except TwentyAPIError as exc:
        logger.exception("Twenty API error syncing lead %r", lead.company_name or lead.full_name)
        return SyncResult(outcome=SyncOutcome.ERROR, reason=str(exc))
    except Exception as exc:  # noqa: BLE001 - a bad row should not kill the whole job
        logger.exception("Unexpected error syncing lead %r", lead.company_name or lead.full_name)
        return SyncResult(outcome=SyncOutcome.ERROR, reason=str(exc))


# ----------------------------------------------------------------------
# Company
# ----------------------------------------------------------------------


def _resolve_company_name(lead: ScrapedLead) -> str:
    if lead.company_name:
        return lead.company_name.strip()
    derived = dedup.derive_company_name_from_title(lead.job_title or "")
    return derived


def _upsert_company(client: TwentyClient, lead: ScrapedLead) -> tuple[Optional[str], str, Optional[str]]:
    """Returns (company_id, "created"|"updated"|"skipped", matched_existing_id)."""
    company_name = _resolve_company_name(lead)
    domain = dedup.normalize_domain(lead.website or "")

    if not company_name and not domain:
        # Nothing to anchor a Company record on -- do not fabricate one.
        return None, "skipped", None

    existing = _find_existing_company(client, name=company_name, domain=domain)

    if existing:
        updated_fields = _diff_company_fields(existing, lead, domain)
        if updated_fields:
            client.update_record("companies", existing["id"], updated_fields)
        return existing["id"], "updated", existing["id"]

    fields: dict = {"name": company_name or domain}
    if domain:
        fields["domainName"] = {"primaryLinkUrl": f"https://{domain}", "primaryLinkLabel": ""}
    if lead.location:
        fields["address"] = {"addressCity": lead.location}
    created = client.create_record("companies", fields)
    return created["id"], "created", None


def _find_existing_company(client: TwentyClient, *, name: str, domain: str) -> Optional[dict]:
    if domain:
        by_domain = client.find_company_by_domain(domain)
        if by_domain:
            return by_domain
    if name:
        # Cheap exact-ish lookup first; fall back to scanning ilike matches
        # for fuzzy comparison since Twenty's REST filter has no "similarity"
        # operator to push the fuzzy match down to the database.
        candidates = client.find_records("companies", filter_query=f"name[ilike]:%{name[:40]}%", limit=10)
        for candidate in candidates:
            if dedup.is_likely_same_company(
                candidate_name=name,
                candidate_domain=domain,
                existing_name=candidate.get("name", ""),
                existing_domain=(candidate.get("domainName") or {}).get("primaryLinkUrl", ""),
            ):
                return candidate
    return None


def _diff_company_fields(existing: dict, lead: ScrapedLead, domain: str) -> dict:
    """Only send fields that are genuinely new/different, so re-syncing the
    same company repeatedly does not generate no-op update calls or
    overwrite a manually-edited value with a blank scraped one.
    """
    updates: dict = {}
    if domain and not (existing.get("domainName") or {}).get("primaryLinkUrl"):
        updates["domainName"] = {"primaryLinkUrl": f"https://{domain}", "primaryLinkLabel": ""}
    if lead.location and not (existing.get("address") or {}).get("addressCity"):
        updates["address"] = {"addressCity": lead.location}
    return updates


# ----------------------------------------------------------------------
# Person / contact
# ----------------------------------------------------------------------


def _has_person_data(lead: ScrapedLead) -> bool:
    return bool(lead.full_name or lead.email or lead.linkedin_url)


def _upsert_person(client: TwentyClient, lead: ScrapedLead, *, company_id: Optional[str]) -> Optional[str]:
    existing = _find_existing_person(client, lead)
    if existing:
        updates = _diff_person_fields(existing, lead, company_id)
        if updates:
            client.update_record("people", existing["id"], updates)
        return existing["id"]

    first_name, last_name = _split_name(lead.full_name or "")
    fields: dict = {"name": {"firstName": first_name, "lastName": last_name}}
    if lead.job_title:
        fields["jobTitle"] = lead.job_title
    if lead.email:
        fields["emails"] = {"primaryEmail": lead.email, "additionalEmails": []}
    if lead.linkedin_url:
        fields["linkedinLink"] = {"primaryLinkUrl": lead.linkedin_url, "primaryLinkLabel": ""}
    if lead.phone:
        fields["phones"] = {"primaryPhoneNumber": lead.phone}
    if company_id:
        fields["companyId"] = company_id

    created = client.create_record("people", fields)
    return created["id"]


def _find_existing_person(client: TwentyClient, lead: ScrapedLead) -> Optional[dict]:
    if lead.email:
        match = client.find_person_by_email(lead.email)
        if match:
            return match
    if lead.linkedin_url:
        match = client.find_person_by_linkedin(lead.linkedin_url)
        if match:
            return match
    return None


def _diff_person_fields(existing: dict, lead: ScrapedLead, company_id: Optional[str]) -> dict:
    updates: dict = {}
    if lead.job_title and not existing.get("jobTitle"):
        updates["jobTitle"] = lead.job_title
    if lead.phone and not (existing.get("phones") or {}).get("primaryPhoneNumber"):
        updates["phones"] = {"primaryPhoneNumber": lead.phone}
    if company_id and not existing.get("companyId"):
        updates["companyId"] = company_id
    return updates


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


# ----------------------------------------------------------------------
# Opportunity ("Lead") + Note ("Activity")
# ----------------------------------------------------------------------


def _create_opportunity_if_new(
    client: TwentyClient, lead: ScrapedLead, *, company_id: Optional[str], outcome: str
) -> Optional[str]:
    if not company_id or outcome != "created":
        # Only open a new opportunity the first time we see this company --
        # re-syncing an already-known company should not spawn duplicate
        # pipeline entries every run.
        return None
    fields = {
        "name": f"{_resolve_company_name(lead) or 'Unknown company'} - inbound lead",
        "companyId": company_id,
        "stage": DEFAULT_OPPORTUNITY_STAGE,
    }
    created = client.create_record("opportunities", fields)
    return created["id"]


def _create_activity_note(
    client: TwentyClient, lead: ScrapedLead, *, company_id: Optional[str], person_id: Optional[str]
) -> Optional[str]:
    if not company_id:
        return None
    body_lines = [f"Imported via Scrapegraph (source: {lead.source})."]
    if lead.summary:
        body_lines.append(lead.summary)
    note = client.create_record("notes", {"title": "Scrapegraph import", "body": "\n\n".join(body_lines)})
    note_id = note["id"]
    # Attach the note to the company (and person, if we have one) via
    # Twenty's noteTargets join object.
    client.create_record("noteTargets", {"noteId": note_id, "companyId": company_id})
    if person_id:
        client.create_record("noteTargets", {"noteId": note_id, "personId": person_id})
    return note_id


def _record_research_job(
    client: TwentyClient,
    lead: ScrapedLead,
    *,
    company_id: Optional[str],
    outcome: str,
    source_run_id: str,
) -> Optional[str]:
    """Writes one ResearchJob record per sync attempt so progress/history is
    visible natively inside Twenty (Settings -> Data model -> Research Jobs),
    independent of the worker's own /jobs API. Status here reflects "the
    import step completed" only -- the AI research pass (Phase 5) will later
    update this same record's status onward, once it exists.
    """
    fields = {
        "name": _resolve_company_name(lead) or lead.full_name or "Unknown",
        "status": "IMPORTED" if outcome in ("created", "updated") else "SKIPPED",
        "source": lead.source,
        "sourceRunId": source_run_id,
        "companyId": company_id,
    }
    try:
        created = client.create_record("researchJobs", fields)
        return created["id"]
    except TwentyAPIError:
        # The ResearchJob custom object may not be synced into this
        # workspace yet -- degrade gracefully rather than failing the whole
        # sync over a bookkeeping record.
        logger.warning("Could not write ResearchJob (custom object may not be installed yet)")
        return None
