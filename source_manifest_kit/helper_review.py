from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .bundle import _collect_bundle_records
from .core.risk_policy import escape_markdown_inline, sanitize_for_report
from .ledger.jsonl import write_json
from .verification import build_verification_packet, load_verification_packet


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _display_path(value: str | Path, *, base_dir: Path) -> str:
    path = Path(value)
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return f"<redacted-external-path>/{path.name or 'path'}"


def _review_claim_index(verification_packet: dict) -> list[dict]:
    return [
        {
            "packet_id": entry.get("packet_id"),
            "claim_text_safe": entry.get("claim_text_safe"),
            "claim_text_masked": entry.get("claim_text_masked") or entry.get("claim_text_safe"),
            "claim_category": entry.get("claim_category"),
            "source_name": entry.get("source_name"),
            "risk_tier": entry.get("risk_tier"),
        }
        for entry in verification_packet.get("packets", [])
        if isinstance(entry, dict)
    ]


def build_helper_review_packet(
    *,
    issue_dir: str | Path,
    output_dir: str | Path | None = None,
    verification_packet_path: str | Path | None = None,
) -> Path:
    issue_path = Path(issue_dir)
    manifest, run_index, _sources, claims, reviews = _collect_bundle_records(issue_path)
    out_dir = Path(output_dir) if output_dir else issue_path / "helper_review"
    out_dir.mkdir(parents=True, exist_ok=True)
    verification_path = (
        Path(verification_packet_path)
        if verification_packet_path
        else build_verification_packet(issue_dir=issue_path, output_dir=out_dir)
    )
    verification_packet = load_verification_packet(verification_path)
    packet = {
        "packet_id": "helper_packet_" + _hash_text(str(issue_path.resolve())),
        "issue_id": manifest.get("issue_id"),
        "advisory_only": True,
        "deterministic_core_is_final_authority": True,
        "helper_must_not_upgrade_claims": True,
        "source_count": manifest.get("source_count"),
        "run_count": len(run_index),
        "claim_count": len(claims),
        "review_item_count": len(reviews),
        "path_display_policy": "relative_to_helper_output_parent_or_redacted",
        "verification_packet_path": _display_path(verification_path, base_dir=out_dir.parent),
        "review_questions": [
            "Are any verification questions phrased as if an unverified claim is already true?",
            "Are any excluded finance claims leaking advice, target, allocation, probability, or expected-profit wording?",
            "Are source-family hints too broad or misleading for the evidence requested?",
            "Are rumor, social, private, or deleted-source claims clearly advisory-only?",
        ],
        "review_claim_index": _review_claim_index(verification_packet),
    }
    json_path = out_dir / "helper_review_packet.json"
    md_path = out_dir / "helper_review_packet.md"
    write_json(json_path, packet)
    md_path.write_text(render_helper_review_packet(packet), encoding="utf-8")
    return json_path


def render_helper_review_packet(packet: dict) -> str:
    lines = [
        "# Advisory Helper Review Packet",
        "",
        f"- Issue ID: {packet.get('issue_id')}",
        "- Advisory only: true",
        "- Deterministic core is final authority: true",
        "- Helper output cannot upgrade claims.",
        "",
        "## Review Questions",
    ]
    for question in packet.get("review_questions", []):
        lines.append(f"- {question}")
    lines.extend(
        [
            "",
            "## Best-Effort Sanitized Claim Index",
            "",
            "- Mask coverage is best-effort; if investment-action verbs, price targets, allocation, probability, or expected-profit wording appears here, do not paste it into an external helper.",
        ]
    )
    for entry in packet.get("review_claim_index", []) or packet.get("safe_claim_index", []):
        lines.append(
            f"- {entry.get('packet_id')}: {entry.get('claim_text_masked') or entry.get('claim_text_safe')} "
            f"(category: {entry.get('claim_category')}; risk: {entry.get('risk_tier')})"
        )
    lines.append("")
    return "\n".join(lines)


def import_helper_review(
    *,
    review_file: str | Path,
    output_dir: str | Path,
    reviewer_name: str = "helper",
    model_name: str = "unknown",
) -> Path:
    source_path = Path(review_file)
    raw_text = source_path.read_text(encoding="utf-8")
    parsed: dict | None = None
    if source_path.suffix.lower() == ".json":
        data = json.loads(raw_text)
        parsed = data if isinstance(data, dict) else {"items": data}
    review = {
        "review_id": "helper_review_" + _hash_text(raw_text),
        "reviewer_name": reviewer_name,
        "model_name": model_name,
        "source_file": str(source_path.resolve()),
        "source_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "advisory_only": True,
        "cannot_upgrade_claims": True,
        "deterministic_core_is_final_authority": True,
        "raw_text": raw_text if parsed is None else "",
        "parsed_json": parsed or {},
    }
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "imported_helper_review.json"
    md_path = out_dir / "imported_helper_review.md"
    write_json(json_path, review)
    md_path.write_text(render_imported_helper_review(review), encoding="utf-8")
    return json_path


def _escape_imported_review_markdown(raw_text: str) -> str:
    """Markdown-escape and finance-mask operator-supplied helper review text.

    Imported review text is untrusted (it comes from an external helper/LLM,
    not the deterministic core), so it must not be able to inject markdown
    structure or leak unsafe finance advice language into a generated report.

    ``escape_markdown_inline`` neutralizes ``[``, ``]``, backtick, ``<``, and
    ``>`` so injected links/code-spans/HTML tags (e.g. ``<script>``) render
    literally instead of being interpreted. It is applied BEFORE
    ``sanitize_for_report`` so the ``[blocked-...]``/``[excluded-...]`` tokens
    sanitize inserts stay unescaped and render as intended, while still
    masking finance advice/action language the same way every other rendered
    claim in this system is masked.

    Imported review text is embedded as its own standalone block rather than
    inline after a list marker, so a leading ``#`` at the start of a line
    would still be parsed as a markdown heading. Backslash-escape any
    line-leading ``#`` here as well, so an imported review cannot inject a
    fake heading (e.g. ``## Confirmed Facts``) that could be mistaken for
    system output.
    """
    escaped = escape_markdown_inline(raw_text)
    sanitized = sanitize_for_report(escaped, "finance")
    lines = sanitized.split("\n")
    neutralized = ["\\" + line if line.startswith("#") else line for line in lines]
    return "\n".join(neutralized)


def render_imported_helper_review(review: dict) -> str:
    lines = [
        "# Imported Advisory Helper Review",
        "",
        f"- Review ID: {review.get('review_id')}",
        f"- Reviewer: {review.get('reviewer_name')}",
        f"- Model: {review.get('model_name')}",
        "- Advisory only: true",
        "- Cannot upgrade claims: true",
        "- Deterministic core is final authority: true",
        "",
        "## Imported Content",
    ]
    if review.get("raw_text"):
        lines.append(
            "Rendered helper content is masked for operator display. "
            "The raw imported text remains in `imported_helper_review.json` for audit only."
        )
        lines.append("")
        lines.append(_escape_imported_review_markdown(review["raw_text"]))
    else:
        lines.append("Structured JSON review imported; see `imported_helper_review.json`.")
    lines.append("")
    return "\n".join(lines)
