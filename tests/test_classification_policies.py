from source_manifest_kit.core.classification import apply_repetition_policy, classify_claim
from source_manifest_kit.core.schema import SourceRecord, utc_now


def source(source_type):
    return SourceRecord("src_001", "run", source_type, "demo", None, None, None, utc_now(), "observable", "input/source_001.txt")


def test_general_news_unsupported_causality():
    claim = classify_claim("The true reason the vote happened was donor pressure.", source("news"), "general")
    assert claim.claim_type == "unverified_causality"
    assert "unsupported_causality" in claim.risk_flags


def test_scheduled_to_is_not_false_causality():
    claim = classify_claim("Construction is scheduled to start in September.", source("news"), "general")
    assert claim.claim_type != "unverified_causality"
    assert "unsupported_causality" not in claim.risk_flags


def test_community_source_not_confirmed():
    claim = classify_claim("Everyone knows this happened.", source("community"), "general")
    assert claim.claim_type != "confirmed_fact"
    assert "community_source" in claim.risk_flags


def test_unobservable_private_deleted_source():
    claim = classify_claim("A deleted post in a private chat proves the claim.", source("news"), "general")
    assert claim.claim_type == "unobservable"
    assert "unobservable_evidence" in claim.risk_flags


def test_analyst_report_interpretation():
    claim = classify_claim("The analyst said the policy may weigh on sentiment.", source("analyst"), "finance")
    assert claim.claim_type == "interpretation"
    assert "analyst_interpretation" in claim.risk_flags


def test_deleted_screenshot_is_unobservable():
    claim = classify_claim("A deleted screenshot proves the internal decision.", source("news"), "general")
    assert claim.claim_type == "unobservable"
    assert "unobservable_evidence" in claim.risk_flags


def test_deleted_staff_message_is_unobservable():
    claim = classify_claim("A deleted staff message confirms the hidden outbreak.", source("news"), "general")
    assert claim.claim_type == "unobservable"
    assert "private_or_inaccessible_source" in claim.risk_flags


def test_private_internal_chat_is_unobservable():
    claim = classify_claim("The private internal chat proves what happened.", source("community"), "finance")
    assert claim.claim_type == "unobservable"
    assert "unobservable_evidence" in claim.risk_flags


def test_inaccessible_comments_member_only_forum_is_unobservable():
    claim = classify_claim("Inaccessible comments in a member-only forum confirm the claim.", source("community"), "finance")
    assert claim.claim_type == "unobservable"
    assert "private_or_inaccessible_source" in claim.risk_flags


def test_fuzzy_duplicate_grouping_for_social_variants():
    s = source("social")
    c1 = classify_claim("A social account says the rally happened because a private group knew earnings early.", s, "finance")
    c2 = classify_claim("Another account says the rally happened because a private group knew earnings early.", s, "finance")
    c1.claim_id = "clm_001"
    c2.claim_id = "clm_002"
    apply_repetition_policy([c1, c2])
    assert c1.duplicate_group_id
    assert c1.duplicate_group_id == c2.duplicate_group_id
    assert "fuzzy_variant_grouped" in c1.risk_flags
    assert "source_laundering_risk" in c2.risk_flags


def test_community_insiders_coordinated_routes_to_rumor_high():
    claim = classify_claim("Insiders coordinated to force liquidations and no primary records were posted.", source("community"), "finance")
    assert claim.claim_type == "rumor"
    assert claim.risk_tier == "high"
