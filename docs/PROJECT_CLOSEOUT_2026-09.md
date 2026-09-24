# Project Closeout — 2026-09

**Status: archived. No further development is planned.** The `v0.2.0`
pre-release remains available as a historical record. The code still installs,
and the test suite and release gate still pass. Do not use it for real
misinformation triage, for the reasons below.

## Why this project existed

The starting point was a concrete failure. A site posted a false,
finance-motivated claim. It was copied across several sites, news outlets
rewrote it as reporting without independent confirmation, and an AI assistant
then repeated it as established fact. The original goal was to help an operator
tell whether a claim like that was actually true.

## What we learned

### 1. Programs cannot decide truth

Truth is not a property of the text. It depends on outside evidence: filings,
records, testimony. That evidence is often private, not yet published, or never
published at all. What *can* be judged is narrower, and it is what would have
prevented the original failure: **whether anyone had grounds to state the claim
as fact.** Checks like "all coverage traces back to one post", "no outlet shows
independent reporting", and "no filing exists where one would be required" do
not require knowing the truth.

### 2. The deterministic classifier does not deliver its purpose on realistic input

A post-release review (2026-09-25) probed `classify_claim` and
`sanitize_for_report` with realistic sentences that are not in the demo or the
gold set:

| Input (source / mode) | Result | Problem |
|---|---|---|
| "Competitor Z has been secretly falsifying its safety reports." (company / general) | `confirmed_fact`, `confirmed`, low, no review | A company-typed source becomes confirmed fact by default |
| "Sources say the minister accepted bribes." (news / general) | `reported_claim`, low, no review | Anonymous sourcing is not detected |
| "The mayor secretly took money from the developer before the vote." (community / general) | `reported_claim`, low, no review | Absent from "Unresolved Claims" in the final package |
| "이 종목 10만원까지 간다." / "월급 절반은 여기 넣어라." (community / finance) | not masked, low or medium | Korean target-price and allocation wording slips through |
| "Shares fell 8% on fears of a recession." (news / finance) | `market_observation` | The most common form of finance causality is not detected |
| Forum post re-published as "Local outlets reported that …" | not grouped | Cross-source laundering detection requires near-identical text |

Structural causes:

- **Default labels imply verification.** `verification_status: confirmed` and
  the verification packet's `confirmed_low_risk` category contradict the
  project's own "does not verify truth" boundary.
- **Keyword lexicons have a low recall ceiling.** Paraphrases, new slang, and
  adversarial rewording defeat them, and the people spreading rumors adapt.
- **The evaluation was self-confirming.** `evaluation/goldset_v1.jsonl` and
  most of `core/risk_policy.py` were written in the same commit (`805b6b0`), so
  "219/219 enforced, precision 1.000" measured the lexicon against sentences it
  already knew.

### 3. Model capability changed the right place for code

Reading and judging text is now done better by frontier models than by
hand-written rules. That is the part of this repository that lost its value.
Code still earns its place where it supplies what models lack. It can give them
access to records, enforce hard constraints (for example, refusing "confirmed"
without a primary-source link), preserve evidence, and validate outputs.

Evidence from the literature:

- Web search alone gives LLM fact-checking only moderate gains. Curated,
  high-quality context improved macro F1 by 233% on average
  ([DeVerna et al., ACL Findings 2026](https://aclanthology.org/2026.findings-acl.1467.pdf)).
- LLM fact checks that are wrong or uncertain can *reduce* people's ability to
  judge headlines
  ([DeVerna et al., PNAS 2024](https://www.pnas.org/doi/10.1073/pnas.2322823121)).
- Chatbots citing low-quality sources is explained largely by **data voids**:
  topics with no authoritative coverage
  ([HKS Misinformation Review](https://misinforeview.hks.harvard.edu/article/llms-grooming-or-data-voids-llm-powered-chatbot-references-to-kremlin-disinformation-reflect-information-gaps-not-manipulation/)).
  A small-cap finance rumor whose only coverage is copies is a classic data
  void.

### 4. Survey of similar open-source projects

- **Claim-in, verdict-out LLM pipelines** (Loki/OpenFactVerification,
  Veracity, FactCheck, FailSafe) are mostly single-author projects. The best
  known, Loki, has had no commits since 2024-10.
- **Provenance and laundering tracers** (LineageRAG, VeriFact, ClaimTrace,
  RumourFlow) share this project's core idea. None has real-world validation.
- **Projects with measured, real-world impact keep humans as the deciders.**
  - [Community Notes](https://github.com/twitter/communitynotes): notes reduce
    reposts of noted posts by 46–62%, and LLM-drafted notes are rated
    helpful by humans.
  - [Meedan Check](https://github.com/meedan/check): a workflow tool for
    professional fact-checkers.
- **Case collections exist but are fragmented or dormant.**
  - The [Media Manipulation Casebook](https://mediamanipulation.org/) (frozen
    since 2023-09).
  - [EUvsDisinfo](https://euvsdisinfo.eu/disinformation-cases/) (pro-Kremlin
    cases only).
  - SNU FactCheck (read-only since 2024-08).
  - Korean regulator sanction releases (anonymized, unstructured).
  - None of them records how a rumor flowed from a forum, to news, to AI
    answers.

## What would be worth building instead

1. **A procedure, not a classifier.** Give a web-searching model fixed rules.
   It must trace the earliest source and separate independent reporting from
   copies. It must count copies of one origin as a single source and check
   primary records (for Korean equities: DART/KIND filings and exchange
   rumor-clarification disclosures). It must flag data voids and use a
   restricted verdict vocabulary: *confirmed by primary record / independent
   reporting only / copied spread, origin unconfirmed / unverifiable*.
2. **A human-verified case dataset.** Record how real situations turned into
   false news. Each case gets a timeline of appearances with archived
   snapshots, the point where hedging disappeared, primary-record status,
   data-void status, AI answers as a stage, the resolution and its evidence,
   and the signals that were visible *before* resolution. The schema should
   work web-wide; cases should come from a domain the curator can actually
   verify. Capture must happen while a rumor spreads, because origin posts get
   deleted.
3. **A minimal collection pipeline, built only after cases exist.** The value
   is in the verified cases, not the tooling. Automate only the steps that
   prove painful after the first 5–10 hand-built cases.

## Reusable parts of this repository

- `source_manifest_kit/acquisition.py`: SSRF-safe fetching into frozen,
  hashed artifacts. Useful for evidence capture.
- The source-manifest provenance fields (title, publisher, captured_at,
  citation_note).
- JSON Schema validation for artifacts
  (`source_manifest_kit/artifact_schema.py`).
- Finance-wording masking, as a best-effort output filter only, given the
  recall gaps above.
