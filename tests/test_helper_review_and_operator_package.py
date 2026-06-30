import json
import subprocess
import sys
from pathlib import Path

from source_manifest_kit.bundle import run_issue_bundle
from source_manifest_kit.helper_review import build_helper_review_packet, import_helper_review
from source_manifest_kit.operator_package import build_operator_package_from_folder
from source_manifest_kit.verification import build_verification_packet


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _bundle_issue(tmp_path: Path) -> Path:
    official = tmp_path / "samples" / "01_official_exchange.txt"
    social = tmp_path / "samples" / "02_social_claim.txt"
    excluded = tmp_path / "samples" / "03_finance_commentary.txt"
    _write(official, "The exchange reported the index closed at 2732.20.")
    _write(social, "Everyone knows this proves manipulation.")
    _write(excluded, "Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month.")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "issue_id": "helper_issue",
                "sources": [
                    {"source_name": "official", "source_type": "official", "mode": "finance", "file_path": str(official)},
                    {"source_name": "social", "source_type": "social", "mode": "finance", "file_path": str(social)},
                    {"source_name": "excluded", "source_type": "analyst", "mode": "finance", "file_path": str(excluded)},
                ],
            }
        ),
        encoding="utf-8",
    )
    return run_issue_bundle(bundle_file=bundle, output_root=tmp_path, report_profile="operator", excluded_detail_mode="detailed", allow_absolute_paths=True)


def test_helper_review_packet_and_import_are_advisory_only(tmp_path):
    issue_dir = _bundle_issue(tmp_path)
    verification_path = build_verification_packet(issue_dir=issue_dir, output_dir=tmp_path / "verification")
    packet_path = build_helper_review_packet(
        issue_dir=issue_dir,
        output_dir=tmp_path / "helper_packet",
        verification_packet_path=verification_path,
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["advisory_only"] is True
    assert packet["deterministic_core_is_final_authority"] is True
    assert packet["review_claim_index"]
    assert "safe_claim_index" not in packet
    assert not Path(packet["verification_packet_path"]).is_absolute()
    helper_md = tmp_path / "simulated_helper_review.md"
    _write(helper_md, "Advisory note: the finance claim remains excluded and must not be upgraded.")
    imported_path = import_helper_review(
        review_file=helper_md,
        output_dir=tmp_path / "imported",
        reviewer_name="simulated",
        model_name="fixture",
    )
    imported = json.loads(imported_path.read_text(encoding="utf-8"))
    assert imported["advisory_only"] is True
    assert imported["cannot_upgrade_claims"] is True


def test_imported_helper_review_markdown_masks_advice_text(tmp_path):
    helper_md = tmp_path / "simulated_helper_review.md"
    _write(helper_md, "Helper says buying exposure now has a target price and 5x returns.")
    imported_path = import_helper_review(
        review_file=helper_md,
        output_dir=tmp_path / "imported",
        reviewer_name="simulated",
        model_name="fixture",
    )
    imported_json = imported_path.read_text(encoding="utf-8").lower()
    imported_md = imported_path.with_suffix(".md").read_text(encoding="utf-8").lower()
    assert "buying exposure" in imported_json
    assert "target price" in imported_json
    assert "buying exposure" not in imported_md
    assert "target price" not in imported_md
    assert "5x returns" not in imported_md
    assert "[blocked-investment-action]" in imported_md


def test_operator_package_from_folder_contains_required_artifacts_and_masks_finance(tmp_path):
    input_dir = tmp_path / "local_sources"
    _write(input_dir / "01_official_exchange.txt", "The exchange reported the index closed at 2732.20.")
    _write(input_dir / "02_social_thread.txt", "Everyone knows this proves manipulation.")
    _write(input_dir / "03_finance_commentary.txt", "Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month.")
    package_dir = build_operator_package_from_folder(
        folder=input_dir,
        issue_id="package_issue",
        output_root=tmp_path / "package_out",
        default_mode="finance",
        default_source_type="unknown",
    )
    assert (package_dir / "final_operator_package.md").exists()
    assert (package_dir / "PACKAGE_INDEX.json").exists()
    assert (package_dir / "PACKAGE_INDEX.md").exists()
    assert (package_dir / "verification" / "verification_packet.json").exists()
    assert (package_dir / "helper_review" / "helper_review_packet.json").exists()
    assert (package_dir / "operator_review_checklist.md").exists()
    text = (package_dir / "final_operator_package.md").read_text(encoding="utf-8").lower()
    verification = (package_dir / "verification" / "verification_packet.md").read_text(encoding="utf-8").lower()
    combined = text + "\n" + verification
    assert "[excluded-unsafe-finance-claim]" in combined
    assert "buy now" not in combined
    assert "target price is higher" not in combined
    assert "70 percent chance" not in combined
    assert "profitable trade this month" not in combined


def test_cli_issue_package(tmp_path):
    input_dir = tmp_path / "local_sources"
    _write(input_dir / "01_official_exchange.txt", "The exchange reported the index closed at 2732.20.")
    _write(input_dir / "02_social_thread.txt", "Everyone knows this proves manipulation.")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "issue-package",
            "--folder",
            str(input_dir),
            "--issue-id",
            "cli_package_issue",
            "--output-root",
            str(tmp_path / "out"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out" / "operator_package" / "final_operator_package.md").exists()
