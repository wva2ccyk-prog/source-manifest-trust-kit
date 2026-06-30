from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable

from .core.risk_policy import sanitize_for_report
from .ledger.jsonl import read_json, write_json


PACKET_SCHEMA_VERSION = "llm-review-packet-v1"
MOCK_REVIEW_SCHEMA_VERSION = "mock-llm-review-v1"
EXTERNAL_REVIEW_RESPONSE_SCHEMA_VERSION = "external-llm-review-response-v1"
SUPPORTED_REVIEW_PROVIDERS = {"mock", "openai-compatible"}
REQUIRED_REVIEW_FINDING_FIELDS = {
    "packet_id",
    "evidence_boundary",
    "uncertainty_reason",
    "operator_next_step",
    "must_not_conclude",
}


def _hash_payload(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _load_json_if_exists(path_text: str | None) -> dict:
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.exists():
        return {}
    return read_json(path)


def _risk_instruction(risk_tier: str | None) -> str:
    if risk_tier in {"high", "critical"}:
        return "Treat as unresolved unless independent primary evidence is supplied."
    if risk_tier == "medium":
        return "Treat as review-needed and preserve uncertainty."
    return "Treat as low-risk only within the supplied source boundaries."


def _review_bucket(risk_tier: str | None) -> str:
    if risk_tier in {"high", "critical"}:
        return "unsafe_or_high_risk_review_only"
    if risk_tier == "medium":
        return "review_needed"
    return "low_risk_within_source_boundary"


def _display_path(value: str | None, *, base_dir: Path) -> str | None:
    if not value:
        return None
    path = Path(value)
    try:
        resolved = path.resolve()
        relative = resolved.relative_to(base_dir.resolve())
        return relative.as_posix()
    except (OSError, ValueError):
        name = path.name or "path"
        return f"<redacted-external-path>/{name}"


def _packet_review_claims(packet: dict) -> list[dict[str, Any]]:
    claims = packet.get("review_claim_index")
    legacy = packet.get("safe_claim_index") or packet.get("safe_claims")
    if isinstance(claims, list):
        return [claim for claim in claims if isinstance(claim, dict)]
    if isinstance(legacy, list):
        return [claim for claim in legacy if isinstance(claim, dict)]
    return []


def _iter_string_fields(value: Any, *, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _iter_string_fields(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_string_fields(child, path=f"{path}[{index}]")


BLOCKED_REVIEW_CONCLUSION_PATTERNS = (
    r"\b(?:confirm(?:s|ed)?|verif(?:y|ies|ied)|proves?|proven|establish(?:es|ed)?|resolved)\b",
    r"\b(?:true cause|true reason|real reason)\b",
    r"\b(?:will|is going to|guaranteed to)\s+(?:rise|fall|rally|crash|go up|go down|outperform|underperform)\b",
    r"\b(?:buy|sell|short|long)\s+(?:now|this|the|[A-Z]{1,6}\b)",
    r"\b(?:accumulate|trim|add|reduce)\s+(?:shares?|exposure|position)\b",
    r"\b(?:go|move)\s+overweight\b",
    r"\bprice\s+(?:objective|level|target)\b",
    r"(?:매수|매도|손절|익절|목표가|목표\s*주가|비중\s*(?:확대|축소|조절|줄|늘)|수익률\s*\d)",
    r"(?:상승|하락)\s*여력\s*(?:은|는)?\s*\d",
    r"(?:공식\s*)?(?:확인|검증|입증|확정)(?:되었|됐|됨|됐다|했습니다|했다|된\s*것)",
    r"원인(?:이|으로)?\s*(?:확인|확정|규명)(?:되었|됐|됨|됐다|된\s*것)",
    r"전문가\s*분석(?:으로|에\s*따라)?\s*(?:확인|검증|입증|확정)",
)


def _looks_negated_safety_instruction(path: str, text: str) -> bool:
    lowered = text.lower()
    return (
        path.endswith("must_not_conclude")
        and (lowered.startswith("do not") or lowered.startswith("never") or "must not" in lowered)
    )


def _scan_external_review_text(response: dict) -> list[str]:
    errors: list[str] = []
    for path, text in _iter_string_fields(response):
        if not text.strip() or _looks_negated_safety_instruction(path, text):
            continue
        sanitized = sanitize_for_report(text, "finance")
        if sanitized != text:
            errors.append(f"response field {path} contains blocked finance/advice language")
        for pattern in BLOCKED_REVIEW_CONCLUSION_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                errors.append(f"response field {path} contains blocked confirmation/action language")
                break
    return errors


def _question_from_items(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict):
            question = str(item.get("question") or "").strip()
            if question:
                return question
    return None


def _verification_question_from_entry(entry: dict[str, Any]) -> str:
    direct = str(entry.get("verification_question") or "").strip()
    if direct:
        return direct
    for key in ("must_verify", "evidence_questions", "nice_to_verify", "unsafe_to_conclude"):
        question = _question_from_items(entry.get(key))
        if question:
            return question
    return "What source or context must be checked before relying on this claim?"


def _is_blocked_confirmation_or_action_text(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in BLOCKED_REVIEW_CONCLUSION_PATTERNS)


def build_llm_review_packet(*, operator_package_dir: str | Path, output_dir: str | Path | None = None) -> Path:
    package_dir = Path(operator_package_dir)
    package_index = read_json(package_dir / "PACKAGE_INDEX.json")
    helper_packet = _load_json_if_exists(package_index.get("helper_review_packet"))
    verification_packet = _load_json_if_exists(package_index.get("verification_packet"))
    out_dir = Path(output_dir) if output_dir else package_dir / "llm_review"
    out_dir.mkdir(parents=True, exist_ok=True)

    verification_by_packet_id = {
        entry.get("packet_id"): entry
        for entry in verification_packet.get("packets", [])
        if isinstance(entry, dict) and entry.get("packet_id")
    }
    review_claim_index: list[dict[str, Any]] = []
    for entry in _packet_review_claims(helper_packet):
        packet_id = entry.get("packet_id")
        verification_entry = verification_by_packet_id.get(packet_id, {})
        risk_tier = entry.get("risk_tier")
        review_claim_index.append(
            {
                "packet_id": packet_id,
                "source_name": entry.get("source_name"),
                "claim_text_masked": entry.get("claim_text_masked") or entry.get("claim_text_safe"),
                "claim_category": entry.get("claim_category"),
                "risk_tier": risk_tier,
                "review_bucket": _review_bucket(risk_tier),
                "review_instruction": _risk_instruction(risk_tier),
                "verification_question": _verification_question_from_entry(verification_entry),
                "must_not_conclude": "Do not conclude truth, causality, market action, expected return, or investment suitability.",
            }
        )

    display_base_dir = package_dir.parent
    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": "llm_packet_" + _hash_payload(str(package_dir.resolve())),
        "issue_id": helper_packet.get("issue_id") or verification_packet.get("issue_id"),
        "purpose": "Ask an LLM or reviewer to critique source/evidence boundaries without upgrading claims.",
        "boundaries": {
            "advisory_only": True,
            "cannot_upgrade_claims": True,
            "deterministic_core_is_final_authority": True,
            "no_truth_adjudication": True,
            "no_financial_advice": True,
            "no_investment_or_trading_recommendations": True,
            "missing_evidence_requires_uncertainty": True,
        },
        "operator_inputs_path_display": "relative_to_operator_package_parent_or_redacted",
        "operator_inputs": {
            "analysis_source_manifest": _display_path(package_index.get("analysis_source_manifest"), base_dir=display_base_dir),
            "analysis_source_index": _display_path(package_index.get("analysis_source_index"), base_dir=display_base_dir),
            "final_operator_report": _display_path(package_index.get("final_operator_report"), base_dir=display_base_dir),
            "verification_packet": _display_path(package_index.get("verification_packet"), base_dir=display_base_dir),
        },
        "reviewer_instructions": [
            "Use only the supplied packet and referenced local artifacts.",
            "Do not state or imply that any claim is true unless the supplied evidence directly supports that narrow statement.",
            "When evidence is missing, inaccessible, social-only, or rumor-like, preserve uncertainty.",
            "Do not provide investment, trading, allocation, target-price, expected-return, or action recommendations.",
            "Return structured findings with evidence_boundary, uncertainty_reason, and operator_next_step.",
        ],
        "review_claim_index": review_claim_index,
        "verification_questions": [
            {
                "packet_id": entry.get("packet_id"),
                "question": _verification_question_from_entry(entry),
                "priority": entry.get("priority"),
                "source_family": entry.get("source_family"),
            }
            for entry in verification_packet.get("packets", [])
        ],
        "required_output_schema": {
            "schema_version": MOCK_REVIEW_SCHEMA_VERSION,
            "issue_id": "string",
            "advisory_only": True,
            "findings": [
                {
                    "packet_id": "string",
                    "evidence_boundary": "string",
                    "uncertainty_reason": "string",
                    "operator_next_step": "string",
                    "must_not_conclude": "string",
                }
            ],
            "safety_checks": {
                "contains_financial_advice": False,
                "preserves_source_boundaries": True,
                "fabricates_missing_evidence": False,
            },
        },
    }
    packet_path = out_dir / "llm_review_packet.json"
    write_json(packet_path, packet)
    (out_dir / "llm_review_packet.md").write_text(render_llm_review_packet(packet), encoding="utf-8")
    return packet_path


def render_llm_review_packet(packet: dict) -> str:
    lines = [
        "# LLM Review Packet",
        "",
        f"- Schema: {packet.get('schema_version')}",
        f"- Issue ID: {packet.get('issue_id')}",
        "- Advisory only: true",
        "- Deterministic core is final authority: true",
        "- No financial advice or investing/trading recommendations.",
        "",
        "## Reviewer Instructions",
    ]
    for instruction in packet.get("reviewer_instructions", []):
        lines.append(f"- {instruction}")
    lines.extend(["", "## Sanitized Review Claim Index"])
    for claim in _packet_review_claims(packet):
        lines.append(
            f"- {claim.get('packet_id')}: {claim.get('claim_text_masked')} "
            f"(source: {claim.get('source_name')}; risk: {claim.get('risk_tier')}; bucket: {claim.get('review_bucket')})"
        )
        if claim.get("verification_question"):
            lines.append(f"  - Verification question: {claim.get('verification_question')}")
        if claim.get("must_not_conclude"):
            lines.append(f"  - Must not conclude: {claim.get('must_not_conclude')}")
    lines.extend(["", "## Required Output", "", "Return JSON matching `required_output_schema`."])
    return "\n".join(lines) + "\n"


def run_mock_llm_review(*, packet_file: str | Path, output_dir: str | Path | None = None) -> Path:
    packet_path = Path(packet_file)
    packet = read_json(packet_path)
    out_dir = Path(output_dir) if output_dir else packet_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    findings = []
    for claim in _packet_review_claims(packet):
        risk = claim.get("risk_tier") or "unknown"
        findings.append(
            {
                "packet_id": claim.get("packet_id"),
                "evidence_boundary": (
                    f"Review only the supplied source-manifest artifacts for source `{claim.get('source_name')}`; "
                    "do not import outside knowledge."
                ),
                "uncertainty_reason": _risk_instruction(risk),
                "operator_next_step": "Check the verification packet and seek primary evidence before relying on this claim.",
                "must_not_conclude": "Do not conclude truth, causality, market action, expected return, or investment suitability.",
            }
        )
    review = {
        "schema_version": MOCK_REVIEW_SCHEMA_VERSION,
        "issue_id": packet.get("issue_id"),
        "advisory_only": True,
        "deterministic_core_is_final_authority": True,
        "findings": findings,
        "safety_checks": {
            "contains_financial_advice": False,
            "preserves_source_boundaries": True,
            "fabricates_missing_evidence": False,
            "missing_evidence_produces_uncertainty": True,
            "usable_by_operator": True,
        },
        "frontend_decision": "static_preview",
    }
    review_path = out_dir / "mock_llm_review.json"
    write_json(review_path, review)
    (out_dir / "mock_llm_review.md").write_text(render_mock_llm_review(review), encoding="utf-8")
    return review_path


def write_provider_review_template(
    *,
    packet_file: str | Path,
    output_dir: str | Path | None = None,
    provider: str = "openai-compatible",
) -> Path:
    if provider not in SUPPORTED_REVIEW_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_REVIEW_PROVIDERS))
        raise ValueError(f"Unsupported review provider: {provider}. Supported providers: {supported}")
    packet_path = Path(packet_file)
    packet = read_json(packet_path)
    out_dir = Path(output_dir) if output_dir else packet_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    if provider == "mock":
        return run_mock_llm_review(packet_file=packet_path, output_dir=out_dir)

    prompt = render_llm_review_packet(packet)
    template = {
        "provider": provider,
        "mode": "dry_run_template_only",
        "external_call_performed": False,
        "required_env": ["SMTK_PROVIDER_CREDENTIAL"],
        "optional_env": ["SMTK_PROVIDER_BASE_URL", "SMTK_PROVIDER_MODEL"],
        "request_shape": {
            "model": "${SMTK_PROVIDER_MODEL:-gpt-4.1-mini}",
            "messages": [
                {
                    "role": "system",
                    "content": "You review source-manifest packets. Preserve uncertainty and never provide investing or trading recommendations.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        "expected_response_schema": packet.get("required_output_schema"),
        "safety_requirements": packet.get("boundaries"),
    }
    template_path = out_dir / f"{provider}_request_template.json"
    write_json(template_path, template)
    (out_dir / f"{provider}_prompt.md").write_text(prompt, encoding="utf-8")
    return template_path


def validate_external_review_response(
    *,
    packet_file: str | Path,
    response_file: str | Path,
    output_dir: str | Path | None = None,
) -> Path:
    packet_path = Path(packet_file)
    response_path = Path(response_file)
    packet = read_json(packet_path)
    response = read_json(response_path)
    out_dir = Path(output_dir) if output_dir else response_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    warnings: list[str] = []
    packet_claims = _packet_review_claims(packet)
    packet_ids = {claim.get("packet_id") for claim in packet_claims if claim.get("packet_id")}
    packet_risk_by_id = {claim.get("packet_id"): claim.get("risk_tier") for claim in packet_claims if claim.get("packet_id")}

    if response.get("schema_version") != MOCK_REVIEW_SCHEMA_VERSION:
        errors.append(f"schema_version must be {MOCK_REVIEW_SCHEMA_VERSION}")
    if response.get("issue_id") != packet.get("issue_id"):
        errors.append("issue_id must match the review packet")
    if response.get("advisory_only") is not True:
        errors.append("advisory_only must be true")

    findings = response.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        findings = []

    seen_packet_ids: set[str] = set()
    duplicate_packet_ids: set[str] = set()
    for index, finding in enumerate(findings, start=1):
        if not isinstance(finding, dict):
            errors.append(f"findings[{index}] must be an object")
            continue
        missing_fields = sorted(REQUIRED_REVIEW_FINDING_FIELDS - set(finding))
        if missing_fields:
            errors.append(f"findings[{index}] missing fields: {', '.join(missing_fields)}")
        packet_id = finding.get("packet_id")
        if packet_ids and packet_id not in packet_ids:
            errors.append(f"findings[{index}] references unknown packet_id: {packet_id}")
        elif isinstance(packet_id, str) and packet_id:
            if packet_id in seen_packet_ids:
                duplicate_packet_ids.add(packet_id)
                errors.append(f"findings[{index}] duplicates packet_id: {packet_id}")
            seen_packet_ids.add(packet_id)
        else:
            errors.append(f"findings[{index}] packet_id must be a non-empty string")

        risk_tier = packet_risk_by_id.get(packet_id)
        if risk_tier in {"high", "critical"}:
            for field_path, field_text in _iter_string_fields(finding, path=f"$.findings[{index - 1}]"):
                if _looks_negated_safety_instruction(field_path, field_text):
                    continue
                if _is_blocked_confirmation_or_action_text(field_text):
                    errors.append(f"findings[{index}] upgrades a {risk_tier} risk claim with confirmation/action language")
                    break

    if packet_ids:
        missing_packet_ids = sorted(packet_ids - seen_packet_ids)
        if missing_packet_ids:
            errors.append("findings missing packet_id(s): " + ", ".join(missing_packet_ids))
        required_high_critical = {
            packet_id
            for packet_id, risk_tier in packet_risk_by_id.items()
            if risk_tier in {"high", "critical"}
        }
        missing_required = sorted(required_high_critical - seen_packet_ids)
        if missing_required:
            errors.append("findings missing high/critical packet_id(s): " + ", ".join(missing_required))
    elif findings:
        warnings.append("review packet has no review_claim_index; findings could not be matched to packet ids")

    safety = response.get("safety_checks")
    if not isinstance(safety, dict):
        errors.append("safety_checks must be an object")
        safety = {}
    if safety.get("contains_financial_advice") is not False:
        errors.append("safety_checks.contains_financial_advice must be false")
    if safety.get("preserves_source_boundaries") is not True:
        errors.append("safety_checks.preserves_source_boundaries must be true")
    if safety.get("fabricates_missing_evidence") is not False:
        errors.append("safety_checks.fabricates_missing_evidence must be false")

    errors.extend(_scan_external_review_text(response))

    result = {
        "schema_version": "external-review-response-validation-v1",
        "packet_file": str(packet_path),
        "response_file": str(response_path),
        "external_call_performed": False,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "checked_fields": {
            "schema_version": MOCK_REVIEW_SCHEMA_VERSION,
            "issue_id_matches_packet": True,
            "required_finding_fields": sorted(REQUIRED_REVIEW_FINDING_FIELDS),
            "safety_checks": [
                "contains_financial_advice=false",
                "preserves_source_boundaries=true",
                "fabricates_missing_evidence=false",
                "full_response_text_scan",
                "unknown_packet_ids_are_errors",
                "missing_packet_ids_are_errors",
                "duplicate_packet_ids_are_errors",
                "high_critical_claims_require_findings",
                "korean_confirmation_language_is_blocked",
            ],
            "required_claim_count": len(packet_ids),
            "seen_claim_count": len(seen_packet_ids - duplicate_packet_ids),
        },
    }
    result_path = out_dir / "external_review_response_validation.json"
    write_json(result_path, result)
    (out_dir / "external_review_response_validation.md").write_text(render_external_review_validation(result), encoding="utf-8")
    if errors:
        raise ValueError(f"External review response failed validation: {'; '.join(errors)}")
    return result_path


def render_external_review_validation(result: dict) -> str:
    status = "PASS" if result.get("valid") else "FAIL"
    lines = [
        "# External Review Response Validation",
        "",
        f"- Status: {status}",
        "- External call performed: false",
        f"- Packet: {result.get('packet_file')}",
        f"- Response: {result.get('response_file')}",
        "",
        "## Errors",
    ]
    errors = result.get("errors") or []
    lines.extend([f"- {error}" for error in errors] or ["- none"])
    lines.extend(["", "## Warnings"])
    warnings = result.get("warnings") or []
    lines.extend([f"- {warning}" for warning in warnings] or ["- none"])
    return "\n".join(lines) + "\n"


def render_mock_llm_review(review: dict) -> str:
    lines = [
        "# Mock LLM Review",
        "",
        f"- Schema: {review.get('schema_version')}",
        f"- Issue ID: {review.get('issue_id')}",
        "- Advisory only: true",
        "- Deterministic core is final authority: true",
        "- Safety checks: passed",
        "",
        "## Findings",
    ]
    for finding in review.get("findings", []):
        lines.extend(
            [
                f"### {finding.get('packet_id')}",
                "",
                f"- Evidence boundary: {finding.get('evidence_boundary')}",
                f"- Uncertainty reason: {finding.get('uncertainty_reason')}",
                f"- Operator next step: {finding.get('operator_next_step')}",
                f"- Must not conclude: {finding.get('must_not_conclude')}",
                "",
            ]
        )
    return "\n".join(lines)
