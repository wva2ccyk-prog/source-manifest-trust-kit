from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .acquisition import (
    ACQUISITION_INDEX_FILENAME,
    AcquisitionError,
    DEFAULT_BYTE_CAP,
    DEFAULT_TIMEOUT_SECONDS,
    acquisition_log_to_analysis_manifest,
    fetch_acquisition_manifest,
    load_acquisition_manifest,
)
from .analysis_package import AnalysisManifestError, build_analysis_package_from_manifest
from .artifact_schema import ArtifactSchemaError, available_schemas, validate_artifact_file, write_artifact_validation
from .capture_helper import build_capture_manifest, capture_source
from .core.report_gates import build_report_gates
from .core.reporting import write_report
from .core.validation import load_run
from .bundle import BundlePathError, compare_issue_bundles, create_bundle_from_folder, run_issue_bundle, write_bundle_summary, write_operator_checklist
from .helper_review import build_helper_review_packet, import_helper_review
from .llm_review import build_llm_review_packet, run_mock_llm_review, validate_external_review_response, write_provider_review_template
from .operator_package import build_operator_package_from_folder
from .verification import build_verification_packet
from .runs import analyze_file, init_workspace
from .search_candidates import (
    SEARCH_CANDIDATE_INDEX_FILENAME,
    load_search_candidate_artifact,
    search_candidate_selection_to_acquisition_manifest,
    write_search_candidate_index,
)


def cmd_init(args: argparse.Namespace) -> None:
    root = init_workspace(args.workspace)
    print(f"Workspace initialized: {root}")


def cmd_analyze_file(args: argparse.Namespace) -> None:
    run_dir = analyze_file(mode=args.mode, input_path=args.input, source_name=args.source_name, source_type=args.source_type, output_root=args.output_root, source_url=args.source_url, title=args.title, published_at=args.published_at, issue_id=args.issue_id)
    print(f"Run directory: {run_dir}")
    print(f"Report: {run_dir / 'report.md'}")


def cmd_validate_run(args: argparse.Namespace) -> None:
    result = build_report_gates(args.run_dir, write=True)
    print(f"Validation passed: {result['passed']}")
    if result["blocking_failures"]:
        print("Blocking failures:")
        for failure in result["blocking_failures"]:
            print(f"- {failure}")
        raise SystemExit(2)
    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"- {warning}")


def cmd_report(args: argparse.Namespace) -> None:
    detail_mode = None if args.excluded_detail_mode == "default" else args.excluded_detail_mode
    report_path = write_report(args.run_dir, report_profile=args.profile, excluded_detail_mode=detail_mode)
    print(f"Report: {report_path}")


def cmd_list_review(args: argparse.Namespace) -> None:
    _manifest, _sources, _claims, reviews = load_run(Path(args.run_dir))
    if not reviews:
        print("No review items.")
        return
    for review in reviews:
        print(f"{review.get('review_id')} {review.get('claim_id')} [{review.get('risk_tier')}] {review.get('reason')}: {review.get('verification_question')}")


def cmd_bundle_run(args: argparse.Namespace) -> None:
    issue_dir = run_issue_bundle(
        bundle_file=args.bundle_file,
        output_root=args.output_root,
        report_profile=args.profile,
        excluded_detail_mode=args.excluded_detail_mode,
        allow_absolute_paths=args.allow_absolute_paths,
    )
    print(f"Issue bundle directory: {issue_dir}")
    print(f"Bundle manifest: {issue_dir / 'bundle_manifest.json'}")
    print(f"Bundle run index: {issue_dir / 'bundle_run_index.json'}")
    print(f"Bundle summary: {issue_dir / 'bundle_operator_summary.md'}")


def cmd_bundle_summary(args: argparse.Namespace) -> None:
    summary_path = write_bundle_summary(issue_dir=args.issue_dir)
    print(f"Bundle summary: {summary_path}")


def cmd_bundle_create(args: argparse.Namespace) -> None:
    bundle_path = create_bundle_from_folder(
        issue_id=args.issue_id,
        folder=args.folder,
        output_file=args.output_file,
        default_mode=args.default_mode,
        default_source_type=args.default_source_type,
        source_type_override_file=args.source_type_override_file,
        use_absolute_paths=args.use_absolute_paths,
    )
    print(f"Bundle file: {bundle_path}")


def cmd_bundle_checklist(args: argparse.Namespace) -> None:
    checklist_path = write_operator_checklist(output_path=args.output)
    print(f"Operator checklist: {checklist_path}")


def cmd_bundle_compare(args: argparse.Namespace) -> None:
    comparison_path = compare_issue_bundles(
        before_issue_dir=args.before_issue_dir,
        after_issue_dir=args.after_issue_dir,
        output_path=args.output,
    )
    print(f"Bundle comparison: {comparison_path}")


def cmd_bundle_verify(args: argparse.Namespace) -> None:
    packet_path = build_verification_packet(issue_dir=args.issue_dir, output_dir=args.output_dir)
    print(f"Verification packet: {packet_path}")
    print(f"Verification packet markdown: {packet_path.with_suffix('.md')}")


def cmd_bundle_helper_packet(args: argparse.Namespace) -> None:
    packet_path = build_helper_review_packet(
        issue_dir=args.issue_dir,
        output_dir=args.output_dir,
        verification_packet_path=args.verification_packet,
    )
    print(f"Helper review packet: {packet_path}")
    print(f"Helper review packet markdown: {packet_path.with_suffix('.md')}")


def cmd_bundle_import_helper_review(args: argparse.Namespace) -> None:
    review_path = import_helper_review(
        review_file=args.review_file,
        output_dir=args.output_dir,
        reviewer_name=args.reviewer_name,
        model_name=args.model_name,
    )
    print(f"Imported helper review: {review_path}")
    print(f"Imported helper review markdown: {review_path.with_suffix('.md')}")


def cmd_issue_package(args: argparse.Namespace) -> None:
    package_dir = build_operator_package_from_folder(
        folder=args.folder,
        issue_id=args.issue_id,
        output_root=args.output_root,
        default_mode=args.default_mode,
        default_source_type=args.default_source_type,
        source_type_override_file=args.source_type_override_file,
        compare_before_issue_dir=args.compare_before_issue_dir,
        excluded_detail_mode=args.excluded_detail_mode,
    )
    print(f"Operator package directory: {package_dir}")
    print(f"Final operator package: {package_dir / 'final_operator_package.md'}")


def cmd_analysis_package(args: argparse.Namespace) -> None:
    package_dir = build_analysis_package_from_manifest(
        source_manifest=args.source_manifest,
        output_root=args.output_root,
        compare_before_issue_dir=args.compare_before_issue_dir,
        excluded_detail_mode=args.excluded_detail_mode,
        allow_absolute=args.allow_absolute_source_paths,
    )
    print(f"Operator package directory: {package_dir}")
    print(f"Analysis source index: {Path(args.output_root) / 'analysis_source_index.md'}")
    print(f"Final operator package: {package_dir / 'final_operator_package.md'}")


def cmd_capture_source(args: argparse.Namespace) -> None:
    entry = capture_source(
        workspace=args.workspace,
        issue_id=args.issue_id,
        source_name=args.source_name,
        source_type=args.source_type,
        mode=args.mode,
        text=args.text,
        input_text_file=args.input_text_file,
        source_url=args.source_url,
        title=args.title,
        publisher=args.publisher,
        published_at=args.published_at,
        captured_at=args.captured_at,
        acquisition_method=args.acquisition_method,
        citation_note=args.citation_note,
    )
    print(f"Captured source file: {entry['file_path']}")
    print(f"Capture log: {Path(args.workspace).resolve() / 'capture_log.json'}")
    print(f"Capture source index: {Path(args.workspace).resolve() / 'capture_source_index.md'}")


def cmd_capture_manifest(args: argparse.Namespace) -> None:
    manifest_path = build_capture_manifest(workspace=args.workspace, output_path=args.output)
    print(f"Analysis source manifest: {manifest_path}")


def cmd_acquisition_validate(args: argparse.Namespace) -> None:
    manifest = load_acquisition_manifest(args.manifest, resolve_dns=args.resolve_dns)
    print(f"Acquisition manifest valid: {len(manifest['sources'])} source(s)")


def cmd_acquisition_fetch(args: argparse.Namespace) -> None:
    log_path = fetch_acquisition_manifest(
        manifest_file=args.manifest,
        output_root=args.output_root,
        timeout_seconds=args.timeout_seconds,
        byte_cap=args.byte_cap,
        html_extractor=args.html_extractor,
    )
    print(f"Acquisition log: {log_path}")
    print(f"Acquisition index: {Path(args.output_root).resolve() / ACQUISITION_INDEX_FILENAME}")


def cmd_acquisition_to_analysis_manifest(args: argparse.Namespace) -> None:
    manifest_path = acquisition_log_to_analysis_manifest(
        acquisition_log_file=args.acquisition_log,
        output_path=args.output,
        confirm_reviewed=args.confirm_reviewed,
    )
    print(f"Analysis source manifest: {manifest_path}")


def cmd_search_candidates_validate(args: argparse.Namespace) -> None:
    artifact = load_search_candidate_artifact(args.artifact)
    print(f"Search candidate artifact valid: {len(artifact['candidates'])} candidate(s)")
    print(f"Selection required before acquisition: {artifact['candidate_boundary']['operator_selection_required_before_acquisition']}")


def cmd_search_candidates_index(args: argparse.Namespace) -> None:
    artifact = load_search_candidate_artifact(args.artifact)
    index_path = write_search_candidate_index(candidate_artifact=artifact, output_path=args.output)
    print(f"Search candidate index: {index_path}")


def cmd_search_candidates_select(args: argparse.Namespace) -> None:
    manifest_path = search_candidate_selection_to_acquisition_manifest(
        candidate_artifact_file=args.artifact,
        selection_file=args.selection,
        output_path=args.output,
    )
    print(f"Acquisition manifest: {manifest_path}")



def cmd_validate_artifact(args: argparse.Namespace) -> None:
    if args.output:
        result_path = write_artifact_validation(schema_name=args.schema, artifact_file=args.file, output_path=args.output)
        result = json.loads(Path(result_path).read_text(encoding="utf-8"))
        print(f"Artifact validation: {result_path}")
    else:
        result = validate_artifact_file(schema_name=args.schema, artifact_file=args.file)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result.get("valid"):
        raise SystemExit(2)

def cmd_llm_review_packet(args: argparse.Namespace) -> None:
    packet_path = build_llm_review_packet(
        operator_package_dir=args.operator_package_dir,
        output_dir=args.output_dir,
    )
    print(f"LLM review packet: {packet_path}")
    print(f"LLM review packet markdown: {packet_path.with_suffix('.md')}")


def cmd_mock_llm_review(args: argparse.Namespace) -> None:
    review_path = run_mock_llm_review(packet_file=args.packet_file, output_dir=args.output_dir)
    print(f"Mock LLM review: {review_path}")
    print(f"Mock LLM review markdown: {review_path.with_suffix('.md')}")


def cmd_llm_review_adapter(args: argparse.Namespace) -> None:
    output_path = write_provider_review_template(
        packet_file=args.packet_file,
        output_dir=args.output_dir,
        provider=args.provider,
    )
    if args.provider == "mock":
        print(f"Mock LLM review: {output_path}")
        print(f"Mock LLM review markdown: {output_path.with_suffix('.md')}")
    else:
        print(f"Provider request template: {output_path}")
        print("External call performed: false")


def cmd_eval_goldset(args: argparse.Namespace) -> None:
    # Imported lazily so the rest of the CLI keeps working even before
    # source_manifest_kit/evaluation.py and its goldset fixture exist
    # (both are produced by a parallel in-flight change).
    from . import evaluation

    goldset_path = Path(args.goldset)
    output_dir = Path(args.output_dir) if args.output_dir else goldset_path.resolve().parent
    cases = evaluation.load_goldset(goldset_path)
    report = evaluation.evaluate_goldset(cases)
    paths = evaluation.write_evaluation_report(report, output_dir)
    print(f"Evaluation report: {paths['json']}")
    print(f"Evaluation report markdown: {paths['markdown']}")
    enforced = report.get("enforced", {})
    print(f"Enforced: {enforced.get('passing', 0)}/{enforced.get('total', 0)} passing")
    if args.enforce and enforced.get("failing", 0):
        print("Enforced gold cases failing:", file=sys.stderr)
        for entry in enforced.get("failing_cases", []):
            print(f"- {entry.get('case_id')}: {entry.get('reason')}", file=sys.stderr)
        raise SystemExit(2)


def cmd_llm_review_validate_response(args: argparse.Namespace) -> None:
    validation_path = validate_external_review_response(
        packet_file=args.packet_file,
        response_file=args.response_file,
        output_dir=args.output_dir,
    )
    print(f"External review response validation: {validation_path}")
    print("Validation passed: true")
    print("External call performed: false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Source Manifest Trust Kit v0 - local source-manifest evidence analysis, "
            "claim/risk labeling, operator-safe reporting, and finance-safety wording controls. "
            "Not financial advice."
        )
    )
    parser.add_argument("--debug", action="store_true", help="Show full tracebacks for CLI debugging")
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init", help="Initialize a local workspace")
    p_init.add_argument("--workspace", required=True)
    p_init.set_defaults(func=cmd_init)
    p_analyze = sub.add_parser("analyze-file", help="Analyze a local text or Markdown file")
    p_analyze.add_argument("--mode", choices=["general", "finance"], required=True)
    p_analyze.add_argument("--input", required=True)
    p_analyze.add_argument("--source-name", required=True)
    p_analyze.add_argument("--source-type", required=True)
    p_analyze.add_argument("--output-root", required=True)
    p_analyze.add_argument("--source-url")
    p_analyze.add_argument("--title")
    p_analyze.add_argument("--published-at")
    p_analyze.add_argument("--issue-id")
    p_analyze.set_defaults(func=cmd_analyze_file)
    p_validate = sub.add_parser("validate-run", help="Validate a run directory")
    p_validate.add_argument("--run-dir", required=True)
    p_validate.set_defaults(func=cmd_validate_run)
    p_report = sub.add_parser("report", help="Render a report from a validated run")
    p_report.add_argument("--run-dir", required=True)
    p_report.add_argument("--profile", choices=["minimal", "operator"], default="minimal", help="Report UX profile for controlled-use operators")
    p_report.add_argument("--excluded-detail-mode", choices=["default", "detailed"], default="default", help="Detail level for excluded finance placeholders")
    p_report.set_defaults(func=cmd_report)
    p_review = sub.add_parser("list-review", help="List review items for a run")
    p_review.add_argument("--run-dir", required=True)
    p_review.set_defaults(func=cmd_list_review)
    p_bundle_run = sub.add_parser("bundle-run", help="Run analyze/validate/report flow for a multi-source issue bundle JSON file")
    p_bundle_run.add_argument("--bundle-file", required=True)
    p_bundle_run.add_argument("--output-root", required=True)
    p_bundle_run.add_argument("--profile", choices=["minimal", "operator"], default="operator")
    p_bundle_run.add_argument("--excluded-detail-mode", choices=["default", "detailed"], default="default")
    p_bundle_run.add_argument(
        "--allow-absolute-paths",
        action="store_true",
        help="Allow absolute file_path values in a trusted local bundle. Do not use with untrusted bundle JSON.",
    )
    p_bundle_run.set_defaults(func=cmd_bundle_run)
    p_bundle_summary = sub.add_parser("bundle-summary", help="Rebuild consolidated operator summary for an issue bundle directory")
    p_bundle_summary.add_argument("--issue-dir", required=True)
    p_bundle_summary.set_defaults(func=cmd_bundle_summary)
    p_bundle_create = sub.add_parser("bundle-create", help="Create issue bundle JSON from a folder of .txt/.md files")
    p_bundle_create.add_argument("--folder", required=True)
    p_bundle_create.add_argument("--issue-id", required=True)
    p_bundle_create.add_argument("--output-file", required=True)
    p_bundle_create.add_argument("--default-mode", choices=["general", "finance"], default="general")
    p_bundle_create.add_argument("--default-source-type", default="news")
    p_bundle_create.add_argument("--source-type-override-file")
    p_bundle_create.add_argument(
        "--use-absolute-paths",
        action="store_true",
        help="Store absolute source paths in the generated bundle (trusted local use only; default is relative).",
    )
    p_bundle_create.set_defaults(func=cmd_bundle_create)
    p_bundle_checklist = sub.add_parser("bundle-checklist", help="Write operator review checklist markdown")
    p_bundle_checklist.add_argument("--output", required=True)
    p_bundle_checklist.set_defaults(func=cmd_bundle_checklist)
    p_bundle_compare = sub.add_parser("bundle-compare", help="Compare two issue bundle directories")
    p_bundle_compare.add_argument("--before-issue-dir", required=True)
    p_bundle_compare.add_argument("--after-issue-dir", required=True)
    p_bundle_compare.add_argument("--output", required=True)
    p_bundle_compare.set_defaults(func=cmd_bundle_compare)
    p_bundle_verify = sub.add_parser("bundle-verify", help="Generate deterministic verification request packet for an issue bundle")
    p_bundle_verify.add_argument("--issue-dir", required=True)
    p_bundle_verify.add_argument("--output-dir")
    p_bundle_verify.set_defaults(func=cmd_bundle_verify)
    p_helper_packet = sub.add_parser("bundle-helper-packet", help="Generate advisory-only helper review packet for an issue bundle")
    p_helper_packet.add_argument("--issue-dir", required=True)
    p_helper_packet.add_argument("--output-dir")
    p_helper_packet.add_argument("--verification-packet")
    p_helper_packet.set_defaults(func=cmd_bundle_helper_packet)
    p_import_review = sub.add_parser("bundle-import-helper-review", help="Import local helper review evidence as advisory-only material")
    p_import_review.add_argument("--review-file", required=True)
    p_import_review.add_argument("--output-dir", required=True)
    p_import_review.add_argument("--reviewer-name", default="helper")
    p_import_review.add_argument("--model-name", default="unknown")
    p_import_review.set_defaults(func=cmd_bundle_import_helper_review)
    p_issue_package = sub.add_parser("issue-package", help="Run local folder intake through final operator package generation")
    p_issue_package.add_argument("--folder", required=True)
    p_issue_package.add_argument("--issue-id", required=True)
    p_issue_package.add_argument("--output-root", required=True)
    p_issue_package.add_argument("--default-mode", choices=["general", "finance"], default="finance")
    p_issue_package.add_argument("--default-source-type", default="unknown")
    p_issue_package.add_argument("--source-type-override-file")
    p_issue_package.add_argument("--compare-before-issue-dir")
    p_issue_package.add_argument("--excluded-detail-mode", choices=["default", "detailed"], default="detailed")
    p_issue_package.set_defaults(func=cmd_issue_package)
    p_analysis_package = sub.add_parser("analysis-package", help="Run a local v0.7 analysis source manifest through final operator package generation")
    p_analysis_package.add_argument("--source-manifest", required=True, help="Local JSON manifest with issue_id and local source files")
    p_analysis_package.add_argument("--output-root", required=True)
    p_analysis_package.add_argument("--compare-before-issue-dir")
    p_analysis_package.add_argument("--excluded-detail-mode", choices=["default", "detailed"], default="detailed")
    p_analysis_package.add_argument(
        "--allow-absolute-source-paths",
        action="store_true",
        help="Allow absolute file_path values in the source manifest (trusted local use only; default rejects absolute paths).",
    )
    p_analysis_package.set_defaults(func=cmd_analysis_package)
    p_capture_source = sub.add_parser("capture-source", help="Capture operator-provided local text into a source file and capture log")
    p_capture_source.add_argument("--workspace", required=True)
    p_capture_source.add_argument("--issue-id", required=True)
    p_capture_source.add_argument("--source-name", required=True)
    p_capture_source.add_argument("--source-type", required=True)
    p_capture_source.add_argument("--mode", choices=["general", "finance"], required=True)
    capture_input = p_capture_source.add_mutually_exclusive_group(required=True)
    capture_input.add_argument("--input-text-file", help="Local .txt or .md file containing copied source text")
    capture_input.add_argument("--text", help="Inline copied source text")
    p_capture_source.add_argument("--source-url", help="Metadata only; never fetched by the runtime")
    p_capture_source.add_argument("--title")
    p_capture_source.add_argument("--publisher")
    p_capture_source.add_argument("--published-at")
    p_capture_source.add_argument("--captured-at")
    p_capture_source.add_argument("--acquisition-method")
    p_capture_source.add_argument("--citation-note")
    p_capture_source.set_defaults(func=cmd_capture_source)
    p_capture_manifest = sub.add_parser("capture-manifest", help="Build analysis_sources.json from a local capture log")
    p_capture_manifest.add_argument("--workspace", required=True)
    p_capture_manifest.add_argument("--output")
    p_capture_manifest.set_defaults(func=cmd_capture_manifest)
    p_acquisition_validate = sub.add_parser("acquisition-validate", help="Validate a direct-URL pre-runtime acquisition manifest")
    p_acquisition_validate.add_argument("--manifest", required=True)
    p_acquisition_validate.add_argument("--resolve-dns", action="store_true", help="Resolve hostnames during validation and block private/internal answers")
    p_acquisition_validate.set_defaults(func=cmd_acquisition_validate)
    p_acquisition_fetch = sub.add_parser("acquisition-fetch", help="Fetch operator-provided direct URLs into frozen pre-runtime artifacts")
    p_acquisition_fetch.add_argument("--manifest", required=True)
    p_acquisition_fetch.add_argument("--output-root", required=True)
    p_acquisition_fetch.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    p_acquisition_fetch.add_argument("--byte-cap", type=int, default=DEFAULT_BYTE_CAP)
    p_acquisition_fetch.add_argument("--html-extractor", choices=["builtin", "trafilatura", "readability"], default="builtin", help="HTML-to-text extractor. Optional extractors require the html extra.")
    p_acquisition_fetch.set_defaults(func=cmd_acquisition_fetch)
    p_acquisition_manifest = sub.add_parser("acquisition-to-analysis-manifest", help="Convert reviewed fetched acquisition records into analysis_sources.json")
    p_acquisition_manifest.add_argument("--acquisition-log", required=True)
    p_acquisition_manifest.add_argument("--output", required=True)
    p_acquisition_manifest.add_argument("--confirm-reviewed", action="store_true", help="Required operator review gate before downstream analysis manifest generation")
    p_acquisition_manifest.set_defaults(func=cmd_acquisition_to_analysis_manifest)
    p_candidate_validate = sub.add_parser("search-candidates-validate", help="Validate a frozen provider-neutral search candidate artifact")
    p_candidate_validate.add_argument("--artifact", required=True)
    p_candidate_validate.set_defaults(func=cmd_search_candidates_validate)
    p_candidate_index = sub.add_parser("search-candidates-index", help="Write operator-facing index for a frozen search candidate artifact")
    p_candidate_index.add_argument("--artifact", required=True)
    p_candidate_index.add_argument("--output", default=SEARCH_CANDIDATE_INDEX_FILENAME)
    p_candidate_index.set_defaults(func=cmd_search_candidates_index)
    p_candidate_select = sub.add_parser("search-candidates-select", help="Convert explicit selected search candidates into the existing direct URL acquisition manifest")
    p_candidate_select.add_argument("--artifact", required=True)
    p_candidate_select.add_argument("--selection", required=True)
    p_candidate_select.add_argument("--output", required=True)
    p_candidate_select.set_defaults(func=cmd_search_candidates_select)

    p_validate_artifact = sub.add_parser("validate-artifact", help="Validate a public JSON artifact against an optional JSON Schema")
    p_validate_artifact.add_argument("--schema", required=True, choices=available_schemas())
    p_validate_artifact.add_argument("--file", required=True)
    p_validate_artifact.add_argument("--output", help="Optional JSON validation result output path")
    p_validate_artifact.set_defaults(func=cmd_validate_artifact)
    p_llm_packet = sub.add_parser("llm-review-packet", help="Build an LLM-consumable advisory review packet from an operator package")
    p_llm_packet.add_argument("--operator-package-dir", required=True)
    p_llm_packet.add_argument("--output-dir")
    p_llm_packet.set_defaults(func=cmd_llm_review_packet)
    p_mock_review = sub.add_parser("mock-llm-review", help="Run deterministic no-API smoke review over an LLM review packet")
    p_mock_review.add_argument("--packet-file", required=True)
    p_mock_review.add_argument("--output-dir")
    p_mock_review.set_defaults(func=cmd_mock_llm_review)
    p_review_adapter = sub.add_parser("llm-review-adapter", help="Run mock review or write a provider-optional dry-run request template")
    p_review_adapter.add_argument("--packet-file", required=True)
    p_review_adapter.add_argument("--provider", choices=["mock", "openai-compatible"], default="mock")
    p_review_adapter.add_argument("--output-dir")
    p_review_adapter.set_defaults(func=cmd_llm_review_adapter)
    p_validate_review = sub.add_parser("llm-review-validate-response", help="Validate a no-key external review response against an LLM review packet")
    p_validate_review.add_argument("--packet-file", required=True)
    p_validate_review.add_argument("--response-file", required=True)
    p_validate_review.add_argument("--output-dir")
    p_validate_review.set_defaults(func=cmd_llm_review_validate_response)
    p_eval_goldset = sub.add_parser("eval-goldset", help="Run deterministic detectors against a gold set JSONL and write eval_report.json/.md")
    p_eval_goldset.add_argument("--goldset", required=True, help="Local gold set JSONL file")
    p_eval_goldset.add_argument("--output-dir", help="Defaults to the goldset file's parent directory")
    p_eval_goldset.add_argument(
        "--enforce",
        action="store_true",
        help="Exit nonzero if any enforced-status gold case fails",
    )
    p_eval_goldset.set_defaults(func=cmd_eval_goldset)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (AcquisitionError, AnalysisManifestError, ArtifactSchemaError, BundlePathError, FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        if getattr(args, "debug", False):
            raise
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
