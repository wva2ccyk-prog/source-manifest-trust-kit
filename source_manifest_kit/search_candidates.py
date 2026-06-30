from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .analysis_package import OPTIONAL_SOURCE_FIELDS, _normalize_source_type, _safe_markdown_inline, _safe_metadata
from .core.schema import MODES
from .ledger.jsonl import write_json


SEARCH_CANDIDATE_ARTIFACT_VERSION = "v0.8C"
SEARCH_CANDIDATE_INDEX_FILENAME = "search_candidate_index.md"
SEARCH_CANDIDATE_SELECTION_NOTE = (
    "Selected from a search candidate artifact after operator review. "
    "Candidate presence does not verify source truth."
)


class SearchCandidateError(ValueError):
    """Raised when search-candidate artifacts or selections are invalid."""


def _non_empty_text(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SearchCandidateError(f"{label} must be non-empty.")
    return text


def _validate_direct_url(value: Any, *, label: str) -> str:
    url = _non_empty_text(value, label=label)
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise SearchCandidateError(f"{label} must be a direct http(s) URL.")
    return url


def _normalize_warning_list(value: Any, *, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SearchCandidateError(f"{label} must be a list.")
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_mode(value: Any, *, label: str) -> str:
    mode = str(value or "").strip().lower()
    if mode not in MODES:
        raise SearchCandidateError(f"{label} must be one of: {', '.join(sorted(MODES))}.")
    return mode


def load_search_candidate_artifact(artifact_file: str | Path) -> dict:
    path = Path(artifact_file)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SearchCandidateError("Search candidate artifact must be a JSON object.")
    version = _non_empty_text(data.get("artifact_version"), label="artifact_version")
    if version != SEARCH_CANDIDATE_ARTIFACT_VERSION:
        raise SearchCandidateError(f"artifact_version must be {SEARCH_CANDIDATE_ARTIFACT_VERSION}.")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise SearchCandidateError("Search candidate artifact requires a non-empty candidates list.")

    normalized_candidates: list[dict] = []
    seen_ids: set[str] = set()
    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            raise SearchCandidateError(f"candidates[{index}] must be an object.")
        candidate_id = _non_empty_text(candidate.get("candidate_id"), label=f"candidates[{index}] candidate_id")
        id_key = candidate_id.casefold()
        if id_key in seen_ids:
            raise SearchCandidateError(f"candidates[{index}] duplicate candidate_id: {candidate_id}")
        seen_ids.add(id_key)
        normalized = {
            "candidate_id": candidate_id,
            "url": _validate_direct_url(candidate.get("url"), label=f"candidates[{index}] url"),
            "warnings": _normalize_warning_list(candidate.get("warnings"), label=f"candidates[{index}] warnings"),
        }
        for field in ("title", "snippet", "publisher", "published_at", "provider_result_id"):
            value = candidate.get(field)
            if value is not None and str(value).strip():
                normalized[field] = str(value).strip()
        normalized_candidates.append(normalized)

    artifact = {
        "artifact_version": version,
        "issue_id": _non_empty_text(data.get("issue_id"), label="issue_id"),
        "query": _non_empty_text(data.get("query"), label="query"),
        "provider": _non_empty_text(data.get("provider"), label="provider"),
        "generated_at": _non_empty_text(data.get("generated_at"), label="generated_at"),
        "candidate_boundary": {
            "lane": "pre_runtime_search_candidate_artifact",
            "candidate_only": True,
            "candidate_presence_is_verification": False,
            "operator_selection_required_before_acquisition": True,
            "analysis_runtime_searching": False,
        },
        "warnings": _normalize_warning_list(data.get("warnings"), label="warnings"),
        "candidates": normalized_candidates,
    }
    analysis_request = str(data.get("analysis_request") or "").strip()
    if analysis_request:
        artifact["analysis_request"] = analysis_request
    return artifact


def write_search_candidate_index(*, candidate_artifact: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Search Candidate Index",
        "",
        f"- Issue ID: {_safe_markdown_inline(candidate_artifact.get('issue_id'))}",
        f"- Query: {_safe_metadata(candidate_artifact.get('query'), mode='finance')}",
        f"- Provider: {_safe_markdown_inline(candidate_artifact.get('provider'))}",
        f"- Generated at: {_safe_markdown_inline(candidate_artifact.get('generated_at'))}",
        "- Status: CANDIDATES ONLY - NOT VERIFIED.",
        "- Selection gate: an operator must review and select candidates before direct URL acquisition.",
        "- Candidate presence is not verification, endorsement, truth adjudication, or finance advice.",
        "",
        "## Candidates",
    ]
    for index, candidate in enumerate(candidate_artifact.get("candidates") or [], start=1):
        lines.extend(
            [
                "",
                f"### {index}. {_safe_markdown_inline(candidate.get('candidate_id'))}",
                "",
                f"- URL: {_safe_markdown_inline(candidate.get('url'))}",
            ]
        )
        for label, field in [
            ("Title", "title"),
            ("Snippet", "snippet"),
            ("Publisher", "publisher"),
            ("Published at", "published_at"),
            ("Provider result ID", "provider_result_id"),
        ]:
            if candidate.get(field):
                lines.append(f"- {label}: {_safe_metadata(candidate.get(field), mode='finance')}")
        warnings = candidate.get("warnings") or []
        if warnings:
            lines.append(f"- Warnings: {', '.join(_safe_markdown_inline(warning) for warning in warnings)}")
    warnings = candidate_artifact.get("warnings") or []
    lines.extend(["", "## Artifact Warnings"])
    if warnings:
        lines.extend(f"- {_safe_markdown_inline(warning)}" for warning in warnings)
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Next Step",
            "",
            "- Create an explicit search-candidate selection JSON with candidate IDs, source metadata, and `confirm_reviewed: true`.",
            "- Convert only selected candidates into the existing direct URL acquisition manifest.",
            "- Search candidates do not bypass acquisition review or local analysis safety gates.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def load_search_candidate_selection(selection_file: str | Path) -> dict:
    path = Path(selection_file)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SearchCandidateError("Search candidate selection must be a JSON object.")
    if data.get("confirm_reviewed") is not True:
        raise SearchCandidateError("Search candidate selection requires confirm_reviewed: true.")
    selections = data.get("selected_candidates")
    if not isinstance(selections, list) or not selections:
        raise SearchCandidateError("Search candidate selection requires a non-empty selected_candidates list.")

    normalized_selections: list[dict] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, selection in enumerate(selections, start=1):
        if not isinstance(selection, dict):
            raise SearchCandidateError(f"selected_candidates[{index}] must be an object.")
        candidate_id = _non_empty_text(
            selection.get("candidate_id"),
            label=f"selected_candidates[{index}] candidate_id",
        )
        id_key = candidate_id.casefold()
        if id_key in seen_ids:
            raise SearchCandidateError(f"selected_candidates[{index}] duplicate candidate_id: {candidate_id}")
        seen_ids.add(id_key)
        source_name = _non_empty_text(
            selection.get("source_name"),
            label=f"selected_candidates[{index}] source_name",
        )
        name_key = source_name.casefold()
        if name_key in seen_names:
            raise SearchCandidateError(f"selected_candidates[{index}] duplicate source_name: {source_name}")
        seen_names.add(name_key)
        mode = _normalize_mode(selection.get("mode"), label=f"selected_candidates[{index}] mode")
        normalized = {
            "candidate_id": candidate_id,
            "source_name": source_name,
            "source_type": _normalize_source_type(
                _non_empty_text(
                    selection.get("source_type"),
                    label=f"selected_candidates[{index}] source_type",
                )
            ),
            "mode": mode,
        }
        for field in sorted(OPTIONAL_SOURCE_FIELDS - {"source_url", "captured_at", "acquisition_method"}):
            value = selection.get(field)
            if value is not None and str(value).strip():
                normalized[field] = _safe_metadata(value, mode=mode)
        normalized_selections.append(normalized)

    normalized = {
        "issue_id": _non_empty_text(data.get("issue_id"), label="issue_id"),
        "confirm_reviewed": True,
        "selected_candidates": normalized_selections,
    }
    analysis_request = str(data.get("analysis_request") or "").strip()
    if analysis_request:
        normalized["analysis_request"] = _safe_metadata(analysis_request, mode="finance")
    return normalized


def search_candidate_selection_to_acquisition_manifest(
    *,
    candidate_artifact_file: str | Path,
    selection_file: str | Path,
    output_path: str | Path,
) -> Path:
    artifact = load_search_candidate_artifact(candidate_artifact_file)
    selection = load_search_candidate_selection(selection_file)
    if artifact["issue_id"] != selection["issue_id"]:
        raise SearchCandidateError("Search candidate artifact and selection issue_id values must match.")

    candidates_by_id = {candidate["candidate_id"]: candidate for candidate in artifact["candidates"]}
    sources: list[dict] = []
    selected_ids: list[str] = []
    for index, selected in enumerate(selection["selected_candidates"], start=1):
        candidate = candidates_by_id.get(selected["candidate_id"])
        if candidate is None:
            raise SearchCandidateError(
                f"selected_candidates[{index}] candidate_id not found in candidate artifact: {selected['candidate_id']}"
            )
        source = {
            "source_name": selected["source_name"],
            "source_type": selected["source_type"],
            "mode": selected["mode"],
            "url": candidate["url"],
        }
        for field in sorted(OPTIONAL_SOURCE_FIELDS - {"source_url", "captured_at", "acquisition_method", "citation_note"}):
            value = selected.get(field) or candidate.get(field)
            if value:
                source[field] = _safe_metadata(value, mode=selected["mode"])
        citation_note = selected.get("citation_note")
        source["citation_note"] = (
            f"{citation_note} | {SEARCH_CANDIDATE_SELECTION_NOTE}"
            if citation_note
            else SEARCH_CANDIDATE_SELECTION_NOTE
        )
        sources.append(source)
        selected_ids.append(selected["candidate_id"])

    manifest = {
        "issue_id": selection["issue_id"],
        "analysis_request": selection.get("analysis_request")
        or artifact.get("analysis_request")
        or "Analyze operator-selected direct URL acquisition artifacts from search candidates without treating candidate presence as verification.",
        "search_candidate_handoff": {
            "candidate_artifact": str(Path(candidate_artifact_file).resolve()),
            "selection_file": str(Path(selection_file).resolve()),
            "query": _safe_metadata(artifact["query"], mode="finance"),
            "provider": _safe_markdown_inline(artifact["provider"]),
            "generated_at": _safe_markdown_inline(artifact["generated_at"]),
            "selected_candidate_ids": selected_ids,
            "candidate_presence_is_verification": False,
            "operator_selection_confirmed": True,
        },
        "sources": sources,
    }
    output = Path(output_path)
    write_json(output, manifest)
    return output
