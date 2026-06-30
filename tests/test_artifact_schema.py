from __future__ import annotations

import json
from pathlib import Path

from source_manifest_kit.artifact_schema import available_schemas, validate_artifact_file, write_artifact_validation


ROOT = Path(__file__).resolve().parents[1]


def test_packaged_schemas_are_available() -> None:
    assert set(available_schemas()) == {
        "acquisition-manifest",
        "external-review-response",
        "llm-review-packet",
    }


def test_validate_artifact_accepts_llm_review_packet_fixture(tmp_path: Path) -> None:
    fixture = ROOT / "examples" / "llm_review_packet_fixture.json"
    result = validate_artifact_file(schema_name="llm-review-packet", artifact_file=fixture)

    assert result["valid"] is True
    assert result["errors"] == []

    output = tmp_path / "schema_validation.json"
    write_artifact_validation(schema_name="llm-review-packet", artifact_file=fixture, output_path=output)
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["valid"] is True


def test_validate_artifact_rejects_wrong_schema() -> None:
    fixture = ROOT / "examples" / "malicious" / "empty_external_review_response.json"
    result = validate_artifact_file(schema_name="llm-review-packet", artifact_file=fixture)

    assert result["valid"] is False
    assert result["errors"]
