# Smoke Tests

These checks require Python 3.10+ and no paid API key.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
.\.venv\Scripts\python -m source_manifest_kit --help
.\.venv\Scripts\python -m source_manifest_kit analysis-package --source-manifest .\examples\synthetic_analysis_sources.json --output-root .\workspace --excluded-detail-mode detailed
.\.venv\Scripts\python -m source_manifest_kit bundle-summary --issue-dir .\workspace\issues\synthetic_source_review
.\.venv\Scripts\python -m source_manifest_kit llm-review-packet --operator-package-dir .\workspace\operator_package
.\.venv\Scripts\python -m source_manifest_kit mock-llm-review --packet-file .\workspace\operator_package\llm_review\llm_review_packet.json
.\.venv\Scripts\python -m source_manifest_kit llm-review-adapter --packet-file .\workspace\operator_package\llm_review\llm_review_packet.json --provider openai-compatible --output-dir .\workspace\provider_template
.\.venv\Scripts\python -m source_manifest_kit llm-review-validate-response --packet-file .\workspace\operator_package\llm_review\llm_review_packet.json --response-file .\workspace\operator_package\llm_review\mock_llm_review.json --output-dir .\workspace\external_review_validation
.\.venv\Scripts\python -m pytest
```

Expected result:

- CLI help prints command list.
- `workspace\issues\synthetic_source_review` is created.
- `workspace\operator_package\llm_review\llm_review_packet.json` is created.
- `workspace\operator_package\llm_review\mock_llm_review.json` is created.
- `workspace\provider_template\openai-compatible_request_template.json` is created without making a network call.
- `workspace\external_review_validation\external_review_response_validation.json` confirms the mock response matches the expected advisory schema.
- Finance action/target/probability wording is masked in report surfaces.
- Mock review preserves source boundaries, keeps missing evidence uncertain, and does not recommend investing or trading actions.
- External response validation rejects missing findings, duplicate/unknown packet IDs, English/Korean certainty upgrades, and finance action/target/probability language.
- Tests pass without network access or API credentials.

Safe skip:

- If Python 3.10+ is unavailable, record the Python version as the blocker.
- No external provider should be called by default.

## macOS/Linux smoke commands

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
python -m source_manifest_kit llm-review-validate-response --packet-file workspace/operator_package/llm_review/llm_review_packet.json --response-file workspace/operator_package/llm_review/mock_llm_review.json --output-dir workspace/external_review_validation
python -m pytest
```

Negative smoke checks:

```bash
python -m source_manifest_kit acquisition-validate --manifest examples/malicious/bad_port_acquisition_manifest.json
python -m source_manifest_kit bundle-run --bundle-file examples/malicious/path_traversal_bundle.json --output-root workspace
python -m source_manifest_kit llm-review-validate-response --packet-file examples/llm_review_packet_fixture.json --response-file examples/malicious/empty_external_review_response.json --output-dir workspace/negative_validation
```

Expected negative result: each command exits non-zero with a concise `Error:` message and no Python traceback.

## Optional schema validation smoke

```bash
python -m source_manifest_kit validate-artifact \
  --schema llm-review-packet \
  --file examples/llm_review_packet_fixture.json \
  --output workspace/schema_validation.json
```

Expected: exit code 0 and `workspace/schema_validation.json` contains `"valid": true`.


## Fresh-clone release check

Run this single command from a fresh clone before any release packaging. It runs
the test suite, exercises the demo pipeline in a temporary directory, and fails
if the package tree contains unexpected generated files (caches, build output,
workspaces, operator packages, provider templates, acquired sources, logs, or
databases).

```bash
python scripts/release_check.py
```

Expected: exit code 0 with `[release-check] PASS`. A non-zero exit lists the
failing step or the unexpected generated files to remove before publishing.