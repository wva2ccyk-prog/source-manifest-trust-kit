# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once it
leaves alpha.

## [Unreleased]

### Added
- Unicode de-obfuscation (`normalize_for_matching`) applied before every detector
  and before report masking: format/zero-width/control-char stripping, NFKC
  folding, and a tight Cyrillic/Greek confusable fold, so obfuscated
  finance-advice wording can no longer slip past detection or masking.
- `eval-goldset` CLI command and the `source_manifest_kit.evaluation` harness,
  reporting per-detector precision/recall/F1, per-language breakdowns,
  claim-type/tier accuracy, masking violations, and the enforced/aspirational
  split. `--enforce` exits non-zero on any enforced-case regression.
- Provider-neutral evaluation gold set (`evaluation/goldset_v1.jsonl`, 222 cases)
  plus `evaluation/GOLDSET_GUIDE.md`. 219 cases are enforced regression guards;
  3 are aspirational and document known gaps.
- Minimum-version floors for the vendored browser assets
  (`tests/test_vendored_frontend_assets.py`). CI's supply-chain job only scans
  the Python environment, so nothing previously covered `frontend/`.
- `source_manifest_kit/core/text_io.py`, a shared operator-source text reader
  that names the offending source, the failing byte, and the remedy when a local
  `.txt`/`.md` file is not valid UTF-8. A leading BOM is still accepted.

### Changed
- Modernized packaging license metadata to the SPDX `license = "MIT"` string
  plus `license-files`, removing the deprecated setuptools license table and
  the redundant license classifier.
- Korean detection and masking corrections: neutral market data (`순매도`,
  `공매도`) is preserved, `목표주가` is masked, the `목표가`-as-goal false positive
  is gone, and the `인해`-inside-`확인해` causal substring bug is fixed.
- Intake hardening: absolute manifest paths are opt-in, manifest-relative paths
  are emitted where possible, filename hints no longer elevate a source to
  official/company trust, and cross-source repetition/laundering is detected
  across all source types.
- `scripts/release_check.py` no longer fails on gitignore-managed packaging
  metadata (`*.egg-info`), which the documented editable install creates. The
  gate now also cross-checks its own exemptions against `git check-ignore`, so an
  exemption that stops being gitignored fails loudly instead of silently passing.
- README quickstart now leads with a POSIX block alongside the PowerShell one,
  matching the cross-platform CI matrix, and the duplicated macOS/Linux section
  was removed.
- Test suite grew from 138 to 287 tests.

### Security
- Upgraded vendored DOMPurify from `3.0.9` to `3.4.12`. The previous version
  predated the 3.x fix for CVE-2024-47875 (nesting-based mXSS), released in
  `3.1.3`. The static viewer renders operator-package Markdown containing claim
  text drawn from untrusted source documents, so the sanitizer sits on an
  untrusted-input path. Vendored marked moved from `15.0.12` to `18.0.7`.
- Direct URL acquisition pins the connection to a pre-validated public IP while
  keeping TLS SNI and certificate verification bound to the original hostname,
  closing the DNS-rebinding TOCTOU gap between validation and connect. Also
  added: IPv4-mapped and IPv4-compatible (`::127.0.0.1`) unwrapping,
  wildcard-DNS embedded-IP preflight blocking, and malformed-port rejection.
- Untrusted claim text is markdown-escaped in all rendered report surfaces.

### Documentation
- Added this changelog, a public `ROADMAP.md`, and GitHub issue/pull-request
  templates to make maintenance and contribution expectations explicit.
- Added `docs/REVIEW_FINDINGS_2026-08-01.md`, an external review of the tree
  recording verified-accurate claims alongside a prioritized fix plan.
- Added `docs/OPEN_FOLLOWUP_F4_RELEASE_TAGGING.md`, a step-by-step runbook for the
  one review finding that needs an owner decision: the `v0.1.1` tag and release
  that `CHANGELOG.md` already links to but which does not exist on the remote.

## [0.1.1] - 2026-06-30

### Added
- Initial public alpha release of the deterministic local source-manifest
  toolkit: claim ledgers, risk labeling, verification work items, operator
  reports, LLM-safe review packets, a dry-run provider request path, and a
  mocked external-review validation path.
- GitHub Actions CI running the test suite on each push.

### Security
- Documented the privacy and safety boundary: inputs stay local, no web access
  or LLM calls by default, and finance/hype wording is masked in report
  surfaces. See `SECURITY.md`, `docs/THREAT_MODEL.md`, and `docs/RISK_POLICY.md`.

[Unreleased]: https://github.com/wva2ccyk-prog/source-manifest-trust-kit/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/wva2ccyk-prog/source-manifest-trust-kit/releases/tag/v0.1.1
