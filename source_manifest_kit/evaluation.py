from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core.classification import classify_claim
from .core.risk_policy import (
    detect_risk_flags,
    has_action_language,
    has_causality,
    has_manipulation_framing,
    has_market_terms,
    has_position_sizing,
    has_trade_probability,
    has_future_return_projection,
    sanitize_for_report,
)
from .core.schema import CLAIM_TYPES, RISK_TIERS, SOURCE_TYPES, SourceRecord, utc_now

# ---------------------------------------------------------------------------
# Gold case schema constants
# ---------------------------------------------------------------------------
LANGUAGES = {"ko", "en", "mixed"}
MODES = {"general", "finance"}
STATUSES = {"enforced", "aspirational"}
DETECTOR_KEYS = {
    "causality",
    "market_terms",
    "manipulation_framing",
    "action_language",
    "target_price",
    "position_sizing",
    "trade_probability",
    "private_or_unobservable",
}
REQUIRED_FIELDS = {"case_id", "text", "language", "mode", "source_type", "status"}
OPTIONAL_EXPECTATION_FIELDS = {"detector_labels", "expected_claim_types", "expected_tiers", "masking"}


class GoldsetError(ValueError):
    """Raised when a gold set JSONL file fails schema validation."""


def _fail(line_no: int, message: str) -> None:
    raise GoldsetError(f"line {line_no}: {message}")


def _validate_case(case: Any, line_no: int) -> None:
    if not isinstance(case, dict):
        _fail(line_no, "case must be a JSON object")
    missing = REQUIRED_FIELDS - case.keys()
    if missing:
        _fail(line_no, f"missing required field(s): {', '.join(sorted(missing))}")
    if not isinstance(case["case_id"], str) or not case["case_id"].strip():
        _fail(line_no, "case_id must be a non-empty string")
    if not isinstance(case["text"], str) or not case["text"]:
        _fail(line_no, "text must be a non-empty string")
    if case["language"] not in LANGUAGES:
        _fail(line_no, f"language must be one of: {', '.join(sorted(LANGUAGES))}")
    if case["mode"] not in MODES:
        _fail(line_no, f"mode must be one of: {', '.join(sorted(MODES))}")
    if case["source_type"] not in SOURCE_TYPES:
        _fail(line_no, f"source_type must be one of: {', '.join(sorted(SOURCE_TYPES))}")
    if case["status"] not in STATUSES:
        _fail(line_no, f"status must be one of: {', '.join(sorted(STATUSES))}")

    if not any(key in case and case[key] not in (None, [], {}) for key in OPTIONAL_EXPECTATION_FIELDS):
        _fail(
            line_no,
            "case must include at least one of: detector_labels, expected_claim_types, expected_tiers, masking",
        )

    detector_labels = case.get("detector_labels")
    if detector_labels is not None:
        if not isinstance(detector_labels, dict):
            _fail(line_no, "detector_labels must be an object")
        unknown = set(detector_labels.keys()) - DETECTOR_KEYS
        if unknown:
            _fail(line_no, f"detector_labels has unknown key(s): {', '.join(sorted(unknown))}")
        for key, value in detector_labels.items():
            if not isinstance(value, bool):
                _fail(line_no, f"detector_labels[{key}] must be a boolean")

    expected_claim_types = case.get("expected_claim_types")
    if expected_claim_types is not None:
        if not isinstance(expected_claim_types, list) or not expected_claim_types:
            _fail(line_no, "expected_claim_types must be a non-empty list")
        unknown_types = set(expected_claim_types) - CLAIM_TYPES
        if unknown_types:
            _fail(line_no, f"expected_claim_types has unknown value(s): {', '.join(sorted(unknown_types))}")

    expected_tiers = case.get("expected_tiers")
    if expected_tiers is not None:
        if not isinstance(expected_tiers, list) or not expected_tiers:
            _fail(line_no, "expected_tiers must be a non-empty list")
        unknown_tiers = set(expected_tiers) - RISK_TIERS
        if unknown_tiers:
            _fail(line_no, f"expected_tiers has unknown value(s): {', '.join(sorted(unknown_tiers))}")

    masking = case.get("masking")
    if masking is not None:
        if not isinstance(masking, dict):
            _fail(line_no, "masking must be an object")
        unknown_masking_keys = set(masking.keys()) - {"must_preserve", "must_mask"}
        if unknown_masking_keys:
            _fail(line_no, f"masking has unknown key(s): {', '.join(sorted(unknown_masking_keys))}")
        for key in ("must_preserve", "must_mask"):
            values = masking.get(key)
            if values is None:
                continue
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                _fail(line_no, f"masking[{key}] must be a list of strings")


def load_goldset(path: str | Path) -> list[dict]:
    """Load and validate a gold set JSONL file.

    Raises GoldsetError (with a 1-based line number) on any schema violation,
    including duplicate case_id values across the file.
    """
    goldset_path = Path(path)
    if not goldset_path.exists():
        raise GoldsetError(f"goldset file not found: {goldset_path}")

    cases: list[dict] = []
    seen_ids: dict[str, int] = {}
    raw_text = goldset_path.read_text(encoding="utf-8")
    for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            case = json.loads(stripped)
        except json.JSONDecodeError as exc:
            _fail(line_no, f"invalid JSON: {exc}")
        _validate_case(case, line_no)
        case_id = case["case_id"]
        if case_id in seen_ids:
            _fail(line_no, f"duplicate case_id '{case_id}' (first seen on line {seen_ids[case_id]})")
        seen_ids[case_id] = line_no
        cases.append(case)
    return cases


# ---------------------------------------------------------------------------
# Per-case evaluation
# ---------------------------------------------------------------------------
def _predict_detector(key: str, text: str, source_type: str, mode: str) -> bool:
    if key == "causality":
        return has_causality(text)
    if key == "market_terms":
        return has_market_terms(text)
    if key == "manipulation_framing":
        return has_manipulation_framing(text)
    if key == "action_language":
        return has_action_language(text)
    if key == "target_price":
        return "target_price_language" in detect_risk_flags(text, source_type, "finance")
    if key == "position_sizing":
        return has_position_sizing(text)
    if key == "trade_probability":
        return has_trade_probability(text) or has_future_return_projection(text)
    if key == "private_or_unobservable":
        flags = detect_risk_flags(text, source_type, mode)
        return "private_or_inaccessible_source" in flags or "unobservable_evidence" in flags
    raise ValueError(f"unknown detector key: {key}")


def _build_source(source_type: str) -> SourceRecord:
    return SourceRecord("eval", "eval", source_type, "eval_source", None, None, "2026-01-01", utc_now(), "observable", "eval.txt")


def evaluate_case(case: dict) -> dict:
    """Evaluate a single gold case against the deterministic detectors.

    Returns a dict describing per-detector predicted/labeled outcomes,
    classification outcome, tier outcome, masking violations, and an
    overall pass bool. A case passes only when every labeled aspect matches.
    """
    text = case["text"]
    mode = case["mode"]
    source_type = case["source_type"]
    case_id = case["case_id"]

    detector_results: dict[str, dict[str, Any]] = {}
    detector_labels = case.get("detector_labels") or {}
    for key in sorted(detector_labels.keys()):
        expected = detector_labels[key]
        predicted = _predict_detector(key, text, source_type, mode)
        detector_results[key] = {
            "expected": expected,
            "predicted": predicted,
            "match": expected == predicted,
        }

    classification_result: dict[str, Any] | None = None
    tier_result: dict[str, Any] | None = None
    expected_claim_types = case.get("expected_claim_types")
    expected_tiers = case.get("expected_tiers")
    if expected_claim_types or expected_tiers:
        source = _build_source(source_type)
        claim = classify_claim(text, source, mode)
        if expected_claim_types:
            classification_result = {
                "expected": list(expected_claim_types),
                "predicted": claim.claim_type,
                "match": claim.claim_type in expected_claim_types,
            }
        if expected_tiers:
            tier_result = {
                "expected": list(expected_tiers),
                "predicted": claim.risk_tier,
                "match": claim.risk_tier in expected_tiers,
            }

    masking_violations: list[str] = []
    masking = case.get("masking")
    if masking:
        sanitized = sanitize_for_report(text, mode)
        for substring in masking.get("must_preserve", []):
            if substring not in sanitized:
                masking_violations.append(f"must_preserve substring missing after sanitize: {substring!r}")
        for substring in masking.get("must_mask", []):
            if substring in sanitized:
                masking_violations.append(f"must_mask substring still present after sanitize: {substring!r}")

    overall_pass = (
        all(result["match"] for result in detector_results.values())
        and (classification_result is None or classification_result["match"])
        and (tier_result is None or tier_result["match"])
        and not masking_violations
    )

    return {
        "case_id": case_id,
        "language": case["language"],
        "mode": mode,
        "status": case["status"],
        "detector_results": detector_results,
        "classification_result": classification_result,
        "tier_result": tier_result,
        "masking_violations": masking_violations,
        "overall_pass": overall_pass,
    }


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------
def _confusion_counts() -> dict[str, int]:
    return {"tp": 0, "fp": 0, "fn": 0, "tn": 0}


def _precision_recall_f1(counts: dict[str, int]) -> dict[str, float | None]:
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    if precision is None or recall is None or (precision + recall) == 0:
        f1 = None
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def _update_confusion(counts: dict[str, int], expected: bool, predicted: bool) -> None:
    if expected and predicted:
        counts["tp"] += 1
    elif not expected and predicted:
        counts["fp"] += 1
    elif expected and not predicted:
        counts["fn"] += 1
    else:
        counts["tn"] += 1


def _detector_summary(evaluations: list[dict], case_by_id: dict[str, dict]) -> dict[str, Any]:
    overall: dict[str, dict[str, int]] = {}
    by_language: dict[str, dict[str, dict[str, int]]] = {}
    failing: dict[str, list[dict[str, str]]] = {}

    for evaluation in evaluations:
        case_id = evaluation["case_id"]
        language = evaluation["language"]
        for key, result in sorted(evaluation["detector_results"].items()):
            overall.setdefault(key, _confusion_counts())
            by_language.setdefault(language, {}).setdefault(key, _confusion_counts())
            _update_confusion(overall[key], result["expected"], result["predicted"])
            _update_confusion(by_language[language][key], result["expected"], result["predicted"])
            if not result["match"]:
                failing.setdefault(key, []).append(
                    {
                        "case_id": case_id,
                        "reason": f"expected {result['expected']}, predicted {result['predicted']}",
                    }
                )

    overall_metrics = {key: {**counts, **_precision_recall_f1(counts)} for key, counts in sorted(overall.items())}
    by_language_metrics = {
        language: {key: {**counts, **_precision_recall_f1(counts)} for key, counts in sorted(keys.items())}
        for language, keys in sorted(by_language.items())
    }
    for key in failing:
        failing[key].sort(key=lambda item: item["case_id"])

    return {
        "overall": overall_metrics,
        "by_language": by_language_metrics,
        "failing_cases": {key: failing[key] for key in sorted(failing.keys())},
    }


def _classification_summary(evaluations: list[dict]) -> dict[str, Any]:
    def _empty_bucket() -> dict[str, int]:
        return {"claim_type_total": 0, "claim_type_correct": 0, "tier_total": 0, "tier_correct": 0}

    overall = _empty_bucket()
    by_language: dict[str, dict[str, int]] = {}
    failing_claim_type: list[dict[str, str]] = []
    failing_tier: list[dict[str, str]] = []

    for evaluation in evaluations:
        language = evaluation["language"]
        by_language.setdefault(language, _empty_bucket())
        classification_result = evaluation["classification_result"]
        tier_result = evaluation["tier_result"]
        if classification_result is not None:
            overall["claim_type_total"] += 1
            by_language[language]["claim_type_total"] += 1
            if classification_result["match"]:
                overall["claim_type_correct"] += 1
                by_language[language]["claim_type_correct"] += 1
            else:
                failing_claim_type.append(
                    {
                        "case_id": evaluation["case_id"],
                        "reason": f"expected claim_type in {classification_result['expected']}, predicted {classification_result['predicted']}",
                    }
                )
        if tier_result is not None:
            overall["tier_total"] += 1
            by_language[language]["tier_total"] += 1
            if tier_result["match"]:
                overall["tier_correct"] += 1
                by_language[language]["tier_correct"] += 1
            else:
                failing_tier.append(
                    {
                        "case_id": evaluation["case_id"],
                        "reason": f"expected tier in {tier_result['expected']}, predicted {tier_result['predicted']}",
                    }
                )

    def _rate(bucket: dict[str, int]) -> dict[str, float | None]:
        claim_type_rate = bucket["claim_type_correct"] / bucket["claim_type_total"] if bucket["claim_type_total"] > 0 else None
        tier_rate = bucket["tier_correct"] / bucket["tier_total"] if bucket["tier_total"] > 0 else None
        return {**bucket, "claim_type_accuracy": claim_type_rate, "tier_accuracy": tier_rate}

    overall_out = _rate(overall)
    by_language_out = {language: _rate(bucket) for language, bucket in sorted(by_language.items())}
    failing_claim_type.sort(key=lambda item: item["case_id"])
    failing_tier.sort(key=lambda item: item["case_id"])

    return {
        "overall": overall_out,
        "by_language": by_language_out,
        "failing_claim_type_cases": failing_claim_type,
        "failing_tier_cases": failing_tier,
    }


def _masking_summary(evaluations: list[dict]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    for evaluation in evaluations:
        if evaluation["masking_violations"]:
            violations.append(
                {
                    "case_id": evaluation["case_id"],
                    "violations": list(evaluation["masking_violations"]),
                }
            )
    violations.sort(key=lambda item: item["case_id"])
    return {
        "violation_count": len(violations),
        "cases": violations,
    }


def _status_summary(evaluations: list[dict], status: str) -> dict[str, Any]:
    subset = [evaluation for evaluation in evaluations if evaluation["status"] == status]
    passing = [evaluation for evaluation in subset if evaluation["overall_pass"]]
    failing = [evaluation for evaluation in subset if not evaluation["overall_pass"]]
    failing_ids = []
    for evaluation in sorted(failing, key=lambda item: item["case_id"]):
        reasons = []
        for key, result in sorted(evaluation["detector_results"].items()):
            if not result["match"]:
                reasons.append(f"detector:{key} expected {result['expected']} predicted {result['predicted']}")
        classification_result = evaluation["classification_result"]
        if classification_result is not None and not classification_result["match"]:
            reasons.append(f"claim_type expected in {classification_result['expected']} predicted {classification_result['predicted']}")
        tier_result = evaluation["tier_result"]
        if tier_result is not None and not tier_result["match"]:
            reasons.append(f"tier expected in {tier_result['expected']} predicted {tier_result['predicted']}")
        if evaluation["masking_violations"]:
            reasons.extend(f"masking: {violation}" for violation in evaluation["masking_violations"])
        failing_ids.append({"case_id": evaluation["case_id"], "reason": "; ".join(reasons) if reasons else "unknown mismatch"})
    return {
        "total": len(subset),
        "passing": len(passing),
        "failing": len(failing),
        "failing_cases": failing_ids,
    }


def evaluate_goldset(cases: list[dict]) -> dict:
    """Evaluate a full gold set and return a deterministic aggregate report."""
    sorted_cases = sorted(cases, key=lambda case: case["case_id"])
    case_by_id = {case["case_id"]: case for case in sorted_cases}
    evaluations = [evaluate_case(case) for case in sorted_cases]
    evaluations.sort(key=lambda evaluation: evaluation["case_id"])

    detectors = _detector_summary(evaluations, case_by_id)
    classification = _classification_summary(evaluations)
    masking = _masking_summary(evaluations)
    enforced = _status_summary(evaluations, "enforced")
    aspirational = _status_summary(evaluations, "aspirational")

    return {
        "case_count": len(sorted_cases),
        "detectors": detectors,
        "classification": classification,
        "masking": masking,
        "enforced": enforced,
        "aspirational": aspirational,
    }


# ---------------------------------------------------------------------------
# Rendering / writing
# ---------------------------------------------------------------------------
def _format_metric(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"


def render_report_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# Evaluation Gold Set Report")
    lines.append("")
    lines.append(f"Total cases: {report['case_count']}")
    lines.append("")

    lines.append("## Enforced vs Aspirational")
    lines.append("")
    lines.append(f"- Enforced: {report['enforced']['passing']}/{report['enforced']['total']} passing")
    lines.append(f"- Aspirational: {report['aspirational']['passing']}/{report['aspirational']['total']} passing")
    lines.append("")
    if report["enforced"]["failing_cases"]:
        lines.append("### Enforced failures (regressions)")
        lines.append("")
        for entry in report["enforced"]["failing_cases"]:
            lines.append(f"- `{entry['case_id']}`: {entry['reason']}")
        lines.append("")
    if report["aspirational"]["failing_cases"]:
        lines.append("### Aspirational failures (gap list)")
        lines.append("")
        for entry in report["aspirational"]["failing_cases"]:
            lines.append(f"- `{entry['case_id']}`: {entry['reason']}")
        lines.append("")

    lines.append("## Detector Metrics (overall)")
    lines.append("")
    lines.append("| detector | tp | fp | fn | tn | precision | recall | f1 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for key, metrics in sorted(report["detectors"]["overall"].items()):
        lines.append(
            f"| {key} | {metrics['tp']} | {metrics['fp']} | {metrics['fn']} | {metrics['tn']} | "
            f"{_format_metric(metrics['precision'])} | {_format_metric(metrics['recall'])} | {_format_metric(metrics['f1'])} |"
        )
    lines.append("")

    lines.append("## Detector Metrics (by language)")
    lines.append("")
    for language, detector_metrics in sorted(report["detectors"]["by_language"].items()):
        lines.append(f"### {language}")
        lines.append("")
        lines.append("| detector | tp | fp | fn | tn | precision | recall | f1 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for key, metrics in sorted(detector_metrics.items()):
            lines.append(
                f"| {key} | {metrics['tp']} | {metrics['fp']} | {metrics['fn']} | {metrics['tn']} | "
                f"{_format_metric(metrics['precision'])} | {_format_metric(metrics['recall'])} | {_format_metric(metrics['f1'])} |"
            )
        lines.append("")

    lines.append("## Classification Accuracy")
    lines.append("")
    overall_classification = report["classification"]["overall"]
    lines.append(
        f"- Overall claim_type-in-set rate: {_format_metric(overall_classification['claim_type_accuracy'])} "
        f"({overall_classification['claim_type_correct']}/{overall_classification['claim_type_total']})"
    )
    lines.append(
        f"- Overall tier-in-set rate: {_format_metric(overall_classification['tier_accuracy'])} "
        f"({overall_classification['tier_correct']}/{overall_classification['tier_total']})"
    )
    lines.append("")
    for language, bucket in sorted(report["classification"]["by_language"].items()):
        lines.append(
            f"- {language}: claim_type {_format_metric(bucket['claim_type_accuracy'])} "
            f"({bucket['claim_type_correct']}/{bucket['claim_type_total']}), "
            f"tier {_format_metric(bucket['tier_accuracy'])} ({bucket['tier_correct']}/{bucket['tier_total']})"
        )
    lines.append("")

    lines.append("## Masking Violations")
    lines.append("")
    lines.append(f"Total violation cases: {report['masking']['violation_count']}")
    lines.append("")
    for entry in report["masking"]["cases"]:
        lines.append(f"- `{entry['case_id']}`: {'; '.join(entry['violations'])}")
    lines.append("")

    return "\n".join(lines) + "\n"


def write_evaluation_report(report: dict, output_dir: str | Path) -> dict[str, Path]:
    """Write eval_report.json (sort_keys, deterministic) and eval_report.md."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "eval_report.json"
    md_path = out_dir / "eval_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_report_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
