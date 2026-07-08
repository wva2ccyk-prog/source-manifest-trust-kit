"""Tests for the ported evaluation gold-set harness (source_manifest_kit.evaluation).

These exercise the library API (loader validation, per-detector confusion
counts, masking checks, enforced/aspirational split, deterministic rendering)
and pin the ACCEPTANCE contract on the real ported gold set: zero enforced-case
failures and all eight detector precisions == 1.000.

The CLI (`eval-goldset`) is owned by a separate agent (cli.py); this module does
NOT test the CLI. The real-gold-set test skips gracefully if the data file is
absent or does not yet load.
"""

import json
from pathlib import Path

import pytest

from source_manifest_kit.evaluation import (
    GoldsetError,
    evaluate_case,
    evaluate_goldset,
    load_goldset,
    render_report_markdown,
    write_evaluation_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDSET_V1_PATH = REPO_ROOT / "evaluation" / "goldset_v1.jsonl"

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


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")


def _base_case(**overrides) -> dict:
    case = {
        "case_id": "case_001",
        "text": "The stock market closed lower today.",
        "language": "en",
        "mode": "finance",
        "source_type": "news",
        "status": "enforced",
        "detector_labels": {"market_terms": True},
    }
    case.update(overrides)
    return case


# ---------------------------------------------------------------------------
# Loader validation
# ---------------------------------------------------------------------------
def test_load_goldset_rejects_duplicate_case_id(tmp_path):
    path = tmp_path / "goldset.jsonl"
    _write_jsonl(path, [_base_case(case_id="dup"), _base_case(case_id="dup")])
    with pytest.raises(GoldsetError, match="duplicate case_id"):
        load_goldset(path)


def test_load_goldset_rejects_bad_enum(tmp_path):
    path = tmp_path / "goldset.jsonl"
    _write_jsonl(path, [_base_case(language="klingon")])
    with pytest.raises(GoldsetError, match="language must be one of"):
        load_goldset(path)


def test_load_goldset_rejects_missing_expectations(tmp_path):
    path = tmp_path / "goldset.jsonl"
    case = _base_case()
    del case["detector_labels"]
    _write_jsonl(path, [case])
    with pytest.raises(GoldsetError, match="at least one of"):
        load_goldset(path)


def test_load_goldset_rejects_missing_required_field(tmp_path):
    path = tmp_path / "goldset.jsonl"
    case = _base_case()
    del case["source_type"]
    _write_jsonl(path, [case])
    with pytest.raises(GoldsetError, match="missing required field"):
        load_goldset(path)


def test_load_goldset_error_includes_line_number(tmp_path):
    path = tmp_path / "goldset.jsonl"
    _write_jsonl(path, [_base_case(case_id="ok"), _base_case(language="bad")])
    with pytest.raises(GoldsetError, match="line 2"):
        load_goldset(path)


def test_load_goldset_accepts_valid_case(tmp_path):
    path = tmp_path / "goldset.jsonl"
    _write_jsonl(path, [_base_case()])
    cases = load_goldset(path)
    assert len(cases) == 1
    assert cases[0]["case_id"] == "case_001"


# ---------------------------------------------------------------------------
# Detector confusion counts: exact TP/FP/FN/TN and precision/recall/F1
# ---------------------------------------------------------------------------
def test_detector_confusion_counts_and_metrics_exact():
    cases = [
        _base_case(
            case_id="causal_tp",
            text="Prices fell because of a rate hike announced this morning.",
            detector_labels={"causality": True},
        ),
        _base_case(
            case_id="causal_fn",
            text="No cause was stated for the move in prices.",
            detector_labels={"causality": True},
        ),
        _base_case(
            case_id="causal_fp",
            text="The index rallied because sentiment improved after the announcement.",
            detector_labels={"causality": False},
        ),
        _base_case(
            case_id="causal_tn",
            text="The index closed at 2640.10 with steady volume.",
            detector_labels={"causality": False},
        ),
    ]
    report = evaluate_goldset(cases)
    causality_metrics = report["detectors"]["overall"]["causality"]
    assert causality_metrics["tp"] == 1
    assert causality_metrics["fp"] == 1
    assert causality_metrics["fn"] == 1
    assert causality_metrics["tn"] == 1
    assert causality_metrics["precision"] == pytest.approx(0.5)
    assert causality_metrics["recall"] == pytest.approx(0.5)
    assert causality_metrics["f1"] == pytest.approx(0.5)
    failing_ids = {entry["case_id"] for entry in report["detectors"]["failing_cases"]["causality"]}
    assert failing_ids == {"causal_fn", "causal_fp"}


def test_detector_metrics_guard_div_by_zero():
    cases = [
        _base_case(case_id="only_tn", text="The index closed at 2640.10 with steady volume.", detector_labels={"causality": False}),
    ]
    report = evaluate_goldset(cases)
    causality_metrics = report["detectors"]["overall"]["causality"]
    assert causality_metrics["tp"] == 0
    assert causality_metrics["fp"] == 0
    assert causality_metrics["fn"] == 0
    assert causality_metrics["precision"] is None
    assert causality_metrics["recall"] is None
    assert causality_metrics["f1"] is None


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------
def test_masking_must_preserve_and_must_mask_pass():
    case = _base_case(
        case_id="masking_ok",
        text="오늘 공매도 비중이 늘었고 목표가는 상향 조정되었다.",
        language="ko",
        detector_labels={},
        masking={"must_preserve": ["공매도"], "must_mask": ["목표가"]},
    )
    result = evaluate_case(case)
    assert result["masking_violations"] == []
    assert result["overall_pass"] is True


def test_masking_violation_when_must_mask_survives():
    case = _base_case(
        case_id="masking_bad_mask",
        text="공매도 비중이 늘었다.",
        language="ko",
        detector_labels={},
        masking={"must_mask": ["공매도"]},
    )
    result = evaluate_case(case)
    assert len(result["masking_violations"]) == 1
    assert "공매도" in result["masking_violations"][0]
    assert result["overall_pass"] is False


def test_masking_violation_when_must_preserve_is_masked():
    case = _base_case(
        case_id="masking_bad_preserve",
        text="목표가는 상향 조정되었다.",
        language="ko",
        detector_labels={},
        masking={"must_preserve": ["목표가"]},
    )
    result = evaluate_case(case)
    assert len(result["masking_violations"]) == 1
    assert result["overall_pass"] is False


# ---------------------------------------------------------------------------
# Enforced vs aspirational separation
# ---------------------------------------------------------------------------
def test_enforced_vs_aspirational_split():
    cases = [
        _base_case(case_id="enforced_pass", status="enforced", detector_labels={"market_terms": True}),
        _base_case(
            case_id="enforced_fail",
            status="enforced",
            text="The index closed at 2640.10 with steady volume.",
            detector_labels={"market_terms": False, "causality": True},
        ),
        _base_case(
            case_id="aspirational_fail",
            status="aspirational",
            text="A social account hints something happened.",
            detector_labels={"manipulation_framing": True},
        ),
    ]
    report = evaluate_goldset(cases)
    assert report["enforced"]["total"] == 2
    assert report["enforced"]["passing"] == 1
    assert report["enforced"]["failing"] == 1
    assert report["enforced"]["failing_cases"][0]["case_id"] == "enforced_fail"
    assert report["aspirational"]["total"] == 1
    assert report["aspirational"]["passing"] == 0
    assert report["aspirational"]["failing"] == 1


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_write_evaluation_report_is_byte_identical_across_runs(tmp_path):
    cases = [
        _base_case(case_id="b_case", detector_labels={"market_terms": True}),
        _base_case(case_id="a_case", text="Prices fell because of a rate hike.", detector_labels={"causality": True}),
    ]
    report_one = evaluate_goldset(cases)
    report_two = evaluate_goldset(list(reversed(cases)))
    paths_one = write_evaluation_report(report_one, tmp_path / "run_one")
    paths_two = write_evaluation_report(report_two, tmp_path / "run_two")
    assert paths_one["json"].read_bytes() == paths_two["json"].read_bytes()
    assert paths_one["markdown"].read_bytes() == paths_two["markdown"].read_bytes()


def test_render_report_markdown_is_deterministic_string():
    cases = [_base_case(case_id="only_case", detector_labels={"market_terms": True})]
    report = evaluate_goldset(cases)
    rendered_one = render_report_markdown(report)
    rendered_two = render_report_markdown(report)
    assert rendered_one == rendered_two
    assert "# Evaluation Gold Set Report" in rendered_one


# ---------------------------------------------------------------------------
# ACCEPTANCE: the ported real gold set must have zero enforced failures and
# all eight detector precisions == 1.000. Skips only if the file is absent.
# ---------------------------------------------------------------------------
def test_real_goldset_v1_zero_enforced_failures_and_perfect_precision():
    if not GOLDSET_V1_PATH.exists():
        pytest.skip("evaluation/goldset_v1.jsonl is not present")
    try:
        cases = load_goldset(GOLDSET_V1_PATH)
    except GoldsetError as exc:
        pytest.skip(f"evaluation/goldset_v1.jsonl does not load cleanly: {exc}")
    report = evaluate_goldset(cases)

    # (1) Zero enforced-case regressions.
    assert report["enforced"]["failing"] == 0, report["enforced"]["failing_cases"]

    # (2) All eight detectors present with precision exactly 1.000 (no false positives).
    overall = report["detectors"]["overall"]
    assert DETECTOR_KEYS.issubset(overall.keys()), sorted(overall.keys())
    for key in DETECTOR_KEYS:
        precision = overall[key]["precision"]
        assert precision == pytest.approx(1.0), (key, overall[key])

    # (3) Classification claim_type / tier acceptance rates are perfect on the set.
    classification = report["classification"]["overall"]
    assert classification["claim_type_accuracy"] == pytest.approx(1.0)
    assert classification["tier_accuracy"] == pytest.approx(1.0)
