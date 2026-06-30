# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once it
leaves alpha.

## [Unreleased]

### Changed
- Modernized packaging license metadata to the SPDX `license = "MIT"` string
  plus `license-files`, removing the deprecated setuptools license table and
  the redundant license classifier.

### Documentation
- Added this changelog, a public `ROADMAP.md`, and GitHub issue/pull-request
  templates to make maintenance and contribution expectations explicit.

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
