import json
import subprocess
import sys
from pathlib import Path

from source_manifest_kit.bundle import run_issue_bundle
from source_manifest_kit.verification import build_verification_packet


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sample_issue(tmp_path: Path) -> Path:
    official = tmp_path / "samples" / "official.txt"
    news = tmp_path / "samples" / "news.txt"
    social = tmp_path / "samples" / "social.txt"
    excluded = tmp_path / "samples" / "excluded.txt"
    _write(official, "The exchange reported the index closed at 2732.20.")
    _write(news, "The index fell because a policy headline spread across trading desks.")
    _write(social, "Everyone knows this proves manipulation.")
    _write(excluded, "Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month.")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "issue_id": "verify_issue",
                "sources": [
                    {"source_name": "official", "source_type": "official", "mode": "finance", "file_path": str(official)},
                    {"source_name": "news", "source_type": "news", "mode": "finance", "file_path": str(news)},
                    {"source_name": "social", "source_type": "social", "mode": "finance", "file_path": str(social)},
                    {"source_name": "excluded", "source_type": "analyst", "mode": "finance", "file_path": str(excluded)},
                ],
            }
        ),
        encoding="utf-8",
    )
    return run_issue_bundle(bundle_file=bundle, output_root=tmp_path, report_profile="operator", excluded_detail_mode="detailed", allow_absolute_paths=True)


def test_verification_packet_shape_and_tiers(tmp_path):
    issue_dir = _sample_issue(tmp_path)
    packet_path = build_verification_packet(issue_dir=issue_dir)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["policy"]["verification_does_not_upgrade_claims"] is True
    assert packet["packet_count"] >= 4
    categories = {entry["claim_category"] for entry in packet["packets"]}
    assert {"confirmed_low_risk", "unsupported_weak", "rumor_manipulation", "excluded_finance"} <= categories
    unsupported = [entry for entry in packet["packets"] if entry["claim_category"] == "unsupported_weak"][0]
    rumor = [entry for entry in packet["packets"] if entry["claim_category"] == "rumor_manipulation"][0]
    excluded = [entry for entry in packet["packets"] if entry["claim_category"] == "excluded_finance"][0]
    assert unsupported["must_verify"]
    assert rumor["must_verify"]
    assert excluded["unsafe_to_conclude"]


def test_verification_packet_finance_safety_leakage_blocked(tmp_path):
    issue_dir = _sample_issue(tmp_path)
    packet_path = build_verification_packet(issue_dir=issue_dir)
    text = packet_path.read_text(encoding="utf-8").lower()
    md_text = packet_path.with_suffix(".md").read_text(encoding="utf-8").lower()
    combined = text + "\n" + md_text
    assert "[excluded-unsafe-finance-claim]" in combined
    assert "buy now" not in combined
    assert "target price is higher" not in combined
    assert "70 percent chance" not in combined
    assert "profitable trade this month" not in combined
    assert "best-effort sanitized claim index" in combined
    assert "safe claim index" not in combined


def test_verification_packet_generation_is_idempotent(tmp_path):
    issue_dir = _sample_issue(tmp_path)
    first = json.loads(build_verification_packet(issue_dir=issue_dir).read_text(encoding="utf-8"))
    second = json.loads(build_verification_packet(issue_dir=issue_dir).read_text(encoding="utf-8"))
    assert [entry["packet_id"] for entry in first["packets"]] == [entry["packet_id"] for entry in second["packets"]]


def test_cli_bundle_verify(tmp_path):
    issue_dir = _sample_issue(tmp_path)
    out_dir = tmp_path / "verify_out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "bundle-verify",
            "--issue-dir",
            str(issue_dir),
            "--output-dir",
            str(out_dir),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "verification_packet.json").exists()
    assert (out_dir / "verification_packet.md").exists()


def test_verification_packet_groups_repeated_questions_without_losing_claims(tmp_path):
    issue_dir = _sample_issue(tmp_path)
    packet_path = build_verification_packet(issue_dir=issue_dir)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    md_text = packet_path.with_suffix(".md").read_text(encoding="utf-8")
    assert packet["question_grouping"]["nice_to_verify_grouped_count"] <= packet["question_grouping"]["nice_to_verify_raw_count"]
    assert packet["question_grouping"]["must_verify_grouped_count"] <= packet["question_grouping"]["must_verify_raw_count"]
    assert "(claims:" in md_text
    assert "Whether an independent reputable source reports the same limited factual statement for official." in md_text
    assert md_text.count("Whether an independent reputable source reports the same limited factual statement for official.") == 1


def test_verification_packet_cautions_low_risk_items_from_excluded_source(tmp_path):
    mixed = tmp_path / "samples" / "mixed_finance.txt"
    _write(mixed, "Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month. The company reported service recovered at 10:05.")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "issue_id": "verify_mixed_source",
                "sources": [
                    {"source_name": "mixed_finance", "source_type": "analyst", "mode": "finance", "file_path": str(mixed)},
                ],
            }
        ),
        encoding="utf-8",
    )
    issue_dir = run_issue_bundle(bundle_file=bundle, output_root=tmp_path, report_profile="operator", excluded_detail_mode="detailed", allow_absolute_paths=True)
    packet_path = build_verification_packet(issue_dir=issue_dir)
    text = packet_path.read_text(encoding="utf-8").lower() + "\n" + packet_path.with_suffix(".md").read_text(encoding="utf-8").lower()
    assert "this source also contains excluded finance material" in text
    assert "[excluded-unsafe-finance-claim]" in text
    assert "buy now" not in text
    assert "70 percent chance" not in text


def test_verification_packet_includes_numeric_divergence_question(tmp_path):
    s1 = tmp_path / "samples" / "wire_a.txt"
    s2 = tmp_path / "samples" / "wire_b.txt"
    _write(s1, "Local police said 18 people were injured after the factory explosion.")
    _write(s2, "Hospital staff told a reporter that 23 people were treated after the factory explosion.")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "issue_id": "verify_numeric_divergence",
                "sources": [
                    {"source_name": "wire_a", "source_type": "news", "mode": "general", "file_path": str(s1)},
                    {"source_name": "wire_b", "source_type": "news", "mode": "general", "file_path": str(s2)},
                ],
            }
        ),
        encoding="utf-8",
    )
    issue_dir = run_issue_bundle(bundle_file=bundle, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    packet_path = build_verification_packet(issue_dir=issue_dir)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    md_text = packet_path.with_suffix(".md").read_text(encoding="utf-8").lower()
    assert packet["numeric_divergence_question_count"] == 1
    assert packet["numeric_divergence_questions"]
    assert "## numeric divergence questions" in md_text
    assert "reported_people_count divergence" in md_text
    assert "18" in md_text
    assert "23" in md_text


def test_verification_packet_uses_source_qualified_claim_refs(tmp_path):
    issue_dir = _sample_issue(tmp_path)
    packet_path = build_verification_packet(issue_dir=issue_dir)
    md_text = packet_path.with_suffix(".md").read_text(encoding="utf-8")
    assert "claims: news/clm_001" in md_text
    assert "claims: social/clm_001" in md_text


def test_verification_packet_does_not_finance_sanitize_general_short_text(tmp_path):
    source = tmp_path / "samples" / "general.txt"
    _write(source, "The operator captured this short excerpt manually.")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "issue_id": "verify_general_short_text",
                "sources": [
                    {"source_name": "general_short", "source_type": "news", "mode": "general", "file_path": str(source)},
                ],
            }
        ),
        encoding="utf-8",
    )
    issue_dir = run_issue_bundle(bundle_file=bundle, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    packet_path = build_verification_packet(issue_dir=issue_dir)
    md_text = packet_path.with_suffix(".md").read_text(encoding="utf-8")
    assert "short excerpt" in md_text
    assert "[blocked-investment-action]" not in md_text


def test_packet_ids_stable_across_independent_reruns(tmp_path):
    # FIX 5: packet_ids are seeded from stable content (issue_id + category +
    # normalized claim hash), NOT run_id/timestamp, so two full independent reruns
    # of the same bundle produce identical packet_ids.
    def _run(root: Path) -> list[str]:
        issue_dir = _sample_issue(root)
        packet = json.loads(build_verification_packet(issue_dir=issue_dir).read_text(encoding="utf-8"))
        return [entry["packet_id"] for entry in packet["packets"]]

    first = _run(tmp_path / "run_one")
    second = _run(tmp_path / "run_two")
    assert first == second
    assert all(pid.startswith("vreq_") for pid in first)


def test_verification_packet_escapes_markdown_injection(tmp_path):
    # FIX 1: the verification masking gate escapes injected markdown/HTML so it
    # renders literally in the packet.
    source = tmp_path / "samples" / "injection.txt"
    _write(
        source,
        "The vendor notice included a link [x](http://evil) and embedded <script>alert(1)</script> in the body.",
    )
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "issue_id": "verify_markdown_injection",
                "sources": [
                    {"source_name": "wire", "source_type": "news", "mode": "general", "file_path": str(source)},
                ],
            }
        ),
        encoding="utf-8",
    )
    issue_dir = run_issue_bundle(bundle_file=bundle, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    packet_path = build_verification_packet(issue_dir=issue_dir)
    combined = packet_path.read_text(encoding="utf-8") + "\n" + packet_path.with_suffix(".md").read_text(encoding="utf-8")
    assert "\\[x\\]" in combined
    assert "[x](http://evil)" not in combined
    assert "&lt;script&gt;" in combined
    assert "<script>" not in combined


def test_verification_packet_defensively_masks_general_mode_finance_text(tmp_path):
    source = tmp_path / "samples" / "general_finance_quote.txt"
    _write(source, "The article quoted a desk saying buying exposure now has a target price and 5x returns.")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "issue_id": "verify_general_finance_quote",
                "sources": [
                    {"source_name": "general_finance_quote", "source_type": "news", "mode": "general", "file_path": str(source)},
                ],
            }
        ),
        encoding="utf-8",
    )
    issue_dir = run_issue_bundle(bundle_file=bundle, output_root=tmp_path, report_profile="operator", allow_absolute_paths=True)
    packet_path = build_verification_packet(issue_dir=issue_dir)
    combined = packet_path.read_text(encoding="utf-8").lower() + "\n" + packet_path.with_suffix(".md").read_text(encoding="utf-8").lower()
    assert "buying exposure" not in combined
    assert "target price" not in combined
    assert "5x returns" not in combined
    assert "[blocked-investment-action]" in combined
