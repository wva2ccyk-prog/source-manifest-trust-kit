import json
import subprocess
import sys
from pathlib import Path

import pytest

from source_manifest_kit.acquisition import load_acquisition_manifest
from source_manifest_kit.search_candidates import (
    SearchCandidateError,
    load_search_candidate_artifact,
    search_candidate_selection_to_acquisition_manifest,
    write_search_candidate_index,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _candidate_artifact(**overrides) -> dict:
    artifact = {
        "artifact_version": "v0.8C",
        "issue_id": "search_issue_demo",
        "query": "regional bank review",
        "provider": "frozen_project_thread_candidates",
        "generated_at": "2026-05-22T01:02:03+00:00",
        "warnings": ["candidate snippets are preview metadata only"],
        "candidates": [
            {
                "candidate_id": "news-001",
                "url": "https://example.invalid/news",
                "title": "Regional bank status report",
                "snippet": "Officials said the review is scheduled for June.",
                "publisher": "Example News",
            },
            {
                "candidate_id": "finance-002",
                "url": "https://example.invalid/finance",
                "title": "Buy now with a target price",
                "snippet": "It gives a 70 percent chance of a profitable trade this month.",
                "warnings": ["finance wording preview needs operator caution"],
            },
        ],
    }
    artifact.update(overrides)
    return artifact


def _selection(**overrides) -> dict:
    selection = {
        "issue_id": "search_issue_demo",
        "confirm_reviewed": True,
        "analysis_request": "Review selected candidate URLs without treating search results as truth.",
        "selected_candidates": [
            {
                "candidate_id": "news-001",
                "source_name": "selected_news",
                "source_type": "news",
                "mode": "general",
                "citation_note": "Operator selected this candidate after reviewing the index.",
            },
            {
                "candidate_id": "finance-002",
                "source_name": "selected_finance",
                "source_type": "analyst",
                "mode": "finance",
            },
        ],
    }
    selection.update(overrides)
    return selection


def test_search_candidate_artifact_requires_direct_urls_unique_candidates_and_version(tmp_path):
    bad_version = _write_json(tmp_path / "bad_version.json", _candidate_artifact(artifact_version="v0.8B"))
    with pytest.raises(SearchCandidateError, match="artifact_version"):
        load_search_candidate_artifact(bad_version)

    bad_url = _candidate_artifact()
    bad_url["candidates"][0]["url"] = "file:///tmp/news.txt"
    with pytest.raises(SearchCandidateError, match="direct http\\(s\\) URL"):
        load_search_candidate_artifact(_write_json(tmp_path / "bad_url.json", bad_url))

    duplicate = _candidate_artifact()
    duplicate["candidates"][1]["candidate_id"] = "NEWS-001"
    with pytest.raises(SearchCandidateError, match="duplicate candidate_id"):
        load_search_candidate_artifact(_write_json(tmp_path / "duplicate.json", duplicate))


def test_search_candidate_index_marks_candidates_only_and_masks_finance_preview(tmp_path):
    artifact_path = _write_json(tmp_path / "candidates.json", _candidate_artifact())
    artifact = load_search_candidate_artifact(artifact_path)
    index_path = write_search_candidate_index(candidate_artifact=artifact, output_path=tmp_path / "candidate_index.md")
    text = index_path.read_text(encoding="utf-8").lower()
    assert "candidates only - not verified" in text
    assert "operator must review and select candidates" in text
    assert "buy now" not in text
    assert "target price" not in text
    assert "70 percent chance" not in text


def test_search_candidate_selection_requires_explicit_review_and_known_ids(tmp_path):
    artifact_path = _write_json(tmp_path / "candidates.json", _candidate_artifact())
    unreviewed = _selection(confirm_reviewed=False)
    with pytest.raises(SearchCandidateError, match="confirm_reviewed"):
        search_candidate_selection_to_acquisition_manifest(
            candidate_artifact_file=artifact_path,
            selection_file=_write_json(tmp_path / "unreviewed.json", unreviewed),
            output_path=tmp_path / "acquisition.json",
        )

    unknown = _selection()
    unknown["selected_candidates"][0]["candidate_id"] = "missing-candidate"
    with pytest.raises(SearchCandidateError, match="not found"):
        search_candidate_selection_to_acquisition_manifest(
            candidate_artifact_file=artifact_path,
            selection_file=_write_json(tmp_path / "unknown.json", unknown),
            output_path=tmp_path / "acquisition.json",
        )


def test_search_candidate_selection_roundtrips_to_direct_url_acquisition_manifest(tmp_path):
    artifact_path = _write_json(tmp_path / "candidates.json", _candidate_artifact())
    selection_path = _write_json(tmp_path / "selection.json", _selection())
    output_path = search_candidate_selection_to_acquisition_manifest(
        candidate_artifact_file=artifact_path,
        selection_file=selection_path,
        output_path=tmp_path / "acquisition_manifest.json",
    )
    selected_manifest = json.loads(output_path.read_text(encoding="utf-8"))
    assert selected_manifest["search_candidate_handoff"]["operator_selection_confirmed"] is True
    assert selected_manifest["search_candidate_handoff"]["selected_candidate_ids"] == ["news-001", "finance-002"]
    assert "Candidate presence does not verify source truth" in selected_manifest["sources"][0]["citation_note"]
    assert "buy now" not in output_path.read_text(encoding="utf-8").lower()
    normalized_acquisition = load_acquisition_manifest(output_path)
    assert [source["url"] for source in normalized_acquisition["sources"]] == [
        "https://example.invalid/news",
        "https://example.invalid/finance",
    ]


def test_cli_search_candidate_validate_index_and_select_smoke(tmp_path):
    artifact_path = _write_json(tmp_path / "candidates.json", _candidate_artifact())
    selection_path = _write_json(tmp_path / "selection.json", _selection())
    cwd = Path(__file__).resolve().parents[1]
    validate_result = subprocess.run(
        [sys.executable, "-m", "source_manifest_kit", "search-candidates-validate", "--artifact", str(artifact_path)],
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    assert validate_result.returncode == 0, validate_result.stderr
    index_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "search-candidates-index",
            "--artifact",
            str(artifact_path),
            "--output",
            str(tmp_path / "candidate_index.md"),
        ],
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    assert index_result.returncode == 0, index_result.stderr
    select_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "search-candidates-select",
            "--artifact",
            str(artifact_path),
            "--selection",
            str(selection_path),
            "--output",
            str(tmp_path / "selected_acquisition_manifest.json"),
        ],
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    assert select_result.returncode == 0, select_result.stderr
