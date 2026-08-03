from scrapegraph_worker.models import ScrapedLead, SyncOutcome
from scrapegraph_worker.sync import sync_lead


def test_new_company_and_person_are_created(fake_client):
    lead = ScrapedLead(
        full_name="Jane Smith",
        job_title="Managing Partner at Smith & Co CPAs",
        linkedin_url="https://linkedin.com/in/jane-smith",
        email="jane@smithcpa.com",
        location="Austin, TX",
        source="linkedin_harvest",
    )

    result = sync_lead(fake_client, lead, source_run_id="run-1")

    assert result.outcome == SyncOutcome.CREATED
    assert result.company_id is not None
    assert result.person_id is not None
    assert result.opportunity_id is not None  # first time seeing this company -> new lead
    assert result.note_id is not None
    assert fake_client.companies[result.company_id]["name"] == "Smith & Co CPAs"
    assert fake_client.people[result.person_id]["jobTitle"] == "Managing Partner at Smith & Co CPAs"


def test_rerunning_same_company_updates_not_duplicates(fake_client):
    lead1 = ScrapedLead(
        company_name="Acme CPA Partners",
        website="https://acme-cpa.com",
        full_name="Bob Lee",
        email="bob@acme-cpa.com",
        source="linkedin_harvest",
    )
    first = sync_lead(fake_client, lead1, source_run_id="run-1")
    assert first.outcome == SyncOutcome.CREATED
    assert len(fake_client.companies) == 1
    assert len(fake_client.opportunities) == 1

    # Same company, second contact, re-synced later (e.g. a nightly re-run).
    lead2 = ScrapedLead(
        company_name="Acme CPA Partners",
        website="https://acme-cpa.com",
        full_name="Carol King",
        email="carol@acme-cpa.com",
        location="Denver, CO",
        source="linkedin_harvest",
    )
    second = sync_lead(fake_client, lead2, source_run_id="run-2")

    assert second.company_id == first.company_id  # matched, not duplicated
    assert len(fake_client.companies) == 1  # still exactly one Company record
    assert len(fake_client.people) == 2  # two distinct contacts at the same firm
    # No second Opportunity opened for a company we already have.
    assert len(fake_client.opportunities) == 1
    # Company gets enriched with location info it didn't have yet.
    assert fake_client.companies[first.company_id]["address"]["addressCity"] == "Denver, CO"


def test_same_person_seen_twice_is_not_duplicated(fake_client):
    lead = ScrapedLead(
        company_name="Acme CPA Partners",
        website="acme-cpa.com",
        full_name="Bob Lee",
        email="bob@acme-cpa.com",
        source="run_a",
    )
    first = sync_lead(fake_client, lead, source_run_id="run-1")
    second = sync_lead(fake_client, lead, source_run_id="run-2")

    assert first.person_id == second.person_id
    assert len(fake_client.people) == 1


def test_row_with_no_identifying_info_is_skipped_not_fabricated(fake_client):
    lead = ScrapedLead(full_name="Nobody", source="run_a")  # no title, no company, no website

    result = sync_lead(fake_client, lead, source_run_id="run-1")

    assert result.company_id is None
    assert len(fake_client.companies) == 0
    # A person with no company can still exist as a bare contact record.
    assert result.person_id is not None


def test_research_job_records_the_sync_attempt(fake_client):
    lead = ScrapedLead(company_name="Acme CPA Partners", website="acme-cpa.com", source="run_a")

    result = sync_lead(fake_client, lead, source_run_id="run-42")

    assert result.research_job_id is not None
    job = fake_client.research_jobs[result.research_job_id]
    assert job["sourceRunId"] == "run-42"
    assert job["status"] == "IMPORTED"
