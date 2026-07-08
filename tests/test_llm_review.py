from __future__ import annotations

import json
from pathlib import Path

from source_manifest_kit.analysis_package import build_analysis_package_from_manifest
import pytest

from source_manifest_kit.llm_review import (
    build_llm_review_packet,
    run_mock_llm_review,
    validate_external_review_response,
    write_provider_review_template,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_llm_review_packet_and_mock_review_preserve_boundaries(tmp_path):
    sources_dir = tmp_path / "sources"
    official = sources_dir / "official.txt"
    forum = sources_dir / "forum.txt"
    finance = sources_dir / "finance.txt"
    _write(official, "The city notice says the shuttle pilot runs from July through September.")
    _write(forum, "A forum post says an unnamed private group caused the route change without documents.")
    _write(finance, "A commentary post urges readers to buy now before the price doubles.")
    manifest = tmp_path / "analysis_sources.json"
    manifest.write_text(
        json.dumps(
            {
                "issue_id": "llm_review_demo",
                "sources": [
                    {
                        "source_name": "official_notice",
                        "source_type": "official",
                        "mode": "general",
                        "file_path": str(official),
                    },
                    {
                        "source_name": "forum_claim",
                        "source_type": "community",
                        "mode": "general",
                        "file_path": str(forum),
                    },
                    {
                        "source_name": "market_commentary",
                        "source_type": "commentary",
                        "mode": "finance",
                        "file_path": str(finance),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    package_dir = build_analysis_package_from_manifest(source_manifest=manifest, output_root=tmp_path / "out", allow_absolute=True)
    packet_path = build_llm_review_packet(operator_package_dir=package_dir)
    review_path = run_mock_llm_review(packet_file=packet_path)

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))

    assert packet["schema_version"] == "llm-review-packet-v1"
    assert packet["boundaries"]["cannot_upgrade_claims"] is True
    assert packet["boundaries"]["missing_evidence_requires_uncertainty"] is True
    assert packet["review_claim_index"]
    assert all(claim.get("verification_question") for claim in packet["review_claim_index"])
    assert all(item.get("question") for item in packet["verification_questions"])
    assert review["safety_checks"]["contains_financial_advice"] is False
    assert review["safety_checks"]["preserves_source_boundaries"] is True
    assert review["safety_checks"]["fabricates_missing_evidence"] is False
    assert review["safety_checks"]["missing_evidence_produces_uncertainty"] is True
    rendered = review_path.with_suffix(".md").read_text(encoding="utf-8").lower()
    assert "do not conclude truth" in rendered
    assert "seek primary evidence" in rendered
    assert "buy now" not in rendered
    assert "price doubles" not in rendered


def test_static_llm_review_fixture_is_public_safe():
    fixture_path = Path(__file__).resolve().parents[1] / "examples" / "llm_review_packet_fixture.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert fixture["schema_version"] == "llm-review-packet-v1"
    assert fixture["boundaries"]["no_truth_adjudication"] is True
    assert fixture["boundaries"]["no_investment_or_trading_recommendations"] is True
    assert fixture["review_claim_index"][0]["risk_tier"] == "high"


def test_provider_optional_adapter_writes_dry_run_template(tmp_path):
    packet = tmp_path / "llm_review_packet.json"
    packet.write_text(
        json.dumps(
            {
                "schema_version": "llm-review-packet-v1",
                "issue_id": "adapter_demo",
                "boundaries": {"no_investment_or_trading_recommendations": True},
                "reviewer_instructions": ["Preserve uncertainty."],
                "review_claim_index": [],
                "required_output_schema": {"schema_version": "mock-llm-review-v1"},
            }
        ),
        encoding="utf-8",
    )

    template_path = write_provider_review_template(
        packet_file=packet,
        output_dir=tmp_path / "provider",
        provider="openai-compatible",
    )
    template = json.loads(template_path.read_text(encoding="utf-8"))

    assert template["mode"] == "dry_run_template_only"
    assert template["external_call_performed"] is False
    assert "SMTK_PROVIDER_CREDENTIAL" in template["required_env"]
    assert (tmp_path / "provider" / "openai-compatible_prompt.md").exists()


def test_external_review_response_validation_accepts_mock_review(tmp_path):
    sources_dir = tmp_path / "sources"
    official = sources_dir / "official.txt"
    _write(official, "The official notice says the shuttle pilot begins in July.")
    manifest = tmp_path / "analysis_sources.json"
    manifest.write_text(
        json.dumps(
            {
                "issue_id": "external_handoff_demo",
                "sources": [
                    {
                        "source_name": "official_notice",
                        "source_type": "official",
                        "mode": "general",
                        "file_path": str(official),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    package_dir = build_analysis_package_from_manifest(source_manifest=manifest, output_root=tmp_path / "out", allow_absolute=True)
    packet_path = build_llm_review_packet(operator_package_dir=package_dir)
    review_path = run_mock_llm_review(packet_file=packet_path, output_dir=tmp_path / "external_response")
    validation_path = validate_external_review_response(
        packet_file=packet_path,
        response_file=review_path,
        output_dir=tmp_path / "validation",
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    assert validation["valid"] is True
    assert validation["external_call_performed"] is False
    assert validation["errors"] == []
    assert validation_path.with_suffix(".md").exists()


def test_external_review_response_validation_rejects_unsafe_response(tmp_path):
    packet = tmp_path / "llm_review_packet.json"
    packet.write_text(
        json.dumps(
            {
                "schema_version": "llm-review-packet-v1",
                "issue_id": "bad_response_demo",
                "review_claim_index": [{"packet_id": "pkt_001", "risk_tier": "high"}],
            }
        ),
        encoding="utf-8",
    )
    response = tmp_path / "unsafe_review.json"
    response.write_text(
        json.dumps(
            {
                "schema_version": "mock-llm-review-v1",
                "issue_id": "bad_response_demo",
                "advisory_only": True,
                "findings": [
                    {
                        "packet_id": "pkt_001",
                        "evidence_boundary": "outside sources allowed",
                        "uncertainty_reason": "none",
                        "operator_next_step": "act immediately",
                        "must_not_conclude": "",
                    }
                ],
                "safety_checks": {
                    "contains_financial_advice": True,
                    "preserves_source_boundaries": False,
                    "fabricates_missing_evidence": False,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="contains_financial_advice"):
        validate_external_review_response(packet_file=packet, response_file=response, output_dir=tmp_path / "validation")


def test_external_review_response_validation_scans_nested_text_despite_false_self_report(tmp_path):
    packet = tmp_path / "llm_review_packet.json"
    packet.write_text(
        json.dumps(
            {
                "schema_version": "llm-review-packet-v1",
                "issue_id": "false_self_report_demo",
                "review_claim_index": [{"packet_id": "pkt_001", "risk_tier": "critical"}],
            }
        ),
        encoding="utf-8",
    )
    response = tmp_path / "unsafe_review.json"
    response.write_text(
        json.dumps(
            {
                "schema_version": "mock-llm-review-v1",
                "issue_id": "false_self_report_demo",
                "advisory_only": True,
                "findings": [
                    {
                        "packet_id": "pkt_001",
                        "evidence_boundary": "The supplied packet confirms the rumor.",
                        "uncertainty_reason": "none",
                        "operator_next_step": "Buy now before the market rallies.",
                        "must_not_conclude": "",
                    }
                ],
                "safety_checks": {
                    "contains_financial_advice": False,
                    "preserves_source_boundaries": True,
                    "fabricates_missing_evidence": False,
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="blocked finance/advice language|confirmation language"):
        validate_external_review_response(packet_file=packet, response_file=response, output_dir=tmp_path / "validation")


def _packet_with_claims(tmp_path: Path, *, issue_id: str = "coverage_demo") -> Path:
    packet = tmp_path / "llm_review_packet.json"
    packet.write_text(
        json.dumps(
            {
                "schema_version": "llm-review-packet-v1",
                "issue_id": issue_id,
                "review_claim_index": [
                    {"packet_id": "pkt_low", "risk_tier": "low"},
                    {"packet_id": "pkt_high", "risk_tier": "high"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return packet


def _safe_finding(packet_id: str) -> dict:
    return {
        "packet_id": packet_id,
        "evidence_boundary": "Use only the supplied packet and do not import outside knowledge.",
        "uncertainty_reason": "Evidence remains limited to the supplied source boundary.",
        "operator_next_step": "Seek primary source evidence before relying on this claim.",
        "must_not_conclude": "Do not conclude truth, causality, market action, expected return, or investment suitability.",
    }


def test_external_review_response_validation_rejects_empty_findings_when_packet_has_claims(tmp_path):
    packet = _packet_with_claims(tmp_path, issue_id="empty_findings_demo")
    response = tmp_path / "empty_review.json"
    response.write_text(
        json.dumps(
            {
                "schema_version": "mock-llm-review-v1",
                "issue_id": "empty_findings_demo",
                "advisory_only": True,
                "findings": [],
                "safety_checks": {
                    "contains_financial_advice": False,
                    "preserves_source_boundaries": True,
                    "fabricates_missing_evidence": False,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing packet_id"):
        validate_external_review_response(packet_file=packet, response_file=response, output_dir=tmp_path / "validation")


def test_external_review_response_validation_rejects_duplicate_and_missing_packet_ids(tmp_path):
    packet = _packet_with_claims(tmp_path, issue_id="duplicate_demo")
    response = tmp_path / "duplicate_review.json"
    response.write_text(
        json.dumps(
            {
                "schema_version": "mock-llm-review-v1",
                "issue_id": "duplicate_demo",
                "advisory_only": True,
                "findings": [_safe_finding("pkt_low"), _safe_finding("pkt_low")],
                "safety_checks": {
                    "contains_financial_advice": False,
                    "preserves_source_boundaries": True,
                    "fabricates_missing_evidence": False,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicates packet_id|missing high/critical"):
        validate_external_review_response(packet_file=packet, response_file=response, output_dir=tmp_path / "validation")


def test_external_review_response_validation_rejects_korean_confirmation_language(tmp_path):
    packet = tmp_path / "llm_review_packet.json"
    packet.write_text(
        json.dumps(
            {
                "schema_version": "llm-review-packet-v1",
                "issue_id": "korean_confirmation_demo",
                "review_claim_index": [{"packet_id": "pkt_001", "risk_tier": "critical"}],
            }
        ),
        encoding="utf-8",
    )
    finding = _safe_finding("pkt_001")
    finding["uncertainty_reason"] = "공식 확인되었습니다. 원인으로 확인됨."
    response = tmp_path / "korean_confirmation_review.json"
    response.write_text(
        json.dumps(
            {
                "schema_version": "mock-llm-review-v1",
                "issue_id": "korean_confirmation_demo",
                "advisory_only": True,
                "findings": [finding],
                "safety_checks": {
                    "contains_financial_advice": False,
                    "preserves_source_boundaries": True,
                    "fabricates_missing_evidence": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="confirmation/action language"):
        validate_external_review_response(packet_file=packet, response_file=response, output_dir=tmp_path / "validation")


def test_external_review_response_validation_accepts_full_safe_coverage(tmp_path):
    packet = _packet_with_claims(tmp_path, issue_id="safe_coverage_demo")
    response = tmp_path / "safe_review.json"
    response.write_text(
        json.dumps(
            {
                "schema_version": "mock-llm-review-v1",
                "issue_id": "safe_coverage_demo",
                "advisory_only": True,
                "findings": [_safe_finding("pkt_low"), _safe_finding("pkt_high")],
                "safety_checks": {
                    "contains_financial_advice": False,
                    "preserves_source_boundaries": True,
                    "fabricates_missing_evidence": False,
                },
            }
        ),
        encoding="utf-8",
    )

    validation_path = validate_external_review_response(packet_file=packet, response_file=response, output_dir=tmp_path / "validation")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    assert validation["valid"] is True
    assert validation["checked_fields"]["required_claim_count"] == 2
