from __future__ import annotations

import hashlib
import re

from .risk_policy import detect_risk_flags, has_causality, has_manipulation_framing, has_market_terms, has_motive_markers, has_number
from .schema import ClaimRecord, SourceRecord, utc_now


def normalized_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Company-branch guards (local to classification.py; do NOT edit risk_policy).
# ---------------------------------------------------------------------------
# FIX 1: A company-typed source must not render self-serving / private-evidence
# claims — or unverifiable third-party allegations — as confirmed fact, even when
# no risk flag fires (e.g. "Our internal investigation proved the rival firm
# bribed ..." raises no lexicon flag but is unobservable, unverifiable material).
_COMPANY_SELF_SERVING_MARKERS_EN = (
    "our internal",
    "our own investigation",
    "our investigation",
    "internal investigation",
    "internal probe",
    "we proved",
    "we have proof",
    "proved that",
    "we confirmed that",
)
_COMPANY_SELF_SERVING_MARKERS_KO = (
    "우리 내부",
    "내부 조사",
    "자체 조사",
    "내부 조사 결과",
    "입증했다",
)


def _company_unverifiable_private_allegation(text: str) -> bool:
    lower = text.lower()
    if any(marker in lower for marker in _COMPANY_SELF_SERVING_MARKERS_EN):
        return True
    if any(marker in text for marker in _COMPANY_SELF_SERVING_MARKERS_KO):
        return True
    return False


# FIX 2: A company-typed source must not render a forward-looking / predictive
# claim that is also market-wide / sector-wide in scope as confirmed fact
# (e.g. "... 업계 전반의 투자 심리가 개선되고 ... 종목 전체의 주가 흐름이 개선될
# 것이라고 밝혔다."). The -로 form is not a lexicon causal marker, so the existing
# (causal and market) guard misses it; detect via forward-looking + broad-scope
# text markers instead.
_FORWARD_LOOKING_RE_EN = re.compile(
    r"\b(?:will|expected to|is expected|are expected|projected to|going to|"
    r"likely to|forecasts?|outlook)\b"
)
_FORWARD_LOOKING_RE_KO = re.compile(
    r"것(?:이다|으로|이라|입니다|이라고)|전망|될\s*것|개선될|호전될|악화될"
)
_SCOPE_BROAD_RE_EN = re.compile(
    r"\b(?:sector-?wide|market-?wide|industry-?wide|"
    r"entire (?:market|sector|industry)|across the (?:market|sector|industry|board))\b"
)
_SCOPE_BROAD_MARKERS_KO = ("업계", "전반", "시장 전체", "종목 전체", "전 종목", "전체 종목", "산업 전반")


def _forward_looking_market_wide(text: str) -> bool:
    lower = text.lower()
    forward = bool(_FORWARD_LOOKING_RE_EN.search(lower)) or bool(_FORWARD_LOOKING_RE_KO.search(text))
    if not forward:
        return False
    if any(marker in text for marker in _SCOPE_BROAD_MARKERS_KO):
        return True
    return bool(_SCOPE_BROAD_RE_EN.search(lower))


def _fuzzy_social_assertion_hash(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"^\[[^\]]+\]\s+", "", normalized)
    normalized = re.sub(r"^(a|an|the)\s+(first|second|third|another)\s+(social\s+)?(account|post)\s+(says|claimed|claims|repeats|repeated)\s+that\s+", "", normalized)
    normalized = re.sub(r"^(a|an|the)\s+(social\s+)?(account|post)\s+(says|claimed|claims|repeats|repeated)\s+", "", normalized)
    normalized = re.sub(r"^(another|second|third)\s+account\s+(says|claimed|claims|repeats|repeated)\s+", "", normalized)
    normalized = re.sub(r"[\W_]+", " ", normalized).strip()
    tokens = [t for t in normalized.split() if t not in {"a", "an", "the", "that", "this", "so", "and"}]
    return " ".join(tokens[:20])


def _risk_tier(flags: list[str], claim_type: str, mode: str) -> str:
    critical_flags = {"investment_advice_language", "target_price_language", "position_sizing_language", "trade_probability_language"}
    high_flags = {"market_causality_claim", "true_cause_market_claim", "unobservable_evidence", "private_or_inaccessible_source"}
    if mode == "finance" and any(flag in flags for flag in critical_flags):
        return "critical"
    if claim_type in {"unverified_causality", "unobservable", "excluded", "rumor"} or any(flag in flags for flag in high_flags):
        return "high"
    if any(flag in flags for flag in {"unsupported_causality", "framing_risk", "loaded_language", "strong_certainty_language", "needs_official_confirmation"}):
        return "medium"
    return "low"


def classify_claim(text: str, source: SourceRecord, mode: str) -> ClaimRecord:
    source_type = source.source_type
    flags = detect_risk_flags(text, source_type, mode, source.published_at)
    causal = has_causality(text)
    market = has_market_terms(text)
    motive = has_motive_markers(text)
    manipulation = has_manipulation_framing(text)
    numbered = has_number(text)
    claim_type = "reported_claim"
    status = "reported"
    output_level = "reported_claim_bucket"
    confidence = 0.35
    notes = "Default reported claim."
    disallowed_reason: str | None = None
    if mode == "finance" and any(flag in flags for flag in {"investment_advice_language", "target_price_language", "position_sizing_language", "trade_probability_language"}):
        # Finance action/price/allocation/probability language is exclusion-worthy at the
        # highest priority: it must outrank the unobservable branch so a finance claim that
        # also carries a private/unobservable marker is still masked as excluded, not leaked.
        claim_type = "excluded"; status = "blocked"; output_level = "excluded"; confidence = 0.9; disallowed_reason = "Finance mode blocks investment-action, price-level, allocation, and probability language."; notes = disallowed_reason
    elif "unobservable_evidence" in flags or source.observable_state == "unobservable":
        claim_type = "unobservable"; status = "unobservable"; output_level = "review_only"; confidence = 0.2; notes = "Claim depends on inaccessible or unobservable material."
    elif source_type in {"community", "social"}:
        if manipulation:
            claim_type = "rumor"; status = "unverified"; output_level = "risk_bucket"; confidence = 0.25; notes = "Community/social manipulation-style narrative is treated as rumor and requires review."
        elif causal:
            claim_type = "unverified_causality"; status = "unverified"; output_level = "risk_bucket"; confidence = 0.3; notes = "Community/social causal claims cannot be confirmed facts."
        elif "framing_risk" in flags or "loaded_language" in flags or "strong_certainty_language" in flags:
            claim_type = "opinion_or_frame"; status = "framing_risk"; output_level = "risk_bucket"; confidence = 0.35; notes = "Community/social framing is treated as a signal, not fact."
        else:
            claim_type = "reported_claim"; status = "unverified"; output_level = "reported_claim_bucket"; confidence = 0.35; notes = "Community/social source is treated as unverified reported material."
    elif source_type == "official":
        official_finance_causal = mode == "finance" and (
            causal and (market or motive or "market_causality_claim" in flags or "flow_data_overinterpretation" in flags)
        )
        if official_finance_causal:
            claim_type = "unverified_causality"; status = "unverified"; output_level = "risk_bucket"; confidence = 0.45; notes = "Official data can show what happened, but this causal statement still needs support."
        elif mode == "finance" and market and numbered:
            claim_type = "market_observation"; status = "confirmed"; output_level = "report_observation_bucket"; confidence = 0.9; notes = "Official market data supports an observation, not motive."
        else:
            claim_type = "official_reported_status"; status = "reported"; output_level = "report_observation_bucket"; confidence = 0.8; notes = "Official source status line is treated as cautious reported status."
    elif source_type == "company":
        if causal and market:
            claim_type = "unverified_causality"; status = "unverified"; output_level = "risk_bucket"; confidence = 0.45; notes = "Company source does not confirm broad market causality."
        elif _company_unverifiable_private_allegation(text):
            # FIX 1: self-serving / private-evidence or unverifiable third-party
            # allegation must not render as observed fact from a company source.
            claim_type = "needs_official_source"; status = "unverified"; output_level = "review_only"; confidence = 0.25; notes = "Company claim rests on internal/private evidence or an unverifiable third-party allegation; needs an official or primary source before it can be treated as fact."
        elif _forward_looking_market_wide(text):
            # FIX 2: forward-looking, market-wide/sector-wide prediction is
            # interpretation, not a company-confirmed fact.
            claim_type = "interpretation"; status = "likely"; output_level = "interpretation_bucket"; confidence = 0.4; notes = "Company forward-looking, market-wide prediction is interpretation and cannot be a confirmed fact."
        else:
            claim_type = "confirmed_fact"; status = "confirmed"; output_level = "report_fact_bucket"; confidence = 0.75; notes = "Company source can support company-specific factual statements."
    elif source_type == "analyst":
        if mode == "finance" and manipulation:
            claim_type = "rumor"; status = "unverified"; output_level = "risk_bucket"; confidence = 0.3; notes = "Analyst manipulation-style framing remains unverified and requires review."
        elif mode == "finance" and causal and market and "true_cause_market_claim" in flags:
            claim_type = "unverified_causality"; status = "unverified"; output_level = "risk_bucket"; confidence = 0.4; notes = "Analyst true-cause market claims remain unverified."
        else:
            claim_type = "interpretation"; status = "likely"; output_level = "interpretation_bucket"; confidence = 0.55; notes = "Analyst material is interpretation by default."
    elif source_type == "news":
        if causal and (market or mode == "general"):
            claim_type = "unverified_causality"; status = "unverified"; output_level = "risk_bucket"; confidence = 0.4; notes = "News causal explanation needs primary or independent support."
        elif mode == "finance" and market and numbered:
            claim_type = "market_observation"; status = "reported"; output_level = "report_observation_bucket"; confidence = 0.55; notes = "News reports a market observation; official source is preferred."
        elif "framing_risk" in flags or "loaded_language" in flags:
            claim_type = "opinion_or_frame"; status = "framing_risk"; output_level = "risk_bucket"; confidence = 0.4; notes = "News text contains framing risk."
        else:
            claim_type = "reported_claim"; status = "reported"; output_level = "reported_claim_bucket"; confidence = 0.5; notes = "News is treated as reported material unless primary support is supplied."
    else:
        if causal:
            claim_type = "unverified_causality"; status = "unverified"; output_level = "risk_bucket"; confidence = 0.3; notes = "Unknown or user-provided causal claim needs verification."
        else:
            claim_type = "needs_official_source"; status = "unverified"; output_level = "review_only"; confidence = 0.25; notes = "Source type is not strong enough for confirmation."
    tier = _risk_tier(flags, claim_type, mode)
    needs_review = tier in {"high", "critical"} or output_level in {"review_only", "excluded"} or claim_type in {"unverified_causality", "unobservable"} or (source_type == "company" and claim_type == "interpretation")
    if source_type in {"community", "social"} and claim_type in {"opinion_or_frame", "rumor"}:
        needs_review = True
    if source_type in {"community", "social"} and claim_type == "confirmed_fact":
        claim_type = "reported_claim"; status = "unverified"; output_level = "reported_claim_bucket"; needs_review = True; disallowed_reason = "Community/social claims cannot become confirmed facts."
    return ClaimRecord("", source.run_id, source.source_id, text, claim_type, status, output_level, tier, flags, needs_review, disallowed_reason, confidence, notes, utc_now(), source_type, source.source_name, normalized_hash(text), None, 1, 1 if claim_type in {"confirmed_fact", "market_observation", "official_reported_status"} and source_type in {"official", "company"} else 0, None)


def apply_repetition_policy(claims: list[ClaimRecord]) -> None:
    groups: dict[str, list[ClaimRecord]] = {}
    for claim in claims:
        if claim.normalized_claim_hash:
            groups.setdefault(claim.normalized_claim_hash, []).append(claim)
    for index, group in enumerate(groups.values(), start=1):
        if len(group) <= 1:
            continue
        group_id = f"dup_{index:03d}"
        for claim in group:
            claim.duplicate_group_id = group_id
            claim.source_count = len(group)
            claim.independent_source_count = min(claim.independent_source_count, 1)
            claim.lineage_note = "Repeated text was detected; v0 does not treat repetition as independent corroboration."
            for flag in ("repetition_without_lineage", "source_laundering_risk"):
                if flag not in claim.risk_flags:
                    claim.risk_flags.append(flag)
            if claim.risk_tier == "low":
                claim.risk_tier = "medium"
    # Optional fuzzy grouping for social/community assertion variants.
    fuzzy_groups: dict[str, list[ClaimRecord]] = {}
    for claim in claims:
        if claim.source_type in {"community", "social"} and claim.claim_type in {"reported_claim", "opinion_or_frame", "unverified_causality", "rumor", "unobservable"}:
            key = _fuzzy_social_assertion_hash(claim.claim_text)
            if key:
                fuzzy_groups.setdefault(key, []).append(claim)
    base_index = len([g for g in groups.values() if len(g) > 1])
    for index, group in enumerate(fuzzy_groups.values(), start=1):
        if len(group) <= 1:
            continue
        if any(c.duplicate_group_id for c in group):
            continue
        group_id = f"dup_fuzzy_{base_index + index:03d}"
        for claim in group:
            claim.duplicate_group_id = group_id
            claim.source_count = len(group)
            claim.independent_source_count = min(claim.independent_source_count, 1)
            claim.lineage_note = "Similar social/community assertion variants were grouped; repetition is not independent corroboration."
            for flag in ("repetition_without_lineage", "source_laundering_risk", "fuzzy_variant_grouped"):
                if flag not in claim.risk_flags:
                    claim.risk_flags.append(flag)
            if claim.risk_tier == "low":
                claim.risk_tier = "medium"

