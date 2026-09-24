# Source Manifest Trust Kit

> **Archived (2026-09).** This project is no longer developed. Its
> keyword-based classifier does not reliably keep unverified claims out of
> "confirmed" or low-risk buckets on realistic input. Its original goal,
> catching rumors that news and AI assistants repeat as fact, is better served
> by a verification procedure for web-searching models plus a human-verified
> case dataset. See [`docs/PROJECT_CLOSEOUT_2026-09.md`](docs/PROJECT_CLOSEOUT_2026-09.md)
> for the findings, a survey of similar projects, and what to build instead.

Source Manifest Trust Kit is a local, deterministic CLI toolkit for analyzing source packages that an operator has already collected. It turns local text files and source manifests into claim ledgers, risk labels, verification work items, and operator-safe reports.

It does not search the web, fetch arbitrary sources by default, call LLMs, verify truth, or give finance advice.

## Problem

People often collect articles, official releases, forum posts, transcripts, and notes before they understand which claims are well supported, which are copied from weaker sources, and which need verification. The hard part is not only summarizing content. It is preserving source provenance, separating evidence from interpretation, and preventing unsafe wording from leaking into reports.

## Target User

- Researchers who already have a small source set and want a local evidence ledger.
- Operators who need deterministic first-pass triage before asking a human or model to review sources.
- Developers experimenting with safety gates for claim labeling and report generation.

This is for local operator workflows. It is not a hosted service or autonomous research system.

## 3-Minute Quickstart

From this directory. CI covers Linux, macOS, and Windows on Python 3.10-3.13;
pick the block for your shell.

POSIX (macOS/Linux):

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m source_manifest_kit --help
python -m source_manifest_kit analysis-package --source-manifest examples/synthetic_analysis_sources.json --output-root workspace --excluded-detail-mode detailed
python -m source_manifest_kit bundle-summary --issue-dir workspace/issues/synthetic_source_review
python -m source_manifest_kit llm-review-packet --operator-package-dir workspace/operator_package
python -m source_manifest_kit mock-llm-review --packet-file workspace/operator_package/llm_review/llm_review_packet.json
python -m source_manifest_kit llm-review-adapter --packet-file workspace/operator_package/llm_review/llm_review_packet.json --provider openai-compatible --output-dir workspace/provider_template
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
.\.venv\Scripts\python -m source_manifest_kit --help
.\.venv\Scripts\python -m source_manifest_kit analysis-package --source-manifest .\examples\synthetic_analysis_sources.json --output-root .\workspace --excluded-detail-mode detailed
.\.venv\Scripts\python -m source_manifest_kit bundle-summary --issue-dir .\workspace\issues\synthetic_source_review
.\.venv\Scripts\python -m source_manifest_kit llm-review-packet --operator-package-dir .\workspace\operator_package
.\.venv\Scripts\python -m source_manifest_kit mock-llm-review --packet-file .\workspace\operator_package\llm_review\llm_review_packet.json
.\.venv\Scripts\python -m source_manifest_kit llm-review-adapter --packet-file .\workspace\operator_package\llm_review\llm_review_packet.json --provider openai-compatible --output-dir .\workspace\provider_template
```

Run tests:

```bash
python -m pytest
```

No paid API key is required.

## What It Does

- Reads local text and Markdown source files listed in a source manifest.
- Preserves source metadata such as title, publisher, source type, captured date, and citation note.
- Extracts simple claim records into JSONL ledgers.
- Labels risk patterns such as unobservable evidence, rumor-like sourcing, unsupported causality, and unsafe finance wording.
- Produces operator reports, verification packets, helper review packets, and package indexes.
- Produces an LLM-consumable review packet and a deterministic mocked-review smoke path.
- Masks finance advice, target-price, allocation, probability, and hype/action wording in report surfaces.

## What It Does Not Do

- Does not verify whether a claim is true.
- Does not decide which source is authoritative.
- Does not recommend investments, trades, allocations, or target prices.
- Does not monitor markets, channels, social feeds, or websites.
- Does not call LLMs, APIs, MCP tools, browser automation, or external connectors.
- Does not replace legal, compliance, journalism, or financial review.

## Privacy And Safety Boundary

Inputs stay local unless the operator separately shares them. The default runtime is deterministic Python over local files. Reports should still be reviewed before sharing because source text may contain copyrighted, private, defamatory, or market-sensitive material.

Use synthetic examples for demos. Do not publish private source packages, raw logs, API keys, personal notes, proprietary documents, or whole workspaces. If you use an external model, share only the generated `llm_review_packet.json` or `llm_review_packet.md` after checking that path displays are relative or redacted.

`bundle-run` rejects absolute file paths by default. Use `--allow-absolute-paths` only for trusted local bundles that you generated and reviewed yourself. Direct URL acquisition is a separate pre-runtime lane; use `acquisition-validate --resolve-dns` when you want DNS checks before fetch, and treat fetched content as acquisition-only, not truth verification.

## Current Status

Archived. See [`docs/PROJECT_CLOSEOUT_2026-09.md`](docs/PROJECT_CLOSEOUT_2026-09.md). The status recorded at `v0.2.0` follows for reference.

Public alpha candidate, pending the release gate (`python -m pytest -q` and `python scripts/release_check.py`). The package has a working local CLI, deterministic test suite, realistic synthetic walkthrough, LLM-review packet, no-key mocked review path, stricter path/URL/LLM-response validation, and public repository baseline documents.

It is not a fact checker, not truth verification, not RAG evaluation, and not finance or investment guidance. Run the full test suite and review `docs/THREAT_MODEL.md` before relying on it. A Codex-for-OSS submission remains future-only until public repository evidence exists.

## Evaluation Gold Set

`evaluation/goldset_v1.jsonl` is a hand-authored, provider-neutral evaluation set
for the deterministic keyword/regex trust classifier (`core/risk_policy.py` +
`core/classification.py`). Each line is a realistic Korean/English/mixed sentence
plus the **policy-correct** labels for the eight detectors, the acceptable claim
type/tier, and masking expectations. It is data, not code; see
`evaluation/GOLDSET_GUIDE.md` for the schema and labeling rules.

Every case carries a `status`:

- **`enforced`** — the current system already produces every labeled aspect. These
  are regression guards: a code change that breaks one flips the case to failing.
- **`aspirational`** — the label is the correct policy, but the current system does
  not yet meet it. These document known gaps and must NOT be "fixed" by weakening
  the label.

The harness lives in `source_manifest_kit/evaluation.py`
(`load_goldset`, `evaluate_goldset`, `evaluate_case`, `write_evaluation_report`).
It reports per-detector precision/recall/F1, per-language breakdowns, claim-type
and tier accuracy, masking violations, and the enforced/aspirational split. The
acceptance contract for this classifier is **zero enforced-case failures and all
eight detector precisions == 1.000** (validated in `tests/test_evaluation.py`).

The `eval-goldset` command (measurement by default; `--enforce` to exit non-zero
on any enforced regression) surfaces this from the CLI:

```bash
python -m source_manifest_kit eval-goldset --goldset evaluation/goldset_v1.jsonl --output-dir eval_out
python -m source_manifest_kit eval-goldset --goldset evaluation/goldset_v1.jsonl --output-dir eval_out --enforce
```

## Repository Layout

- `source_manifest_kit/`: Python CLI and deterministic analysis runtime.
- `evaluation/`: provider-neutral trust-classifier gold set (`goldset_v1.jsonl`) and its labeling guide.
- `examples/`: synthetic source manifest and sample source files.
- `tests/`: deterministic tests copied from the private baseline for package review.
- `docs/WHY.md`: rationale and design intent.
- `docs/USER_JOURNEY.md`: public source-manifest to review-output flow.
- `docs/THREAT_MODEL.md`: explicit trust boundaries and residual risks.
- `docs/CLI_CONTRACT.md`: exit codes and stable CLI/artifact expectations.
- `docs/EXTERNAL_LLM_REVIEW_BOUNDARY.md`: what can be sent to external LLMs and how responses are validated.
- `docs/DIRECT_URL_ACQUISITION_BOUNDARY.md`: SSRF/network boundary for direct URL acquisition.
- `docs/ARTIFACT_SCHEMA.md`: JSON schema notes.
- `docs/FRONTEND_DECISION.md`: frontend scope decision.
- `docs/LLM_ADAPTER_DECISION.md`: mock-default/provider-optional adapter decision.
- `docs/DEMO_WALKTHROUGH.md`: realistic synthetic walkthrough.
- `docs/PUBLIC_DIFFERENTIATION.md`: comparison against common alternatives.
- `USAGE_EXAMPLES.md`: task-oriented CLI examples.
- `SMOKE_TESTS.md`: no-paid-API smoke path.
- `PUBLICATION_RISK_REVIEW.md`: pre-publication risk review.
- `SECURITY.md`, `CONTRIBUTING.md`, `LICENSE`: public repository basics.

## Optional extras

The runtime core keeps third-party dependencies out of the default install. Extras are available for bounded helper lanes:

- `source-manifest-trust-kit[schema]`: enables `validate-artifact` JSON Schema checks for public artifacts.
- `source-manifest-trust-kit[html]`: enables optional `acquisition-fetch --html-extractor trafilatura|readability` extraction. The default remains the built-in extractor.
- `source-manifest-trust-kit[cli]`: reserved for terminal display helpers.
- `source-manifest-trust-kit[supplychain]`: release/CI scanning helpers, not runtime dependencies.
