# Public User Journey

Source Manifest Trust Kit is built around a source-manifest-first flow.

## Flow

1. Prepare local source excerpts.
   - Save each excerpt as `.txt` or `.md`.
   - Use synthetic or operator-controlled text.
   - Do not put sensitive credentials, raw private records, or unreviewed sensitive material into a public demo.

2. Write a source manifest.
   - Include `issue_id`, `source_name`, `source_type`, `mode`, and `file_path`.
   - Optional metadata such as title, publisher, capture date, and citation note stays attached to the source.

3. Generate the deterministic analysis package.
   - Run `analysis-package`.
   - The runtime creates ledgers, source indexes, verification packets, helper-review packets, and an operator report.

4. Generate an LLM review packet.
   - Run `llm-review-packet` against the operator package.
   - The packet includes safe claim text, source boundaries, review instructions, and a required output schema.

5. Review through a model or deterministic smoke.
   - For public smoke tests, run `mock-llm-review`.
   - A real LLM can be used later by pasting or routing the packet, but the default package does not require an API key.

6. Inspect output.
   - Review uncertainty reasons, evidence boundaries, operator next steps, and safety checks.
   - Treat all model/helper review as advisory. The deterministic package remains the local record.

## Boundary

The tool prepares source/evidence review artifacts. It does not verify truth, provide investment or trading guidance, monitor live sources, or fetch arbitrary web content by default.
