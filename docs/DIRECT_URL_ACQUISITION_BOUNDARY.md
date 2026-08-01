# Direct URL Acquisition Boundary

Direct URL acquisition is a pre-runtime convenience lane for operator-provided HTTP(S) URLs. It freezes fetched text into local artifacts that must be reviewed before conversion into `analysis_sources.json`.

## It does not verify truth

Fetching a URL does not verify source authenticity, claim truth, official status, authorship, publication time, market relevance, or factual correctness.

## Network controls

The acquisition lane:

- accepts only direct HTTP(S) URLs;
- rejects embedded credentials;
- rejects localhost and `.localhost`;
- rejects private, loopback, link-local, reserved, multicast, and other non-global literal IPs;
- can pre-resolve DNS and block hostnames resolving to non-global IPs;
- pins the fetch connection to the validated address, keeping TLS SNI and
  certificate verification bound to the original hostname, so a second
  resolution cannot re-point the request at a private host;
- rejects non-canonical IPv4 host forms such as integer, octal, hex, or short forms;
- requires normalized ASCII/IDNA hostnames;
- blocks redirects;
- disables environment proxy use in its opener;
- enforces timeout, byte cap, and source count limits.

`acquisition-fetch` always resolves and pins, so the frozen
`acquisition_manifest.normalized.json` and `acquisition_log.json` report
`dns_checked_when_requested: true` and
`fetch_connection_pinned_to_validated_ip: true` on that path. The validate-only
lane (`acquisition-validate` without `--resolve-dns`) reports
`dns_checked_when_requested: false`, because it performs no resolution.

## Residual risk

This is not a complete SSRF sandbox. DNS rebinding and platform resolver behavior are documented residual risks. Use this lane only with URLs you intentionally selected and reviewed.

## HTML extraction boundary

The default extractor is `builtin`, a local visible-text parser intended to avoid runtime dependencies. Optional `trafilatura` and `readability` extractors are available only through the `html` extra and must be requested explicitly with `--html-extractor`.

Extractor choice does not change the acquisition trust boundary. The output is still a frozen source artifact that requires operator review before conversion to an analysis source manifest. The acquisition log records `html_extractor`, optional version metadata, fallback use, raw HTML preservation, hashes, and extracted text length.
