# Publication Risk Review

## Secrets And Private-Path Leakage

This package was assembled without private handoffs, raw personal trial logs, `.git` history, runtime workspaces, or private source packages. The release gate re-runs a fresh leakage scan for local usernames, absolute paths, credentials, private repo URLs, and personal evidence text before any push.

The Python package import path is `source_manifest_kit`. The historical `information_finance_trust_os` name was removed so public positioning matches the non-finance source-manifest scope.

## Dependency And License Risk

The Python runtime has no required third-party dependencies. Development tests require `pytest`. The package includes a static frontend viewer, and `THIRD_PARTY_LICENSES.md` covers the bundled browser assets (marked, DOMPurify) with upstream notice headers preserved.

## Maintenance Burden

The deterministic CLI and tests are maintainable for a small OSS package. The main burden is documentation clarity: keeping the project framed as source-manifest analysis rather than automated research, truth verification, or investing/trading guidance.

## LLM Review Path Risk

The package includes an LLM-consumable packet and a deterministic no-provider mock review path. This proves packet shape and safety checks without requiring credentials. A real provider integration is deliberately out of scope; the default path stays no-key.

## Frontend Risk

The frontend is explicitly `static preview`. It is not API-backed, does not execute commands, and should not be marketed as the primary product path. The product path is CLI-first.

## Overclaim Risk

High-risk phrases to avoid:

- truth engine
- verifies facts
- investment recommendation
- market signal
- autonomous research
- production-ready analysis platform

Safer framing:

- local source-manifest analysis
- claim and risk labeling
- verification packet generation
- deterministic first-pass review artifacts
- operator-supervised reporting

## Must Check Before Public Release

- Internal Python package and CLI module use the neutral `source_manifest_kit` import path; public help text uses `Source Manifest Trust Kit`.
- Run a full private-path and credential scan after final package changes.
- Review tests and examples for advice-like language. Unsafe examples are acceptable only when they demonstrate masking and are clearly synthetic.

## Preliminary Recommendation

`public_alpha_candidate` once the release gate passes. Public-facing branding and naming blockers have been repaired. The LLM-review path is mocked but executable, and the frontend is clearly marked as a static viewer. Public repository creation, push, and any Codex-for-OSS submission remain owner/coordinator decisions.
