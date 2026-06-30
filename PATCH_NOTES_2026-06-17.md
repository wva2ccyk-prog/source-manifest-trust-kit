# Patch notes - 2026-06-17

This patch hardens the package for CLI-first AI-assisted news/finance review.

## Implemented

- Normalized Windows-style relative manifest paths (`.\\file.txt`, `subdir\\file.txt`, `..\\outside.txt`) before resolution on POSIX systems.
- Kept traversal rejection intact after normalization, so backslash traversal cannot bypass the manifest-directory boundary.
- Added regression tests for Windows-style relative paths and backslash traversal.
- Blocked direct-URL acquisition of private, local, link-local, reserved, multicast, and loopback network targets.
- Disabled implicit HTTP redirects in direct-URL acquisition; redirected URLs must be reviewed and supplied explicitly.
- Added direct-URL tests for literal private-network rejection and DNS-gated fetch tests.
- Strengthened LLM review packets in the public package:
  - Replaced misleading `safe_claims` output with `review_claim_index`.
  - Added claim review buckets, verification questions, and explicit `must_not_conclude` boundaries.
  - Redacted or relativized operator input paths in LLM handoff packets.
  - Preserved legacy `safe_claims` input compatibility only for validation/template reading.
- Strengthened external LLM response validation in the public package:
  - Scans all nested string fields, not only self-reported `safety_checks`.
  - Treats unknown packet IDs as blocking errors.
  - Blocks finance/advice/action language even when the external model claims it is safe.
  - Blocks confirmation/verification language on high/critical-risk findings.
- Updated public examples to use portable relative paths.
- Added macOS/Linux smoke commands to public docs.

## Verification performed

- Public package targeted tests: `tests/test_analysis_package.py`, `tests/test_acquisition.py`, `tests/test_llm_review.py` passed.
- Personal package targeted tests: `tests/test_analysis_package.py`, `tests/test_acquisition.py` passed.
- Public synthetic smoke flow generated analysis package, LLM review packet, mock review, and external review validation successfully.
- Public malicious external response fixture was rejected by the strengthened validator.

Note: In this execution environment, long aggregated `pytest -q` runs repeatedly timed out after many already-passed tests, while the same test files passed when run individually. This appears to be harness-related rather than a deterministic failing assertion.
