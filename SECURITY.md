# Security Policy

## Supported status

Source Manifest Trust Kit is a local deterministic CLI toolkit. It is a public alpha candidate, not a hosted security product. Treat all source manifests, bundle JSON files, direct URL acquisition manifests, search candidate artifacts, and external LLM responses as untrusted input unless you authored and reviewed them.

## Reporting security issues

Please report suspected security issues privately before public disclosure. Include:

- package version and commit or ZIP filename;
- operating system and Python version;
- command line used;
- minimal malicious manifest, bundle, URL, or response fixture;
- expected and observed behavior.

Do not include private source packages, API keys, personal documents, or proprietary material in a report. Use synthetic fixtures whenever possible.

## Security boundary

The default analysis runtime is local and deterministic. It does not search the web, fetch source URLs, call LLMs, call market APIs, or use browser automation. The direct URL acquisition lane is separate pre-runtime functionality and remains acquisition-only: fetched content is not truth verification.

## Known non-goals

- This project is not an investment, trading, allocation, target-price, or expected-return tool.
- This project is not a truth adjudicator.
- This project is not a sandbox for arbitrary untrusted files.
- This project is not a complete SSRF firewall. The direct URL acquisition lane performs conservative checks, blocks private/local/reserved network destinations, blocks redirects, disables proxy use in its opener, and records the boundary, but DNS rebinding and platform resolver behavior remain part of the threat model.
