# Open follow-up: tag and release `v0.1.1` (finding F4)

This is the one finding from `docs/REVIEW_FINDINGS_2026-08-01.md` that cannot be
closed from a review branch, because tagging and publishing a release is a
publishing action and an owner decision. Everything needed to execute it is
written out here so the owner, or another agent picking this up, does not have to
re-derive it.

## The problem

`CHANGELOG.md` documents a `[0.1.1] - 2026-06-30` entry and its link block points
at:

- `https://github.com/wva2ccyk-prog/source-manifest-trust-kit/releases/tag/v0.1.1`
- `https://github.com/wva2ccyk-prog/source-manifest-trust-kit/compare/v0.1.1...HEAD`

Neither target exists. Verified with `gh release list` (empty) and
`git ls-remote --tags origin` (empty). So the changelog reads as though an alpha
was published when nothing was ever tagged, and both links 404.

This is worth more than a link fix: `docs/PUBLIC_READINESS.md` makes a
Codex-for-OSS submission conditional on "public repository evidence (issues,
releases, and maintenance history)". A tag plus release is the smallest action
that both makes the changelog true and starts producing that evidence.

## Decision the owner has to make first

Pick one. The rest of this document assumes option A.

**Option A — tag the historical commit (recommended).** Tag `v0.1.1` at the
commit that actually was the 0.1.1 tree, `0231593` ("Initial public alpha
release: source-manifest-trust-kit v0.1.1", 2026-06-30). This makes the existing
changelog entry and its date honest, and `compare/v0.1.1...HEAD` then shows every
change since, which is what a reader expects.

Trade-off: the tagged tree predates the `805b6b0` hardening work, so anyone
installing from the tag gets the pre-hardening code, including the outdated
DOMPurify. Mark the GitHub release as a **pre-release** and say so in the notes.

**Option B — skip 0.1.1 and cut `v0.2.0` from current `main`.** Rewrite the
`[0.1.1]` section into `[Unreleased]`, or retitle it as an untagged historical
entry, and release the current tree instead. Choose this if you would rather not
point users at a tag containing the known-vulnerable sanitizer.

Under option B, update the `CHANGELOG.md` link block accordingly and drop the
`v0.1.1` references rather than leaving them dangling.

## Prerequisites

1. Merge PR #3 (`fix/p1-vendored-sanitizer-and-release-gate`) first if you intend
   any release to reflect the fixed sanitizer. Under option A this does not block
   the tag, since the tag points at history.
2. Confirm the gate passes on the tree you are releasing:

   ```bash
   python -m pytest -q
   python scripts/release_check.py
   ```

   Expected: tests green and `[release-check] PASS`. Paste this output into the
   release notes; the readiness doc's status claim depends on it.

## Steps (option A)

Annotated tag, not lightweight, so the tag carries a message and a tagger date:

```bash
git tag -a v0.1.1 0231593 -m "source-manifest-trust-kit v0.1.1 (public alpha)"
git push origin v0.1.1
```

The commit hash is verified: `0231593` resolves to
`02315937dd47b3cd377ce6f6309b8859cfb3a848`, "Initial public alpha release:
source-manifest-trust-kit v0.1.1" (2026-06-30). The `git tag -a` form above was
dry-run against that commit during review, confirming the tag lands on the
intended tree rather than on `HEAD`.

Note the tagger identity comes from your local git config, so set `user.name` and
`user.email` before tagging if they are unset in this clone.

Then create the release from that tag, marked as a pre-release:

```bash
gh release create v0.1.1 \
  --title "v0.1.1 — public alpha" \
  --prerelease \
  --notes-file release_notes_v0.1.1.md
```

Suggested `release_notes_v0.1.1.md` content:

```markdown
Initial public alpha of the deterministic local source-manifest toolkit: claim
ledgers, risk labeling, verification work items, operator reports, LLM-safe
review packets, a dry-run provider request path, and a mocked external-review
validation path.

This tag marks the 2026-06-30 tree for changelog accuracy. It predates later
hardening work and ships DOMPurify 3.0.9 in the static viewer, which is affected
by CVE-2024-47875. Use `main` rather than this tag.

Not a fact checker, not truth verification, not RAG evaluation, and not finance
or investment guidance. See `docs/THREAT_MODEL.md`.
```

Delete the scratch notes file afterwards; it should not be committed.

## Verify

```bash
git ls-remote --tags origin        # v0.1.1 present
gh release list                    # v0.1.1 listed as Pre-release
```

Then confirm the two `CHANGELOG.md` links resolve instead of 404ing. No changelog
edit is required under option A: the existing link block already points at the
tag and compare URLs this creates.

## Do not

- Do not force-push or move an existing tag; if `v0.1.1` is ever published wrong,
  publish a corrected `v0.1.2` instead.
- Do not tag `main` as `v0.1.1`. `main` is well past that tree, and a tag whose
  contents do not match its changelog entry recreates the problem in a worse form.
- Do not attach built artifacts (`dist/`) unless you intend to publish to PyPI;
  that is a separate decision with its own supply-chain surface.
