from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SOURCE_TYPES = {
    "official",
    "company",
    "news",
    "analyst",
    "community",
    "social",
    "user_note",
    "unknown",
}

SOURCE_STATES = {
    "observable",
    "partially_observable",
    "unobservable",
    "missing_source",
    "stale_or_undated",
}

CLAIM_TYPES = {
    "confirmed_fact",
    "official_reported_status",
    "market_observation",
    "reported_claim",
    "interpretation",
    "opinion_or_frame",
    "unverified_causality",
    "rumor",
    "needs_official_source",
    "unobservable",
    "excluded",
    "question_to_verify",
}

VERIFICATION_STATUSES = {
    "confirmed",
    "reported",
    "likely",
    "unverified",
    "disputed",
    "framing_risk",
    "unobservable",
    "blocked",
}

OUTPUT_LEVELS = {
    "report_fact_bucket",
    "report_observation_bucket",
    "reported_claim_bucket",
    "interpretation_bucket",
    "risk_bucket",
    "review_only",
    "excluded",
}

RISK_TIERS = {"low", "medium", "high", "critical"}
MODES = {"general", "finance"}

REQUIRED_RISK_FLAGS = {
    "unsupported_causality",
    "framing_risk",
    "loaded_language",
    "strong_certainty_language",
    "action_recommendation_language",
    "private_or_inaccessible_source",
    "stale_or_missing_date",
    "repetition_without_lineage",
    "source_laundering_risk",
    "community_source",
    "social_source",
    "needs_official_confirmation",
    "unobservable_evidence",
    "market_causality_claim",
    "flow_data_overinterpretation",
    "official_data_causality_mismatch",
    "analyst_interpretation",
    "community_market_signal_misuse",
    "investment_advice_language",
    "target_price_language",
    "position_sizing_language",
    "trade_probability_language",
    "true_cause_market_claim",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_source_type(value: str | None) -> str:
    if not value:
        return "unknown"
    normalized = value.strip().lower().replace("-", "_")
    return normalized if normalized in SOURCE_TYPES else "unknown"


@dataclass(slots=True)
class SourceRecord:
    source_id: str
    run_id: str
    source_type: str
    source_name: str
    source_url: str | None
    title: str | None
    published_at: str | None
    captured_at: str
    observable_state: str
    raw_input_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ClaimRecord:
    claim_id: str
    run_id: str
    source_id: str
    claim_text: str
    claim_type: str
    verification_status: str
    output_level: str
    risk_tier: str
    risk_flags: list[str] = field(default_factory=list)
    needs_human_review: bool = False
    disallowed_reason: str | None = None
    confidence: float = 0.3
    classification_notes: str = ""
    created_at: str = field(default_factory=utc_now)
    source_type: str = "unknown"
    source_name: str = "unknown"
    normalized_claim_hash: str | None = None
    duplicate_group_id: str | None = None
    source_count: int = 1
    independent_source_count: int = 0
    lineage_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewItem:
    review_id: str
    claim_id: str
    reason: str
    risk_tier: str
    status: str
    verification_question: str
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunManifest:
    run_id: str
    mode: str
    issue_id: str | None
    input_file: str
    created_at: str
    source_count: int
    claim_count: int
    review_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
