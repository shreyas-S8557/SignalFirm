from scrapegraph_worker import dedup


def test_normalize_domain_strips_scheme_www_path():
    assert dedup.normalize_domain("https://www.Acme-CPA.com/about") == "acme-cpa.com"
    assert dedup.normalize_domain("acme-cpa.com") == "acme-cpa.com"
    assert dedup.normalize_domain("") == ""


def test_normalize_company_name_strips_legal_suffixes():
    # "Co", "CPAs", "LLC" are all treated as legal-form/practice-type noise
    # for comparison purposes -- only the distinctive part of the name should
    # survive normalization.
    assert dedup.normalize_company_name("Smith & Co CPAs, LLC") == "smith"
    assert dedup.normalize_company_name("Smith & Co, CPAs") == "smith"


def test_is_likely_same_company_domain_match_is_decisive():
    assert dedup.is_likely_same_company(
        candidate_name="Totally Different Name Inc",
        candidate_domain="https://acme-cpa.com",
        existing_name="Acme CPA Partners LLC",
        existing_domain="acme-cpa.com",
    )


def test_is_likely_same_company_different_domains_never_match_on_name_alone():
    # Even a high name-similarity should not override two different domains.
    assert not dedup.is_likely_same_company(
        candidate_name="Acme CPA Partners",
        candidate_domain="acme-cpa.com",
        existing_name="Acme CPA Partners",
        existing_domain="acme-cpa-of-texas.com",
    )


def test_is_likely_same_company_fuzzy_name_fallback_when_no_domain():
    assert dedup.is_likely_same_company(
        candidate_name="Smith & Associates CPAs",
        candidate_domain="",
        existing_name="Smith and Associates CPA",
        existing_domain="",
    )
    assert not dedup.is_likely_same_company(
        candidate_name="Smith & Associates CPAs",
        candidate_domain="",
        existing_name="Jones & Partners Accounting",
        existing_domain="",
    )


def test_is_likely_same_person_email_decisive():
    assert dedup.is_likely_same_person(
        candidate_email="Jane@Acme.com",
        candidate_linkedin="",
        existing_email="jane@acme.com",
        existing_linkedin="https://linkedin.com/in/someone-else",
    )


def test_is_likely_same_person_linkedin_normalizes_tracking_params():
    assert dedup.is_likely_same_person(
        candidate_email="",
        candidate_linkedin="https://www.linkedin.com/in/jane-smith/?utm_source=x",
        existing_email="",
        existing_linkedin="linkedin.com/in/jane-smith",
    )


def test_derive_company_name_from_title_at_pattern():
    assert dedup.derive_company_name_from_title("Managing Partner at Smith & Co CPAs") == "Smith & Co CPAs"


def test_derive_company_name_from_title_comma_pattern():
    assert dedup.derive_company_name_from_title("Partner, Jones Accounting Group") == "Jones Accounting Group"


def test_derive_company_name_from_title_no_pattern_returns_empty():
    assert dedup.derive_company_name_from_title("Accountant") == ""
    assert dedup.derive_company_name_from_title("") == ""
