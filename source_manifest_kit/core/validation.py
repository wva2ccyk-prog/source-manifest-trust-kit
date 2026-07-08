from __future__ import annotations

from pathlib import Path

from source_manifest_kit.ledger.jsonl import read_json, read_jsonl
from .schema import CLAIM_TYPES, MODES, OUTPUT_LEVELS, RISK_TIERS, SOURCE_TYPES, VERIFICATION_STATUSES

REQUIRED_ARTIFACTS = ["run_manifest.json", "input/source_001.txt", "ledger/sources.jsonl", "ledger/claims.jsonl", "ledger/review_items.jsonl"]


def validate_records(manifest: dict, sources: list[dict], claims: list[dict]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    mode = manifest.get("mode")
    if mode not in MODES:
        errors.append(f"Invalid mode: {mode}")
    source_ids: set[str] = set()
    for source in sources:
        sid = source.get("source_id")
        if not sid:
            errors.append("Source missing source_id")
            continue
        source_ids.add(sid)
        if source.get("source_type") not in SOURCE_TYPES:
            errors.append(f"Invalid source_type for {sid}: {source.get('source_type')}")
        if not source.get("source_name"):
            errors.append(f"Source {sid} missing source_name")
        if not source.get("captured_at"):
            errors.append(f"Source {sid} missing captured_at")
    for claim in claims:
        cid = claim.get("claim_id", "<missing>")
        if claim.get("source_id") not in source_ids:
            errors.append(f"Claim {cid} references missing source")
        if not claim.get("claim_text"):
            errors.append(f"Claim {cid} missing claim_text")
        if claim.get("claim_type") not in CLAIM_TYPES:
            errors.append(f"Claim {cid} invalid claim_type: {claim.get('claim_type')}")
        if claim.get("verification_status") not in VERIFICATION_STATUSES:
            errors.append(f"Claim {cid} invalid verification_status: {claim.get('verification_status')}")
        if claim.get("output_level") not in OUTPUT_LEVELS:
            errors.append(f"Claim {cid} invalid output_level: {claim.get('output_level')}")
        if claim.get("risk_tier") not in RISK_TIERS:
            errors.append(f"Claim {cid} invalid risk_tier: {claim.get('risk_tier')}")
        stype = claim.get("source_type")
        ctype = claim.get("claim_type")
        flags = set(claim.get("risk_flags") or [])
        if stype in {"community", "social"} and ctype == "confirmed_fact":
            errors.append(f"Claim {cid} violates community/social confirmed fact invariant")
        if ctype == "confirmed_fact" and ("unobservable_evidence" in flags or claim.get("verification_status") == "unobservable"):
            errors.append(f"Claim {cid} violates unobservable fact invariant")
        if ctype == "confirmed_fact" and "unsupported_causality" in flags:
            errors.append(f"Claim {cid} violates causality-as-fact invariant")
        if mode == "finance" and ctype == "confirmed_fact" and "official_data_causality_mismatch" in flags:
            errors.append(f"Claim {cid} treats official data as causality")
        if mode == "finance" and claim.get("output_level") not in {"excluded", "review_only"} and flags.intersection({"investment_advice_language", "target_price_language", "position_sizing_language", "trade_probability_language"}):
            errors.append(f"Claim {cid} has finance action language outside excluded/review buckets")
        # Repetition is not independent corroboration: a known duplicate
        # (repetition_without_lineage) coming from an UNTRUSTED source must never be
        # laundered into a fact/observation bucket via repetition. Identical text from
        # official/company sources is benign (same primary data), so it is exempt to
        # avoid hard-blocking legitimate multi-source official reporting. (The old guard
        # keyed on independent_source_count > 1, which is unreachable — it is capped at 1.)
        if (
            "repetition_without_lineage" in flags
            and stype not in {"official", "company"}
            and (
                claim.get("output_level") in {"report_fact_bucket", "report_observation_bucket"}
                or ctype in {"confirmed_fact", "market_observation", "official_reported_status"}
            )
        ):
            errors.append(f"Claim {cid} treats repetition as independent corroboration")
    return errors, warnings


def load_run(run_dir: Path) -> tuple[dict, list[dict], list[dict], list[dict]]:
    manifest = read_json(run_dir / "run_manifest.json")
    sources = read_jsonl(run_dir / "ledger" / "sources.jsonl")
    claims = read_jsonl(run_dir / "ledger" / "claims.jsonl")
    reviews = read_jsonl(run_dir / "ledger" / "review_items.jsonl")
    return manifest, sources, claims, reviews


def validate_run_dir(run_dir: str | Path) -> dict:
    run_path = Path(run_dir)
    errors: list[str] = []
    warnings: list[str] = []
    for rel in REQUIRED_ARTIFACTS:
        if not (run_path / rel).exists():
            errors.append(f"Missing artifact: {rel}")
    if errors:
        return {"passed": False, "blocking_failures": errors, "warnings": warnings}
    manifest, sources, claims, _reviews = load_run(run_path)
    rec_errors, rec_warnings = validate_records(manifest, sources, claims)
    errors.extend(rec_errors)
    warnings.extend(rec_warnings)
    return {"passed": not errors, "blocking_failures": errors, "warnings": warnings}
