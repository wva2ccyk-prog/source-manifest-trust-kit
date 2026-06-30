# External LLM Review Boundary

External LLM review is advisory-only. It is used to critique evidence boundaries, missing verification, and unsafe conclusions. It must not decide truth, cause, authority, market direction, investment suitability, target prices, allocations, probabilities, or expected returns.

## Safe handoff artifact

Share only:

- `operator_package/llm_review/llm_review_packet.json`, or
- `operator_package/llm_review/llm_review_packet.md`.

Do not share the whole local workspace unless you have separately reviewed and redacted it.

## Validator guarantees

`llm-review-validate-response` checks:

- schema version;
- matching `issue_id`;
- `advisory_only=true`;
- required finding fields;
- unknown, duplicate, and missing `packet_id` values;
- high/critical claim coverage;
- recursive blocked language scan;
- finance advice/action/target/probability/return-certainty wording;
- English and Korean confirmation/verification/causality upgrade language.

A passing validation means the response matches the safety contract. It does not mean any source claim is true.
