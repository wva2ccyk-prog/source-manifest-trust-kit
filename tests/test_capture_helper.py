import json
import subprocess
import sys
from pathlib import Path

import pytest

from source_manifest_kit.analysis_package import build_analysis_package_from_manifest
from source_manifest_kit.capture_helper import (
    CAPTURE_INDEX_FILENAME,
    CAPTURE_LOG_FILENAME,
    CaptureError,
    build_capture_manifest,
    capture_source,
    write_capture_source_index,
)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_capture_source_writes_deterministic_file_log_and_index(tmp_path):
    entry = capture_source(
        workspace=tmp_path,
        issue_id="capture_issue",
        source_name="News Report",
        source_type="news",
        mode="general",
        text="The city announced a meeting schedule.\r\nWork starts Monday.",
        source_url="https://example.invalid/news",
        title="Meeting schedule",
        captured_at="2026-05-21T00:00:00+00:00",
    )
    source_file = Path(entry["file_path"])
    assert source_file == tmp_path.resolve() / "captured_sources" / "capture_issue" / "News_Report.txt"
    assert source_file.read_text(encoding="utf-8") == "The city announced a meeting schedule.\nWork starts Monday."
    log = _json(tmp_path / CAPTURE_LOG_FILENAME)
    assert log[0]["issue_id"] == "capture_issue"
    assert log[0]["source_url_is_metadata_only"] is True
    assert log[0]["runtime_fetching"] is False
    assert (tmp_path / CAPTURE_INDEX_FILENAME).exists()
    index = (tmp_path / CAPTURE_INDEX_FILENAME).read_text(encoding="utf-8")
    assert "metadata only; not fetched" in index


def test_capture_source_rejects_url_like_text_and_input_path(tmp_path):
    with pytest.raises(CaptureError, match="does not fetch URLs"):
        capture_source(
            workspace=tmp_path,
            issue_id="url_text",
            source_name="bad",
            source_type="news",
            mode="general",
            text="https://example.invalid/story",
        )
    with pytest.raises(CaptureError, match="input_text_file looks like a URL"):
        capture_source(
            workspace=tmp_path,
            issue_id="url_path",
            source_name="bad",
            source_type="news",
            mode="general",
            input_text_file="https://example.invalid/story.txt",
        )


def test_capture_source_reads_valid_input_text_file(tmp_path):
    input_file = tmp_path / "operator_clip.txt"
    input_file.write_text("Copied source text from a local operator file.", encoding="utf-8")
    entry = capture_source(
        workspace=tmp_path,
        issue_id="file_capture",
        source_name="file_source",
        source_type="news",
        mode="general",
        input_text_file=input_file,
    )
    assert Path(entry["file_path"]).read_text(encoding="utf-8") == "Copied source text from a local operator file."


def test_capture_source_strips_utf8_bom_from_input_text_file(tmp_path):
    input_file = tmp_path / "bom_clip.txt"
    input_file.write_bytes("Copied source text saved with a BOM.".encode("utf-8-sig"))
    entry = capture_source(
        workspace=tmp_path,
        issue_id="bom_capture",
        source_name="bom_source",
        source_type="news",
        mode="general",
        input_text_file=input_file,
    )
    captured_text = Path(entry["file_path"]).read_text(encoding="utf-8")
    assert captured_text == "Copied source text saved with a BOM."
    assert not captured_text.startswith("﻿")


def test_capture_source_disambiguates_slug_collision(tmp_path):
    first = capture_source(
        workspace=tmp_path,
        issue_id="collision_issue",
        source_name="Source #1",
        source_type="news",
        mode="general",
        text="First source text.",
    )
    second = capture_source(
        workspace=tmp_path,
        issue_id="collision_issue",
        source_name="Source@1",
        source_type="news",
        mode="general",
        text="Second source text.",
    )
    first_path = Path(first["file_path"])
    second_path = Path(second["file_path"])
    assert first_path != second_path
    assert first_path.name == "Source_1.txt"
    assert second_path.name == "Source_1_2.txt"
    assert first_path.read_text(encoding="utf-8") == "First source text."
    assert second_path.read_text(encoding="utf-8") == "Second source text."


def test_capture_source_rejects_duplicate_source_name(tmp_path):
    capture_source(
        workspace=tmp_path,
        issue_id="duplicate_issue",
        source_name="Same Name",
        source_type="news",
        mode="general",
        text="First capture.",
    )
    with pytest.raises(CaptureError, match="Duplicate source_name"):
        capture_source(
            workspace=tmp_path,
            issue_id="duplicate_issue",
            source_name="same name",
            source_type="news",
            mode="general",
            text="Second capture with same name, different case.",
        )


def test_capture_manifest_is_deterministic_and_source_url_metadata_only(tmp_path):
    capture_source(
        workspace=tmp_path,
        issue_id="manifest_issue",
        source_name="zeta",
        source_type="forum",
        mode="finance",
        text="Everyone knows this proves manipulation.",
        source_url="https://example.invalid/forum",
    )
    capture_source(
        workspace=tmp_path,
        issue_id="manifest_issue",
        source_name="alpha",
        source_type="news",
        mode="general",
        text="Officials said the hearing is scheduled for Friday.",
    )
    manifest_path = build_capture_manifest(workspace=tmp_path)
    manifest = _json(manifest_path)
    assert manifest["issue_id"] == "manifest_issue"
    assert [source["source_name"] for source in manifest["sources"]] == ["alpha", "zeta"]
    assert manifest["sources"][1]["source_url"] == "https://example.invalid/forum"
    # file_path is emitted relative to the manifest's own directory (the
    # normal workspace layout) so it can be read without an absolute-path opt-in.
    assert not Path(manifest["sources"][1]["file_path"]).is_absolute()
    assert "source_url" not in (manifest_path.parent / manifest["sources"][1]["file_path"]).read_text(encoding="utf-8")


def test_capture_manifest_and_index_output_path_overrides(tmp_path):
    capture_source(
        workspace=tmp_path,
        issue_id="override_issue",
        source_name="override",
        source_type="news",
        mode="general",
        text="Override path check.",
    )
    manifest_path = build_capture_manifest(workspace=tmp_path, output_path=tmp_path / "custom" / "sources.json")
    index_path = write_capture_source_index(workspace=tmp_path, output_path=tmp_path / "custom" / "index.md")
    assert manifest_path == tmp_path / "custom" / "sources.json"
    assert index_path == tmp_path / "custom" / "index.md"
    assert manifest_path.exists()
    assert index_path.exists()


def test_capture_manifest_rejects_mixed_issue_log(tmp_path):
    capture_source(workspace=tmp_path, issue_id="one", source_name="a", source_type="news", mode="general", text="A.")
    capture_source(workspace=tmp_path, issue_id="two", source_name="b", source_type="news", mode="general", text="B.")
    with pytest.raises(CaptureError, match="exactly one issue_id"):
        build_capture_manifest(workspace=tmp_path)


def test_capture_manifest_rejects_empty_or_non_list_log(tmp_path):
    (tmp_path / CAPTURE_LOG_FILENAME).write_text("[]", encoding="utf-8")
    with pytest.raises(CaptureError, match="missing or empty"):
        build_capture_manifest(workspace=tmp_path)
    (tmp_path / CAPTURE_LOG_FILENAME).write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    with pytest.raises(CaptureError, match="must contain a JSON list"):
        build_capture_manifest(workspace=tmp_path)


def test_captured_finance_text_remains_masked_after_analysis_package(tmp_path):
    capture_source(
        workspace=tmp_path,
        issue_id="finance_capture",
        source_name="finance_note",
        source_type="analyst",
        mode="finance",
        text="Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month.",
        citation_note="Operator copied a note that said buy now.",
    )
    manifest_path = build_capture_manifest(workspace=tmp_path)
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")
    package_index = _json(package_dir / "PACKAGE_INDEX.json")
    paths = [
        package_dir / "final_operator_package.md",
        Path(package_index["analysis_source_index"]),
        Path(package_index["bundle_summary"]),
        Path(package_index["verification_packet"]).with_suffix(".md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert "[excluded-unsafe-finance-claim]" in combined
    assert "buy now" not in combined
    assert "target price is higher" not in combined
    assert "70 percent chance" not in combined
    assert "profitable trade this month" not in combined


def test_captured_finance_urgency_action_remains_masked_after_analysis_package(tmp_path):
    capture_source(
        workspace=tmp_path,
        issue_id="finance_urgency_capture",
        source_name="social_note",
        source_type="social",
        mode="finance",
        text="Insider sources confirm XYZ is being acquired next week. Load up now before it is too late.",
        citation_note="Operator copied a social post.",
    )
    manifest_path = build_capture_manifest(workspace=tmp_path)
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")
    package_index = _json(package_dir / "PACKAGE_INDEX.json")
    paths = [
        package_dir / "final_operator_package.md",
        Path(package_index["analysis_source_index"]),
        Path(package_index["bundle_summary"]),
        Path(package_index["verification_packet"]).with_suffix(".md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert "[excluded-unsafe-finance-claim]" in combined
    assert "load up" not in combined
    assert "before it is too late" not in combined


def test_capture_index_sanitizes_unsafe_finance_metadata(tmp_path):
    capture_source(
        workspace=tmp_path,
        issue_id="metadata_safety",
        source_name="metadata_case",
        source_type="analyst",
        mode="finance",
        text="The report discussed operational risk.",
        title="Buy now before the target price is higher.",
        citation_note="70 percent chance of a profitable trade this month.",
    )
    index = (tmp_path / CAPTURE_INDEX_FILENAME).read_text(encoding="utf-8").lower()
    assert "buy now" not in index
    assert "target price is higher" not in index
    assert "70 percent chance" not in index
    assert "profitable trade this month" not in index
    log = (tmp_path / CAPTURE_LOG_FILENAME).read_text(encoding="utf-8").lower()
    assert "buy now" not in log
    assert "target price is higher" not in log
    assert "70 percent chance" not in log
    assert "profitable trade this month" not in log


def test_cli_capture_source_manifest_and_analysis_package_smoke(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "capture-source",
            "--workspace",
            str(tmp_path),
            "--issue-id",
            "cli_capture",
            "--source-name",
            "cli_news",
            "--source-type",
            "news",
            "--mode",
            "general",
            "--text",
            "The agency said the review is scheduled for June.",
            "--source-url",
            "https://example.invalid/cli",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    manifest_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "capture-manifest",
            "--workspace",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    assert manifest_result.returncode == 0, manifest_result.stderr
    package_dir = build_analysis_package_from_manifest(
        source_manifest=tmp_path / "analysis_sources.json",
        output_root=tmp_path / "package",
    )
    assert (package_dir / "final_operator_package.md").exists()


def test_capture_manifest_emits_relative_file_paths_for_normal_workspace_layout(tmp_path):
    capture_source(
        workspace=tmp_path,
        issue_id="relative_path_issue",
        source_name="news_source",
        source_type="news",
        mode="general",
        text="The city announced a meeting schedule.",
    )
    manifest_path = build_capture_manifest(workspace=tmp_path)
    manifest = _json(manifest_path)
    source = manifest["sources"][0]
    assert not Path(source["file_path"]).is_absolute()
    assert "warnings" not in source
    # analysis-package must consume the relative path without any absolute-path opt-in.
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "package")
    assert (package_dir / "final_operator_package.md").exists()
