# Artifact Schema Notes

Formal JSON Schema files are stored under `schemas/`. They are intentionally lightweight and focused on public handoff artifacts.

Current schema coverage:

- `llm_review_packet.schema.json`
- `external_review_response.schema.json`
- `acquisition_manifest.schema.json`

Install `.[schema]` to validate these schemas in downstream tooling with `jsonschema`. The deterministic core does not require `jsonschema` at runtime.

## CLI validation helper

Packaged schemas are available both in the top-level `schemas/` directory for repository inspection and inside the Python package for installed CLI use. The helper command is optional:

```bash
python -m source_manifest_kit validate-artifact --schema llm-review-packet --file packet.json
```

It returns exit code `0` for a valid artifact and `2` for schema validation failure or malformed input. The command requires the optional `schema` extra.
