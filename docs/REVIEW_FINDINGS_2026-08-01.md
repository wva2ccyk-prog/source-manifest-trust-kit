# External Review Findings — 2026-08-01

Independent review of `main` at commit `805b6b0` ("Harden detection, masking,
intake, and add evaluation gold set (#1)"). Method: fresh clone, documented
install path (`python -m pip install -e '.[dev]'`, Python 3.14.6 on macOS), then
the documented test/gate/smoke commands, followed by source reading of the
acquisition, risk-policy, LLM-review, CLI, and frontend surfaces.

This document records what was verified as accurate, what was found to be wrong
or stale, and a prioritized fix plan. It does not change runtime behavior.

**Status:** eight of nine findings are fixed in the follow-up branch
`fix/p1-vendored-sanitizer-and-release-gate`. Only F4 remains open, because
tagging and publishing a release is an owner decision; it has a step-by-step
runbook at `docs/OPEN_FOLLOWUP_F4_RELEASE_TAGGING.md`. Per-finding status is noted
inline below.

## Verified accurate

These documented claims were re-derived from the actual tree, not taken on trust:

- `python -m pytest -q` → **278 passed**, no network access, no API key.
- `eval-goldset --enforce` → **219/219 enforced cases passing**, exit 0, and all
  eight detector precisions **1.000** (matches the acceptance contract stated in
  `README.md`). Aspirational cases are **0/3 passing** and are correctly reported
  as known gaps (`en_fin_066` masking, `ko_fin_077`/`ko_fin_078` causality
  recall) rather than papered over by weakened labels.
- CLI exit-code contract holds: missing `PACKAGE_INDEX.json`, malicious port
  manifest, path-traversal bundle, and empty external review response all exit
  `2` with a concise `Error:` line and no traceback.
- `docs/CLI_CONTRACT.md` artifact-name list matches what the pipeline actually
  writes; `schemas/*.json` and `source_manifest_kit/schemas/*.json` are byte
  identical, so the packaged copy cannot drift silently.
- SSRF controls in `acquisition.py` are real, not aspirational: DNS pre-resolve
  plus connection pinning with TLS SNI/cert verification still bound to the
  original hostname, IPv4-mapped **and** IPv4-compatible (`::127.0.0.1`) unwrap,
  wildcard-DNS embedded-IP preflight, non-canonical IPv4 rejection, redirect
  block, and an opener with environment proxies disabled.
- Core runtime dependencies are genuinely empty; `jsonschema`, HTML extractors,
  and supply-chain tooling are all behind extras as documented.

## Findings

### F1 — The documented release gate cannot pass from a fresh clone (P1, blocking)

**Status: fixed.** `*.egg-info` now gets the same gitignore-managed exemption as
the caches, and the gate cross-checks its own exemption list against
`git check-ignore`, so an exemption that stops being gitignored fails loudly
instead of silently waving a file through. Verified: the gate exits 0 with
`[release-check] PASS`, and a deliberately planted `workspace_*/` directory and
`.log` file are still reported.

`README.md` and `docs/PUBLIC_READINESS.md` both gate public-alpha status on
`python scripts/release_check.py`. Following the documented install first
(`pip install -e '.[dev]'`, the only install path the README gives) the gate
**fails**:

```
[release-check] FAILED: unexpected generated files in package tree:
  - source_manifest_trust_kit.egg-info
  - source_manifest_trust_kit.egg-info/PKG-INFO
  ... (5 more)
exit=1
```

Tests and the demo pipeline pass; only the clean-tree scan fails. The scan
exempts `__pycache__` and `.pytest_cache` with the explicit reasoning that they
are "produced by running this very check and are gitignore-managed" — but
`*.egg-info/` is *also* gitignored (`.gitignore` line 4) and is produced by the
documented editable install. `git status` is clean while the gate reports the
tree dirty, which is the contradiction.

Fix: apply the same gitignore-managed exemption to `*.egg-info` (keep flagging
`build/`, `dist/`, workspaces, logs, and DBs), or have the scan consult
`git check-ignore` instead of a hand-maintained name list. Either way the gate
should be run once from a clean clone and its output pasted into the release
notes, since the current status claim rests on a gate nobody can currently pass.

### F2 — Vendored DOMPurify 3.0.9 is a known-vulnerable sanitizer (P1, security)

**Status: fixed.** Re-vendored DOMPurify `3.0.9` → `3.4.12` and marked
`15.0.12` → `18.0.7`, both pulled from the npm registry with the published
`shasum` verified before use. marked 18 ships no pre-minified build, so the
bundle is upstream `lib/marked.umd.js` kept under the existing `marked.min.js`
filename; its browser-global `marked.parse` path was exercised before the swap
because that is the viewer's only call site. `THIRD_PARTY_LICENSES.md` now
records both shipped versions.

`frontend/purify.min.js` is DOMPurify **3.0.9**, pinned as such in
`THIRD_PARTY_LICENSES.md`. That version is affected by **CVE-2024-47875**
(nesting-based mXSS); per NVD the fix landed in **3.1.3** on the 3.x branch
(2.5.0 on 2.x), and the current release is **3.4.12** (2026-07-11).

This is the one third-party component on the trust path that matters. In
`frontend/app.js` the operator-supplied `final_operator_package.md` is rendered
with `marked.parse()` → `DOMPurify.sanitize(html)` → `tempDiv.innerHTML = html`,
and that Markdown embeds claim text originating from untrusted source documents.
`docs/THREAT_MODEL.md` already lists "frontend-loaded JSON artifacts" and
"source text itself" as untrusted inputs, so a bypass in the sanitizer is
in-scope by the project's own model, even for a local static viewer.

Note the Python core is not affected: `escape_markdown_inline` in
`core/risk_policy.py` escapes `[`, `]`, backtick and entity-encodes `<`/`>`
before rendering, so the generated Markdown is defensively escaped upstream.
The sanitizer is the second layer, and the second layer is the outdated one.

Fix: upgrade the vendored bundle to a current DOMPurify (>= 3.1.3, preferably
latest), update the version and license header quoted in
`THIRD_PARTY_LICENSES.md`, and record the upgrade in `CHANGELOG.md` under
Security.

Secondary: `frontend/marked.min.js` is **15.0.12** against a current
**18.0.7**. Snyk reports no known vulnerabilities for 15.0.12, so this is
hygiene rather than exposure — but it should move on the same cadence as the
sanitizer.

### F3 — Nothing in CI or the test suite can detect F2 (P1, process)

**Status: fixed.** Added `tests/test_vendored_frontend_assets.py`. It parses the
version banner from each bundle, enforces a minimum-version floor (DOMPurify
`3.1.3`, marked `15.0.12`), requires `THIRD_PARTY_LICENSES.md` to name the
versions actually shipped, and asserts the upstream license headers survive
minification. Stdlib only and offline. The license cross-check earned its place
immediately by catching the stale `3.0.9` notice during the fix.

`tests/test_frontend_static.py` asserts that DOMPurify loads before `app.js` and
that `DOMPurify.sanitize(html)` is called, which is good wiring coverage — but no
test asserts *which version* is vendored. CI's `supply-chain` job runs
`pip-audit` and CycloneDX over the Python environment only, so the vendored
browser assets sit outside every automated check. A stale sanitizer can be
carried indefinitely with a fully green pipeline, which is exactly what
happened.

Fix: add a test that parses the version banner out of `frontend/purify.min.js`
and `frontend/marked.min.js` and enforces a minimum-version floor, so a future
re-vendor cannot silently regress. Keep it stdlib-only and offline.

### F4 — `CHANGELOG.md` points at a release and tag that do not exist (P2)

**Status: open, owner decision — runbook written.** Creating a tag and cutting a
release is a publishing action, so it is left to the owner rather than performed as
part of a review. `docs/OPEN_FOLLOWUP_F4_RELEASE_TAGGING.md` makes it executable
without re-deriving anything: the two options and their trade-offs, the verified
target commit (`0231593`), exact commands, draft release notes, verification steps,
and the failure modes to avoid.

`CHANGELOG.md` documents a `[0.1.1] - 2026-06-30` entry and links to
`releases/tag/v0.1.1` and `compare/v0.1.1...HEAD`. On the remote there are **no
releases and no tags** (`gh release list` and `git ls-remote --tags` both return
empty), so both links are dead and the "initial public alpha release" reads as
published when it was not.

This matters more than a normal broken link because `docs/PUBLIC_READINESS.md`
makes a Codex-for-OSS submission conditional on "public repository evidence
(issues, releases, and maintenance history)". Tagging `v0.1.1` at the release
commit and cutting the matching GitHub release is the smallest action that makes
the changelog true and starts building the evidence the readiness doc asks for.

### F5 — `CHANGELOG.md` omits the largest change in the tree (P2)

**Status: fixed.** `[Unreleased]` now carries Added/Changed/Security entries for
the unicode de-obfuscation layer, the Korean masking corrections, intake
hardening, DNS-rebinding pinning, the `eval-goldset` lane and gold set, the
sanitizer upgrade, and the test-count growth.

The `[Unreleased]` section lists only the SPDX license-metadata change and the
docs additions. It says nothing about commit `805b6b0`, which touched 30+ files,
rewrote much of `core/risk_policy.py` (+890 lines), added the evaluation harness
and the 222-case gold set, added DNS-rebinding IP pinning, and took the suite
from 138 to 278 tests. A reader using the changelog to understand the current
state would badly under-estimate it.

Fix: add Added/Changed/Security entries under `[Unreleased]` covering unicode
de-obfuscation before detection, the Korean masking corrections, absolute-path
opt-in on intake, DNS-rebinding pinning, and the `eval-goldset` lane.

### F6 — `ROADMAP.md` lists already-shipped work as `planned` (P2)

**Status: fixed.** The exit-code contract item is now `done` and points at
`docs/CLI_CONTRACT.md`; the masking-coverage item names the three aspirational
gold cases as the concrete open gaps.

Near-term item "`planned` Document a stable exit-code contract for the CLI" is
already delivered: `docs/CLI_CONTRACT.md` specifies `0`/`2` and the
traceback-suppression rule, and this review confirmed all four error paths
behave that way. Leaving it `planned` makes the roadmap unreliable as a status
surface.

Fix: mark it `done` and point at `docs/CLI_CONTRACT.md`. The "broaden masking
edge-case coverage" item should also name the three known aspirational gold
cases, since those are the concrete open gaps.

### F7 — Acquisition provenance metadata under-reports its own DNS check (P3)

**Status: fixed.** The fetch path now records
`dns_checked_when_requested: true` plus a new
`fetch_connection_pinned_to_validated_ip: true`, both set from what that path
actually does. The flag is corrected after loading rather than by passing
`resolve_dns=True` to the loader: that would perform a second resolution per
source, and an existing test correctly pins the fetch to exactly one
`getaddrinfo` call per source, since the extra resolution is precisely what the
pinning design exists to avoid. The validate-only lane still reports `false`, and
the residual-risk disclosure (`dns_rebinding_not_fully_eliminated`) is unchanged.

`fetch_acquisition_manifest` calls `load_acquisition_manifest(manifest_file)`
without `resolve_dns=True`, so the emitted
`acquisition_manifest.normalized.json` records:

```json
"dns_checked_when_requested": false
```

…even though the fetch loop then calls `_assert_public_http_url(...,
resolve_dns=True)` per source and pins the connection to a validated address.
The frozen artifact therefore understates the control that actually ran. Since
these artifacts are the audit trail an operator reviews before conversion, the
metadata should reflect reality.

Fix: load with `resolve_dns=True` on the fetch path, or set the boundary flag
from the fetch behavior rather than from the loader argument.

### F8 — Non-UTF-8 source files surface a raw codec error (P3)

**Status: fixed.** Added `source_manifest_kit/core/text_io.py`, a shared
operator-source reader used by `runs.analyze_file` and `capture_helper`. The error
now names the source, the failing byte offset and value, and the remedy. Because
`UnicodeDecodeError` is already a `ValueError`, exit code 2 and traceback
suppression were never broken — only the message was unhelpful — so the wrapper
preserves that hierarchy instead of introducing a new exception type. BOM
stripping is unchanged and now has a regression test.

A source file that is not UTF-8 fails with
`Error: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte`.
The exit code and traceback suppression are correct, but the message does not
say which source, which file, or that `.txt`/`.md` inputs must be UTF-8. The
roadmap already has a planned troubleshooting item for "mixed encodings"; this
is the concrete case to fix alongside it — wrap the read and name the offending
`sources[n]` and path, matching the style of the other intake errors.

### F9 — Quickstart leads with PowerShell on a cross-platform project (P3)

**Status: fixed.** The quickstart now leads with a POSIX block and keeps the
PowerShell block beside it, the duplicated macOS/Linux section is removed, and the
Windows path separator in the Current Status line is corrected.

CI covers ubuntu/macos/windows across Python 3.10–3.13, but the README's
"3-Minute Quickstart" is PowerShell-only, with POSIX commands relegated to a
section near the bottom; the Current Status line also quotes
`python scripts\release_check.py` with a Windows separator. On macOS/Linux the
first copy-paste fails. Lead with a POSIX block or show both side by side, and
use a forward slash in prose.

## Prioritized fix plan

| # | Finding | Priority | Type | Status |
|---|---|---|---|---|
| 1 | F2 upgrade vendored DOMPurify past CVE-2024-47875 | P1 | Security | fixed |
| 2 | F3 add vendored-asset version-floor test | P1 | Process | fixed |
| 3 | F1 make `release_check.py` pass after the documented install | P1 | Blocking | fixed |
| 4 | F4 tag `v0.1.1` and cut the release the changelog links to | P2 | Accuracy | open |
| 5 | F5 changelog entries for the hardening commit | P2 | Accuracy | fixed |
| 6 | F6 roadmap status correction | P2 | Accuracy | fixed |
| 7 | F7 acquisition boundary metadata reflects the DNS check performed | P3 | Correctness | fixed |
| 8 | F8 actionable encoding error message | P3 | UX | fixed |
| 9 | F9 POSIX-first quickstart | P3 | Docs | fixed |

F1–F3 were the release blockers: two were the difference between a documented
gate that passes and one that cannot, and the third was a known-vulnerable
sanitizer on the untrusted-input path. All three are fixed. F4 is the only item
left, and it gates the public-release evidence `docs/PUBLIC_READINESS.md` asks
for; see `docs/OPEN_FOLLOWUP_F4_RELEASE_TAGGING.md` to execute it.

## Out of scope for this review

Detector precision, masking policy, and the gold-set labels were audited for
internal consistency and deliberately left untouched. The three aspirational
failures are correct policy labels documenting real gaps and must not be "fixed"
by weakening them, as `README.md` already states.

Runtime changes in the follow-up branch are limited to two narrow items: the
acquisition boundary metadata in F7, which corrects what the audit artifact
reports about controls that already ran rather than changing which requests are
allowed or blocked, and the F8 encoding error path, which changes an error
message while preserving the existing exception hierarchy and exit code.
