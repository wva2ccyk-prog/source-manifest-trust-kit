from __future__ import annotations

import os
from pathlib import Path

from .report_gates import bucket_for_claim, build_report_gates
from .risk_policy import escape_markdown_inline, sanitize_for_report
from .validation import load_run

SECTION_ORDER = [
    ("confirmed_facts", "Confirmed facts"),
    ("official_reported_status", "Official reported status"),
    ("market_observations", "Market observations"),
    ("reported_claims", "Reported claims"),
    ("interpretations", "Interpretations"),
    ("opinion_frame_risks", "Opinion and frame risks"),
    ("unverified_causality", "Unverified causality"),
    ("rumors", "Rumors"),
    ("needs_official_source", "Needs official source"),
    ("unobservable", "Unobservable material"),
    ("excluded", "Excluded or blocked material"),
]


def _claim_line(claim: dict, mode: str, detail_mode: str) -> str:
    if mode == "finance" and claim.get("claim_type") == "excluded":
        flags = ", ".join(claim.get("risk_flags") or []) or "none"
        note = claim.get("classification_notes") or ""
        if detail_mode == "detailed":
            categories = []
            if "investment_advice_language" in (claim.get("risk_flags") or []):
                categories.append("investment_action")
            if "target_price_language" in (claim.get("risk_flags") or []):
                categories.append("price_target")
            if "position_sizing_language" in (claim.get("risk_flags") or []):
                categories.append("allocation")
            if "trade_probability_language" in (claim.get("risk_flags") or []):
                categories.append("probability_or_outcome")
            category_text = ", ".join(categories) if categories else "finance_policy_block"
            return (
                "- [excluded-unsafe-finance-claim] "
                f"(blocked_categories: {category_text}; source: {claim.get('source_name')}; "
                f"type: {claim.get('claim_type')}; risk: {claim.get('risk_tier')}; flags: {flags}; note: {note})"
            )
        return (
            "- [excluded-unsafe-finance-claim] "
            f"(source: {claim.get('source_name')}; type: {claim.get('claim_type')}; "
            f"risk: {claim.get('risk_tier')}; flags: {flags}; note: {note})"
        )
    # Escape untrusted claim text FIRST (all modes), then sanitize the escaped
    # text so sanitize's [blocked-...] tokens stay unescaped and render intact.
    text = sanitize_for_report(escape_markdown_inline(claim.get("claim_text", "")), mode)
    flags = ", ".join(claim.get("risk_flags") or []) or "none"
    note = claim.get("classification_notes") or ""
    return f"- {text} (source: {claim.get('source_name')}; type: {claim.get('claim_type')}; risk: {claim.get('risk_tier')}; flags: {flags}; note: {note})"


def _source_classification_lines(sources: list[dict]) -> list[str]:
    by_type: dict[str, int] = {}
    by_state: dict[str, int] = {}
    for source in sources:
        stype = source.get("source_type") or "unknown"
        sstate = source.get("observable_state") or "unknown"
        by_type[stype] = by_type.get(stype, 0) + 1
        by_state[sstate] = by_state.get(sstate, 0) + 1
    type_text = ", ".join(f"{k}={v}" for k, v in sorted(by_type.items())) or "none"
    state_text = ", ".join(f"{k}={v}" for k, v in sorted(by_state.items())) or "none"
    return [f"- Source types: {type_text}", f"- Observable states: {state_text}"]


def _review_line(review: dict, profile: str) -> str:
    if profile == "operator":
        return f"- [{review.get('risk_tier')}] {review.get('claim_id')}: {review.get('verification_question')} (reason: {review.get('reason')})"
    return f"- {review.get('claim_id')}: {review.get('verification_question')} (reason: {review.get('reason')})"


def render_report(run_dir: str | Path, report_profile: str = "minimal", excluded_detail_mode: str | None = None) -> str:
    run_path = Path(run_dir)
    gates = build_report_gates(run_path, write=True)
    if not gates["passed"]:
        failures = "; ".join(gates["blocking_failures"])
        raise ValueError(f"Report validation failed: {failures}")
    manifest, sources, claims, reviews = load_run(run_path)
    mode = manifest.get("mode", "general")
    detail_mode = (excluded_detail_mode or os.getenv("IFTOS_EXCLUDED_DETAIL_MODE", "")).strip().lower()
    if detail_mode not in {"", "detailed"}:
        detail_mode = ""
    profile = report_profile if report_profile in {"minimal", "operator"} else "minimal"
    buckets: dict[str, list[dict]] = {}
    for claim in claims:
        buckets.setdefault(bucket_for_claim(claim), []).append(claim)

    lines: list[str] = ["# Information Trust Report", "", f"- Run ID: {manifest.get('run_id')}", f"- Mode: {mode}"]
    if manifest.get("issue_id"):
        lines.append(f"- Issue ID: {manifest.get('issue_id')}")
    if mode == "finance":
        lines.append("- Safety note: This report separates evidence from interpretation and is not financial advice.")
        lines.append("- Excluded finance content is masked to prevent advice-like leakage.")
    lines.append(f"- Report profile: {profile}")
    # Record the effective excluded-detail mode so the rendered report
    # self-documents which mode produced it, even when it came from the
    # ambient IFTOS_EXCLUDED_DETAIL_MODE env var rather than an explicit arg.
    lines.append(f"- Excluded detail mode: {detail_mode or 'default'}")
    lines.extend(["", "## Sources"])
    for source in sources:
        lines.append(f"- {source.get('source_id')}: {source.get('source_name')} ({source.get('source_type')}, {source.get('observable_state')})")
    lines.extend(["", "## Source Classification", *_source_classification_lines(sources)])
    if profile == "operator":
        lines.extend(["", "## Operator Notes", "- This report is for controlled-use review and triage, not for trading decisions."])
    lines.append("")

    for bucket, title in SECTION_ORDER:
        lines.append(f"## {title}")
        items = buckets.get(bucket, [])
        if not items:
            lines.append("- None")
        else:
            for claim in items:
                lines.append(_claim_line(claim, mode, detail_mode))
            if bucket == "rumors":
                lines.append("- Operator note: Rumor/high social claims require corroboration before downstream use.")
            if bucket == "excluded" and mode == "finance":
                lines.append("- Operator note: Excluded finance claims are policy-blocked and masked in this report.")
        lines.append("")

    lines.append("## Verification checklist")
    if not reviews:
        lines.append("- No review items generated.")
    else:
        for review in reviews:
            lines.append(_review_line(review, profile))
    lines.extend(["", "## Validation warnings"])
    warnings = gates.get("warnings") or []
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def write_report(run_dir: str | Path, report_profile: str = "minimal", excluded_detail_mode: str | None = None) -> Path:
    run_path = Path(run_dir)
    report = render_report(run_path, report_profile=report_profile, excluded_detail_mode=excluded_detail_mode)
    report_path = run_path / "report.md"
    report_path.write_text(report + "\n", encoding="utf-8")
    gates = build_report_gates(run_path, write=True)
    warnings = gates.get("warnings") or []
    warning_text = "# Warnings\n\n" + ("\n".join(f"- {w}" for w in warnings) if warnings else "- None") + "\n"
    (run_path / "warnings.md").write_text(warning_text, encoding="utf-8")
    return report_path
