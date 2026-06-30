# Naming Decision

Public user-facing name: `Source Manifest Trust Kit`

Python import/module path: `source_manifest_kit`

Distribution name: `source-manifest-trust-kit`

## Decision

The internal Python package was renamed from the historical
`information_finance_trust_os` path to `source_manifest_kit`. The import
path, `__main__` module entry, console-script target, tests, docs, frontend
references, and packaging metadata all use the neutral name.

## Reason

The historical module name carried a finance-centered framing that did not match
the project's actual scope: deterministic local source-manifest review. The
neutral `source_manifest_kit` import path keeps the public package consistent
with the user-facing name and the documented non-finance boundary.

## Status

Resolved. No legacy module references remain in the package. Run the module via
`python -m source_manifest_kit` or the `source-manifest-trust-kit` console
script.