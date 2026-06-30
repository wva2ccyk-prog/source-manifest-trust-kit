from source_manifest_kit.core.classification import classify_claim
from source_manifest_kit.core.risk_policy import (
    has_finance_hype_action_language,
    has_security_price_projection,
    sanitize_for_report,
)
from source_manifest_kit.core.schema import SourceRecord, utc_now


def source(source_type):
    return SourceRecord("src_001", "run", source_type, "demo", None, None, None, utc_now(), "observable", "input/source_001.txt")


def test_finance_news_market_causality_downgraded():
    claim = classify_claim("Foreign investors sold because global fund managers saw the headline.", source("news"), "finance")
    assert claim.claim_type == "unverified_causality"
    assert "market_causality_claim" in claim.risk_flags


def test_official_data_observation_not_motive():
    observation = classify_claim("The exchange reported the index closed at 2640.10 and foreign investors recorded net selling.", source("official"), "finance")
    motive = classify_claim("Foreign investors sold because of one policy headline.", source("official"), "finance")
    assert observation.claim_type == "market_observation"
    assert motive.claim_type == "unverified_causality"
    assert "official_data_causality_mismatch" in motive.risk_flags


def test_official_status_line_classified_as_official_reported_status():
    status_line = classify_claim("Matching engine latency spike observed between 09:42 and 09:57. Service recovered at 10:05.", source("official"), "finance")
    assert status_line.claim_type == "official_reported_status"
    assert status_line.output_level == "report_observation_bucket"


def test_advice_target_position_probability_blocked():
    claim = classify_claim("Buy the stock; target price is higher and position sizing should reflect a 70% chance of success.", source("user_note"), "finance")
    assert claim.claim_type == "excluded"
    assert claim.output_level == "excluded"
    assert "investment_advice_language" in claim.risk_flags
    assert "target_price_language" in claim.risk_flags
    assert "position_sizing_language" in claim.risk_flags
    assert "trade_probability_language" in claim.risk_flags


def test_textual_percent_chance_probability_blocked():
    claim = classify_claim("It gives a 70 percent chance of a profitable trade this month.", source("analyst"), "finance")
    assert claim.claim_type == "excluded"
    assert "trade_probability_language" in claim.risk_flags
    assert "investment_advice_language" in claim.risk_flags


def test_advice_inflections_blocked_and_sanitized():
    text = "The desk is buying exposure aggressively, bought calls yesterday, and says 5x returns are possible."
    claim = classify_claim(text, source("analyst"), "finance")
    assert claim.claim_type == "excluded"
    assert "investment_advice_language" in claim.risk_flags
    sanitized = sanitize_for_report(text, "finance").lower()
    assert "buying exposure" not in sanitized
    assert "bought calls" not in sanitized
    assert "5x returns" not in sanitized


def test_general_mode_defensively_masks_explicit_finance_language_without_short_false_positive():
    assert "buying exposure" not in sanitize_for_report("The source says buying exposure is attractive.", "general").lower()
    assert "target price" not in sanitize_for_report("The note mentions a target price.", "general").lower()
    assert "short excerpt" in sanitize_for_report("The operator captured this short excerpt manually.", "general").lower()


def test_allocating_portfolio_return_projection_blocked():
    claim = classify_claim(
        "The post says allocating 20 percent of a portfolio could produce a 3x return within 90 days.",
        source("community"),
        "finance",
    )
    assert claim.claim_type == "excluded"
    assert claim.output_level == "excluded"
    assert claim.risk_tier == "critical"
    assert "position_sizing_language" in claim.risk_flags
    assert "trade_probability_language" in claim.risk_flags


def test_future_return_projection_without_allocation_blocked():
    claim = classify_claim(
        "The setup could produce a 3x return within 90 days.",
        source("analyst"),
        "finance",
    )
    assert claim.claim_type == "excluded"
    assert "trade_probability_language" in claim.risk_flags


def test_official_benchmark_rate_percent_not_blocked():
    claim = classify_claim("The central bank maintained the benchmark rate at 4.25 percent.", source("official"), "finance")
    assert claim.claim_type == "official_reported_status"
    assert claim.risk_tier == "low"
    assert "position_sizing_language" not in claim.risk_flags
    assert "trade_probability_language" not in claim.risk_flags


def test_investment_rating_language_blocked():
    claim = classify_claim("The desk maintains an overweight view on XYZ.", source("analyst"), "finance")
    assert claim.claim_type == "excluded"
    assert claim.output_level == "excluded"
    assert "investment_advice_language" in claim.risk_flags


def test_urgency_action_language_blocked_and_sanitized():
    text = "Load up now before it is too late."
    claim = classify_claim(text, source("social"), "finance")
    assert claim.claim_type == "excluded"
    assert claim.output_level == "excluded"
    assert "investment_advice_language" in claim.risk_flags
    sanitized = sanitize_for_report(text, "finance").lower()
    assert "load up" not in sanitized
    assert "before it is too late" not in sanitized
    assert "[blocked-investment-action]" in sanitized
    assert "[blocked-urgency-language]" in sanitized


def test_security_price_projection_blocked_and_sanitized():
    text = 'The post says "MU is going to $1300" and the setup is still under 800.'
    claim = classify_claim(text, source("community"), "finance")
    assert claim.claim_type == "excluded"
    assert "target_price_language" in claim.risk_flags
    assert has_security_price_projection(text)
    sanitized = sanitize_for_report(text, "finance")
    assert "MU is going to $1300" not in sanitized
    assert "under 800" not in sanitized
    assert "[blocked-price-level]" in sanitized


def test_finance_hype_action_language_blocked_and_sanitized():
    text = "Better hop on the ride while it is still under 800."
    claim = classify_claim(text, source("community"), "finance")
    assert claim.claim_type == "excluded"
    assert "investment_advice_language" in claim.risk_flags
    assert has_finance_hype_action_language(text)
    sanitized = sanitize_for_report(text, "finance")
    assert "hop on the ride" not in sanitized.lower()
    assert "[blocked-finance-hype-action]" in sanitized


def test_security_price_projection_does_not_mask_general_nonfinance_text():
    text = "The train is going to platform 8 and attendance stayed under 800 workers."
    assert not has_security_price_projection(text)
    sanitized = sanitize_for_report(text, "general")
    assert text in sanitized


def test_korean_community_investment_action_language_blocked_and_sanitized():
    text = "조심들하세요. 저는 환율보고 넥장에서 다 던졌어요. 뉴스마다 사고 팔고 할 필요는 없고 큰손들은 아무도 주식안합니다."
    claim = classify_claim(text, source("community"), "finance")
    assert claim.claim_type == "excluded"
    assert claim.output_level == "excluded"
    assert "investment_advice_language" in claim.risk_flags
    sanitized = sanitize_for_report(text, "finance")
    assert "조심들하세요" not in sanitized
    assert "다 던졌어요" not in sanitized
    assert "사고 팔고" not in sanitized
    assert "주식안합니다" not in sanitized
    assert "[blocked-investment-action]" in sanitized
    assert "[blocked-urgency-language]" in sanitized


def test_korean_recommendation_language_blocked_and_sanitized():
    text = "투자자들은 섹터의 근본적인 성장 궤적인 메모리 수요 확대에 집중할 것을 권고한다."
    claim = classify_claim(text, source("analyst"), "finance")
    assert claim.claim_type == "excluded"
    assert claim.output_level == "excluded"
    assert "investment_advice_language" in claim.risk_flags
    sanitized = sanitize_for_report(text, "finance")
    assert "권고" not in sanitized
    assert "집중할 것을" not in sanitized
    assert "[blocked-investment-recommendation]" in sanitized


def test_korean_recommendation_language_not_masked_in_general_rendering():
    text = "정부는 국민에게 건강한 식습관을 권고한다."
    assert "권고" in sanitize_for_report(text, "general")


def test_official_commentary_with_motive_language_is_not_confirmed_fact():
    claim = classify_claim(
        "A later commentary paragraph claimed investors sold because a translated policy clip spread across overseas desks.",
        source("official"),
        "finance",
    )
    assert claim.claim_type == "unverified_causality"
    assert claim.output_level == "risk_bucket"
    assert "unsupported_causality" in claim.risk_flags
    assert "market_causality_claim" in claim.risk_flags
    assert "official_data_causality_mismatch" in claim.risk_flags
    assert "needs_official_confirmation" in claim.risk_flags


def test_community_manipulation_finance_claim_is_not_neutral_reported_claim():
    claim = classify_claim(
        "The screenshot allegedly shows large funds coordinating exits before the announcement.",
        source("community"),
        "finance",
    )
    assert claim.claim_type in {"rumor", "unverified_causality", "opinion_or_frame"}
    assert claim.claim_type != "reported_claim"
    assert claim.risk_tier == "high"
    assert claim.needs_human_review is True


def test_community_proof_style_planned_claim_is_high_risk():
    claim = classify_claim(
        "This proves the market drop was planned, and the media is hiding the evidence.",
        source("community"),
        "finance",
    )
    assert claim.claim_type != "reported_claim"
    assert claim.risk_tier == "high"
    assert "strong_certainty_language" in claim.risk_flags


def test_social_proof_style_manipulation_escalates_to_rumor_high():
    claim = classify_claim(
        "Everyone knows this proves manipulation.",
        source("social"),
        "finance",
    )
    assert claim.claim_type == "rumor"
    assert claim.risk_tier == "high"
    assert "strong_certainty_language" in claim.risk_flags


def test_analyst_hiding_crash_risk_framing_escalates_to_rumor_high():
    claim = classify_claim(
        "Everyone knows the Fed is hiding the real crash risk to protect banks.",
        source("analyst"),
        "finance",
    )
    assert claim.claim_type == "rumor"
    assert claim.risk_tier == "high"
    assert claim.output_level == "risk_bucket"
    assert "strong_certainty_language" in claim.risk_flags


def test_community_crash_inevitable_routes_to_frame_not_neutral_reported():
    claim = classify_claim(
        "The market is detached from economic reality and a crash is inevitable.",
        source("community"),
        "finance",
    )
    assert claim.claim_type == "opinion_or_frame"
    assert claim.output_level == "risk_bucket"
    assert claim.risk_tier == "medium"
    assert claim.needs_human_review is True


def test_normal_crash_risk_discussion_not_forced_to_rumor():
    claim = classify_claim(
        "Analysts note elevated recession probability based on yield curve inversion.",
        source("analyst"),
        "finance",
    )
    assert claim.claim_type == "interpretation"
    assert claim.risk_tier != "high"



def test_long_inflections_masked_symmetrically_with_short_inflections():
    # Asymmetry guard: GENERAL_RENDER_MASK_PATTERNS must mask long-side
    # inflections (longs/longing/longed) the same way it masks short-side
    # inflections (shorts/shorting/shorted). INVESTMENT_ACTION_PATTERNS
    # already includes both, so detection is symmetric; the masker must be
    # symmetric too, otherwise non-excluded paths leak the raw verb forms.
    for verb in ("longs", "longing", "longed"):
        text = f"The desk {verb} exposure aggressively this week."
        for mode in ("finance", "general"):
            sanitized = sanitize_for_report(text, mode).lower()
            assert verb not in sanitized, (mode, verb, sanitized)
            assert "[blocked-investment-action]" in sanitized, (mode, verb, sanitized)
    # Negative control: the base verb "long" intentionally remains
    # finance-mode-only, to avoid false positives like "long excerpt".
    assert "long excerpt" in sanitize_for_report("The operator captured a long excerpt manually.", "general").lower()
