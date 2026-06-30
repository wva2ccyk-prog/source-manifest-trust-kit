# Usage Examples

## Local manifest to operator package

```bash
python -m source_manifest_kit analysis-package \
  --source-manifest examples/synthetic_analysis_sources.json \
  --output-root workspace \
  --excluded-detail-mode detailed
```

Review:

- `workspace/analysis_source_index.md`
- `workspace/operator_package/final_operator_package.md`
- `workspace/operator_package/verification/verification_packet.md`

## Build an external LLM review packet

```bash
python -m source_manifest_kit llm-review-packet \
  --operator-package-dir workspace/operator_package
```

Only send `workspace/operator_package/llm_review/llm_review_packet.json` or `.md` to an external model.

## Validate external LLM response

```bash
python -m source_manifest_kit llm-review-validate-response \
  --packet-file workspace/operator_package/llm_review/llm_review_packet.json \
  --response-file external_response.json \
  --output-dir workspace/external_review_validation
```

A valid response is still advisory-only.

## Direct URL acquisition lane

```bash
python -m source_manifest_kit acquisition-validate \
  --manifest selected_acquisition_manifest.json \
  --resolve-dns

python -m source_manifest_kit acquisition-fetch \
  --manifest selected_acquisition_manifest.json \
  --output-root workspace/acquired

python -m source_manifest_kit acquisition-to-analysis-manifest \
  --acquisition-log workspace/acquired/acquisition_log.json \
  --output workspace/analysis_sources.json \
  --confirm-reviewed
```

Inspect frozen files and warnings before conversion.

## Trusted local bundle JSON

`bundle-run` rejects absolute file paths by default. If a bundle was generated locally and reviewed, use:

```bash
python -m source_manifest_kit bundle-run \
  --bundle-file workspace/local_bundle.json \
  --output-root workspace \
  --allow-absolute-paths
```

Do not use `--allow-absolute-paths` for bundle JSON received from another person or tool.

## Optional artifact schema validation

JSON Schema validation is optional and intentionally outside the deterministic core dependency set. Install the schema extra when you want machine-readable contract checks:

```bash
python -m pip install 'source-manifest-trust-kit[schema]'
python -m source_manifest_kit validate-artifact \
  --schema llm-review-packet \
  --file examples/llm_review_packet_fixture.json \
  --output workspace/schema_validation.json
```

Available schema names are:

- `llm-review-packet`
- `external-review-response`
- `acquisition-manifest`

## Optional HTML extraction extras

Direct URL acquisition uses the built-in deterministic visible-text extractor by default. Optional extractors can be installed for better article-body extraction, but they remain outside the core dependency set:

```bash
python -m pip install 'source-manifest-trust-kit[html]'
python -m source_manifest_kit acquisition-fetch \
  --manifest workspace/acquisition_manifest.json \
  --output-root workspace/acquisition \
  --html-extractor trafilatura
```

The acquisition log records the requested extractor, the extractor actually used, fallback status, raw HTML path, content hash, and extracted-text length. Extractor output is still a frozen source artifact; it does not verify source truth.
