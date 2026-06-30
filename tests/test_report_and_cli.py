import json
import subprocess
import sys
from pathlib import Path

from source_manifest_kit.runs import analyze_file


def test_report_generation_after_validation(tmp_path):
    input_file = tmp_path / "unsafe.txt"
    input_file.write_text("Buy this stock. The target price is higher. The real reason the market moved was policy news.", encoding="utf-8")
    run_dir = analyze_file(mode="finance", input_path=input_file, source_name="draft", source_type="user_note", output_root=tmp_path)
    gates = json.loads((run_dir / "ledger" / "report_gates.json").read_text(encoding="utf-8"))
    report = (run_dir / "report.md").read_text(encoding="utf-8").lower()
    assert gates["passed"] is True
    assert "[excluded-unsafe-finance-claim]" in report
    assert "buy this stock" not in report
    assert "target price is higher" not in report
    assert "true reason" not in report


def test_report_hides_unsafe_excluded_finance_text(tmp_path):
    input_file = tmp_path / "unsafe_probability.txt"
    input_file.write_text(
        "It gives a 70 percent chance of a profitable trade this month.",
        encoding="utf-8",
    )
    run_dir = analyze_file(
        mode="finance",
        input_path=input_file,
        source_name="draft",
        source_type="analyst",
        output_root=tmp_path,
    )
    report = (run_dir / "report.md").read_text(encoding="utf-8").lower()
    assert "[excluded-unsafe-finance-claim]" in report
    assert "profitable trade this month" not in report
    assert "70 percent chance" not in report
    assert "this finance claim is blocked by policy and remains excluded" in report
    assert "rewritten as a non-advice" not in report


def test_report_operator_profile_sections(tmp_path):
    input_file = tmp_path / "operator.txt"
    input_file.write_text(
        "A social post says private chat evidence proves manipulation.",
        encoding="utf-8",
    )
    run_dir = analyze_file(
        mode="finance",
        input_path=input_file,
        source_name="operator_profile_source",
        source_type="social",
        output_root=tmp_path,
    )
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "## Source Classification" in report
    assert "- Report profile: minimal" in report


def test_report_detailed_excluded_mode_keeps_safe_masking(tmp_path, monkeypatch):
    monkeypatch.setenv("IFTOS_EXCLUDED_DETAIL_MODE", "detailed")
    input_file = tmp_path / "unsafe_detail.txt"
    input_file.write_text(
        "Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month.",
        encoding="utf-8",
    )
    run_dir = analyze_file(
        mode="finance",
        input_path=input_file,
        source_name="draft",
        source_type="analyst",
        output_root=tmp_path,
    )
    report = (run_dir / "report.md").read_text(encoding="utf-8").lower()
    assert "[excluded-unsafe-finance-claim]" in report
    assert "blocked_categories:" in report
    assert "buy now" not in report
    assert "target price is higher" not in report
    assert "profitable trade this month" not in report
    assert "70 percent chance" not in report


def test_cli_report_operator_profile_and_detailed_mode(tmp_path):
    input_file = tmp_path / "cli_operator.txt"
    input_file.write_text(
        "Buy now. Target price is higher. It gives a 70 percent chance of a profitable trade this month.",
        encoding="utf-8",
    )
    analyze = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "analyze-file",
            "--mode",
            "finance",
            "--input",
            str(input_file),
            "--source-name",
            "cli_operator_source",
            "--source-type",
            "analyst",
            "--output-root",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    assert analyze.returncode == 0, analyze.stderr
    run_dir = list((tmp_path / "runs").iterdir())[0]
    report_cmd = subprocess.run(
        [
            sys.executable,
            "-m",
            "source_manifest_kit",
            "report",
            "--run-dir",
            str(run_dir),
            "--profile",
            "operator",
            "--excluded-detail-mode",
            "detailed",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    assert report_cmd.returncode == 0, report_cmd.stderr
    report = (run_dir / "report.md").read_text(encoding="utf-8").lower()
    assert "report profile: operator" in report
    assert "blocked_categories:" in report
    assert "buy now" not in report
    assert "target price is higher" not in report
    assert "70 percent chance" not in report


def test_cli_smoke_flow(tmp_path):
    input_file = tmp_path / "article.txt"
    input_file.write_text("The index fell 1.8 percent. News said it fell because of a headline.", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "source_manifest_kit", "analyze-file", "--mode", "finance", "--input", str(input_file), "--source-name", "demo_news", "--source-type", "news", "--output-root", str(tmp_path)], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    run_dirs = list((tmp_path / "runs").iterdir())
    assert run_dirs
    run_dir = run_dirs[0]
    assert (run_dir / "report.md").exists()
    validate = subprocess.run([sys.executable, "-m", "source_manifest_kit", "validate-run", "--run-dir", str(run_dir)], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True)
    assert validate.returncode == 0, validate.stderr
