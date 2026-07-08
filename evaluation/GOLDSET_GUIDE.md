# Trust-Classification Gold Set — Labeling Guide

`goldset_v1.jsonl` is a hand-authored evaluation set for the deterministic
keyword/regex trust classifier in `information_finance_trust_os/core/`
(`risk_policy.py` + `classification.py`). It is **data**, not code: each line is
a realistic Korean/English/mixed sentence plus a label describing the
**policy-correct** behavior, and a `status` recording whether the current system
already produces that behavior.

The harness that consumes this file is built separately. This guide documents the
schema, the status semantics, and the exact decision rules used to label each
detector, so new cases can be added consistently.

Run everything from the runtime root with `PYTHONUTF8=1`.

---

## 1. File format

- UTF-8, **no BOM**, Unix newlines (`\n`).
- One JSON object per line (JSONL). Lines are sorted by `case_id`.
- `case_id` is unique, zero-padded, and namespaced by language×mode:
  `ko_fin_NNN`, `ko_gen_NNN`, `en_fin_NNN`, `en_gen_NNN`, `mx_fin_NNN`.

### Case schema

```jsonc
{
  "case_id": "ko_fin_001",
  "text": "...",                       // the sentence under test
  "language": "ko" | "en" | "mixed",
  "mode": "general" | "finance",
  "source_type": "official"|"company"|"news"|"analyst"|"community"|"social"|"user_note"|"unknown",
  "status": "enforced" | "aspirational",
  "detector_labels": {                 // optional; label ONLY clearly-judgeable aspects
    "causality": bool, "market_terms": bool, "manipulation_framing": bool,
    "action_language": bool, "target_price": bool, "position_sizing": bool,
    "trade_probability": bool, "private_or_unobservable": bool
  },
  "expected_claim_types": ["..."],     // optional; ACCEPTABLE set (values from schema.py CLAIM_TYPES)
  "expected_tiers": ["..."],           // optional; ACCEPTABLE set of low|medium|high|critical
  "masking": { "must_preserve": ["..."], "must_mask": ["..."] },  // optional; substrings
  "notes": "one-line rationale (English)"
}
```

Every case includes **at least one** of `detector_labels`,
`expected_claim_types`, `expected_tiers`, or `masking`. `expected_claim_types`
and `expected_tiers` are **acceptable sets** (kept tight, max 2–3) for the cases
where policy legitimately allows more than one outcome.

### Detector → system mapping (what the harness computes)

Build the `SourceRecord` as
`SourceRecord('g','g',source_type,'n',None,None,'2026-01-01',utc_now(),'observable','x.txt')`.

| label key | how it is computed |
|---|---|
| `causality` | `has_causality(text)` |
| `market_terms` | `has_market_terms(text)` |
| `manipulation_framing` | `has_manipulation_framing(text)` |
| `action_language` | `has_action_language(text)` |
| `target_price` | `"target_price_language" in detect_risk_flags(text, source_type, "finance")` |
| `position_sizing` | `has_position_sizing(text)` |
| `trade_probability` | `has_trade_probability(text) or has_future_return_projection(text)` |
| `private_or_unobservable` | `"private_or_inaccessible_source"` or `"unobservable_evidence"` in `detect_risk_flags(text, source_type, mode)` |
| claim type | `classify_claim(text, source, mode).claim_type` |
| tier | `classify_claim(text, source, mode).risk_tier` |
| masking | `sanitize_for_report(text, "finance")` — a `must_preserve` substring must remain, a `must_mask` substring must be gone |

Masking is only meaningful in finance mode; all `masking` cases use
`"mode": "finance"`.

---

## 2. Status semantics — the most important field

- **`enforced`** — the **current** system already produces every labeled aspect.
  These are regression guards: if the code regresses, the case flips to failing.
- **`aspirational`** — the **label is the correct policy**, but the current
  system fails it. These document known gaps and must NOT be "fixed" by editing
  the label.

**Rule: the label always encodes correct policy; `status` encodes current
reality.** Determine `status` empirically by running the detectors/classifier.
Set `status="enforced"` only when EVERY labeled aspect matches current behavior.
Never weaken a label to make a case enforced. If you become unsure the label
itself is right, delete the case.

**Drift trap (hard negatives):** the easiest way to corrupt the set is to label
a detector `false` because the current lexicon happens to miss the text, not
because policy says so. For every negative label ask: *"is this false because
policy says so, or because the lexicon misses it?"* If policy says true, label
it **true** and let the case be `aspirational` until the lexicon catches up.
Example: `물렸는데 그냥 존버 중입니다` — the lexicon once returned
`market_terms=False`, but 물리다/존버 are stock-position slang, so the policy label
is `true` (this gap has since been closed and the case is now enforced). The trap
also exists in the over-trigger direction: "The farmers' market opens every
Saturday" once returned `market_terms=True`, but policy says `false` (also now
closed via the physical-marketplace exclusion). If a term's market-ness is genuinely borderline (e.g.
`밸류에이션`, "the sector"), omit that detector key (and any tier label that
hinges on it) rather than keep a false label.

A case is "matched by the current system" iff **all** present labeled aspects
match: every `detector_labels` entry equals the computed detector, the claim type
is in `expected_claim_types`, the tier is in `expected_tiers`, every
`must_preserve` substring survives sanitize, and every `must_mask` substring is
removed. `enforced` ⇒ matched; `aspirational` ⇒ not matched.

---

## 3. Per-detector labeling rules (advice vs data)

The recurring judgement is **advice/interpretation vs. neutral data/description**.
Neutral market vocabulary must be preserved; advice must be flagged and masked.

**Unicode de-obfuscation (applies to EVERY detector + masking).** All detectors and
`sanitize_for_report` first run `normalize_for_matching`: it drops format /
zero-width / soft-hyphen and control chars (Unicode categories Cf/Cc, except
`\n`/`\t`), NFKC-normalizes (folds full-width `ｂｕｙ`/`４０％`, composes
NFD-decomposed Hangul), and folds a tight, documented Cyrillic/Greek homoglyph
whitelist to ASCII. So `b​uy`, `bуy` (Cyrillic), `bu­y`, `매​수`,
and NFD `매수`/`목표가` are all detected AND rendered de-obfuscated+masked. This is
deterministic (stdlib `unicodedata` only). Idempotent on clean ASCII/Hangul, so no
existing enforced case changed.

### causality (`has_causality`)
- **True (positive):** an explicit cause is asserted. KO connectives
  `때문에 / 탓에 / 여파로 / 덕분에 / 영향으로 / 인해`, KO markers `원인은 / 이유는`,
  EN `because / caused / triggered by / led to / due to / the real reason`.
- **False (hard negative):** description of a move with **no** causal connector
  (`코스피는 1.2% 하락 마감했다`), or an explicit **no-cause** disclaimer
  (`원인을 밝히지 않았다`, "no cause was stated"), or a schedule/announcement.
- **Closed:** `힘입어` (buoyed by — same force as `덕분에`) and `때문이라고`/`때문이다`
  are now in the connective set; `원인(은|이) … 밝혀지지 않` is now a no-cause
  disclaimer (suppresses the `원인은` marker when the sentence says the cause is
  unknown — policy **False**).
- **Closed (FIX 6, self-inflicted regression):** bare `인해`/`인한` used to
  substring-match inside innocent words (`확인해보세요`, `확인한 결과` — policy
  **False**), so they were replaced by connective-anchored patterns
  `(?:으로|로)\s*인해` / `(?:으로|로)\s*인한`. `수요 감소로 인해 …` / `규제 강화로 인한 …`
  stay **True**; `확인해/확인해 주세요/확인했습니다/확인한` are now **False**.
- **Gaps (aspirational, still open):** the connectives are a fixed list, so native
  `~아서/~어서` (`좋아서`, `커서`) remain missed. These are **deliberately left open**
  (`ko_fin_077`, `ko_fin_078`): `~아서/~어서` is ubiquitous non-causal grammar
  (`높아서`, `앉아서`, `만나서`), so any pattern general enough to catch the causal
  use over-triggers on ordinary sentences. Closing them would drop precision, so
  the policy label stays **True** and the cases stay aspirational.

### market_terms (`has_market_terms`)
- **True:** descriptive market/flow vocabulary — `코스피/코스닥/증시/주가/환율/금리`,
  `순매수/순매도/공매도/매도세/매수세/거래량`, EN `index/shares/turnover/volume/
  net selling/net buying/foreign investors`. This is **data vocabulary, not
  advice** — its presence is expected in clean market reports. Now also covered
  (previously aspirational, now enforced): `short interest`, `거래소` (exchange),
  `상장` (listing), `장 초반|중반|후반|막판|시작|마감|초|중|후` as the market session
  (NEVER bare `장`; a `(?<![가-힣])` lookbehind keeps `시장/공장/상장/입장` out), and
  position slang `물렸(다|는데|음…)/존버`.
- **Closed (FIX 3):** English plurals `yields / equities / bonds / treasuries /
  futures` are now market terms (`Treasury yields fell` => True, so the official
  causal sentence downgrades to `unverified_causality`). Bare `equity`/`bond`
  are **deliberately omitted** (home equity, social equity, chemical bond) as a
  fail-safe against non-market false positives.
- **Closed (FIX 5):** Korean sector/sentiment vocabulary `반도체 / 업종 / 섹터 /
  투자심리 / 투자 심리` are market terms, so `반도체 업황 개선 덕분에 …` fires the finance
  market-causality gate.
- **False:** non-market text; note `long`/`short` alone are NOT market terms
  ("a long history of short supply chains"), and neither are non-financial
  markets — `전통시장/야시장`. A farmers'/flea/fish/street/night market is also
  false: bare EN "market" is now a dedicated regex that **excludes** those
  physical-marketplace compounds (`en_gen_013` closed).

### manipulation_framing (`has_manipulation_framing`)
- **True:** an accusation of coordinated wrongdoing. KO strong markers fire alone
  (`작전주 / 주가조작 / 시세조종 / 개미털기 / 은폐`) and patterns `개미털기`, `짜고 치`,
  `미리 알고 팔`, `언론이 숨기`. KO **weak** markers (`작전 / 세력 / 조작 / 내부자`) fire
  **only with a certainty cue** (`무조건 / 확실하다 / 분명하다 / 누가 봐도 / 틀림없`).
  EN needs a proof frame: `this proves manipulation`, `coordinating exits`,
  `market drop was planned`, `media is hiding`, or `(manipulation|rigged)` +
  `(this proves|proves|obvious|everyone knows)`.
- **False (hard negative):** the same words in a neutral sense — 작전 (military/
  firefighting), 세력 (political/market-leading), 조작 (document-fraud news),
  "rules to deter market manipulation", "manipulated images … propaganda" — i.e.
  a weak marker with **no** certainty cue.
- **Closed:** bounded gaps are now allowed in `언론이.{0,20}숨기` (intervening words
  no longer defeat it); `세력.{0,10}짜고` (bounded gap, so compound particles like
  `세력들이` do not defeat it) fires without a certainty cue but ONLY with a market
  co-signal (`개미/물량/주가/종목/매집/시세/주식`) in the same text; and the English
  analog of `미리 알고 팔` — `insiders? … (dumped|sold|unloaded) … before` — is in
  the English lexicon. Guarded: `여당 세력이 예산안을 짜고` (drafting — the gap
  matches but there is no market co-signal) and `insiders traded … before`
  (no dump/sell cue) stay False.
- **Closed (FIX 5):** English progressive forms `manipulating / rigging` join the
  proof-framed regex (still require a `this proves/proves/obvious/everyone knows`
  cue, so `deter market manipulation` / `manipulating the spreadsheet` stay
  False). Korean statistics cover-up — `숫자를/통계를/수치를 축소` or `축소 …발표`
  paired with an authority/announcement cue (`정부/당국/발표/통계청/금융위/감독원/
  한국은행`) — is manipulation framing; the innocent `제품 크기를 축소` (no
  figure/announcement) stays False.

### action_language (`has_action_language`)
- **True:** an imperative/recommendation to trade. EN `buy/sell`, urgency
  (`buy now`, `load up`, `last chance`), trading `go long / short the / shorting`,
  ratings (`overweight rating`, `strong buy`). KO `풀매수/풀매도/몰빵/손절/익절/
  사세요/파세요/사라/팔아라/목표가/비중 확대`, and context-gated cues
  (`강력 추천 / 매수 추천 / 지금 들어가 / 올라타`) that require nearby finance context.
- **False (hard negative):** neutral flow **data** (`공매도 잔고 …증가`,
  `기관 순매수 규모 …집계`, `매도세가 강했다`), a regulator discussing short-selling
  **policy**, disclosure-policy discussion (`추천 종목 공시 제도`), and non-finance
  uses (`빙판길 조심하세요`, `이 책 강력 추천합니다`).
- **Closed:** spacing variants (`매 수 추천`, via spacing-tolerant `매\s*수`/`매\s*도`
  that keep the `순/공` lookbehinds), bare Korean+`long` (`long 잡`),
  `increase(d)/raise(d)/boost(ed) (your|their|his|her|my|our|the|its) exposure to
  this name/stock` (inflection-tolerant verbs, noun-anchored), and euphemism
  **conjunctions** that resist homographs: `담아야 할 자리` + a finance co-signal
  (`빚내/저점/분할/매수`); `타이밍` + `지금이/바로 그` + `놓치`; `물타기` + a
  first-person/rally cue (`들어갑니다/같이 가시죠`). Each is guarded by a negative
  (macro rate-timing, political `물타기 들어간다`, literal `이삿짐 … 담아야 할 자리`,
  `long term`, `exposure to sunlight`, bare `exposure to loud noise`).
- **Closed (FIX 7, over-block):** a NARROW meta-disclaimer whitelist neutralizes
  advice by removing only the disclaimer span before detection: `not a
  recommendation to buy or sell`, `is not (investment|financial) advice`, `not
  intended as (investment )?advice`, `for informational purposes only`, and Korean
  `투자 권유가 아닙니다/아니며`, `정보 제공 목적`. So `This is not a recommendation to buy
  or sell any security.` is **not** advice/masked, while a REAL advice sentence
  elsewhere (`You should buy now`, or `Buy XYZ now. This is not financial advice.`)
  still fires, and the ambiguous `I would not recommend ignoring this buy signal`
  STILL masks (fail-safe — no general negation handling).

### target_price (flag `target_price_language`)
- **True:** EN price-target lexicon (`target price / price target / upside target /
  downside target`, also embedded in KO), plus KO `목표주가 / 목표 주가` (target STOCK
  price) and hanja `目標價` which always fire.
- **False:** a price **level** that is a close/rate, not a target
  (`코스피는 2,640선에서 마감`, benchmark rate); `목표 수익률` is a return, not a target.
- **Closed (FIX 2):** bare `목\s*표\s*가` is now GATED — it fires as a price target
  only with an adjacent price/number co-signal
  (`만원/천원/원/억/상향/하향/제시/유지/도달/달성/돌파/디지트`). `목표주가` fires
  unconditionally. The goal-particle usage `목표(goal)+가(subject particle)` —
  `이번 조치의 목표가 물가 안정임을 강조했다`, `회사의 목표가 분명하다` — does **NOT**
  fire and is **not** masked.

### position_sizing (`has_position_sizing`)
- **True:** EN `position size / position sizing / allocate / allocating /
  allocation`, or `N% of (a|the|your|my) portfolio`.
- **False:** a percentage that is a stat, ownership, turnover, or index move —
  not a portfolio allocation.
- **Closed:** KO `비중 (…) 확대/축소/조절` now fires `has_position_sizing`. Tight
  form (particle + optional 크게/소폭/대폭 adverb) so passive
  `보유 비중이 사상 최고로 확대됐다` (ownership share) stays False.
- **Closed (FIX 1):** a Korean number-WORD/quantity may intervene between 비중 and
  확대/축소/조절 (`비중을 삼십 프로 확대` — number-words defeat numeric `%` patterns).
  The gap is restricted to number-words/digits/percent so `사상 최고로` cannot
  bridge it (ko_fin_084 passive case still False).
- **Closed (FIX 4):** when 비중 is modified by a product/revenue/segment noun
  (`제품/매출/사업/부문/제품군/매출액/원가`) it is business-MIX strategy, NOT portfolio
  allocation, so `고부가가치 제품 비중을 확대` does **not** fire and is **not** masked.
  Portfolio nouns (`포트폴리오/자산/주식/종목/섹터 비중 확대`) and bare `비중 확대` still fire.

### trade_probability (`has_trade_probability` OR `has_future_return_projection`)
- **True:** numeric win-odds or a forward return — KO `확률 N / 승률 N / N% 수익률 /
  N배 수익 / 목표 수익률 N`, EN `N% chance|probability|odds`,
  `probability of success`, `N x return/gain`, `could produce a … return`,
  `return within N days`.
- **False (hard negative):** statistics that are not trade odds/returns — margin
  of error, unemployment/poll/approval percentages, bond yield, dividend yield,
  a **realized** index move, weather probability.
- **Closed:** verbal odds without digits — KO `열에 아홉` (nine of ten) and EN
  `(nearly|almost) always … profit` — now fire. `열에 아홉` is a common general
  idiom, so it is gated on a finance/profit co-signal
  (`오르/먹/수익/익절/승률/번다/자리/종목`) in the same text; `열에 아홉은 감기몸살이
  원인이다` stays False (and unmasked). Also guarded by `train nearly always runs
  on time` (no profit outcome → False). Sanitize now also masks `승률 N%`
  (was leaking).
- **Known over-block — DELIBERATELY KEPT (D15, aspirational `en_fin_066`):**
  `Futures markets are pricing in an 80% probability of a quarter-point cut` is a
  neutral market-implied odd, not a retail trade tip, so policy says it should NOT
  mask. But reliably distinguishing market-implied odds from advice risks
  **under-blocking real advice**, so `has_trade_probability` is intentionally NOT
  weakened and the case stays a fail-safe over-block. The case encodes this as a
  masking `must_preserve` miss (aspirational), and the `trade_probability`
  detector key is intentionally OMITTED from its labels — labeling it `false`
  while the system returns `true` would register a detector false positive and
  drop precision below 1.000, which is exactly what we must not do.

### private_or_unobservable (`private_or_inaccessible_source` / `unobservable_evidence`)
- **True:** inaccessible/closed evidence — KO `단톡방 / 카톡방 / 텔레그램방 / 리딩방 /
  유료방 / 삭제된 글 / 지워진 글 / 비공개 카페 / 회원 전용`, and the
  `삭제된 … 캡처` (deleted screenshot) combination; EN `deleted post / private
  group / members-only / internal desk / deleted screenshot`.
- **False (hard negative):** public sources — public IR/filing/bulletin,
  disclosure, press conference, a screenshot of a **public** dashboard (a bare
  `캡처`/screenshot is NOT private; only a *deleted* one is).
- **Closed:** a deleted/erased open-chat (`지워진`/`삭제된` + `오픈채팅`) is now
  caught. A public (non-deleted) `오픈채팅방 공지` stays False.

### Masking rules (`sanitize_for_report(text, "finance")`)
- **`must_preserve`:** neutral finance vocabulary that must survive — `공매도`,
  `순매수`, `순매도`, `매도세`, `매수세`, `추천 종목` (disclosure policy),
  `short interest`, `net selling`, `long-term outlook`, `long history`,
  `short supply`.
- **`must_mask`:** advice/target/allocation/probability that must be replaced by a
  `[blocked-…]`/`[redacted-…]` token — `목표가`, `매수 추천`, `비중 확대`, `풀매수`,
  `몰빵`, `buy`, `go long`, `price target`, `allocate`, `N% 수익률`, `확률 N`.
- Pick `must_mask` substrings that do **not** appear inside the replacement token
  (e.g. avoid the literal word `allocation`, which is echoed by
  `[blocked-allocation-language]`).
- **Masking gaps — CLOSED:** imperative `사라` (tight `사라(?![가-힣])` so
  `사라졌다/사라져` are preserved) / `팔아라`, `승률 N%`, and a Latin token followed by
  a Hangul particle (`target price를`, `allocation을`) are now all masked. The
  Latin↔Hangul fix replaces `\b` with ASCII-aware lookarounds
  (`(?<![A-Za-z0-9])` / `(?![A-Za-z0-9])`) across the English sanitize AND
  detection patterns (advice/target/position/probability/rating/urgency/long-short),
  since Python `\b` does not fire between an ASCII letter and a Hangul syllable.
- **Masking — CLOSED (FIX 1/2/4/7):** `sanitize_for_report` de-obfuscates FIRST
  (see the Unicode note above), so zero-width/homoglyph/full-width/NFD advice is
  masked and rendered clean. `목표주가`/gated `목표가` masks to
  `[blocked-price-level]` (goal-particle `목표가` is preserved); Korean allocation
  masking honors the number-word gap AND the product-mix guard (`제품 비중을 확대`
  preserved, `비중을 삼십 프로 확대` masked). Narrow advice disclaimers are protected
  during masking (buy/sell inside `not a recommendation to buy or sell` survive).

---

## 4. Classification cases (source_type × mode)

Label `expected_claim_types` (+ optional `expected_tiers`) with the tight set of
outcomes policy allows. Anchors observed in `classification.py`:

- **Finance action/target/allocation/probability language ⇒ `excluded`,
  `critical`** — highest priority; outranks the unobservable branch.
- **official** finance + market + number, no causal ⇒ `market_observation` (low);
  status line ⇒ `official_reported_status`; official causal-motive over market ⇒
  `unverified_causality` (high, `official_data_causality_mismatch`).
- **company** ⇒ `confirmed_fact` for company-specific facts, but `unverified_causality`
  when it asserts broad market causality.
- **analyst** ⇒ `interpretation` by default; true-cause market claim ⇒
  `unverified_causality`.
- **news** causal (finance-market or general) ⇒ `unverified_causality`; else
  market+number ⇒ `market_observation`; framing/loaded ⇒ `opinion_or_frame`.
- **community/social** never `confirmed_fact`: manipulation ⇒ `rumor`, causal ⇒
  `unverified_causality`, framing ⇒ `opinion_or_frame`, else `reported_claim`.
- **unknown/user_note** causal ⇒ `unverified_causality`; else weak ⇒
  `needs_official_source`.
- Tier: `unverified_causality/unobservable/excluded/rumor` and the high flags map
  to **high** (finance critical flags ⇒ **critical**); `unsupported_causality /
  framing_risk / loaded_language / strong_certainty_language /
  needs_official_confirmation` ⇒ **medium**; otherwise **low**.

---

## 5. How to add a case

1. Write a fresh, realistic sentence in the right register (regulator notice,
   market wrap, analyst note, forum 구어체 with slang, social one-liner). Do not
   copy personal data or long verbatim passages from captured samples.
2. Decide the **policy-correct** labels first (advice vs data, correct claim
   type/tier, what must be preserved/masked). Keep acceptable sets tight.
3. **Run the actual functions** on the sentence (detectors, `detect_risk_flags`,
   `sanitize_for_report`, `classify_claim` with the SourceRecord above).
4. If current behavior matches every labeled aspect ⇒ `status="enforced"`.
   If it diverges ⇒ keep the policy-correct label and set
   `status="aspirational"`, and describe the gap in `notes`.
5. Never change a label just to make a case enforced. If unsure the label is
   right, drop the case.

### Validation

A case matches current behavior iff all labeled aspects match. The set is valid
when: ids are unique and sorted, all enums are in range, every case has ≥1
labeled aspect, **zero** `enforced` cases fail current behavior, and **zero**
`aspirational` cases pass it. Re-run this check after any edit.
