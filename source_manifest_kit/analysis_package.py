from __future__ import annotations

import json
import os
import re
from pathlib import Path, PureWindowsPath
from typing import Any

from .bundle import compare_issue_bundles, run_issue_bundle, write_bundle_summary, write_operator_checklist
from .core.risk_policy import sanitize_for_report
from .core.schema import MODES, safe_source_type
from .helper_review import build_helper_review_packet
from .ledger.jsonl import write_json
from .operator_package import write_final_operator_package
from .verification import build_verification_packet


URL_LIKE_PATH = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//|^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
LOCAL_TEXT_SUFFIXES = {".txt", ".md"}
SOURCE_TYPE_ALIASES = {
    "commentary": "analyst",
    "exchange": "official",
    "finance_commentary": "analyst",
    "forum": "community",
    "regulator": "official",
}
OPTIONAL_SOURCE_FIELDS = {
    "source_url",
    "title",
    "publisher",
    "published_at",
    "captured_at",
    "acquisition_method",
    "citation_note",
}
REQUIRED_SOURCE_FIELDS = {"source_name", "source_type", "mode", "file_path"}


class AnalysisManifestError(ValueError):
    """Raised when a v0.7 analysis source manifest is invalid."""


def _safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    return cleaned or "issue"


def _normalize_source_type(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    raw = SOURCE_TYPE_ALIASES.get(raw, raw)
    return safe_source_type(raw)


def _normalize_mode(value: Any, *, index: int) -> str:
    mode = str(value or "").strip().lower()
    if mode not in MODES:
        raise AnalysisManifestError(f"sources[{index}] mode must be one of: {', '.join(sorted(MODES))}")
    return mode


def _reject_url_like_file_path(raw_path: str, *, index: int) -> None:
    if URL_LIKE_PATH.match(raw_path.strip()):
        raise AnalysisManifestError(
            f"sources[{index}] file_path looks like a URL. "
            "The runtime does not fetch URLs; provide a local .txt or .md file path."
        )


def _normalize_manifest_file_path(raw_path: str, *, index: int) -> str:
    """Return a platform-safe path string for manifest-local source files.

    JSON examples are often authored on Windows and use paths such as
    `.\\source.txt` or `subdir\\source.txt`. On POSIX these are not
    separators; they are literal filename characters. Normalize only
    drive-less relative manifest paths so that the same manifest keeps the
    same meaning on Windows, macOS, and Linux.
    """
    stripped = str(raw_path or "").strip()
    if not stripped:
        raise AnalysisManifestError(f"sources[{index}] file_path must be non-empty")
    _reject_url_like_file_path(stripped, index=index)

    windows_path = PureWindowsPath(stripped)
    has_windows_anchor = bool(windows_path.drive or windows_path.root.startswith('\\\\'))
    if has_windows_anchor and os.name != 'nt':
        raise AnalysisManifestError(
            f"sources[{index}] file_path uses a Windows absolute/UNC path that is not portable on this platform: {raw_path}"
        )
    if not has_windows_anchor and "\\" in stripped:
        return stripped.replace("\\", "/")
    return stripped


def _resolve_local_text_file(raw_path: str, *, base_dir: Path, index: int, allow_absolute: bool = False) -> Path:
    normalized_path = _normalize_manifest_file_path(raw_path, index=index)
    candidate = Path(normalized_path)
    is_relative = not candidate.is_absolute()
    if not is_relative and not allow_absolute:
        raise AnalysisManifestError(
            f"sources[{index}] file_path is an absolute path, which is rejected by default: {raw_path}. "
            "Use a file_path relative to the manifest directory, or explicitly opt in with "
            "--allow-absolute-source-paths (analysis-package CLI) / allow_absolute=True."
        )
    if is_relative:
        candidate = base_dir / candidate
    if candidate.is_symlink():
        raise AnalysisManifestError(f"sources[{index}] file_path must not be a symlink: {raw_path}")
    resolved = candidate.resolve()
    if is_relative:
        try:
            resolved.relative_to(base_dir)
        except ValueError as exc:
            raise AnalysisManifestError(f"sources[{index}] relative file_path must stay under manifest directory: {raw_path}") from exc
    if not resolved.is_file():
        raise AnalysisManifestError(f"sources[{index}] local file not found: {resolved}")
    if resolved.suffix.lower() not in LOCAL_TEXT_SUFFIXES:
        raise AnalysisManifestError(f"sources[{index}] file_path must point to a .txt or .md file: {resolved}")
    return resolved


def _safe_markdown_inline(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    for char in ("\\", "`", "[", "]", "(", ")"):
        text = text.replace(char, "\\" + char)
    return text


def _safe_metadata(value: Any, *, mode: str) -> str:
    sanitized = sanitize_for_report(str(value), "finance" if mode == "finance" else "general")
    return _safe_markdown_inline(sanitized)


def _display_path(value: str | Path | None, *, base_dir: Path) -> str:
    if not value:
        return "not generated"
    path = Path(value)
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return f"<redacted-external-path>/{path.name or 'path'}"


def load_analysis_source_manifest(manifest_file: str | Path, *, allow_absolute: bool = False) -> dict:
    manifest_path = Path(manifest_file)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AnalysisManifestError("Analysis source manifest must be a JSON object.")
    issue_id = str(data.get("issue_id") or "").strip()
    if not issue_id:
        raise AnalysisManifestError("Analysis source manifest requires a non-empty issue_id.")
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise AnalysisManifestError("Analysis source manifest requires a non-empty sources list.")

    base_dir = manifest_path.parent.resolve()
    normalized_sources: list[dict] = []
    seen_source_names: set[str] = set()
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            raise AnalysisManifestError(f"sources[{index}] must be an object.")
        missing = sorted(REQUIRED_SOURCE_FIELDS - set(source.keys()))
        if missing:
            raise AnalysisManifestError(f"sources[{index}] missing fields: {', '.join(missing)}")
        mode = _normalize_mode(source.get("mode"), index=index)
        file_path = _resolve_local_text_file(
            str(source.get("file_path") or ""), base_dir=base_dir, index=index, allow_absolute=allow_absolute
        )
        source_name = str(source.get("source_name") or "").strip() or f"source_{index:03d}"
        source_name_key = source_name.lower()
        if source_name_key in seen_source_names:
            raise AnalysisManifestError(f"sources[{index}] duplicate source_name: {source_name}")
        seen_source_names.add(source_name_key)
        normalized = {
            "source_name": source_name,
            "source_type": _normalize_source_type(source.get("source_type")),
            "mode": mode,
            "file_path": str(file_path),
        }
        for field in sorted(OPTIONAL_SOURCE_FIELDS):
            value = source.get(field)
            if value is not None and str(value).strip():
                normalized[field] = str(value)
        normalized_sources.append(normalized)

    normalized_manifest = {
        "issue_id": issue_id,
        "analysis_request": str(data.get("analysis_request") or "").strip() or None,
        # Boundary metadata is written so operators can confirm acquisition stayed outside the runtime.
        "acquisition_boundary": {
            "runtime_fetching": False,
            "runtime_url_fetching": False,
            "runtime_external_api_calls": False,
            "runtime_llm_calls": False,
            "source_url_is_metadata_only": True,
        },
        "sources": normalized_sources,
    }
    if not normalized_manifest["analysis_request"]:
        normalized_manifest.pop("analysis_request")
    return normalized_manifest


def write_analysis_source_index(*, normalized_manifest: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Analysis Source Index",
        "",
        f"- Issue ID: {normalized_manifest.get('issue_id')}",
        "- Runtime boundary: local files only; source URLs are stored as metadata and are not fetched.",
        "- Acquisition responsibility: the human/operator or orchestrator is responsible for collecting source excerpts before runtime analysis.",
    ]
    analysis_request = normalized_manifest.get("analysis_request")
    if analysis_request:
        lines.append(f"- Analysis request: {_safe_metadata(analysis_request, mode='finance')}")
    lines.extend(["", "## Sources"])
    for index, source in enumerate(normalized_manifest.get("sources") or [], start=1):
        mode = source.get("mode") or "general"
        lines.extend(
            [
                "",
                f"### {index}. {_safe_metadata(source.get('source_name'), mode=mode)}",
                "",
                f"- Source type: {source.get('source_type')}",
                f"- Mode: {mode}",
                f"- Local file: `{source.get('file_path')}`",
            ]
        )
        for label, field in [
            ("Title", "title"),
            ("Publisher", "publisher"),
            ("Published at", "published_at"),
            ("Captured at", "captured_at"),
            ("Acquisition method", "acquisition_method"),
            ("Citation note", "citation_note"),
        ]:
            if source.get(field):
                lines.append(f"- {label}: {_safe_metadata(source.get(field), mode=mode)}")
        if not source.get("citation_note") and source.get("source_type") in {"community", "social"}:
            lines.append("- Citation note guidance: add provenance and whether primary records were available for this community/social source.")
        if source.get("source_url"):
            lines.append(f"- Source URL: {_safe_markdown_inline(source.get('source_url'))} (metadata only; not fetched)")
    lines.extend(
        [
            "",
            "## Citation Note Guidance",
            "",
            "- Citation notes are operator-supplied provenance metadata only.",
            "- Citation notes are not verified by the runtime and do not upgrade any claim.",
            "- For community, social, private, deleted, or finance-related sources, note whether primary records were available in the local excerpt.",
            "- If a citation note references a URL, that URL is metadata only and is not fetched by the runtime.",
            "",
            "## Boundary Notice",
            "",
            "- This runtime does not search the web, fetch URLs, call external APIs, call LLMs, use MCP/connectors, or run automation.",
            "- The package summarizes only the local `.txt` and `.md` files listed above.",
            "- Source metadata can guide follow-up verification, but it does not verify or upgrade any claim.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _bundle_from_manifest(normalized_manifest: dict) -> dict:
    bundle_sources: list[dict] = []
    for source in normalized_manifest.get("sources") or []:
        entry = {
            "source_name": source["source_name"],
            "source_type": source["source_type"],
            "mode": source["mode"],
            "file_path": source["file_path"],
            "source_url": source.get("source_url"),
            "title": source.get("title"),
            "published_at": source.get("published_at"),
        }
        bundle_sources.append(entry)
    return {"issue_id": normalized_manifest["issue_id"], "sources": bundle_sources}


def build_analysis_package_from_manifest(
    *,
    source_manifest: str | Path,
    output_root: str | Path,
    compare_before_issue_dir: str | Path | None = None,
    excluded_detail_mode: str = "detailed",
    allow_absolute: bool = False,
) -> Path:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    normalized_manifest = load_analysis_source_manifest(source_manifest, allow_absolute=allow_absolute)
    issue_id = _safe_slug(normalized_manifest["issue_id"])

    manifest_path = root / "analysis_source_manifest.json"
    source_index_path = root / "analysis_source_index.md"
    bundle_path = root / f"{issue_id}_analysis_bundle.json"
    write_json(manifest_path, normalized_manifest)
    write_analysis_source_index(normalized_manifest=normalized_manifest, output_path=source_index_path)
    write_json(bundle_path, _bundle_from_manifest(normalized_manifest))

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
        analysis_source_manifest_path=manifest_path,
        analysis_source_index_path=source_index_path,
    )
    package_index = {
        "path_display_policy": "PACKAGE_INDEX.json contains local audit paths; PACKAGE_INDEX.md displays relative/redacted paths.",
        "analysis_source_manifest": str(manifest_path),
        "analysis_source_index": str(source_index_path),
        "analysis_bundle": str(bundle_path),
        "issue_dir": str(issue_dir),
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
                f"- Analysis source manifest: {_display_path(package_index['analysis_source_manifest'], base_dir=display_base)}",
                f"- Analysis source index: {_display_path(package_index['analysis_source_index'], base_dir=display_base)}",
                f"- Analysis bundle: {_display_path(package_index['analysis_bundle'], base_dir=display_base)}",
                f"- Issue directory: {_display_path(package_index['issue_dir'], base_dir=display_base)}",
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
    write_json(root / "analysis_package_outputs.json", package_index)
    return package_dir
