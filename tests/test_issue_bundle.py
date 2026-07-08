import json
from pathlib import Path

import pytest

from source_manifest_kit.bundle import BundlePathError, create_bundle_from_folder, run_issue_bundle


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_bundle_manifest_and_run_index_creation(tmp_path):
    s1 = tmp_path / "samples" / "src1.txt"
    s2 = tmp_path / "samples" / "src2.txt"
    _write(s1, "The city announced a new library schedule.")
    _write(s2, "The index fell because of a headline.")
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_test_001",
        "sources": [
            {"source_name": "general_city_news", "source_type": "news", "mode": "general", "file_path": str(s1)},
            {"source_name": "finance_news", "source_type": "news", "mode": "finance", "file_path": str(s2)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, allow_absolute_paths=True)
    manifest = json.loads((issue_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
    run_index = json.loads((issue_dir / "bundle_run_index.json").read_text(encoding="utf-8"))
    assert manifest["issue_id"] == "issue_bundle_test_001"
    assert manifest["source_count"] == 2
    assert len(run_index["runs"]) == 2
    assert all(Path(row["run_dir"]).exists() for row in run_index["runs"])


def test_consolidated_summary_sections_and_safety_masking(tmp_path):
    s1 = tmp_path / "samples" / "safe.txt"
    s2 = tmp_path / "samples" / "excluded.txt"
    s3 = tmp_path / "samples" / "rumor.txt"
    _write(s1, "The exchange reported the index closed at 2732.20.")
    _write(s2, "Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month.")
    _write(s3, "Everyone knows this proves manipulation.")
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_test_002",
        "sources": [
            {"source_name": "official_observation", "source_type": "official", "mode": "finance", "file_path": str(s1)},
            {"source_name": "analyst_excluded", "source_type": "analyst", "mode": "finance", "file_path": str(s2)},
            {"source_name": "social_rumor", "source_type": "social", "mode": "finance", "file_path": str(s3)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", excluded_detail_mode="detailed", allow_absolute_paths=True)
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8").lower()
    assert "## low-risk reported material (deterministic classification only)" in summary
    assert "## unsupported or weakly supported claims" in summary
    assert "## rumor / social / manipulation-framing claims" in summary
    assert "## excluded finance claims summary" in summary
    assert "## source conflict or divergence notes" in summary
    assert "## follow-up verification questions" in summary
    assert "[excluded-unsafe-finance-claim]" in summary
    assert "id=analyst_excluded/clm_001" in summary
    assert "buy now" not in summary
    assert "target price is higher" not in summary
    assert "70 percent chance" not in summary
    assert "profitable trade this month" not in summary


def test_cross_run_duplicate_grouping_for_social_variants(tmp_path):
    s1 = tmp_path / "samples" / "social1.txt"
    s2 = tmp_path / "samples" / "social2.txt"
    _write(s1, "[Social thread] A social account says the rally happened because a private group knew earnings early.")
    _write(s2, "[Forum repost] Another account says the rally happened because a private group knew earnings early.")
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_test_003",
        "sources": [
            {"source_name": "social_variant_1", "source_type": "social", "mode": "finance", "file_path": str(s1)},
            {"source_name": "social_variant_2", "source_type": "social", "mode": "finance", "file_path": str(s2)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    duplicate_json = json.loads((issue_dir / "bundle_cross_run_duplicates.json").read_text(encoding="utf-8"))
    assert duplicate_json["groups"]
    first = duplicate_json["groups"][0]
    assert first["claim_count"] >= 2
    assert first["run_count"] >= 2


def test_bundle_summary_routes_community_manipulation_to_rumor_section(tmp_path):
    s1 = tmp_path / "samples" / "community.txt"
    _write(s1, "Everyone knows this proves manipulation. Insiders coordinated to force liquidations. No primary records were posted.")
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_test_004",
        "sources": [
            {"source_name": "community_claim", "source_type": "community", "mode": "finance", "file_path": str(s1)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", excluded_detail_mode="detailed", allow_absolute_paths=True)
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8").lower()
    unsupported_start = summary.index("## unsupported or weakly supported claims")
    rumor_start = summary.index("## rumor / social / manipulation-framing claims")
    excluded_start = summary.index("## excluded finance claims summary")
    unsupported_block = summary[unsupported_start:rumor_start]
    rumor_block = summary[rumor_start:excluded_start]
    assert "everyone knows this proves manipulation." in rumor_block
    assert "everyone knows this proves manipulation." not in unsupported_block


def test_bundle_summary_keeps_social_reported_claim_out_of_low_risk_section(tmp_path):
    social = tmp_path / "samples" / "social.txt"
    news = tmp_path / "samples" / "news.txt"
    _write(social, "A social account said MNO Corp reported quarterly revenue rose 15 percent year over year.")
    _write(news, "MNO Corp reported quarterly revenue rose 15 percent year over year.")
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_test_social_low_risk_routing",
        "sources": [
            {"source_name": "social_repeat", "source_type": "social", "mode": "finance", "file_path": str(social)},
            {"source_name": "news_report", "source_type": "news", "mode": "finance", "file_path": str(news)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8").lower()
    low_risk_start = summary.index("## low-risk reported material (deterministic classification only)")
    unsupported_start = summary.index("## unsupported or weakly supported claims")
    rumor_start = summary.index("## rumor / social / manipulation-framing claims")
    excluded_start = summary.index("## excluded finance claims summary")
    low_risk_block = summary[low_risk_start:unsupported_start]
    rumor_block = summary[rumor_start:excluded_start]
    assert "source: news_report" in low_risk_block
    assert "source: social_repeat" not in low_risk_block
    assert "source: social_repeat" in rumor_block


def test_bundle_summary_flags_numeric_conflict_without_truth_adjudication(tmp_path):
    s1 = tmp_path / "samples" / "wire_a.txt"
    s2 = tmp_path / "samples" / "article_b.txt"
    _write(s1, "Local police said 18 people were injured after the factory explosion.")
    _write(s2, "Hospital staff told a reporter that 23 people were treated after the factory explosion.")
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_test_numeric_conflict",
        "sources": [
            {"source_name": "wire_a", "source_type": "news", "mode": "general", "file_path": str(s1)},
            {"source_name": "article_b", "source_type": "news", "mode": "general", "file_path": str(s2)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8").lower()
    numeric_conflicts = json.loads((issue_dir / "bundle_numeric_conflicts.json").read_text(encoding="utf-8"))
    assert "numeric divergence requires review" in summary
    assert "### medium priority" in summary
    assert "numeric:reported_people_count" in summary
    assert "which primary or official record explains the reported_people_count divergence" in summary
    assert "18" in summary
    assert "23" in summary
    assert "true" not in summary
    assert "false" not in summary
    assert numeric_conflicts["conflicts"]


def test_bundle_summary_flags_affected_worker_count_divergence(tmp_path):
    s1 = tmp_path / "samples" / "city_report.txt"
    s2 = tmp_path / "samples" / "union_report.txt"
    _write(s1, "The city said 18 workers were affected by the plant shutdown notice.")
    _write(s2, "A union representative said 23 workers were affected by the plant shutdown notice.")
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_test_worker_count_conflict",
        "sources": [
            {"source_name": "city_report", "source_type": "news", "mode": "general", "file_path": str(s1)},
            {"source_name": "union_report", "source_type": "news", "mode": "general", "file_path": str(s2)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8").lower()
    numeric_conflicts = json.loads((issue_dir / "bundle_numeric_conflicts.json").read_text(encoding="utf-8"))
    assert "numeric divergence requires review" in summary
    assert "18" in summary
    assert "23" in summary
    assert numeric_conflicts["conflicts"]


def test_bundle_summary_splits_unrelated_people_count_contexts(tmp_path):
    files = {
        "explosion_a.txt": "Local police said 18 people were injured after the factory explosion.",
        "explosion_b.txt": "Hospital staff told a reporter that 23 people were treated after the factory explosion.",
        "workers_a.txt": "The city said 18 workers were affected by the plant shutdown notice.",
        "workers_b.txt": "A union representative said 23 workers were affected by the plant shutdown notice.",
    }
    sources = []
    for name, text in files.items():
        path = tmp_path / "samples" / name
        _write(path, text)
        sources.append({"source_name": path.stem, "source_type": "news", "mode": "general", "file_path": str(path)})
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps({"issue_id": "issue_bundle_test_context_split", "sources": sources}), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    numeric_conflicts = json.loads((issue_dir / "bundle_numeric_conflicts.json").read_text(encoding="utf-8"))
    assert len(numeric_conflicts["conflicts"]) == 2
    source_groups = {tuple(conflict["sources"]) for conflict in numeric_conflicts["conflicts"]}
    assert ("explosion_a", "explosion_b") in source_groups
    assert ("workers_a", "workers_b") in source_groups


def test_bundle_summary_cautions_interpretation_from_excluded_finance_source(tmp_path):
    s1 = tmp_path / "samples" / "finance_commentary.txt"
    _write(s1, "Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month. This is the easiest setup of the quarter.")
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_test_excluded_source_caution",
        "sources": [
            {"source_name": "finance_commentary", "source_type": "analyst", "mode": "finance", "file_path": str(s1)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", excluded_detail_mode="detailed", allow_absolute_paths=True)
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8").lower()
    assert "operator caution: this source also contains excluded finance material" in summary
    assert "[excluded-unsafe-finance-claim]" in summary
    assert "buy now" not in summary
    assert "70 percent chance" not in summary


def test_bundle_summary_defensively_masks_general_mode_finance_language(tmp_path):
    s1 = tmp_path / "samples" / "general_news.txt"
    _write(s1, "The article quoted a desk saying buying exposure now has a target price and 5x returns.")
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_general_mode_masking",
        "sources": [
            {"source_name": "general_news", "source_type": "news", "mode": "general", "file_path": str(s1)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8").lower()
    assert "buying exposure" not in summary
    assert "target price" not in summary
    assert "5x returns" not in summary
    assert "[blocked-investment-action]" in summary


def test_bundle_summary_escapes_markdown_injection(tmp_path):
    # FIX 1: untrusted claim text is escaped through the single masking gate so an
    # injected markdown link / raw HTML tag renders literally, not as active markup.
    s1 = tmp_path / "samples" / "injection.txt"
    _write(
        s1,
        "The vendor notice included a link [x](http://evil) and embedded <script>alert(1)</script> in the body.",
    )
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_markdown_injection",
        "sources": [
            {"source_name": "wire", "source_type": "news", "mode": "general", "file_path": str(s1)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8")
    assert "\\[x\\]" in summary
    assert "[x](http://evil)" not in summary
    assert "&lt;script&gt;" in summary
    assert "<script>" not in summary


def test_cross_source_repetition_flags_news_and_community_dup(tmp_path):
    # FIX 2: identical text repeated across DIFFERENT source types (news + community)
    # is grouped and flagged as repetition-without-lineage; the old detector only
    # keyed community/social and missed the news+repost laundering case.
    verbatim = "The mayor confirmed the bridge will reopen on Tuesday morning."
    news = tmp_path / "samples" / "news.txt"
    community = tmp_path / "samples" / "community.txt"
    _write(news, verbatim)
    _write(community, verbatim)
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_cross_source_laundering",
        "sources": [
            {"source_name": "news_wire", "source_type": "news", "mode": "general", "file_path": str(news)},
            {"source_name": "community_repost", "source_type": "community", "mode": "general", "file_path": str(community)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    duplicate_json = json.loads((issue_dir / "bundle_cross_run_duplicates.json").read_text(encoding="utf-8"))
    assert duplicate_json["groups"]
    group = duplicate_json["groups"][0]
    assert group["source_count"] >= 2
    assert set(group["sources"]) == {"news_wire", "community_repost"}
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8").lower()
    assert "cross-source repeated claim group" in summary
    assert "not independent corroboration" in summary


def test_bundle_summary_includes_medium_reported_claim_catch_all(tmp_path):
    # FIX 3: a reported_claim forced to risk_tier medium (strong-certainty flag) is
    # neither low-risk nor weak nor rumor, and was silently dropped by the summary.
    # The catch-all bucket now surfaces it.
    s1 = tmp_path / "samples" / "merger.txt"
    _write(s1, "Sources say the merger is guaranteed to close and will certainly double revenue.")
    bundle_path = tmp_path / "bundle.json"
    bundle_data = {
        "issue_id": "issue_bundle_medium_catch_all",
        "sources": [
            {"source_name": "wire", "source_type": "news", "mode": "general", "file_path": str(s1)},
        ],
    }
    bundle_path.write_text(json.dumps(bundle_data), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8").lower()
    assert "## other reported claims needing review" in summary
    catch_all_start = summary.index("## other reported claims needing review")
    rumor_start = summary.index("## rumor / social / manipulation-framing claims")
    catch_all_block = summary[catch_all_start:rumor_start]
    assert "the merger is guaranteed to close" in catch_all_block
    assert "risk: medium" in catch_all_block


def test_bundle_summary_flags_korean_financial_figure_divergence(tmp_path):
    # FIX 4: divergent Korean 조/억/만/원 figures for the same metric context are
    # detected language-agnostically, while an unrelated figure (share price) with a
    # different context does not falsely group.
    files = {
        "wire_a": "회사의 올해 예상 매출은 12조 3,000억원이다.",
        "wire_b": "회사의 올해 예상 매출은 18조원이다.",
        "analyst_c": "회사의 올해 예상 매출은 25조원이다.",
        "unrelated_d": "그 회사의 주가는 5만원까지 올랐다.",
    }
    sources = []
    for name, text in files.items():
        path = tmp_path / "samples" / f"{name}.txt"
        _write(path, text)
        sources.append({"source_name": name, "source_type": "news", "mode": "general", "file_path": str(path)})
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps({"issue_id": "issue_bundle_korean_divergence", "sources": sources}), encoding="utf-8")
    issue_dir = run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    numeric_conflicts = json.loads((issue_dir / "bundle_numeric_conflicts.json").read_text(encoding="utf-8"))
    assert len(numeric_conflicts["conflicts"]) == 1
    conflict = numeric_conflicts["conflicts"][0]
    assert set(conflict["sources"]) == {"wire_a", "wire_b", "analyst_c"}
    assert "unrelated_d" not in conflict["sources"]
    assert set(conflict["values"]) == {"12조 3,000억원", "18조원", "25조원"}
    summary = (issue_dir / "bundle_operator_summary.md").read_text(encoding="utf-8").lower()
    assert "numeric divergence requires review" in summary


def test_bundle_run_rejects_relative_path_traversal_by_default(tmp_path):
    outside = tmp_path / "outside.txt"
    _write(outside, "This file must not be read through traversal.")
    bundle_dir = tmp_path / "bundle_dir"
    bundle_dir.mkdir()
    bundle_path = bundle_dir / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "issue_id": "path_traversal_rejected",
                "sources": [
                    {"source_name": "outside", "source_type": "news", "mode": "general", "file_path": "../outside.txt"}
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(BundlePathError, match="path traversal"):
        run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path / "out")


def test_bundle_run_rejects_absolute_paths_without_trusted_mode(tmp_path):
    source = tmp_path / "source.txt"
    _write(source, "The city announced a new schedule.")
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "issue_id": "absolute_path_rejected",
                "sources": [
                    {"source_name": "source", "source_type": "news", "mode": "general", "file_path": str(source)}
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(BundlePathError, match="absolute file_path"):
        run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path / "out")


def test_bundle_run_rejects_symlink_even_in_trusted_mode(tmp_path):
    outside = tmp_path / "outside.txt"
    _write(outside, "The linked file should not be analyzed through a symlink.")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable on this platform: {exc}")
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "issue_id": "symlink_rejected",
                "sources": [
                    {"source_name": "linked", "source_type": "news", "mode": "general", "file_path": str(link)}
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(BundlePathError, match="symlink"):
        run_issue_bundle(bundle_file=bundle_path, output_root=tmp_path / "out", allow_absolute_paths=True)


def test_bundle_create_skips_symlink_sources(tmp_path):
    folder = tmp_path / "sources"
    _write(folder / "real.txt", "The agency posted a schedule.")
    outside = tmp_path / "outside.txt"
    _write(outside, "This should not be included by bundle-create.")
    try:
        (folder / "linked.txt").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable on this platform: {exc}")

    bundle = create_bundle_from_folder(issue_id="skip_symlink", folder=folder, output_file=tmp_path / "bundle.json")
    data = json.loads(bundle.read_text(encoding="utf-8"))
    assert [source["source_name"] for source in data["sources"]] == ["real"]
