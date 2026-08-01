from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis_package import (
    OPTIONAL_SOURCE_FIELDS,
    URL_LIKE_PATH,
    _normalize_mode,
    _normalize_source_type,
    _safe_markdown_inline,
    _safe_metadata,
    _safe_slug,
)
from .core.text_io import read_source_text
from .ledger.jsonl import write_json


CAPTURE_LOG_FILENAME = "capture_log.json"
CAPTURE_INDEX_FILENAME = "capture_source_index.md"
ANALYSIS_SOURCES_FILENAME = "analysis_sources.json"
LOCAL_CAPTURE_METHOD = "local_capture_helper"


class CaptureError(ValueError):
    """Raised when local capture helper input is invalid."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalized_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _safe_filename(source_name: str) -> str:
    return f"{_safe_slug(source_name)}.txt"


def _unique_capture_filename(*, issue_id: str, source_name: str, existing_entries: list[dict]) -> str:
    """Return a deterministic, collision-free filename for a captured source.

    Two different source_names can normalize to the same slug (e.g. "Source #1"
    and "Source@1" both -> "Source_1"). Without disambiguation the second
    capture would silently overwrite the first source's file while
    capture_log.json kept both entries pointing at the (now overwritten) file.
    This appends a deterministic "_2", "_3", ... suffix based on filenames
    already recorded for other source_names in this issue's capture_log.json.

    An exact-duplicate source_name (same issue_id, same name ignoring case)
    is rejected outright since it is ambiguous which capture it refers to.
    """
    slug = _safe_slug(source_name)
    base_filename = f"{slug}.txt"
    name_key = source_name.strip().casefold()
    used_filenames: set[str] = set()
    for entry in existing_entries:
        if str(entry.get("issue_id") or "").strip() != issue_id:
            continue
        entry_name_key = str(entry.get("source_name") or "").strip().casefold()
        if entry_name_key == name_key:
            raise CaptureError(
                f"Duplicate source_name '{source_name}' for issue_id '{issue_id}'. "
                "Use a distinct source_name for each captured source."
            )
        entry_filename = Path(str(entry.get("file_path") or "")).name
        if entry_filename:
            used_filenames.add(entry_filename)

    if base_filename not in used_filenames:
        return base_filename
    counter = 2
    while f"{slug}_{counter}.txt" in used_filenames:
        counter += 1
    return f"{slug}_{counter}.txt"


def _reject_url_like_text_input(text: str) -> None:
    stripped = text.strip()
    if URL_LIKE_PATH.match(stripped) and len(stripped) < 200:
        raise CaptureError(
            "Capture text looks like a URL. The local capture helper does not fetch URLs; "
            "provide copied source text instead."
        )


def _reject_url_like_path(path: str) -> None:
    if URL_LIKE_PATH.match(path.strip()):
        raise CaptureError(
            "input_text_file looks like a URL. The local capture helper does not fetch URLs; "
            "provide a local .txt or .md file."
        )


def _read_capture_log(workspace: Path) -> list[dict]:
    log_path = workspace / CAPTURE_LOG_FILENAME
    if not log_path.exists():
        return []
    data = json.loads(log_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise CaptureError(f"{CAPTURE_LOG_FILENAME} must contain a JSON list.")
    return data


def _write_capture_log(workspace: Path, entries: list[dict]) -> Path:
    log_path = workspace / CAPTURE_LOG_FILENAME
    write_json(log_path, entries)
    return log_path


def capture_source(
    *,
    workspace: str | Path,
    issue_id: str,
    source_name: str,
    source_type: str,
    mode: str,
    text: str | None = None,
    input_text_file: str | Path | None = None,
    source_url: str | None = None,
    title: str | None = None,
    publisher: str | None = None,
    published_at: str | None = None,
    captured_at: str | None = None,
    acquisition_method: str | None = None,
    citation_note: str | None = None,
) -> dict:
    if (text is None) == (input_text_file is None):
        raise CaptureError("Provide exactly one of text or input_text_file.")
    issue = str(issue_id or "").strip()
    if not issue:
        raise CaptureError("issue_id must be non-empty.")
    name = str(source_name or "").strip()
    if not name:
        raise CaptureError("source_name must be non-empty.")

    normalized_mode = _normalize_mode(mode, index=0)
    normalized_source_type = _normalize_source_type(source_type)
    workspace_path = Path(workspace).resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)

    if input_text_file is not None:
        raw_input = str(input_text_file)
        _reject_url_like_path(raw_input)
        source_path = Path(raw_input)
        if not source_path.is_file():
            raise CaptureError(f"input_text_file not found: {source_path}")
        try:
            raw_text = read_source_text(source_path, label="input_text_file")
        except ValueError as exc:
            # Keep this lane's own error type so callers catching CaptureError
            # continue to work; the message already names file, byte, and fix.
            raise CaptureError(str(exc)) from exc
    else:
        raw_text = str(text)

    if not raw_text.strip():
        raise CaptureError("Capture text must be non-empty.")
    _reject_url_like_text_input(raw_text)

    normalized = _normalized_text(raw_text)
    issue_slug = _safe_slug(issue)
    captured_dir = workspace_path / "captured_sources" / issue_slug
    captured_dir.mkdir(parents=True, exist_ok=True)

    existing_entries = _read_capture_log(workspace_path)
    filename = _unique_capture_filename(issue_id=issue, source_name=name, existing_entries=existing_entries)
    output_file = captured_dir / filename
    output_file.write_text(normalized, encoding="utf-8")

    safe_acquisition_method = _safe_metadata(acquisition_method or LOCAL_CAPTURE_METHOD, mode=normalized_mode)
    entry: dict[str, Any] = {
        "issue_id": issue,
        "source_name": name,
        "source_type": normalized_source_type,
        "mode": normalized_mode,
        "file_path": str(output_file),
        "captured_at": str(captured_at or _now_iso()),
        "acquisition_method": safe_acquisition_method,
        "source_url_is_metadata_only": True,
        "runtime_fetching": False,
        "content_hash_sha256": _sha256_text(normalized),
        "content_length_bytes": len(normalized.encode("utf-8")),
    }
    for key, value in {
        "source_url": source_url,
    }.items():
        if value is not None and str(value).strip():
            entry[key] = str(value).strip()
    for key, value in {
        "title": title,
        "publisher": publisher,
        "citation_note": citation_note,
    }.items():
        if value is not None and str(value).strip():
            entry[key] = _safe_metadata(value, mode=normalized_mode)
    if published_at is not None and str(published_at).strip():
        entry["published_at"] = _safe_metadata(published_at, mode=normalized_mode)

    existing_entries.append(entry)
    _write_capture_log(workspace_path, existing_entries)
    write_capture_source_index(workspace=workspace_path)
    return entry


def _manifest_relative_file_path(file_path: str, *, manifest_dir: Path) -> tuple[str, bool]:
    """Return (file_path, is_relative) for a captured file in an emitted manifest.

    The analysis-package loader rejects absolute file_path entries by default,
    so the manifest should reference captured files relative to the manifest's
    own directory whenever they sit underneath it (the normal workspace layout:
    manifest at the workspace root with captured_sources/ below). If the file
    is outside the manifest directory (or on a different drive) the relative
    form would start with "..", which downstream traversal guards reject, so
    the absolute path is kept and the entry is flagged with a warning.
    """
    try:
        relative = os.path.relpath(file_path, manifest_dir)
    except ValueError:
        # Different drive on Windows: no relative form exists.
        return file_path, False
    if relative == ".." or relative.startswith(".." + os.sep) or relative.startswith("../"):
        return file_path, False
    return relative.replace(os.sep, "/"), True


def build_capture_manifest(*, workspace: str | Path, output_path: str | Path | None = None) -> Path:
    workspace_path = Path(workspace).resolve()
    entries = _read_capture_log(workspace_path)
    if not entries:
        raise CaptureError(f"{CAPTURE_LOG_FILENAME} is missing or empty.")

    issue_ids = {str(entry.get("issue_id") or "").strip() for entry in entries}
    issue_ids.discard("")
    if len(issue_ids) != 1:
        raise CaptureError("capture_log.json must contain exactly one issue_id to build an analysis manifest.")
    issue_id = next(iter(issue_ids))

    path = Path(output_path) if output_path else workspace_path / ANALYSIS_SOURCES_FILENAME
    manifest_dir = path.resolve().parent

    sources: list[dict] = []
    for entry in sorted(entries, key=lambda item: (str(item.get("source_name") or "").lower(), str(item.get("file_path") or ""))):
        file_path, is_relative = _manifest_relative_file_path(str(entry["file_path"]), manifest_dir=manifest_dir)
        source = {
            "source_name": entry["source_name"],
            "source_type": entry["source_type"],
            "mode": entry["mode"],
            "file_path": file_path,
        }
        if not is_relative:
            source["warnings"] = ["absolute_path_requires_allow_absolute_flag"]
        for field in sorted(OPTIONAL_SOURCE_FIELDS):
            if entry.get(field):
                source[field] = entry[field]
        sources.append(source)

    manifest = {
        "issue_id": issue_id,
        "analysis_request": "Analyze locally captured source excerpts. Capture metadata is operator-supplied and not verified by the runtime.",
        "sources": sources,
    }
    write_json(path, manifest)
    return path


def write_capture_source_index(*, workspace: str | Path, output_path: str | Path | None = None) -> Path:
    workspace_path = Path(workspace).resolve()
    entries = _read_capture_log(workspace_path)
    path = Path(output_path) if output_path else workspace_path / CAPTURE_INDEX_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Capture Source Index",
        "",
        "- Boundary: local capture only. No URLs are fetched by this helper.",
        "- Source URLs are operator-supplied metadata only.",
        "- Capture metadata is not truth verification and does not upgrade any claim.",
        "",
        "## Captured Sources",
    ]
    if not entries:
        lines.append("- None")
    for index, entry in enumerate(sorted(entries, key=lambda item: str(item.get("source_name") or "").lower()), start=1):
        mode = entry.get("mode") or "general"
        lines.extend(
            [
                "",
                f"### {index}. {_safe_metadata(entry.get('source_name'), mode=mode)}",
                "",
                f"- Issue ID: {_safe_markdown_inline(entry.get('issue_id'))}",
                f"- Source type: {_safe_markdown_inline(entry.get('source_type'))}",
                f"- Mode: {_safe_markdown_inline(mode)}",
                f"- Local file: `{entry.get('file_path')}`",
                f"- Captured at: {_safe_markdown_inline(entry.get('captured_at'))}",
                f"- Acquisition method: {_safe_markdown_inline(entry.get('acquisition_method'))}",
                f"- Content SHA-256: `{entry.get('content_hash_sha256')}`",
                f"- Runtime fetching: {bool(entry.get('runtime_fetching'))}",
            ]
        )
        for label, field in [
            ("Title", "title"),
            ("Publisher", "publisher"),
            ("Published at", "published_at"),
            ("Citation note", "citation_note"),
        ]:
            if entry.get(field):
                lines.append(f"- {label}: {_safe_metadata(entry.get(field), mode=mode)}")
        if entry.get("source_url"):
            lines.append(f"- Source URL: {_safe_markdown_inline(entry.get('source_url'))} (metadata only; not fetched)")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
