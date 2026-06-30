# Threat Model

## Assets protected

- Operator source boundaries and provenance.
- Local file paths and workspace layout when producing external LLM packets.
- Report surfaces that could otherwise leak investment advice, target-price language, probability claims, or unsupported conclusions.
- Local network boundary during optional direct URL acquisition.

## Trusted components

- Deterministic Python core over local `.txt`/`.md` files.
- Operator-authored `analysis_sources.json` after local review.
- Local tests and static examples.

## Untrusted inputs

- Raw issue bundle JSON files.
- Source manifests received from other people or tools.
- Direct URL acquisition manifests.
- Search candidate artifacts.
- External LLM responses.
- Frontend-loaded JSON artifacts.
- Source text itself.

## Boundary decisions

- `analysis-package` resolves manifest-relative paths under the manifest directory and rejects path traversal, URL-like file paths, non-text suffixes, and symlinks.
- `bundle-run` rejects absolute paths by default. Absolute paths require `--allow-absolute-paths` and should only be used for trusted locally generated bundles.
- Direct URL acquisition accepts only HTTP(S), rejects credentials, localhost/private/link-local/reserved/multicast/non-global IP destinations, rejects non-canonical IPv4 forms, can pre-resolve DNS, blocks redirects, and disables environment proxy use in its opener.
- LLM review packets display relative or redacted paths and include explicit `review_claim_index`, review bucket, verification question, and `must_not_conclude` fields.
- External LLM responses must cover packet IDs, cannot reference unknown IDs, cannot duplicate IDs, must preserve safety checks, and are recursively scanned for blocked finance/action/confirmation language.

## Known residual risks

- Direct URL acquisition is not a full network sandbox. DNS rebinding and platform resolver behavior are reduced but not fully eliminated.
- HTML extraction is best-effort and not semantic truth verification.
- Source text may contain private, copyrighted, defamatory, or market-sensitive content.
- The static frontend previews local artifacts; it is not an orchestrator or authority boundary.
