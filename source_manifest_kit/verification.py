from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .bundle import _collect_bundle_records, _safe_claim_text_for_output
from .core.risk_policy import escape_markdown_inline, sanitize_for_report
from .ledger.jsonl import write_json


def _packet_id(issue_id: str, claim: dict, category: str) -> str:
    # FIX 5: seed with STABLE content only — issue_id + category + the claim's
    # normalized hash (falling back to normalized claim text). The former seed
    # mixed in bundle_run_id/run_id, which carries a fresh timestamp per run, so
    # every id churned between identical reruns. Within-packet uniqueness for
    # claims that share a hash is handled by _dedupe_packet_ids after building.
    normalized_hash = str(claim.get("normalized_claim_hash") or "")
    if not normalized_hash:
        normalized_hash = re.sub(r"\s+", " ", str(claim.get("claim_text") or "").lower()).strip()
    seed = "|".join([issue_id, category, normalized_hash])
    return "vreq_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _dedupe_packet_ids(packets: list[dict]) -> None:
    """Make packet_ids unique within a packet without reintroducing run state.

    Two distinct claims can share a normalized hash + category (identical text),
    which now yields the same base id. Append a deterministic positional suffix so
    they stay distinct; ordering is stable across identical reruns.
    """
    seen: dict[str, int] = {}
    for entry in packets:
        base = entry["packet_id"]
        count = seen.get(base, 0) + 1
        seen[base] = count
        if count > 1:
            entry["packet_id"] = f"{base}_{count}"


def _category_for_claim(claim: dict) -> str:
    claim_type = claim.get("claim_type")
    source_type = claim.get("source_type")
    if claim_type == "excluded":
        return "excluded_finance"
    if claim_type in {"rumor", "unobservable"} or source_type in {"community", "social"}:
        return "rumor_manipulation"
    if claim_type in {"unverified_causality", "needs_official_source", "interpretation", "opinion_or_frame"}:
        return "unsupported_weak"
    return "confirmed_low_risk"


def _source_family_hint(claim: dict) -> str:
    source_type = claim.get("source_type")
    claim_type = claim.get("claim_type")
    flags = set(claim.get("risk_flags") or [])
    text = (claim.get("claim_text") or "").lower()
    if claim_type == "excluded":
        return "operator_policy_review"
    if source_type == "official":
        if "exchange" in text or "turnover" in text or "net selling" in text:
            return "exchange_announcement"
        return "regulator_notice"
    if "market_causality_claim" in flags or "true_cause_market_claim" in flags:
        return "official_market_data"
    if claim_type == "unobservable":
        return "observable_primary_source"
    if source_type in {"community", "social"}:
        return "primary_source_or_official_statement"
    if source_type == "company":
        return "company_statement"
    return "official_statement"


def _official_query(claim: dict) -> str:
    source = claim.get("bundle_source_name") or claim.get("source_name") or "source"
    claim_type = claim.get("claim_type")
    if claim_type == "excluded":
        return "This finance claim is blocked by policy and remains excluded. If factual context is needed, capture a separate factual claim from a primary source."
    return f"Check official or primary records for claim {claim.get('claim_id')} from {source}."


def _safe_claim_text(claim: dict) -> str:
    # Single masking gate: excluded -> placeholder, else sanitize by run mode.
    # Escape untrusted claim text FIRST, then sanitize, matching the bundle gate,
    # so injected markdown/HTML renders literally. The excluded branch routes
    # through _safe_claim_text_for_output, which already escapes.
    if claim.get("claim_type") == "excluded":
        return _safe_claim_text_for_output(claim)
    mode = "finance" if claim.get("source_mode") == "finance" else "general"
    return sanitize_for_report(escape_markdown_inline(claim.get("claim_text", "")), mode)


def _claim_ref(claim: dict) -> str:
    source = claim.get("bundle_source_name") or claim.get("source_name") or "source"
    claim_id = claim.get("claim_id") or "claim"
    return f"{source}/{claim_id}"


def _must_verify_item(claim: dict, *, source_has_excluded: bool = False) -> dict:
    reason = claim.get("classification_notes") or "Claim requires verification before downstream use."
    if source_has_excluded and claim.get("claim_type") != "excluded":
        reason = (
            f"{reason} This source also contains excluded finance material; "
            "do not treat adjacent interpretation as advice or verified fact."
        )
    return {
        "claim_id": claim.get("claim_id"),
        "claim_ref": _claim_ref(claim),
        "question": f"Whether the claim from {claim.get('bundle_source_name') or claim.get('source_name')} is supported by observable primary or official evidence.",
        "reason": reason,
        "official_source_query": _official_query(claim),
        "source_family_hint": _source_family_hint(claim),
        "expected_evidence_type": "timestamped_record",
    }


def _nice_to_verify_item(claim: dict, *, source_has_excluded: bool = False) -> dict:
    reason = "Useful for context, but does not by itself upgrade the claim."
    if source_has_excluded:
        reason = (
            "Useful for context, but this source also contains excluded finance material; "
            "independent verification is recommended before downstream use."
        )
    return {
        "claim_id": claim.get("claim_id"),
        "claim_ref": _claim_ref(claim),
        "question": f"Whether an independent reputable source reports the same limited factual statement for {claim.get('bundle_source_name') or claim.get('source_name')}.",
        "reason": reason,
        "source_family_hint": "independent_reporting",
        "expected_evidence_type": "corroborating_report",
    }


def _unsafe_to_conclude_item(claim: dict) -> dict:
    if claim.get("claim_type") == "excluded":
        risk = "finance_advice_or_prediction"
        question = "Do not conclude investment action, target, allocation, trade probability, or expected profit from this excluded claim."
    elif claim.get("claim_type") in {"rumor", "unobservable"} or claim.get("source_type") in {"community", "social"}:
        risk = "rumor_or_unobservable_material"
        question = "Do not conclude that the social/community or unobservable claim is true without observable primary evidence."
    elif claim.get("claim_type") == "unverified_causality":
        risk = "unsupported_causality"
        question = "Do not conclude a definitive cause from this claim."
    else:
        risk = "overstatement"
        question = "Do not state more than the source directly supports."
    return {"claim_id": claim.get("claim_id"), "claim_ref": _claim_ref(claim), "question": question, "risk_if_answered": risk}


def _packet_for_claim(issue_id: str, claim: dict, *, source_has_excluded: bool = False) -> dict:
    category = _category_for_claim(claim)
    must_verify = []
    nice_to_verify = []
    unsafe_to_conclude = []
    if category in {"unsupported_weak", "rumor_manipulation"}:
        must_verify.append(_must_verify_item(claim, source_has_excluded=source_has_excluded))
        unsafe_to_conclude.append(_unsafe_to_conclude_item(claim))
    elif category == "excluded_finance":
        unsafe_to_conclude.append(_unsafe_to_conclude_item(claim))
    elif category == "confirmed_low_risk":
        nice_to_verify.append(_nice_to_verify_item(claim, source_has_excluded=source_has_excluded))
    return {
        "packet_id": _packet_id(issue_id, claim, category),
        "issue_id": issue_id,
        "claim_id": claim.get("claim_id"),
        "source_name": claim.get("bundle_source_name") or claim.get("source_name"),
        "source_type": claim.get("source_type"),
        "claim_type": claim.get("claim_type"),
        "risk_tier": claim.get("risk_tier"),
        "claim_text_safe": _safe_claim_text(claim),
        "claim_text_masked": _safe_claim_text(claim),
        "claim_category": category,
        "must_verify": must_verify,
        "nice_to_verify": nice_to_verify,
        "unsafe_to_conclude": unsafe_to_conclude,
        "evidence_questions": [
            {
                "question": "What observable source or record would be sufficient to support this claim?",
                "applies_to": "must_verify" if must_verify else "nice_to_verify",
                "deterministic_check": "operator_review_required",
            }
        ],
    }


def _sources_with_excluded_claims(claims: list[dict]) -> set[str]:
    return {
        c.get("bundle_source_name") or c.get("source_name")
        for c in claims
        if c.get("claim_type") == "excluded" and (c.get("bundle_source_name") or c.get("source_name"))
    }


def _numeric_divergence_questions(issue_path: Path) -> list[dict]:
    path = issue_path / "bundle_numeric_conflicts.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    questions: list[dict] = []
    for conflict in data.get("conflicts") or []:
        metric = str(conflict.get("metric") or "reported_numeric_value")
        values = ", ".join(conflict.get("values") or [])
        sources = ", ".join(conflict.get("sources") or [])
        questions.append(
            {
                "question_id": f"numeric:{metric}",
                "risk_tier": "medium",
                "question": (
                    f"Which primary or official record explains the {metric} divergence "
                    f"across values ({values}) and sources ({sources})?"
                ),
                "reason": "Multiple sources report different numeric values for the same metric.",
                "source_family_hint": "official_or_primary_numeric_record",
                "expected_evidence_type": "timestamped_record",
                "values": conflict.get("values") or [],
                "sources": conflict.get("sources") or [],
            }
        )
    return questions


def _verification_item_key(item: dict) -> tuple[str, str, str, str]:
    return (
        str(item.get("question") or "").strip().lower(),
        str(item.get("reason") or "").strip().lower(),
        str(item.get("source_family_hint") or "").strip().lower(),
        str(item.get("expected_evidence_type") or "").strip().lower(),
    )


def _group_verification_items(items: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str, str], dict] = {}
    for item in items:
        key = _verification_item_key(item)
        if key not in grouped:
            grouped[key] = {**item, "claim_ids": [], "claim_refs": []}
        claim_id = item.get("claim_id")
        claim_ref = item.get("claim_ref") or claim_id
        if claim_id and claim_id not in grouped[key]["claim_ids"]:
            grouped[key]["claim_ids"].append(claim_id)
        if claim_ref and claim_ref not in grouped[key]["claim_refs"]:
            grouped[key]["claim_refs"].append(claim_ref)
    return list(grouped.values())


def build_verification_packet(*, issue_dir: str | Path, output_dir: str | Path | None = None) -> Path:
    issue_path = Path(issue_dir)
    manifest, _run_index, _sources, claims, _reviews = _collect_bundle_records(issue_path)
    issue_id = str(manifest.get("issue_id") or "issue")
    source_modes = {
        str(source.get("source_name")): source.get("mode")
        for source in manifest.get("sources") or []
        if source.get("source_name")
    }
    claims = [
        {
            **claim,
            "source_mode": source_modes.get(str(claim.get("bundle_source_name") or claim.get("source_name"))),
        }
        for claim in claims
    ]
    excluded_sources = _sources_with_excluded_claims(claims)
    packets = [
        _packet_for_claim(
            issue_id,
            claim,
            source_has_excluded=(claim.get("bundle_source_name") or claim.get("source_name")) in excluded_sources,
        )
        for claim in claims
    ]
    _dedupe_packet_ids(packets)
    raw_must = _items_by_tier({"packets": packets}, "must_verify")
    raw_nice = _items_by_tier({"packets": packets}, "nice_to_verify")
    raw_unsafe = _items_by_tier({"packets": packets}, "unsafe_to_conclude")
    numeric_questions = _numeric_divergence_questions(issue_path)
    packet = {
        "issue_id": issue_id,
        "source_count": manifest.get("source_count"),
        "packet_count": len(packets),
        "numeric_divergence_question_count": len(numeric_questions),
        "question_grouping": {
            "must_verify_raw_count": len(raw_must),
            "must_verify_grouped_count": len(_group_verification_items(raw_must)),
            "nice_to_verify_raw_count": len(raw_nice),
            "nice_to_verify_grouped_count": len(_group_verification_items(raw_nice)),
            "unsafe_to_conclude_raw_count": len(raw_unsafe),
            "unsafe_to_conclude_grouped_count": len(_group_verification_items(raw_unsafe)),
        },
        "numeric_divergence_questions": numeric_questions,
        "policy": {
            "verification_does_not_upgrade_claims": True,
            "no_web_fetching": True,
            "no_external_api_in_product_logic": True,
            "excluded_finance_claims_remain_masked": True,
        },
        "packets": packets,
    }
    out_dir = Path(output_dir) if output_dir else issue_path
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "verification_packet.json"
    md_path = out_dir / "verification_packet.md"
    write_json(json_path, packet)
    md_path.write_text(render_verification_packet(packet), encoding="utf-8")
    return json_path


def render_verification_packet(packet: dict) -> str:
    lines = [
        "# Verification Request Packet",
        "",
        f"- Issue ID: {packet.get('issue_id')}",
        f"- Packet count: {packet.get('packet_count')}",
        "- Note: This packet prepares verification work only; it does not verify, upgrade, or conclude claims.",
        "",
        "## Must Verify",
    ]
    for item in _group_verification_items(_items_by_tier(packet, "must_verify")):
        refs = ", ".join(item.get("claim_refs") or item.get("claim_ids") or [])
        lines.append(
            f"- {item['question']} (claims: {refs}; source_family: {item['source_family_hint']}; evidence: {item['expected_evidence_type']})"
        )
    if lines[-1] == "## Must Verify":
        lines.append("- None")
    lines.extend(["", "## Nice To Verify"])
    for item in _group_verification_items(_items_by_tier(packet, "nice_to_verify")):
        refs = ", ".join(item.get("claim_refs") or item.get("claim_ids") or [])
        lines.append(
            f"- {item['question']} (claims: {refs}; source_family: {item['source_family_hint']}; evidence: {item['expected_evidence_type']})"
        )
    if lines[-1] == "## Nice To Verify":
        lines.append("- None")
    lines.extend(["", "## Unsafe To Conclude"])
    for item in _group_verification_items(_items_by_tier(packet, "unsafe_to_conclude")):
        refs = ", ".join(item.get("claim_refs") or item.get("claim_ids") or [])
        lines.append(f"- {item['question']} (claims: {refs}; risk: {item['risk_if_answered']})")
    if lines[-1] == "## Unsafe To Conclude":
        lines.append("- None")
    lines.extend(["", "## Numeric Divergence Questions"])
    numeric_questions = packet.get("numeric_divergence_questions") or []
    if not numeric_questions:
        lines.append("- None")
    else:
        for item in numeric_questions:
            lines.append(
                f"- [{item.get('risk_tier')}] {item.get('question')} "
                f"(evidence: {item.get('expected_evidence_type')}; reason: {item.get('reason')})"
            )
    lines.extend(["", "## Best-Effort Sanitized Claim Index"])
    for entry in packet.get("packets", []):
        lines.append(
            f"- {entry.get('packet_id')}: {entry.get('claim_text_masked') or entry.get('claim_text_safe')} "
            f"(category: {entry.get('claim_category')}; source: {entry.get('source_name')}; risk: {entry.get('risk_tier')})"
        )
    lines.append("")
    return "\n".join(lines)


def _items_by_tier(packet: dict, tier: str) -> list[dict]:
    items: list[dict] = []
    for entry in packet.get("packets", []):
        items.extend(entry.get(tier) or [])
    return items


def load_verification_packet(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
