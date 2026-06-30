# Contributing

Contributions should preserve the core design: deterministic, local-first, source-boundary preserving, and no finance advice.

## Rules for changes

- Keep core runtime dependencies empty unless there is a clear security or correctness reason.
- Put optional integrations behind extras or separate adapters.
- Do not add live search, market ranking, LLM provider calls, or browser automation to the deterministic core.
- Any new report surface must pass finance-safety and source-boundary tests.
- Any new input surface must include malicious fixture tests.
- External LLM output is advisory only and must never upgrade deterministic labels.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

## Test expectations

Add tests for:

- normal success path;
- malformed JSON/schema;
- path traversal and symlink handling where relevant;
- finance advice, target, allocation, probability, and return-certainty wording;
- source laundering from community/social/rumor material;
- CLI error output and exit code if a command is user-facing.
