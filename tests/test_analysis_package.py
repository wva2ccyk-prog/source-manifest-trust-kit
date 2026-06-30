import json
import subprocess
import sys
from pathlib import Path

import pytest

from source_manifest_kit.analysis_package import AnalysisManifestError, build_analysis_package_from_manifest


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _manifest(tmp_path: Path) -> Path:
    sources = tmp_path / "sources"
    _write(sources / "01_news_article.txt", "Local police said 18 people were injured after the factory explosion.")
    _write(sources / "02_social_forum.md", "Everyone knows this proves manipulation. No primary records were posted.")
    _write(
        sources / "03_finance_commentary.txt",
        "Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month.",
    )
    manifest_path = tmp_path / "analysis_sources.json"
    manifest_path.write_text(
        json.dumps(
            {
                "issue_id": "analysis_package_issue",
                "analysis_request": "Assess the local source bundle without making investment recommendations.",
                "sources": [
                    {
                        "source_name": "local_news_report",
                        "source_type": "news",
                        "mode": "general",
                        "file_path": str(sources / "01_news_article.txt"),
                        "source_url": "https://example.invalid/news-report",
                        "title": "Local incident report",
                        "publisher": "Example News",
                    },
                    {
                        "source_name": "community_claim",
                        "source_type": "forum",
                        "mode": "finance",
                        "file_path": str(sources / "02_social_forum.md"),
                        "citation_note": "Captured manually by operator.",
                    },
                    {
                        "source_name": "finance_commentary_case",
                        "source_type": "finance_commentary",
                        "mode": "finance",
                        "file_path": str(sources / "03_finance_commentary.txt"),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_analysis_package_manifest_generates_operator_artifacts_and_source_index(tmp_path):
    manifest_path = _manifest(tmp_path)
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")
    package_index = json.loads((package_dir / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    assert (package_dir / "final_operator_package.md").exists()
    assert Path(package_index["analysis_source_manifest"]).exists()
    assert Path(package_index["analysis_source_index"]).exists()
    assert Path(package_index["analysis_bundle"]).exists()
    source_index = Path(package_index["analysis_source_index"]).read_text(encoding="utf-8")
    assert "metadata only; not fetched" in source_index
    assert "## Citation Note Guidance" in source_index
    assert "Citation notes are not verified by the runtime" in source_index
    assert "https://example.invalid/news-report" in source_index
    final_report = (package_dir / "final_operator_package.md").read_text(encoding="utf-8")
    assert "## Analysis Source Intake" in final_report
    normalized = json.loads(Path(package_index["analysis_source_manifest"]).read_text(encoding="utf-8"))
    source_types = {source["source_name"]: source["source_type"] for source in normalized["sources"]}
    assert source_types["community_claim"] == "community"
    assert source_types["finance_commentary_case"] == "analyst"


def test_analysis_package_rejects_url_like_file_path(tmp_path):
    manifest_path = tmp_path / "bad_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "issue_id": "bad_url_path",
                "sources": [
                    {
                        "source_name": "remote_source",
                        "source_type": "news",
                        "mode": "general",
                        "file_path": "https://example.invalid/story.txt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AnalysisManifestError, match="does not fetch URLs"):
        build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")


def test_analysis_package_operator_outputs_mask_unsafe_finance_text(tmp_path):
    manifest_path = _manifest(tmp_path)
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")
    package_index = json.loads((package_dir / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    paths = [
        package_dir / "final_operator_package.md",
        package_dir / "PACKAGE_INDEX.md",
        Path(package_index["analysis_source_index"]),
        Path(package_index["bundle_summary"]),
        Path(package_index["verification_packet"]).with_suffix(".md"),
        Path(package_index["helper_review_packet"]).with_suffix(".md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert "[excluded-unsafe-finance-claim]" in combined
    assert "buy now" not in combined
    assert "target price is higher" not in combined
    assert "70 percent chance" not in combined
    assert "profitable trade this month" not in combined


def test_analysis_package_masks_allocation_return_projection(tmp_path):
    sources = tmp_path / "sources"
    _write(
        sources / "community_finance.md",
        "The post says allocating 20 percent of a portfolio could produce a 3x return within 90 days.",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "issue_id": "allocation_projection_masking",
                "sources": [
                    {
                        "source_name": "community_finance",
                        "source_type": "community",
                        "mode": "finance",
                        "file_path": str(sources / "community_finance.md"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")
    package_index = json.loads((package_dir / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    paths = [
        package_dir / "final_operator_package.md",
        Path(package_index["bundle_summary"]),
        Path(package_index["verification_packet"]).with_suffix(".md"),
        Path(package_index["helper_review_packet"]).with_suffix(".md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert "[excluded-unsafe-finance-claim]" in combined
    assert "allocating 20 percent" not in combined
    assert "3x return" not in combined
    assert "within 90 days" not in combined


def test_analysis_package_masks_investment_rating_language(tmp_path):
    sources = tmp_path / "sources"
    _write(sources / "analyst.txt", "The desk maintains an overweight view on XYZ.")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "issue_id": "investment_rating_masking",
                "sources": [
                    {
                        "source_name": "analyst",
                        "source_type": "analyst",
                        "mode": "finance",
                        "file_path": str(sources / "analyst.txt"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")
    package_index = json.loads((package_dir / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    paths = [
        package_dir / "final_operator_package.md",
        Path(package_index["bundle_summary"]),
        Path(package_index["verification_packet"]).with_suffix(".md"),
        Path(package_index["helper_review_packet"]).with_suffix(".md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert "[excluded-unsafe-finance-claim]" in combined
    assert "overweight view" not in combined


def test_analysis_package_masks_korean_community_investment_action_language(tmp_path):
    sources = tmp_path / "sources"
    _write(
        sources / "community_finance.txt",
        "조심들하세요. 저는 환율보고 넥장에서 다 던졌어요. 뉴스마다 사고 팔고 할 필요는 없고 큰손들은 아무도 주식안합니다.",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "issue_id": "korean_community_action_masking",
                "sources": [
                    {
                        "source_name": "community_finance",
                        "source_type": "community",
                        "mode": "finance",
                        "file_path": str(sources / "community_finance.txt"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")
    package_index = json.loads((package_dir / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    paths = [
        package_dir / "final_operator_package.md",
        Path(package_index["bundle_summary"]),
        Path(package_index["verification_packet"]).with_suffix(".md"),
        Path(package_index["helper_review_packet"]).with_suffix(".md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "[excluded-unsafe-finance-claim]" in combined
    assert "조심들하세요" not in combined
    assert "다 던졌어요" not in combined
    assert "사고 팔고" not in combined
    assert "주식안합니다" not in combined


def test_cli_analysis_package(tmp_path):
    manifest_path = _manifest(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "analysis-package",
            "--source-manifest",
            str(manifest_path),
            "--output-root",
            str(tmp_path / "cli_out"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "cli_out" / "operator_package" / "final_operator_package.md").exists()
    assert (tmp_path / "cli_out" / "analysis_source_index.md").exists()


def test_analysis_package_escapes_source_url_metadata_for_markdown(tmp_path):
    source = tmp_path / "source.txt"
    _write(source, "The city announced a meeting schedule.")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "issue_id": "source_url_escape",
                "sources": [
                    {
                        "source_name": "news",
                        "source_type": "news",
                        "mode": "general",
                        "file_path": str(source),
                        "source_url": "https://example.invalid/[click](javascript:alert(1))",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")
    package_index = json.loads((package_dir / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    source_index = Path(package_index["analysis_source_index"]).read_text(encoding="utf-8")
    assert "\\[click\\]\\(javascript:alert\\(1\\)\\)" in source_index
    assert "[click](javascript:alert(1))" not in source_index



def test_analysis_package_accepts_windows_style_manifest_relative_paths(tmp_path):
    sources = tmp_path / "sources"
    _write(sources / "news.txt", "The city announced a meeting schedule.")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "issue_id": "windows_relative_path",
                "sources": [
                    {
                        "source_name": "news",
                        "source_type": "news",
                        "mode": "general",
                        "file_path": ".\\sources\\news.txt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")
    assert (package_dir / "final_operator_package.md").exists()

def test_analysis_package_rejects_empty_sources_duplicate_names_and_relative_traversal(tmp_path):
    empty_manifest = tmp_path / "empty.json"
    empty_manifest.write_text(json.dumps({"issue_id": "empty", "sources": []}), encoding="utf-8")
    with pytest.raises(AnalysisManifestError, match="non-empty sources"):
        build_analysis_package_from_manifest(source_manifest=empty_manifest, output_root=tmp_path / "empty_out")

    source = tmp_path / "source.txt"
    _write(source, "The city announced a meeting schedule.")
    duplicate_manifest = tmp_path / "duplicate.json"
    duplicate_manifest.write_text(
        json.dumps(
            {
                "issue_id": "duplicate",
                "sources": [
                    {"source_name": "same", "source_type": "news", "mode": "general", "file_path": str(source)},
                    {"source_name": "same", "source_type": "news", "mode": "general", "file_path": str(source)},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AnalysisManifestError, match="duplicate source_name"):
        build_analysis_package_from_manifest(source_manifest=duplicate_manifest, output_root=tmp_path / "duplicate_out")

    outside = tmp_path / "outside.txt"
    _write(outside, "The city announced a meeting schedule.")
    nested = tmp_path / "nested"
    nested.mkdir()
    traversal_manifest = nested / "traversal.json"
    traversal_manifest.write_text(
        json.dumps(
            {
                "issue_id": "traversal",
                "sources": [
                    {"source_name": "outside", "source_type": "news", "mode": "general", "file_path": "../outside.txt"},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AnalysisManifestError, match="must stay under manifest directory"):
        build_analysis_package_from_manifest(source_manifest=traversal_manifest, output_root=tmp_path / "traversal_out")


def test_analysis_package_compare_before_issue_dir_generates_comparison(tmp_path):
    manifest_path = _manifest(tmp_path)
    before_package = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "before")
    before_index = json.loads((before_package / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    after_package = build_analysis_package_from_manifest(
        source_manifest=manifest_path,
        output_root=tmp_path / "after",
        compare_before_issue_dir=before_index["issue_dir"],
    )
    after_index = json.loads((after_package / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    assert after_index["comparison_summary"]
    assert Path(after_index["comparison_summary"]).exists()
    assert Path(after_index["comparison_summary"]).with_suffix(".json").exists()


def test_analysis_source_index_guides_missing_community_citation_note(tmp_path):
    source = tmp_path / "community.md"
    _write(source, "Everyone knows this proves manipulation.")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "issue_id": "citation_guidance",
                "sources": [
                    {
                        "source_name": "community",
                        "source_type": "community",
                        "mode": "finance",
                        "file_path": str(source),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    package_dir = build_analysis_package_from_manifest(source_manifest=manifest_path, output_root=tmp_path / "out")
    package_index = json.loads((package_dir / "PACKAGE_INDEX.json").read_text(encoding="utf-8"))
    source_index = Path(package_index["analysis_source_index"]).read_text(encoding="utf-8")
    assert "Citation note guidance: add provenance" in source_index
    assert "do not upgrade any claim" in source_index
