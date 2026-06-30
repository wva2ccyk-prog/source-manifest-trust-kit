# Demo Walkthrough

This walkthrough uses only synthetic sources.

## Scenario

An operator collected four excerpts about a city shuttle pilot:

- an official city notice;
- a local news article;
- a forum rumor alleging hidden pressure;
- a finance-sensitive commentary post about a related company.

The operator wants to know what is supported, what needs verification, and what should not be repeated.

## Run

```powershell
python -m source_manifest_kit analysis-package --source-manifest .\examples\realistic_scenario\analysis_sources.json --output-root .\workspace_demo --excluded-detail-mode detailed
python -m source_manifest_kit bundle-summary --issue-dir .\workspace_demo\issues\realistic_shuttle_review
python -m source_manifest_kit llm-review-packet --operator-package-dir .\workspace_demo\operator_package
python -m source_manifest_kit mock-llm-review --packet-file .\workspace_demo\operator_package\llm_review\llm_review_packet.json
python -m source_manifest_kit llm-review-adapter --packet-file .\workspace_demo\operator_package\llm_review\llm_review_packet.json --provider openai-compatible --output-dir .\workspace_demo\provider_template
python -m source_manifest_kit llm-review-validate-response --packet-file .\workspace_demo\operator_package\llm_review\llm_review_packet.json --response-file .\workspace_demo\operator_package\llm_review\mock_llm_review.json --output-dir .\workspace_demo\external_review_validation
```

## No-Key External Handoff Proof

The external handoff smoke has three local artifacts:

- `workspace_demo\operator_package\llm_review\llm_review_packet.json`: the source-bounded packet a reviewer or model would receive.
- `workspace_demo\provider_template\openai-compatible_request_template.json`: a dry-run request template with `external_call_performed` set to `false`.
- `workspace_demo\external_review_validation\external_review_response_validation.json`: a schema and safety validation result for a mock external response.

This proves the handoff shape without a provider key, network call, or hidden source upload. A real provider adapter remains future work and must keep the same safety checks: advisory-only output, preserved source boundaries, no fabricated missing evidence, and no investing or trading recommendations.

## What The Tool Should Catch

- The official notice is stronger evidence for schedule and route details.
- The forum claim is weak because it depends on unnamed or inaccessible evidence.
- The market commentary includes finance-sensitive action/probability/return wording and should not be repeated as advice.
- Unsupported causal claims should become verification work, not confident conclusions.

## What The Tool Refuses Or Masks

- It does not verify whether the forum allegation is true.
- It does not recommend buying, selling, trading, allocation, targets, or expected returns.
- It does not fetch missing meeting records or search the web.

## What The Operator Should Do Next

- Inspect `workspace_demo\operator_package\final_operator_package.md`.
- Inspect `workspace_demo\operator_package\verification\verification_packet.md`.
- Inspect `workspace_demo\operator_package\llm_review\mock_llm_review.md`.
- Inspect `workspace_demo\external_review_validation\external_review_response_validation.md`.
- Seek primary records before repeating the unsupported causal claim.
- Keep the frontend as optional static preview only.
