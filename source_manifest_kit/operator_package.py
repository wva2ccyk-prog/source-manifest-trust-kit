from __future__ import annotations

from pathlib import Path

from .bundle import _collect_bundle_records, _safe_claim_text_for_output, compare_issue_bundles, create_bundle_from_folder, run_issue_bundle, write_bundle_summary, write_operator_checklist
from .core.risk_policy import sanitize_for_report
from .helper_review import build_helper_review_packet
from .ledger.jsonl import write_json
from .verification import build_verification_packet


def _display_path(value: str | Path | None, *, base_dir: Path) -> str:
    if not value:
        return "not generated"
    path = Path(value)
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return f"<redacted-external-path>/{path.name or 'path'}"


def build_operator_package_from_folder(
    *,
    folder: str | Path,
    issue_id: str,
    output_root: str | Path,
    default_mode: str = "finance",
    default_source_type: str = "unknown",
    source_type_override_file: str | Path | None = None,
    compare_before_issue_dir: str | Path | None = None,
    excluded_detail_mode: str = "detailed",
) -> Path:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    bundle_path = root / f"{issue_id}_bundle.json"
    create_bundle_from_folder(
        issue_id=issue_id,
        folder=folder,
        output_file=bundle_path,
        default_mode=default_mode,
        default_source_type=default_source_type,
        source_type_override_file=source_type_override_file,
    )
    issue_dir = run_issue_bundle(
        bundle_file=bundle_path,
        output_root=root,
        report_profile="operator",
        excluded_detail_mode=excluded_detail_mode,
        allow_absolute_paths=True,
    )
    write_bundle_summary(issue_dir=issue_dir)
    package_dir = root / "operator_package"
    package_dir.mkdir(parents=True, exist_ok=True)
    checklist_path = write_operator_checklist(output_path=package_dir / "operator_review_checklist.md")
    verification_path = build_verification_packet(issue_dir=issue_dir, output_dir=package_dir / "verification")
    helper_packet_path = build_helper_review_packet(
        issue_dir=issue_dir,
        output_dir=package_dir / "helper_review",
        verification_packet_path=verification_path,
    )
    comparison_path = None
    if compare_before_issue_dir:
        comparison_path = compare_issue_bundles(
            before_issue_dir=compare_before_issue_dir,
            after_issue_dir=issue_dir,
            output_path=package_dir / "comparison_summary.md",
        )
    final_report = write_final_operator_package(
        issue_dir=issue_dir,
        package_dir=package_dir,
        checklist_path=checklist_path,
        verification_path=verification_path,
        helper_packet_path=helper_packet_path,
        comparison_path=comparison_path,
    )
    package_index = {
        "path_display_policy": "PACKAGE_INDEX.json contains local audit paths; PACKAGE_INDEX.md displays relative/redacted paths.",
        "final_operator_report": str(final_report),
        "bundle_summary": str(Path(issue_dir) / "bundle_operator_summary.md"),
        "verification_packet": str(verification_path),
        "helper_review_packet": str(helper_packet_path),
        "operator_checklist": str(checklist_path),
        "comparison_summary": str(comparison_path) if comparison_path else None,
    }
    write_json(package_dir / "PACKAGE_INDEX.json", package_index)
    display_base = package_dir.parent
    (package_dir / "PACKAGE_INDEX.md").write_text(
        "\n".join(
            [
                "# Operator Package Index",
                "",
                "- Path display: relative to package output root or redacted.",
                f"- Final operator report: {_display_path(package_index['final_operator_report'], base_dir=display_base)}",
                f"- Bundle summary: {_display_path(package_index['bundle_summary'], base_dir=display_base)}",
                f"- Verification packet: {_display_path(package_index['verification_packet'], base_dir=display_base)}",
                f"- Helper review packet: {_display_path(package_index['helper_review_packet'], base_dir=display_base)}",
                f"- Operator checklist: {_display_path(package_index['operator_checklist'], base_dir=display_base)}",
                f"- Comparison summary: {_display_path(package_index['comparison_summary'], base_dir=display_base)}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return package_dir


def write_final_operator_package(
    *,
    issue_dir: str | Path,
    package_dir: str | Path,
    checklist_path: str | Path,
    verification_path: str | Path,
    helper_packet_path: str | Path,
    comparison_path: str | Path | None = None,
    analysis_source_manifest_path: str | Path | None = None,
    analysis_source_index_path: str | Path | None = None,
) -> Path:
    issue_path = Path(issue_dir)
    package_path = Path(package_dir)
    display_base = package_path.parent
    manifest, run_index, _sources, claims, _reviews = _collect_bundle_records(issue_path)
    excluded = [c for c in claims if c.get("claim_type") == "excluded"]
    unresolved = [
        c
        for c in claims
        if c.get("risk_tier") in {"high", "critical"}
        or c.get("claim_type") in {"unverified_causality", "rumor", "unobservable", "needs_official_source", "excluded"}
    ]
    risk_counts: dict[str, int] = {}
    for claim in claims:
        risk = claim.get("risk_tier") or "unknown"
        risk_counts[risk] = risk_counts.get(risk, 0) + 1
    type_counts: dict[str, int] = {}
    for claim in claims:
        claim_type = claim.get("claim_type") or "unknown"
        type_counts[claim_type] = type_counts.get(claim_type, 0) + 1
    duplicate_path = issue_path / "bundle_cross_run_duplicates.json"
    duplicate_note = "not generated"
    if duplicate_path.exists():
        duplicate_note = _display_path(duplicate_path, base_dir=display_base)
    lines = [
        "# Final Operator Package",
        "",
        f"- Issue ID: {manifest.get('issue_id')}",
        f"- Source count: {manifest.get('source_count')}",
        f"- Run count: {len(run_index)}",
        "- Safety note: This package is for evidence review and verification planning. It is not financial advice.",
        "",
        "## Bundle Summary",
        f"- {_display_path(issue_path / 'bundle_operator_summary.md', base_dir=display_base)}",
        "",
        "## Risk Buckets",
    ]
    if analysis_source_manifest_path or analysis_source_index_path:
        lines[7:7] = [
            "## Analysis Source Intake",
            f"- Source manifest: {_display_path(analysis_source_manifest_path, base_dir=display_base)}",
            f"- Source index: {_display_path(analysis_source_index_path, base_dir=display_base)}",
            "- Source URLs, when present, are citation metadata only and are not fetched by the runtime.",
            "",
        ]
    for key, value in sorted(risk_counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Claim Type Buckets"])
    for key, value in sorted(type_counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Excluded Finance Summary"])
    if not excluded:
        lines.append("- None")
    else:
        for claim in excluded:
            lines.append(
                f"- {_safe_claim_text_for_output(claim)} (source: {claim.get('bundle_source_name')}; claim_id: {claim.get('claim_id')}; risk: {claim.get('risk_tier')})"
            )
    lines.extend(["", "## Unresolved Claims"])
    if not unresolved:
        lines.append("- None")
    else:
        for claim in unresolved:
            text = _safe_claim_text_for_output(claim) if claim.get("claim_type") == "excluded" else sanitize_for_report(claim.get("claim_text", ""), "finance")
            lines.append(
                f"- {text} (source: {claim.get('bundle_source_name')}; type: {claim.get('claim_type')}; risk: {claim.get('risk_tier')})"
            )
    lines.extend(
        [
            "",
            "## Verification Request Packet",
            f"- {_display_path(verification_path, base_dir=display_base)}",
            "",
            "## Source Conflict Summary",
            f"- Duplicate and divergence evidence: {duplicate_note}",
            "",
            "## Comparison Summary",
            f"- {_display_path(comparison_path, base_dir=display_base)}",
            "",
            "## Helper Review Packet",
            f"- {_display_path(helper_packet_path, base_dir=display_base)}",
            "- Helper review output is advisory only and cannot override deterministic gates.",
            "",
            "## Operator Checklist",
            f"- {_display_path(checklist_path, base_dir=display_base)}",
            "",
            "## Known Limitations",
            "- No live web search, URL fetching, external API verification, or market-data connector is performed.",
            "- Verification packets prepare follow-up work; they do not verify claims by themselves.",
            "- Excluded finance material remains masked, so operators must not reconstruct advice-like text from source memory.",
            "- Source conflict detection is conservative and does not resolve factual truth.",
            "",
        ]
    )
    report_path = package_path / "final_operator_package.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
