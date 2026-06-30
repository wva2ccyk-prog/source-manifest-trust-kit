# Implementation Report — 2026-06-17

This package was updated from the reviewed distribution candidate. The implementation focuses on preserving the deterministic core while tightening the boundaries around untrusted manifests, direct URL acquisition, external LLM review packets, CLI behavior, docs, and packaging.

## Implemented changes

### P0/P1 safety fixes

- Hardened external LLM response validation in `source_manifest_kit/llm_review.py`.
  - Empty `findings` are rejected when the packet contains claims.
  - Missing, duplicate, and unknown `packet_id` values are blocking errors.
  - High/critical claims require coverage in the response.
  - Recursive scanning blocks nested unsafe text.
  - English and Korean confirmation/certainty/causality language is blocked for high/critical claims.
  - Additional finance-action/target/allocation/return-certainty wording is blocked.
- Fixed LLM review packet question propagation.
  - `verification_question` is now derived from deterministic verification packet fields.
  - Packet rendering no longer emits null questions when verification packet questions exist.
- Hardened raw issue bundle paths in `source_manifest_kit/bundle.py`.
  - Relative bundle paths cannot contain `..` or Windows backslash traversal.
  - Absolute paths require explicit trusted mode.
  - Symlinks are rejected.
  - URL-like file paths and non-text suffixes are rejected.
- Hardened manifest-based package path handling in `analysis_package.py` and local operator package flow.
  - Manifest sources reject symlinks.
  - Internal trusted bundle handoff is explicit.
- Hardened direct URL acquisition in `acquisition.py`.
  - Invalid ports are rejected during validation.
  - Unicode hostnames are rejected unless supplied in normalized ASCII/IDNA form.
  - Non-canonical IPv4 forms are rejected.
  - Optional DNS validation is exposed through `acquisition-validate --resolve-dns`.
  - Fetch-time DNS validation remains enabled.
  - Redirects remain blocked.
  - Environment proxies are disabled for the fetch opener.
- Reduced external packet path disclosure.
  - Helper review packets now use `review_claim_index` and relative/redacted path display.
  - Operator package indexes display relative/redacted paths where possible.
- Hardened frontend static viewer URL handling.
  - `frontend/app.js` only creates clickable anchors for `http:` and `https:` URLs.
  - Other schemes are displayed as plain text.
- Stabilized CLI failure behavior.
  - Known safety/validation errors print a clean `Error: ...` and exit with code 2.
  - Full traceback is available only through `--debug`.

### Optional helper lanes

- Added packaged JSON Schemas and `validate-artifact` CLI.
  - Available schemas: `llm-review-packet`, `external-review-response`, `acquisition-manifest`.
  - Runtime core remains dependency-free; schema validation uses optional `jsonschema`.
- Added optional HTML extractor selection for direct URL acquisition.
  - Default remains `builtin`.
  - Optional extractors: `trafilatura`, `readability`, available through the `html` extra.
  - Acquisition logs record extractor metadata and fallback use.

### Tests and examples

- Added regression tests for:
  - missing/duplicate/empty external review findings,
  - Korean confirmation language,
  - verification question propagation,
  - malicious bundle path traversal,
  - absolute bundle path rejection,
  - symlink rejection,
  - invalid URL port handling,
  - non-canonical IPv4 rejection,
  - Unicode hostname rejection,
  - DNS private-resolution blocking,
  - clean CLI errors,
  - frontend non-http URL filtering,
  - JSON Schema artifact validation.
- Added malicious examples under `examples/malicious/`.
- Updated `examples/llm_review_packet_fixture.json` to the stricter packet schema.

### Documentation and packaging

- Added:
  - `LICENSE`
  - `SECURITY.md`
  - `CONTRIBUTING.md`
  - `USAGE_EXAMPLES.md`
  - `docs/THREAT_MODEL.md`
  - `docs/CLI_CONTRACT.md`
  - `docs/EXTERNAL_LLM_REVIEW_BOUNDARY.md`
  - `docs/DIRECT_URL_ACQUISITION_BOUNDARY.md`
  - `docs/ARTIFACT_SCHEMA.md`
  - `docs/RISK_POLICY.md`
  - `docs/TEST_PLAN.md`
  - `schemas/*.schema.json`
  - `.github/workflows/ci.yml`
- Updated `README.md` and `SMOKE_TESTS.md` with stricter safety boundaries, optional extras, negative smoke checks, and external LLM sharing guidance.
- Fixed version mismatch.
  - `pyproject.toml`: `0.1.1`
  - `source_manifest_kit.__version__`: `0.1.1`
- Fixed package discovery and packaged schema files for wheel builds.

## Validation performed

```text
python3 -m pytest -q
138 passed in 22.16s
```

Positive CLI smoke was run through:

```text
analysis-package → bundle-summary → llm-review-packet → mock-llm-review → llm-review-validate-response
```

External review validation produced `"valid": true` for the deterministic mock response.

Negative smoke checks were run:

```text
acquisition-validate examples/malicious/bad_port_acquisition_manifest.json
exit 2, clean error: invalid port

bundle-run examples/malicious/path_traversal_bundle.json
exit 2, clean error: path traversal

llm-review-validate-response with empty findings
exit 2, clean error: missing packet_id/high-critical coverage
```

Packaging validation was run:

```text
python3 -m pip wheel . -w /tmp/smtk_wheel --no-deps
Successfully built source-manifest-trust-kit 0.1.1
```

Clean virtual environment install check was run:

```text
source-manifest-trust-kit --help
source_manifest_kit.__version__ == 0.1.1
```

## Deliberately not added to the deterministic core

- OpenBB or any live finance adapter.
- Trading, ranking, allocation, target-price, return-probability, or investment recommendation features.
- Rich/Typer migration.
- Browser automation or API-backed frontend behavior.

These remain excluded to preserve the project boundary: frozen source manifest handling, deterministic safety labeling, and advisory-only external review.

## Known residual boundary

DNS rebinding cannot be completely eliminated by pre-resolving a hostname and then using the standard `urllib` fetch path. This package now blocks private DNS answers before fetch, disables environment proxies, rejects malformed/ambiguous hosts, and documents the residual risk. A stricter future implementation would need a custom connector that pins the resolved public IP through the actual socket connection while preserving the original Host/SNI semantics.
