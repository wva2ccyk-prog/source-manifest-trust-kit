from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from .adapters import finance, general_news
from .core.claim_extraction import extract_claim_texts
from .core.classification import apply_repetition_policy
from .core.reporting import write_report
from .core.schema import ReviewItem, RunManifest, SourceRecord, safe_source_type, utc_now
from .core.text_io import read_source_text
from .ledger.jsonl import write_json, write_jsonl


def make_run_id(mode: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}_{mode}"


def init_workspace(workspace: str | Path) -> Path:
    root = Path(workspace)
    (root / "runs").mkdir(parents=True, exist_ok=True)
    return root


def _observable_state(source_type: str, observable: bool = True) -> str:
    if not observable:
        return "unobservable"
    if source_type == "unknown":
        return "missing_source"
    return "observable"


def _review_reason(claim: dict) -> str:
    if claim.get("disallowed_reason"):
        return claim["disallowed_reason"]
    flags = set(claim.get("risk_flags") or [])
    if "true_cause_market_claim" in flags:
        return "unsafe true-cause market claim"
    if "unobservable_evidence" in flags:
        return "unobservable evidence"
    if "market_causality_claim" in flags:
        return "unsupported market causality"
    if "unsupported_causality" in flags:
        return "unsupported causality"
    if "needs_official_confirmation" in flags:
        return "needs official confirmation"
    if claim.get("claim_type") == "excluded":
        return "blocked output"
    return "human review required"


def _review_question(claim: dict) -> str:
    flags = set(claim.get("risk_flags") or [])
    if claim.get("claim_type") == "excluded":
        return "This finance claim is blocked by policy and remains excluded. If factual context is needed, capture a separate factual claim from a primary source."
    if "unobservable_evidence" in flags:
        return "What observable source can replace or corroborate the inaccessible material?"
    if "market_causality_claim" in flags:
        return "What official or independent evidence supports this market-causality claim?"
    if "needs_official_confirmation" in flags:
        return "Which official or primary source can confirm the factual part of this claim?"
    return "What source or context should be checked before trusting this claim?"


def analyze_file(*, mode: str, input_path: str | Path, source_name: str, source_type: str, output_root: str | Path, source_url: str | None = None, title: str | None = None, published_at: str | None = None, issue_id: str | None = None) -> Path:
    if mode not in {"general", "finance"}:
        raise ValueError("mode must be general or finance")
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(input_file)
    out_root = init_workspace(output_root)
    run_id = make_run_id(mode)
    run_dir = out_root / "runs" / run_id
    input_dir = run_dir / "input"
    ledger_dir = run_dir / "ledger"
    input_dir.mkdir(parents=True, exist_ok=True)
    ledger_dir.mkdir(parents=True, exist_ok=True)
    text = read_source_text(input_file, label=f"source `{source_name}`")
    (input_dir / "source_001.txt").write_text(text, encoding="utf-8")
    stype = safe_source_type(source_type)
    source = SourceRecord("src_001", run_id, stype, source_name, source_url, title or input_file.name, published_at, utc_now(), _observable_state(stype), "input/source_001.txt")
    classifier = finance.classify if mode == "finance" else general_news.classify
    claims = []
    for index, claim_text in enumerate(extract_claim_texts(text), start=1):
        claim = classifier(claim_text, source)
        claim.claim_id = f"clm_{index:03d}"
        claims.append(claim)
    apply_repetition_policy(claims)
    reviews: list[ReviewItem] = []
    for claim in claims:
        if claim.needs_human_review:
            claim_dict = claim.to_dict()
            reviews.append(ReviewItem(f"rev_{len(reviews) + 1:03d}", claim.claim_id, _review_reason(claim_dict), claim.risk_tier, "open", _review_question(claim_dict)))
    manifest = RunManifest(run_id, mode, issue_id, str(input_file), utc_now(), 1, len(claims), len(reviews))
    write_json(run_dir / "run_manifest.json", manifest.to_dict())
    write_jsonl(ledger_dir / "sources.jsonl", [source.to_dict()])
    write_jsonl(ledger_dir / "claims.jsonl", [claim.to_dict() for claim in claims])
    write_jsonl(ledger_dir / "review_items.jsonl", [review.to_dict() for review in reviews])
    write_report(run_dir)
    return run_dir
