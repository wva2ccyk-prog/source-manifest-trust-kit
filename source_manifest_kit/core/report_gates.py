from __future__ import annotations

from pathlib import Path

from source_manifest_kit.ledger.jsonl import write_json
from .validation import load_run, validate_run_dir

BUCKETS = {"confirmed_fact": "confirmed_facts", "official_reported_status": "official_reported_status", "market_observation": "market_observations", "reported_claim": "reported_claims", "interpretation": "interpretations", "opinion_or_frame": "opinion_frame_risks", "unverified_causality": "unverified_causality", "rumor": "rumors", "needs_official_source": "needs_official_source", "unobservable": "unobservable", "excluded": "excluded", "question_to_verify": "questions_to_verify"}


def bucket_for_claim(claim: dict) -> str:
    return BUCKETS.get(claim.get("claim_type"), "excluded")


def build_report_gates(run_dir: str | Path, write: bool = True) -> dict:
    run_path = Path(run_dir)
    validation = validate_run_dir(run_path)
    manifest, _sources, claims, _reviews = load_run(run_path) if (run_path / "run_manifest.json").exists() else ({}, [], [], [])
    bucket_counts = {name: 0 for name in set(BUCKETS.values())}
    for claim in claims:
        bucket = bucket_for_claim(claim)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    result = {"run_id": manifest.get("run_id"), "passed": validation["passed"], "blocking_failures": validation["blocking_failures"], "warnings": validation["warnings"], "bucket_counts": dict(sorted(bucket_counts.items()))}
    if write:
        write_json(run_path / "ledger" / "report_gates.json", result)
    return result
