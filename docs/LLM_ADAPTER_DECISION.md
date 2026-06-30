# LLM Adapter Decision

Decision: provider-optional interface, mock default.

## Current Behavior

- `llm-review-packet` writes a model-consumable JSON and Markdown packet.
- `mock-llm-review` runs the no-key deterministic smoke reviewer.
- `llm-review-adapter --provider mock` runs the same deterministic review.
- `llm-review-adapter --provider openai-compatible` writes a dry-run request template and prompt file. It does not perform a network call.

## Why No Real External Call In Public Staging

Real external calls require API-key handling, provider-specific error handling, output validation, cost controls, and privacy documentation. That is public-release work, not a safe staging default.

## Future Real Review Shape

A future adapter can use the generated `openai-compatible_request_template.json` and require:

- explicit provider-neutral environment variables;
- explicit operator opt-in;
- no source upload unless the operator chooses it;
- strict JSON output validation;
- safety scan rejecting investing/trading recommendations and fabricated certainty.
