# Resolved: release tagging (finding F4)

**Status: resolved in `v0.2.0` via option B.** This was the one finding from
`docs/REVIEW_FINDINGS_2026-08-01.md` that needed an owner decision, because
tagging and publishing is a publishing action. The decision was made and executed:
`v0.1.1` was deliberately **not** tagged, and `v0.2.0` was cut from `main`
instead. The reasoning and the procedure are kept below because the same trade-off
recurs at every future release.

## What was decided and why

Option A (tag the historical `0231593` tree as `v0.1.1`) was rejected. It would
have repaired two dead changelog links, but at the cost of publishing a
downloadable release whose tree predates the security hardening and ships
DOMPurify `3.0.9`, affected by CVE-2024-47875. A release page is the first place
most people click, so creating an official download pointing at vulnerable code is
a worse outcome than a dead link, even with a pre-release flag and a warning note.

Option B was taken instead: the `[0.1.1]` changelog entry is marked as an untagged
historical record with its dead links removed, and `v0.2.0` is the first tagged
release. The first thing anyone can download is therefore a tree with the
sanitizer upgraded, the release gate passing, and 287 tests green. The version
jump from `0.1.1` to `0.2.0` is accurate rather than cosmetic: substantial
detection, masking, intake, and security work landed in between.

## The problem this addressed

`CHANGELOG.md` documents a `[0.1.1] - 2026-06-30` entry and its link block points
at:

- `https://github.com/wva2ccyk-prog/source-manifest-trust-kit/releases/tag/v0.1.1`
- `https://github.com/wva2ccyk-prog/source-manifest-trust-kit/compare/v0.1.1...HEAD`

Neither target existed. Verified with `gh release list` (empty) and
`git ls-remote --tags origin` (empty). So the changelog reads as though an alpha
was published when nothing was ever tagged, and both links 404.

This is worth more than a link fix: `docs/PUBLIC_READINESS.md` makes a
Codex-for-OSS submission conditional on "public repository evidence (issues,
releases, and maintenance history)". A tag plus release is the smallest action
that both makes the changelog true and starts producing that evidence.

## Release procedure (reusable)

This is the sequence used for `v0.2.0` and the one to follow for future releases.

1. Merge outstanding fix PRs into `main` first, so the tag reflects them.
2. Confirm the gate passes on the exact tree being released:

   ```bash
   python -m pytest -q
   python scripts/release_check.py
   ```

   Expected: tests green and `[release-check] PASS`. Paste this output into the
   release notes; the readiness doc's status claim depends on it.

3. Bump `version` in `pyproject.toml` and promote the `[Unreleased]` changelog
   section to the new version with a date. Update the link block at the bottom so
   `[Unreleased]` compares against the new tag.
4. Merge that release-prep change into `main`, then tag the resulting commit.
   Annotated, not lightweight, so the tag carries a message and tagger date:

   ```bash
   git tag -a v0.2.0 -m "source-manifest-trust-kit v0.2.0"
   git push origin v0.2.0
   ```

   The tagger identity comes from local git config, so set `user.name` and
   `user.email` first if they are unset in the clone.

5. Create the release from that tag:

   ```bash
   gh release create v0.2.0 --title "v0.2.0" --notes-file <notes>
   ```

   Keep `--prerelease` while the project is still alpha-status per
   `docs/PUBLIC_READINESS.md`.

## Verify

```bash
git ls-remote --tags origin   # the new tag is present
gh release list               # the release is listed
```

Then confirm the `CHANGELOG.md` link block resolves instead of 404ing.

## Do not

- Do not force-push or move a published tag. If a release goes out wrong, publish
  a corrected patch version instead.
- Do not tag a tree whose contents contradict its changelog entry. That is exactly
  the mismatch this finding was about.
- Do not tag a tree that fails `scripts/release_check.py`. The public-alpha status
  claim in `docs/PUBLIC_READINESS.md` rests on that gate passing.
- Do not attach built artifacts (`dist/`) unless you intend to publish to PyPI;
  that is a separate decision with its own supply-chain surface.
