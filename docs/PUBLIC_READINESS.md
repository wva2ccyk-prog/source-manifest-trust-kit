# Public Readiness

Classification: `public_alpha_candidate`

This package is a public alpha candidate once the release gate passes
(`python -m pytest -q` and `python scripts\release_check.py`). It ships a
deterministic local CLI, a realistic synthetic walkthrough, and bounded
review-packet generation.

## Scope Boundaries

- Not a fact checker.
- Not truth verification.
- Not RAG evaluation.
- Not finance advice or investment guidance.
- A Codex-for-OSS submission is future-only until public repository evidence
  exists (issues, releases, and maintenance history).

## Known Limitations

- The real LLM adapter is a dry-run request template, not a live provider
  integration; the default review path is the no-key deterministic mock.
- The frontend is a static local artifact viewer, not an API-backed workflow.
- The target user is narrow: operators who already collect source excerpts and
  want a deterministic pre-model package.

## Why It Is Useful

- It gives a repeatable source-manifest workflow.
- It converts weak, rumor, or finance-sensitive material into review and
  verification tasks instead of confident narrative.
- It creates a bounded LLM review packet before any model sees the source
  package.
- It keeps missing evidence explicitly uncertain.

## Recommendation

Run the release gate on the final candidate. Public repository creation, push,
visibility changes, and any Codex-for-OSS submission remain owner/coordinator
decisions made outside this package.