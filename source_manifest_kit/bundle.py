from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .core.report_gates import build_report_gates
from .core.reporting import write_report
from .core.risk_policy import escape_markdown_inline, has_manipulation_framing, sanitize_for_report
from .core.schema import safe_source_type
from .core.validation import load_run
from .ledger.jsonl import write_json
from .runs import analyze_file


LOCAL_TEXT_SUFFIXES = {".txt", ".md"}
URL_LIKE_PATH = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//|^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
WINDOWS_ABSOLUTE_OR_UNC_RE = re.compile(r"^[a-zA-Z]:[\\/]|^\\\\")


class BundlePathError(ValueError):
    """Raised when a bundle source path is outside the allowed local boundary."""


def _safe_issue_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    return cleaned or "issue"


def _normalize_social_variant(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"^\[[^\]]+\]\s+", "", normalized)
    normalized = re.sub(r"^(a|an|the)\s+(first|second|third|another)\s+(social\s+)?(account|post)\s+(says|claimed|claims|repeats|repeated)\s+that\s+", "", normalized)
    normalized = re.sub(r"^(a|an|the)\s+(social\s+)?(account|post)\s+(says|claimed|claims|repeats|repeated)\s+", "", normalized)
    normalized = re.sub(r"^(another|second|third)\s+account\s+(says|claimed|claims|repeats|repeated)\s+", "", normalized)
    normalized = re.sub(r"[\W_]+", " ", normalized).strip()
    tokens = [t for t in normalized.split() if t not in {"a", "an", "the", "that", "this", "so", "and"}]
    return " ".join(tokens[:24])


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_token(value: str | None, *, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return cleaned or fallback


def _normalize_bundle_relative_path(raw_path: str, *, index: int) -> Path:
    stripped = str(raw_path or "").strip()
    if not stripped:
        raise BundlePathError(f"sources[{index}] file_path must be non-empty.")
    if URL_LIKE_PATH.match(stripped):
        raise BundlePathError(f"sources[{index}] file_path must be a local .txt or .md path, not a URL.")
    if WINDOWS_ABSOLUTE_OR_UNC_RE.search(stripped):
        raise BundlePathError(f"sources[{index}] file_path must not be a Windows absolute or UNC path.")
    normalized = stripped.replace("\\", "/")
    relative = Path(normalized)
    if relative.is_absolute():
        raise BundlePathError(f"sources[{index}] file_path must be relative unless absolute paths are explicitly allowed.")
    if any(part == ".." for part in relative.parts):
        raise BundlePathError(f"sources[{index}] file_path must not contain path traversal.")
    return relative


def _resolve_bundle_source_path(
    raw_path: str,
    *,
    bundle_parent: Path,
    index: int,
    allow_absolute_paths: bool,
) -> Path:
    stripped = str(raw_path or "").strip()
    candidate = Path(stripped)
    if candidate.is_absolute():
        if not allow_absolute_paths:
            raise BundlePathError(f"sources[{index}] absolute file_path requires --allow-absolute-paths trusted mode.")
        local_candidate = candidate
    else:
        relative = _normalize_bundle_relative_path(stripped, index=index)
        local_candidate = bundle_parent / relative

    if local_candidate.is_symlink():
        raise BundlePathError(f"sources[{index}] file_path must not be a symlink.")
    resolved = local_candidate.resolve()
    if not candidate.is_absolute():
        try:
            resolved.relative_to(bundle_parent.resolve())
        except ValueError as exc:
            raise BundlePathError(f"sources[{index}] file_path escapes the bundle directory.") from exc
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    if resolved.suffix.lower() not in LOCAL_TEXT_SUFFIXES:
        raise BundlePathError(f"sources[{index}] file_path must point to a .txt or .md file: {resolved}")
    return resolved


def _excluded_placeholder(claim: dict) -> str:
    source = _safe_token(claim.get("bundle_source_name") or claim.get("source_name"), fallback="source")
    claim_id = _safe_token(claim.get("claim_id"), fallback="claim")
    return f"[excluded-unsafe-finance-claim] id={source}/{claim_id}"


def _claim_key(claim: dict) -> str:
    text = re.sub(r"\s+", " ", (claim.get("claim_text") or "").lower()).strip()
    if claim.get("source_type") in {"social", "community"}:
        text = _normalize_social_variant(text)
    return _hash_key(f"{claim.get('claim_type')}|{text}")


def _is_risky_unresolved(claim: dict) -> bool:
    if claim.get("claim_type") in {"excluded", "unverified_causality", "rumor", "unobservable", "needs_official_source"}:
        return True
    if claim.get("risk_tier") in {"high", "critical"}:
        return True
    return bool(claim.get("needs_human_review"))


def _safe_claim_text_for_output(claim: dict) -> str:
    """Single masking gate for every human-facing claim_text render.

    Excluded finance claims collapse to the placeholder; every other claim is
    escaped (markdown/HTML neutralized) then passed through sanitize_for_report
    using the run's mode. Mode is stamped on each claim in
    _collect_bundle_records; default to the safer "finance" when absent so a
    missing mode never leaks unmasked advice-like text.

    Escape the untrusted claim text FIRST, then sanitize the escaped text so the
    [blocked-...]/[excluded-...] tokens sanitize inserts remain unescaped.
    """
    if claim.get("claim_type") == "excluded":
        return _excluded_placeholder(claim)
    mode = str(claim.get("mode") or claim.get("source_mode") or "finance")
    return sanitize_for_report(escape_markdown_inline(claim.get("claim_text", "")), mode)


SOURCE_TYPE_ALIASES = {
    "finance_commentary": "analyst",
    "commentary": "analyst",
    "forum": "community",
    "mixed": "unknown",
}


FILENAME_SOURCE_HINTS: list[tuple[str, set[str]]] = [
    ("official", {"official", "exchange", "regulator", "agency", "ministry", "gov", "government"}),
    ("social", {"social", "tweet", "xpost", "x_post", "reddit"}),
    ("community", {"community", "forum", "board", "thread"}),
    ("news", {"news", "article", "wire", "headline", "press"}),
    # "finance" removed — a filename containing "finance" is not evidence of
    # analyst/interpretation material and was silently misrouting plain content.
    ("analyst", {"analyst", "commentary", "opinion", "research"}),
]


# Trust-elevating source types must never be assigned from a filename hint
# (fail-open trust inflation: e.g. `official_reddit_leak.txt` -> "official").
# Only the explicit sidecar override may assign these; a filename hint that
# resolves to one of them is ignored in favor of the operator default and a
# per-source warning is recorded.
TRUST_ELEVATING_SOURCE_TYPES = {"official", "company"}
FILENAME_TRUST_HINT_IGNORED_WARNING = "trusted_source_type_hint_ignored_use_override_file"


def _coerce_source_type(value: str | None, *, fallback: str = "unknown") -> str:
    if not value:
        return fallback
    normalized = value.strip().lower().replace("-", "_")
    normalized = SOURCE_TYPE_ALIASES.get(normalized, normalized)
    stype = safe_source_type(normalized)
    if stype == "unknown":
        return fallback
    return stype


def _infer_source_type_from_filename(path: Path) -> str | None:
    token_base = re.sub(r"[^a-z0-9]+", " ", path.stem.lower())
    tokens = [tok for tok in token_base.split() if tok]
    token_set = set(tokens)
    for source_type, hints in FILENAME_SOURCE_HINTS:
        if token_set.intersection(hints):
            return source_type
    return None


def _load_source_type_overrides(
    *,
    folder_path: Path,
    source_type_override_file: str | Path | None,
) -> dict[str, str]:
    if source_type_override_file:
        cfg_path = Path(source_type_override_file)
    else:
        cfg_path = folder_path / "source_type_overrides.json"
    if not cfg_path.exists():
        return {}
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    mapping: dict[str, str]
    if isinstance(data, dict) and "source_types" in data and isinstance(data["source_types"], dict):
        mapping = {str(k): str(v) for k, v in data["source_types"].items()}
    elif isinstance(data, dict):
        mapping = {str(k): str(v) for k, v in data.items()}
    else:
        raise ValueError(f"Source type override must be an object: {cfg_path}")
    resolved: dict[str, str] = {}
    for key, value in mapping.items():
        resolved[key.lower()] = _coerce_source_type(value, fallback="unknown")
    return resolved


def _bundle_stored_path(
    path: Path,
    *,
    bundle_parent: Path,
    use_absolute_paths: bool,
) -> str:
    """Return a relative-first stored path for a generated bundle source.

    Public bundles default to paths relative to the bundle file location so the
    generated manifest does not leak local absolute paths. Absolute paths are an
    explicit opt-in for trusted local debugging.
    """
    resolved = path.resolve()
    if use_absolute_paths:
        return str(resolved)
    try:
        relative = resolved.relative_to(bundle_parent)
        return relative.as_posix()
    except ValueError:
        return str(resolved)


def create_bundle_from_folder(
    *,
    issue_id: str,
    folder: str | Path,
    output_file: str | Path,
    default_mode: str = "general",
    default_source_type: str = "news",
    source_type_override_file: str | Path | None = None,
    use_absolute_paths: bool = False,
) -> Path:
    folder_path = Path(folder)
    if not folder_path.exists():
        raise FileNotFoundError(folder_path)
    overrides = _load_source_type_overrides(
        folder_path=folder_path,
        source_type_override_file=source_type_override_file,
    )
    output_path = Path(output_file)
    bundle_parent = output_path.parent.resolve()
    files = sorted(
        [p for p in folder_path.iterdir() if not p.is_symlink() and p.is_file() and p.suffix.lower() in LOCAL_TEXT_SUFFIXES],
        key=lambda p: p.name.lower(),
    )
    sources = []
    for path in files:
        source_name = path.stem
        override = overrides.get(path.name.lower()) or overrides.get(source_name.lower())
        warnings: list[str] = []
        # Explicit operator override is authoritative and MAY assign trusted types.
        resolved_source_type = _coerce_source_type(override, fallback="unknown") if override else "unknown"
        if resolved_source_type == "unknown":
            inferred = _coerce_source_type(_infer_source_type_from_filename(path), fallback="unknown")
            if inferred in TRUST_ELEVATING_SOURCE_TYPES:
                # Filename hints must not elevate trust. Ignore the hint, fall back
                # to the operator default, and record a per-source warning.
                warnings.append(FILENAME_TRUST_HINT_IGNORED_WARNING)
            elif inferred != "unknown":
                resolved_source_type = inferred
        if resolved_source_type == "unknown":
            resolved_source_type = _coerce_source_type(default_source_type, fallback="unknown")
        entry = {
            "source_name": source_name,
            "source_type": resolved_source_type,
            "mode": default_mode,
            "file_path": _bundle_stored_path(
                path,
                bundle_parent=bundle_parent,
                use_absolute_paths=use_absolute_paths,
            ),
        }
        if warnings:
            entry["warnings"] = warnings
        sources.append(entry)
    write_json(output_path, {"issue_id": issue_id, "sources": sources})
    return output_path


def write_operator_checklist(*, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Issue Bundle Operator Review Checklist",
                "",
                "## Before Trusting a Bundle Summary",
                "",
                "- Confirm every expected local source file is present in `bundle_manifest.json`.",
                "- Confirm every source has the intended `source_type` and `mode`.",
                "- Confirm `bundle_run_index.json` shows validation passed for each source.",
                "- Review `bundle_operator_summary.md` before using any claim downstream.",
                "",
                "## Meaning of Key Labels",
                "",
                "- Unsupported: the text contains a claim that needs primary or independent support.",
                "- Rumor: social/community or manipulation-style material that must not be treated as fact.",
                "- Excluded finance claim: finance advice, target, allocation, probability, or trade-outcome language blocked from report text.",
                "- Conflict: multiple sources produce divergent causal explanations or repeated claims without lineage.",
                "",
                "## Escalate to Human/Web Verification When",
                "",
                "- A claim affects financial, legal, medical, or operational decisions.",
                "- A claim is high or critical risk.",
                "- A source is private, deleted, inaccessible, or only repeated through social/community channels.",
                "- A bundle summary reports source divergence or cross-run repeated social/community claims.",
                "- A fact must be confirmed against an official or primary source.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def load_bundle(path: str | Path) -> dict:
    bundle_path = Path(path)
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Bundle file must be a JSON object.")
    issue_id = data.get("issue_id")
    sources = data.get("sources")
    if not isinstance(issue_id, str) or not issue_id.strip():
        raise ValueError("Bundle file requires non-empty issue_id.")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Bundle file requires non-empty sources list.")
    validated_sources = []
    required = {"source_name", "source_type", "mode", "file_path"}
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            raise ValueError(f"sources[{index}] must be an object.")
        missing = sorted(required - set(source.keys()))
        if missing:
            raise ValueError(f"sources[{index}] missing fields: {', '.join(missing)}")
        validated_sources.append(
            {
                "source_name": str(source["source_name"]),
                "source_type": str(source["source_type"]),
                "mode": str(source["mode"]),
                "file_path": str(source["file_path"]),
                "source_url": source.get("source_url"),
                "title": source.get("title"),
                "published_at": source.get("published_at"),
                # Preserve intake-time warnings (e.g. an ignored trusted filename
                # hint) so they reach bundle_manifest.json for operator review.
                "warnings": source.get("warnings") or [],
            }
        )
    return {"issue_id": issue_id, "sources": validated_sources, "_bundle_file": str(bundle_path.resolve())}


def run_issue_bundle(
    *,
    bundle_file: str | Path,
    output_root: str | Path,
    report_profile: str = "operator",
    excluded_detail_mode: str = "default",
    allow_absolute_paths: bool = False,
) -> Path:
    bundle = load_bundle(bundle_file)
    bundle_parent = Path(bundle["_bundle_file"]).parent
    issue_id = _safe_issue_id(bundle["issue_id"])
    issue_root = Path(output_root) / "issues" / issue_id
    issue_root.mkdir(parents=True, exist_ok=True)
    run_index: list[dict] = []
    for seq, source in enumerate(bundle["sources"], start=1):
        input_path = _resolve_bundle_source_path(
            str(source["file_path"]),
            bundle_parent=bundle_parent,
            index=seq,
            allow_absolute_paths=allow_absolute_paths,
        )
        run_dir = analyze_file(
            mode=source["mode"],
            input_path=input_path,
            source_name=source["source_name"],
            source_type=source["source_type"],
            output_root=Path(output_root),
            source_url=source.get("source_url"),
            title=source.get("title"),
            published_at=source.get("published_at"),
            issue_id=issue_id,
        )
        gates = build_report_gates(run_dir, write=True)
        if not gates.get("passed"):
            failures = "; ".join(gates.get("blocking_failures") or [])
            raise ValueError(f"Validation failed for source {source['source_name']}: {failures}")
        detail_mode = None if excluded_detail_mode == "default" else excluded_detail_mode
        write_report(run_dir, report_profile=report_profile, excluded_detail_mode=detail_mode)
        manifest, _sources, claims, reviews = load_run(run_dir)
        run_index.append(
            {
                "sequence": seq,
                "issue_id": issue_id,
                "mode": source["mode"],
                "source_name": source["source_name"],
                "source_type": source["source_type"],
                "file_path": str(input_path),
                "run_id": manifest.get("run_id"),
                "run_dir": str(run_dir),
                "claim_count": len(claims),
                "review_count": len(reviews),
                "validation_passed": True,
            }
        )
    bundle_manifest = {
        "issue_id": issue_id,
        "bundle_file": str(Path(bundle_file)),
        "source_count": len(bundle["sources"]),
        "report_profile": report_profile,
        "excluded_detail_mode": excluded_detail_mode,
        "sources": bundle["sources"],
    }
    write_json(issue_root / "bundle_manifest.json", bundle_manifest)
    write_json(issue_root / "bundle_run_index.json", {"issue_id": issue_id, "runs": run_index})
    summary_path = write_bundle_summary(issue_dir=issue_root)
    write_json(issue_root / "bundle_outputs.json", {"issue_id": issue_id, "summary_path": str(summary_path)})
    return issue_root


def _collect_bundle_records(issue_dir: Path) -> tuple[dict, list[dict], list[dict], list[dict], list[dict]]:
    manifest = json.loads((issue_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
    run_index = json.loads((issue_dir / "bundle_run_index.json").read_text(encoding="utf-8")).get("runs", [])
    all_claims: list[dict] = []
    all_reviews: list[dict] = []
    all_sources: list[dict] = []
    for row in run_index:
        run_dir = Path(row["run_dir"])
        _run_manifest, sources, claims, reviews = load_run(run_dir)
        run_mode = _run_manifest.get("mode") or row.get("mode") or "finance"
        for source in sources:
            source["bundle_issue_id"] = manifest["issue_id"]
        for claim in claims:
            claim["bundle_issue_id"] = manifest["issue_id"]
            claim["bundle_run_id"] = row["run_id"]
            claim["bundle_source_name"] = row["source_name"]
            claim["source_mode"] = row.get("mode")
            claim["mode"] = run_mode
        for review in reviews:
            review["bundle_issue_id"] = manifest["issue_id"]
            review["bundle_run_id"] = row["run_id"]
            review["bundle_source_name"] = row["source_name"]
        all_sources.extend(sources)
        all_claims.extend(claims)
        all_reviews.extend(reviews)
    return manifest, run_index, all_sources, all_claims, all_reviews


def _cross_run_social_duplicates(claims: list[dict]) -> list[dict]:
    """Cross-source repetition / laundering detector.

    FIX 2: repetition is grouped across ALL source types, not only
    community/social. The textbook laundering case is an identical claim shared
    between a NEWS source and a community repost; keying only on
    community/social missed it entirely. The community/social grouping is
    preserved as a subset. This only adds warnings/flags — it never promotes a
    claim into a higher-trust bucket.
    """
    grouped: dict[str, list[dict]] = {}
    for claim in claims:
        if claim.get("claim_type") == "excluded":
            continue
        # _normalize_social_variant strips social/community repost prefixes so a
        # verbatim claim shared between a news source and a community repost still
        # collapses to the same key; on non-prefixed text it is plain normalization.
        key_text = _normalize_social_variant(claim.get("claim_text", ""))
        if not key_text:
            continue
        grouped.setdefault(_hash_key(key_text), []).append(claim)
    notes: list[dict] = []
    group_index = 1
    for _, bucket in sorted(grouped.items(), key=lambda item: item[0]):
        sources = sorted({claim.get("bundle_source_name") for claim in bucket})
        # Laundering requires the same text across MORE THAN ONE source; identical
        # text repeated within a single source is not cross-source corroboration.
        if len(bucket) <= 1 or len(sources) <= 1:
            continue
        group_id = f"bundle_dup_{group_index:03d}"
        group_index += 1
        run_ids = sorted({claim.get("bundle_run_id") for claim in bucket})
        note = {
            "group_id": group_id,
            "claim_count": len(bucket),
            "run_count": len(run_ids),
            "source_count": len(sources),
            "runs": run_ids,
            "sources": sources,
            "example_claim": _safe_claim_text_for_output(bucket[0]),
        }
        notes.append(note)
        for claim in bucket:
            claim["bundle_duplicate_group_id"] = group_id
            flags = list(claim.get("risk_flags") or [])
            for flag in ("bundle_repetition_without_lineage", "bundle_source_laundering_risk"):
                if flag not in flags:
                    flags.append(flag)
            claim["risk_flags"] = flags
    return notes


def _source_divergence_notes(claims: list[dict]) -> list[str]:
    notes: list[str] = []
    causal = [c for c in claims if c.get("claim_type") == "unverified_causality"]
    if len(causal) > 1:
        snippets = sorted({_safe_claim_text_for_output(c)[:120] for c in causal if c.get("claim_text")})
        if len(snippets) > 1:
            notes.append(f"Causal explanations diverge across sources ({len(snippets)} variants).")
    for conflict in _numeric_divergence_notes(claims):
        notes.append(
            "Numeric divergence requires review: "
            f"{conflict['variant_count']} reported values for {conflict['metric']} "
            f"({', '.join(conflict['values'])}) across sources ({', '.join(conflict['sources'])})."
        )
    return notes


def _is_english_casualty_claim(text: str) -> bool:
    lower = text.lower()
    if re.search(r"\bworkers?\s+(?:were\s+)?affected\b", lower):
        return True
    return any(token in lower for token in ("injured", "treated", "casualty", "casualties", "people"))


# Korean money/number units in ascending magnitude. 조=10^12, 억=10^8, 만=10^4, 천=10^3.
_KO_UNIT_VALUES = {"조": 10 ** 12, "억": 10 ** 8, "만": 10 ** 4, "천": 10 ** 3}
# A Korean amount: one or more <digits><unit> segments (optionally trailing 원), or a
# plain <digits>원 amount (e.g. "12조 3,000억원", "18조원", "5,000원").
_KO_AMOUNT_RE = re.compile(r"(?:\d[\d,]*\s*[조억만천]\s*)+원?|\d[\d,]*\s*원")
_KO_PARTICLE_RE = re.compile(r"(?:은|는|이|가|을|를|의|에서|에|으로|로|와|과|도|만|고|며|라고|이라고)$")
# Copulas / high-frequency verbs that carry no metric identity.
_KO_CONTEXT_STOPWORDS = {"이다", "한다", "했다", "있다", "됐다", "라고", "밝혔", "집계", "달했", "기록"}
_EN_CONTEXT_STOPWORDS = {"the", "and", "was", "were", "are", "that", "with", "for", "from", "reported", "said", "told", "after", "about", "this"}


def _parse_korean_amount(expr: str) -> int | None:
    total = 0
    found = False
    for num, unit in re.findall(r"(\d[\d,]*)\s*([조억만천])", expr):
        total += int(num.replace(",", "")) * _KO_UNIT_VALUES[unit]
        found = True
    if found:
        return total
    plain = re.search(r"(\d[\d,]*)", expr)
    if plain:
        return int(plain.group(1).replace(",", ""))
    return None


def _primary_numeric_amount(text: str) -> tuple[str, int] | None:
    """Return (display, magnitude) for the first parseable numeric amount, or None.

    Supports Korean 조/억/만/천/원 formats and comma thousands first, then plain
    numbers and percentages, so the metric-divergence check is language-agnostic.
    """
    ko = _KO_AMOUNT_RE.search(text)
    if ko:
        magnitude = _parse_korean_amount(ko.group(0))
        if magnitude is not None:
            return re.sub(r"\s+", " ", ko.group(0).strip()), magnitude
    pct = re.search(r"\d+(?:\.\d+)?\s*(?:%|percent|퍼센트|프로)", text)
    if pct:
        num = re.search(r"\d+(?:\.\d+)?", pct.group(0))
        if num:
            return re.sub(r"\s+", " ", pct.group(0).strip()), int(float(num.group(0)) * 100)
    num = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if num:
        raw = num.group(0).replace(",", "")
        return num.group(0), int(float(raw))
    return None


def _numeric_context_key(text: str) -> str:
    """Deterministic metric-label key from the non-numeric context tokens.

    Conservative by design: two sources only group when their surrounding content
    tokens match exactly (after stripping amounts and common particles), so
    unrelated figures (revenue vs share price) never collapse together.
    """
    residual = _KO_AMOUNT_RE.sub(" ", text)
    residual = re.sub(r"\d[\d,]*(?:\.\d+)?\s*(?:%|percent|퍼센트|프로|명|원)?", " ", residual)
    tokens: set[str] = set()
    for raw in re.findall(r"[가-힣]{2,}", residual):
        stripped = _KO_PARTICLE_RE.sub("", raw)
        if len(stripped) >= 2 and stripped not in _KO_CONTEXT_STOPWORDS:
            tokens.add(stripped)
    for word in re.findall(r"[a-z]{3,}", residual.lower()):
        if word not in _EN_CONTEXT_STOPWORDS:
            tokens.add(word)
    if len(tokens) < 2:
        return ""
    return "|".join(sorted(tokens))


def _english_casualty_divergence(claims: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for claim in claims:
        if claim.get("claim_type") == "excluded":
            continue
        text = claim.get("claim_text") or ""
        if not _is_english_casualty_claim(text):
            continue
        lower = text.lower()
        values = re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b", text)
        if not values:
            continue
        context_match = re.search(r"\b(?:after|by)\s+(?:the\s+)?([a-z0-9][a-z0-9\s-]{0,80})", lower)
        context = ""
        if context_match:
            context = re.split(r"[.;,:]", context_match.group(1), maxsplit=1)[0]
            context = re.sub(r"\s+", " ", context).strip()
        group_key = f"reported_people_count|{context or 'unscoped'}"
        grouped.setdefault(group_key, []).append(
            {
                "claim_id": claim.get("claim_id"),
                "source": claim.get("bundle_source_name") or claim.get("source_name"),
                "value": values[0].replace(",", ""),
                "claim_text": _safe_claim_text_for_output(claim)[:160],
            }
        )
    notes: list[dict] = []
    for group_key, items in sorted(grouped.items()):
        values = sorted({item["value"] for item in items})
        sources = sorted({item["source"] for item in items if item.get("source")})
        if len(values) <= 1 or len(sources) <= 1:
            continue
        notes.append(
            {
                "metric": group_key.split("|", maxsplit=1)[0],
                "variant_count": len(values),
                "values": values,
                "sources": sources,
                "items": items,
            }
        )
    return notes


def _generic_numeric_divergence(claims: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for claim in claims:
        if claim.get("claim_type") == "excluded":
            continue
        text = claim.get("claim_text") or ""
        # The English casualty path (above) already owns these claims; skip them
        # here so a casualty conflict is never double-counted.
        if _is_english_casualty_claim(text):
            continue
        amount = _primary_numeric_amount(text)
        if amount is None:
            continue
        context = _numeric_context_key(text)
        if not context:
            continue
        display, magnitude = amount
        grouped.setdefault(context, []).append(
            {
                "claim_id": claim.get("claim_id"),
                "source": claim.get("bundle_source_name") or claim.get("source_name"),
                "value": display,
                "magnitude": magnitude,
                "claim_text": _safe_claim_text_for_output(claim)[:160],
            }
        )
    notes: list[dict] = []
    for _context, items in sorted(grouped.items()):
        magnitudes = {item["magnitude"] for item in items}
        sources = sorted({item["source"] for item in items if item.get("source")})
        if len(magnitudes) <= 1 or len(sources) <= 1:
            continue
        values = sorted({item["value"] for item in items})
        notes.append(
            {
                "metric": "reported_numeric_value",
                "variant_count": len(values),
                "values": values,
                "sources": sources,
                "items": items,
            }
        )
    return notes


def _numeric_divergence_notes(claims: list[dict]) -> list[dict]:
    # English casualty path first (owns people-count claims), then the
    # language-agnostic generic path for everything else (Korean 조/억원 figures,
    # plain numbers, percentages).
    return _english_casualty_divergence(claims) + _generic_numeric_divergence(claims)


def _sources_with_excluded_claims(claims: list[dict]) -> set[str]:
    return {
        c.get("bundle_source_name") or c.get("source_name")
        for c in claims
        if c.get("claim_type") == "excluded" and (c.get("bundle_source_name") or c.get("source_name"))
    }


def _format_claim_for_summary(claim: dict, *, excluded_sources: set[str]) -> str:
    source = claim.get("bundle_source_name")
    text = _safe_claim_text_for_output(claim)
    caution = ""
    if source in excluded_sources and claim.get("claim_type") != "excluded":
        caution = (
            " Operator caution: this source also contains excluded finance material; "
            "do not treat adjacent interpretation as advice or verified fact."
        )
    return f"- {text} (source: {source}; type: {claim.get('claim_type')}; risk: {claim.get('risk_tier')}){caution}"


def _group_review_items(reviews: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str, str], dict] = {}
    for review in reviews:
        key = (
            str(review.get("bundle_source_name") or ""),
            str(review.get("risk_tier") or ""),
            str(review.get("reason") or ""),
            str(review.get("verification_question") or ""),
        )
        if key not in grouped:
            grouped[key] = {
                "bundle_source_name": review.get("bundle_source_name"),
                "risk_tier": review.get("risk_tier"),
                "reason": review.get("reason"),
                "verification_question": review.get("verification_question"),
                "claim_ids": [],
            }
        claim_id = review.get("claim_id")
        if claim_id and claim_id not in grouped[key]["claim_ids"]:
            grouped[key]["claim_ids"].append(claim_id)
    return list(grouped.values())


def _numeric_divergence_review_items(numeric_conflicts: list[dict]) -> list[dict]:
    items: list[dict] = []
    for conflict in numeric_conflicts:
        values = ", ".join(conflict.get("values") or [])
        sources = ", ".join(conflict.get("sources") or [])
        metric = str(conflict.get("metric") or "reported_numeric_value")
        items.append(
            {
                "bundle_source_name": "source_divergence",
                "risk_tier": "medium",
                "reason": "numeric divergence",
                "verification_question": (
                    f"Which primary or official record explains the {metric} divergence "
                    f"across values ({values}) and sources ({sources})?"
                ),
                "claim_ids": [f"numeric:{metric}"],
            }
        )
    return items


def _render_grouped_review_questions(lines: list[str], review_items: list[dict]) -> None:
    if not review_items:
        lines.append("- None")
        return
    severity_order = ["critical", "high", "medium", "low", "unknown"]
    for tier in severity_order:
        tier_items = [r for r in review_items if (r.get("risk_tier") or "unknown") == tier]
        if not tier_items:
            continue
        lines.append(f"### {tier.capitalize()} Priority")
        for review in tier_items:
            claim_ids = ", ".join(review.get("claim_ids") or [])
            lines.append(
                f"- {claim_ids} ({review.get('bundle_source_name')}): "
                f"{review.get('verification_question')} (reason: {review.get('reason')})"
            )


def write_bundle_summary(*, issue_dir: str | Path) -> Path:
    issue_path = Path(issue_dir)
    manifest, run_index, _sources, claims, reviews = _collect_bundle_records(issue_path)
    duplicate_notes = _cross_run_social_duplicates(claims)
    def is_rumor_social_claim(claim: dict) -> bool:
        if claim.get("claim_type") in {"rumor", "unobservable"}:
            return True
        if claim.get("source_type") in {"social", "community"}:
            return True
        return has_manipulation_framing(claim.get("claim_text", ""))

    low_risk = [
        c
        for c in claims
        if c.get("risk_tier") == "low"
        and c.get("claim_type") in {"confirmed_fact", "official_reported_status", "market_observation", "reported_claim"}
        and not is_rumor_social_claim(c)
    ]
    weak_or_unsupported = [
        c
        for c in claims
        if c.get("claim_type") in {"unverified_causality", "needs_official_source", "interpretation", "opinion_or_frame"}
        and not is_rumor_social_claim(c)
    ]
    rumor_social = [c for c in claims if c.get("claim_type") != "excluded" and is_rumor_social_claim(c)]
    excluded_finance = [c for c in claims if c.get("claim_type") == "excluded"]
    # FIX 3: catch every non-excluded, non-rumor claim that did not land in the
    # low-risk or weak buckets (e.g. a reported_claim forced to risk_tier "medium"
    # by needs_official_confirmation) so it is never silently omitted from the
    # summary while present in every other artifact.
    def _identity(c: dict) -> tuple:
        return (c.get("bundle_run_id"), c.get("bundle_source_name"), c.get("claim_id"))

    categorized_ids = {_identity(c) for c in low_risk + weak_or_unsupported + rumor_social + excluded_finance}
    other_reported = [c for c in claims if _identity(c) not in categorized_ids]
    excluded_sources = _sources_with_excluded_claims(claims)
    divergence_notes = _source_divergence_notes(claims)
    numeric_conflicts = _numeric_divergence_notes(claims)
    lines: list[str] = [
        "# Issue Bundle Operator Summary",
        "",
        f"- Issue ID: {manifest.get('issue_id')}",
        f"- Source count: {manifest.get('source_count')}",
        f"- Run count: {len(run_index)}",
        "",
        "## Low-Risk Reported Material (deterministic classification only)",
    ]
    if not low_risk:
        lines.append("- None")
    else:
        for claim in low_risk:
            lines.append(_format_claim_for_summary(claim, excluded_sources=excluded_sources))
    lines.extend(["", "## Unsupported or Weakly Supported Claims"])
    if not weak_or_unsupported:
        lines.append("- None")
    else:
        for claim in weak_or_unsupported:
            lines.append(_format_claim_for_summary(claim, excluded_sources=excluded_sources))
    lines.extend(["", "## Other Reported Claims Needing Review"])
    if not other_reported:
        lines.append("- None")
    else:
        for claim in other_reported:
            lines.append(_format_claim_for_summary(claim, excluded_sources=excluded_sources))
    lines.extend(["", "## Rumor / Social / Manipulation-Framing Claims"])
    if not rumor_social:
        lines.append("- None")
    else:
        for claim in rumor_social:
            lines.append(f"- {_safe_claim_text_for_output(claim)} (source: {claim.get('bundle_source_name')}; type: {claim.get('claim_type')}; risk: {claim.get('risk_tier')})")
    lines.extend(["", "## Excluded Finance Claims Summary"])
    if not excluded_finance:
        lines.append("- None")
    else:
        for claim in excluded_finance:
            lines.append(
                f"- {_excluded_placeholder(claim)} "
                f"(source: {claim.get('bundle_source_name')}; claim_id: {claim.get('claim_id')}; risk: {claim.get('risk_tier')}; flags: {', '.join(claim.get('risk_flags') or []) or 'none'})"
            )
    lines.extend(["", "## Source Conflict or Divergence Notes"])
    if not divergence_notes and not duplicate_notes:
        lines.append("- None")
    else:
        for note in divergence_notes:
            lines.append(f"- {note}")
        for note in duplicate_notes:
            lines.append(
                f"- Cross-source repeated claim group {note['group_id']}: "
                f"identical/near-identical text repeated across {note['source_count']} sources "
                f"({', '.join(note['sources'])}); repetition is not independent corroboration."
            )
    lines.extend(["", "## Follow-Up Verification Questions"])
    grouped_reviews = _group_review_items(reviews)
    numeric_reviews = _numeric_divergence_review_items(numeric_conflicts)
    _render_grouped_review_questions(lines, grouped_reviews + numeric_reviews)
    lines.append("")
    summary_path = issue_path / "bundle_operator_summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    write_json(
        issue_path / "bundle_cross_run_duplicates.json",
        {"issue_id": manifest.get("issue_id"), "groups": duplicate_notes},
    )
    write_json(
        issue_path / "bundle_numeric_conflicts.json",
        {"issue_id": manifest.get("issue_id"), "conflicts": numeric_conflicts},
    )
    return summary_path


def _claim_map_for_issue(issue_dir: str | Path) -> dict[str, dict]:
    issue_path = Path(issue_dir)
    _manifest, _run_index, _sources, claims, _reviews = _collect_bundle_records(issue_path)
    _cross_run_social_duplicates(claims)
    result: dict[str, dict] = {}
    for claim in claims:
        key = _claim_key(claim)
        if key not in result:
            result[key] = {
                "key": key,
                "claim_text": _safe_claim_text_for_output(claim),
                "claim_type": claim.get("claim_type"),
                "risk_tier": claim.get("risk_tier"),
                "source_type": claim.get("source_type"),
                "sources": sorted({claim.get("bundle_source_name")}),
                "risky_unresolved": _is_risky_unresolved(claim),
            }
        else:
            existing = result[key]
            existing["sources"] = sorted(set(existing["sources"]) | {claim.get("bundle_source_name")})
            existing["risky_unresolved"] = existing["risky_unresolved"] or _is_risky_unresolved(claim)
    return result


def compare_issue_bundles(*, before_issue_dir: str | Path, after_issue_dir: str | Path, output_path: str | Path) -> Path:
    before = _claim_map_for_issue(before_issue_dir)
    after = _claim_map_for_issue(after_issue_dir)
    before_keys = set(before)
    after_keys = set(after)
    new_keys = sorted(after_keys - before_keys)
    disappeared_keys = sorted(before_keys - after_keys)
    repeated_keys = sorted(before_keys & after_keys)
    still_unresolved_keys = sorted(k for k in repeated_keys if before[k]["risky_unresolved"] or after[k]["risky_unresolved"])

    def rows(keys: list[str], data: dict[str, dict]) -> list[dict]:
        return [data[k] for k in keys]

    comparison = {
        "before_issue_dir": str(Path(before_issue_dir)),
        "after_issue_dir": str(Path(after_issue_dir)),
        "new": rows(new_keys, after),
        "repeated": rows(repeated_keys, after),
        "disappeared": rows(disappeared_keys, before),
        "still_unresolved_risky": rows(still_unresolved_keys, after),
    }
    out_path = Path(output_path)
    write_json(out_path.with_suffix(".json"), comparison)
    lines = [
        "# Issue Bundle Comparison",
        "",
        f"- Before: {Path(before_issue_dir)}",
        f"- After: {Path(after_issue_dir)}",
        "",
        "## New Claims",
    ]
    for section_name, keys, data in [
        ("New Claims", new_keys, after),
        ("Repeated Claims", repeated_keys, after),
        ("Disappeared Claims", disappeared_keys, before),
        ("Still-Unresolved Risky Claims", still_unresolved_keys, after),
    ]:
        if section_name != "New Claims":
            lines.extend(["", f"## {section_name}"])
        if not keys:
            lines.append("- None")
        else:
            for key in keys:
                item = data[key]
                # claim_text in the map is already the masked/sanitized safe text.
                text = item.get("claim_text", "")
                lines.append(f"- {text} (type: {item.get('claim_type')}; risk: {item.get('risk_tier')}; sources: {', '.join(item.get('sources') or [])})")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
