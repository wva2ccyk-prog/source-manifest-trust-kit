# CLI Contract

## Exit codes

- `0`: command succeeded.
- `2`: validation, safety, schema, path, acquisition, or user input error.
- Python tracebacks are hidden by default for known user-facing errors.
- Add `--debug` before the subcommand to show tracebacks during development.

Example:

```bash
python -m source_manifest_kit --debug acquisition-validate --manifest bad.json
```

## Stable user-facing commands

The preferred public entry point is:

```bash
source-manifest-trust-kit <command>
```

The module entry point remains supported:

```bash
python -m source_manifest_kit <command>
```

## Public JSON artifacts

These artifact names are intended to remain stable for operator workflows:

- `analysis_source_manifest.json`
- `analysis_source_index.md`
- `acquisition_manifest.normalized.json`
- `acquisition_log.json`
- `acquisition_source_index.md`
- `search_candidate_selection.json`
- `verification_packet.json`
- `llm_review_packet.json`
- `external_review_response_validation.json`

Raw bundle JSON and helper packets are local workflow artifacts. Do not treat their internal fields as permanent API without checking the schema/version fields.

## Optional validation and extraction commands

`validate-artifact` is a schema-contract helper. It requires the optional `schema` extra because the runtime core does not depend on `jsonschema`.

```bash
python -m source_manifest_kit validate-artifact --schema llm-review-packet --file packet.json
```

`acquisition-fetch --html-extractor builtin|trafilatura|readability` controls only HTML-to-text extraction for already accepted direct URLs. `builtin` is the default and has no third-party dependency. The other extractors require the optional `html` extra and are recorded in `acquisition_log.json`.
