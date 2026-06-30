import json
from pathlib import Path

from source_manifest_kit.bundle import compare_issue_bundles, create_bundle_from_folder, run_issue_bundle, write_operator_checklist


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_folder_to_bundle_generation_and_deterministic_ordering(tmp_path):
    folder = tmp_path / "input"
    _write(folder / "b_second.md", "Second file.")
    _write(folder / "a_first.txt", "First file.")
    _write(folder / "ignore.csv", "ignore")
    bundle_path = create_bundle_from_folder(
        issue_id="folder_issue",
        folder=folder,
        output_file=tmp_path / "bundle.json",
        default_mode="finance",
        default_source_type="news",
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["issue_id"] == "folder_issue"
    assert [Path(s["file_path"]).name for s in bundle["sources"]] == ["a_first.txt", "b_second.md"]
    assert all(s["mode"] == "finance" for s in bundle["sources"])
    assert all(s["source_type"] == "news" for s in bundle["sources"])


def test_bundle_create_infers_source_type_and_honors_override_file(tmp_path):
    folder = tmp_path / "input"
    _write(folder / "01_official_exchange_status.txt", "status")
    _write(folder / "02_community_forum_claim.md", "claim")
    _write(folder / "03_news_article.txt", "news")
    _write(folder / "04_finance_commentary.md", "commentary")
    _write(folder / "05_social_thread_claim.txt", "social")
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"04_finance_commentary": "analyst"}), encoding="utf-8")
    bundle_path = create_bundle_from_folder(
        issue_id="infer_issue",
        folder=folder,
        output_file=tmp_path / "bundle.json",
        default_mode="finance",
        default_source_type="mixed",
        source_type_override_file=overrides,
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    types = {item["source_name"]: item["source_type"] for item in bundle["sources"]}
    assert types["01_official_exchange_status"] == "official"
    assert types["02_community_forum_claim"] == "community"
    assert types["03_news_article"] == "news"
    assert types["04_finance_commentary"] == "analyst"
    assert types["05_social_thread_claim"] == "social"


def test_operator_checklist_artifact_generation(tmp_path):
    path = write_operator_checklist(output_path=tmp_path / "checklist.md")
    text = path.read_text(encoding="utf-8")
    assert "Issue Bundle Operator Review Checklist" in text
    assert "Unsupported" in text
    assert "Rumor" in text
    assert "Excluded finance claim" in text
    assert "Escalate to Human/Web Verification" in text


def test_bundle_comparison_categories_and_safety(tmp_path):
    before_dir = tmp_path / "before_samples"
    after_dir = tmp_path / "after_samples"
    _write(before_dir / "official.txt", "The exchange reported the index closed at 2732.20.")
    _write(before_dir / "social.txt", "A social account says the rally happened because a private group knew earnings early.")
    _write(before_dir / "old.txt", "Summary said the index fell because of weak exports.")
    _write(after_dir / "official.txt", "The exchange reported the index closed at 2732.20.")
    _write(after_dir / "social.txt", "Another account says the rally happened because a private group knew earnings early.")
    _write(after_dir / "excluded.txt", "Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month.")
    before_bundle = create_bundle_from_folder(
        issue_id="compare_before",
        folder=before_dir,
        output_file=tmp_path / "before_bundle.json",
        default_mode="finance",
        default_source_type="news",
    )
    after_bundle = create_bundle_from_folder(
        issue_id="compare_after",
        folder=after_dir,
        output_file=tmp_path / "after_bundle.json",
        default_mode="finance",
        default_source_type="news",
    )
    before_data = json.loads(before_bundle.read_text(encoding="utf-8"))
    after_data = json.loads(after_bundle.read_text(encoding="utf-8"))
    for source in before_data["sources"]:
        if source["source_name"] == "social":
            source["source_type"] = "social"
    for source in after_data["sources"]:
        if source["source_name"] == "social":
            source["source_type"] = "social"
        if source["source_name"] == "excluded":
            source["source_type"] = "analyst"
    before_bundle.write_text(json.dumps(before_data), encoding="utf-8")
    after_bundle.write_text(json.dumps(after_data), encoding="utf-8")
    before_issue = run_issue_bundle(bundle_file=before_bundle, output_root=tmp_path / "runs", allow_absolute_paths=True)
    after_issue = run_issue_bundle(bundle_file=after_bundle, output_root=tmp_path / "runs", allow_absolute_paths=True)
    comparison_path = compare_issue_bundles(
        before_issue_dir=before_issue,
        after_issue_dir=after_issue,
        output_path=tmp_path / "comparison.md",
    )
    comparison = comparison_path.read_text(encoding="utf-8").lower()
    comparison_json = json.loads(comparison_path.with_suffix(".json").read_text(encoding="utf-8"))
    assert comparison_json["new"]
    assert comparison_json["repeated"]
    assert comparison_json["disappeared"]
    assert comparison_json["still_unresolved_risky"]
    comparison_json_text = json.dumps(comparison_json).lower()
    assert "[excluded-unsafe-finance-claim]" in comparison
    assert "[excluded-unsafe-finance-claim]" in comparison_json_text
    assert "buy now" not in comparison
    assert "buy now" not in comparison_json_text
    assert "target price is higher" not in comparison
    assert "target price is higher" not in comparison_json_text
    assert "70 percent chance" not in comparison
    assert "70 percent chance" not in comparison_json_text


def test_bundle_create_defaults_to_relative_paths(tmp_path):
    folder = tmp_path / "input"
    _write(folder / "a_first.txt", "First file.")
    _write(folder / "b_second.md", "Second file.")
    bundle_path = create_bundle_from_folder(
        issue_id="relative_issue",
        folder=folder,
        output_file=tmp_path / "bundle.json",
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    stored = [s["file_path"] for s in bundle["sources"]]
    assert stored == ["input/a_first.txt", "input/b_second.md"]
    assert all(not Path(p).is_absolute() for p in stored)
    # Relative paths resolve against the bundle file location and run cleanly.
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path / "runs")
    assert issue_dir.exists()


def test_bundle_create_absolute_paths_are_opt_in(tmp_path):
    folder = tmp_path / "input"
    _write(folder / "a_first.txt", "First file.")
    bundle_path = create_bundle_from_folder(
        issue_id="absolute_issue",
        folder=folder,
        output_file=tmp_path / "bundle.json",
        use_absolute_paths=True,
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert all(Path(s["file_path"]).is_absolute() for s in bundle["sources"])