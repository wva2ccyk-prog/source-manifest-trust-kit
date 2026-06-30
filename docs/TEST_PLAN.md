# Test Plan

## Unit tests

- path traversal and separator normalization;
- symlink rejection;
- manifest schema and required fields;
- finance advice/action/target/allocation/probability wording masks;
- rumor/community/social source laundering prevention;
- LLM response coverage and recursive unsafe language scan;
- Korean confirmation and causality upgrade expressions.

## Integration tests

- `analysis-package` to operator package;
- direct URL acquisition to reviewed analysis manifest;
- LLM packet to mock review to external response validation;
- frontend static artifact preview checks.

## CLI smoke tests

- successful README flow;
- invalid direct URL manifest without traceback;
- malicious bundle path without traceback;
- missing LLM findings fail validation.

## Cross-platform tests

Run on Linux, macOS, and Windows for Python 3.10-3.13. Include paths with spaces, non-ASCII filenames, Windows-style relative paths, and UNC/drive negative cases.
