# Roadmap

This roadmap describes the direction for Source Manifest Trust Kit. It is a
local, deterministic operator tool, so every item here must preserve the core
boundary: no truth verification, no source ranking authority, no finance advice,
and no default network or LLM calls. Items are intentionally scoped to stay
auditable.

Status legend: `planned`, `exploring`, `done`.

## Near term

- `done` Modernize packaging license metadata to SPDX.
- `done` Document a stable exit-code contract for the CLI so the toolkit is
  easier to script in operator pipelines. See `docs/CLI_CONTRACT.md`: `0` on
  success, `2` for validation/safety/schema/path/acquisition/input errors, with
  tracebacks suppressed for known user-facing errors unless `--debug` is passed.
- `planned` Expand the realistic example set with more publisher and source-type
  variety so risk labeling behavior is easier to inspect.
- `done` Name the offending source and its path when a source file is not valid
  UTF-8, instead of surfacing the raw codec error. See
  `source_manifest_kit/core/text_io.py`.
- `planned` Add a short troubleshooting section for the remaining common manifest
  formatting mistakes (missing fields, empty source bodies).

## Medium term

- `exploring` Optional pluggable risk-pattern packs so operators can add
  domain-specific patterns without editing core code.
- `exploring` A machine-readable summary artifact for the review packet to make
  downstream operator dashboards simpler.
- `planned` Broaden test coverage around report masking edge cases (mixed
  language finance wording, nested quotes). The concrete open gaps are the three
  aspirational gold-set cases: `en_fin_066` (an `80% probability` substring that
  masking must preserve) and `ko_fin_077` / `ko_fin_078` (Korean causality
  recall). These are correct policy labels and must not be resolved by weakening
  the labels.

## Explicitly out of scope

- Automated web search, scraping, or source acquisition.
- Deciding whether a claim is true or which source is authoritative.
- Investment, trading, allocation, or target-price recommendations.
- Always-on monitoring of markets, channels, or feeds.

## How to influence the roadmap

Open a feature request issue describing the operator workflow you are trying to
support. Concrete, local-first use cases are the most likely to be accepted.
