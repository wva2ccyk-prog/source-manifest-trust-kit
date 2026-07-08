from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Unicode de-obfuscation for matching (FIX 1)
# ---------------------------------------------------------------------------
# Detection and masking must be resistant to zero-width / homoglyph / full-width
# smuggling. normalize_for_matching runs deterministically (stdlib unicodedata
# only, no network/LLM) and is applied at the entry of every detector and at the
# top of sanitize_for_report, so one inserted format char, one Cyrillic/Greek
# lookalike, or an NFD-split Hangul syllable can no longer slip a claim past
# detection (and past masking).
#
# Structure chars kept so multi-line report text is not merged.
_FORMAT_CHARS_TO_KEEP = {"\n", "\t"}
# Explicit belt-and-suspenders set in case a unicodedata version categorizes any
# of these outside Cf (they are all Cf in modern Unicode, but pin them anyway).
_EXPLICIT_STRIP = {
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "﻿",  # zero-width no-break space / BOM
    "­",  # soft hyphen
    "⁠",  # word joiner
    "᠎",  # Mongolian vowel separator
}
# Tight, documented Latin-lookalike confusable fold. Only the Cyrillic and Greek
# letters that appear in the finance/advice lexicon (buy, sell, short, long,
# entry, exit, target, price, stop, loss, profit, position, size, margin, rate)
# are mapped to ASCII. This is a whitelist, not a general confusables table:
# folding is deterministic and never touches Hangul or ordinary ASCII.
_CONFUSABLE_MAP = {
    # Cyrillic lowercase -> ASCII
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "к": "k", "і": "i", "ѕ": "s", "ј": "j", "т": "t",
    # Cyrillic uppercase -> ASCII
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "У": "Y", "Х": "X",
    "К": "K", "І": "I", "Ѕ": "S", "Т": "T", "В": "B", "Н": "H", "М": "M",
    # Greek lowercase -> ASCII
    "ο": "o", "α": "a", "ε": "e", "ρ": "p", "χ": "x", "κ": "k", "ι": "i",
    "ν": "v", "τ": "t",
    # Greek uppercase -> ASCII
    "Ο": "O", "Α": "A", "Ε": "E", "Ρ": "P", "Χ": "X", "Κ": "K", "Ι": "I",
    "Τ": "T", "Β": "B", "Η": "H", "Μ": "M", "Ν": "N",
}
_CONFUSABLE_TABLE = {ord(key): value for key, value in _CONFUSABLE_MAP.items()}


def normalize_for_matching(text: str) -> str:
    """Deterministically de-obfuscate text before pattern matching (FIX 1).

    Steps:
      1. Drop Unicode format / zero-width / soft-hyphen and control chars
         (categories Cf/Cc, except ``\\n``/``\\t``) so an inserted U+200B / U+00AD
         / U+FEFF cannot split a lexicon word (``b\\u200buy``, ``se\\u00adll``,
         ``매\\u200b수``).
      2. NFKC-normalize to fold full-width forms (``ｂｕｙ`` / ``４０％``),
         compatibility characters, and to compose NFD-decomposed Hangul.
      3. Fold the tight Cyrillic/Greek homoglyph whitelist to ASCII
         (``bуy`` -> ``buy``, ``sеll`` -> ``sell``).

    Deterministic and idempotent on clean ASCII / composed Hangul. stdlib only.
    """
    if not text:
        return text
    kept: list[str] = []
    for char in text:
        if char in _FORMAT_CHARS_TO_KEEP:
            kept.append(char)
            continue
        if char in _EXPLICIT_STRIP:
            continue
        if unicodedata.category(char) in ("Cf", "Cc"):
            continue
        kept.append(char)
    normalized = unicodedata.normalize("NFKC", "".join(kept))
    return normalized.translate(_CONFUSABLE_TABLE)


# ---------------------------------------------------------------------------
# Advice disclaimers (FIX 7) — narrow meta-disclaimer whitelist
# ---------------------------------------------------------------------------
# A sentence that explicitly disclaims advice ("not a recommendation to buy or
# sell", "for informational purposes only", "투자 권유가 아닙니다") must not be
# masked/excluded on the strength of the buy/sell tokens INSIDE the disclaimer.
# This is a deliberately NARROW whitelist: anything ambiguous still masks
# (fail-safe against under-blocking). It neutralizes advice ONLY by removing the
# whitelisted phrase span; any real advice elsewhere in the same text still fires.
_ADVICE_DISCLAIMER_PATTERNS = (
    r"not\s+a\s+recommendation\s+to\s+buy\s+or\s+sell",
    r"is\s+not\s+(?:investment|financial)\s+advice",
    r"not\s+intended\s+as\s+(?:investment\s+)?advice",
    r"for\s+informational\s+purposes\s+only",
    r"투자\s*권유가?\s*아(?:닙니다|니며|님)",
    r"정보\s*제공\s*목적",
)


def _strip_advice_disclaimers(text: str) -> str:
    stripped = text
    for pattern in _ADVICE_DISCLAIMER_PATTERNS:
        stripped = re.sub(pattern, " ", stripped, flags=re.IGNORECASE)
    return stripped


# ---------------------------------------------------------------------------
# Causal markers
# ---------------------------------------------------------------------------
CAUSAL_MARKERS = {"because", "caused", "triggered", "led to", "as a result", "therefore", "due to", "the reason", "the real reason", "true cause", "true reason", "explains the move", "immediately reacted"}
NO_CAUSE_MARKERS = {"did not state a cause", "did not provide a cause", "without stating a cause", "no cause was stated"}
# Korean causal connectives (plain substring is safe for Hangul).
KOREAN_CAUSAL_MARKERS = {
    "때문에",
    "때문이",  # 때문이라고 / 때문이다 / 때문입니다 — same causal force as 때문에
    "탓에",
    "탓이다",
    "덕분에",
    "힘입어",  # "buoyed by / thanks to" — same causal force as 덕분에
    "영향으로",
    "여파로",
    "원인이다",
    "원인은",
    "이유는",
    "이유다",
}
# FIX 6 (self-inflicted regression): bare 인해/인한 substring-match inside innocent
# words (확인해보세요 → contains 인해; 확인한 → contains 인한), so they were removed
# from the plain-substring marker set above. The real causal form always carries
# the connective particle 로/으로, so require it. This keeps "수요 감소로 인해
# 하락했다" causal while making 확인해/확인한/확인했 non-causal.
KOREAN_CAUSAL_PATTERNS = (
    r"(?:으로|로)\s*인해",
    r"(?:으로|로)\s*인한",
)
# Korean "no cause was stated" style disclaimers (regex to allow particle variation).
# The 밝혀지지 않 form negates causality even though the 원인은 marker is present:
# the sentence says the cause is UNKNOWN, not that a cause is asserted.
KOREAN_NO_CAUSE_PATTERNS = (
    r"원인을?\s*밝히지\s*않",
    r"이유를?\s*밝히지\s*않",
    r"원인(?:은|이|을)?.{0,10}밝혀지지\s*않",
    r"이유(?:는|가|를)?.{0,10}밝혀지지\s*않",
)

# ---------------------------------------------------------------------------
# Certainty / framing / loaded language
# ---------------------------------------------------------------------------
STRONG_CERTAINTY = {
    # English
    "true reason", "real reason", "confirmed truth", "everyone knows", "no doubt", "guaranteed", "certain", "inevitable", "this proves", "obvious",
    # Korean
    "무조건", "확실하다", "확실합니다", "분명하다", "누가 봐도", "틀림없", "100프로", "100퍼",
}
LOADED_LANGUAGE = {
    # English
    "shock", "bombshell", "disaster", "panic", "collapse", "crash", "treason", "traitor", "rigged", "manipulated", "propaganda", "destroyed confidence",
    # Korean
    "폭락", "패닉", "충격", "붕괴", "대참사", "폭탄",
}
FRAME_LANGUAGE = LOADED_LANGUAGE | {"far right", "far left", "policy disaster", "political risk"}

# ---------------------------------------------------------------------------
# Private / unobservable source markers
# ---------------------------------------------------------------------------
PRIVATE_MARKERS = {
    # English
    "private chat", "private group", "members-only", "member-only", "closed community", "deleted post", "deleted comments", "inaccessible", "paywalled", "internal desk", "proprietary",
    # Korean (NOTE: bare 캡처/screenshot is intentionally excluded — screenshots are
    # ubiquitous; only a *deleted* screenshot is unobservable, handled in detect_risk_flags)
    "단톡방", "카톡방", "텔레그램방", "텔레그램 방", "리딩방", "유료방",
    "삭제된 글", "삭제된 게시글", "삭제된 댓글", "지워진 글",
    "비공개 카페", "회원 전용", "유료 기사", "내부 메신저",
}

# ---------------------------------------------------------------------------
# Market / flow terms
# ---------------------------------------------------------------------------
# NOTE: bare English "market" is intentionally NOT in this set — it is handled by
# a dedicated regex in has_market_terms that excludes physical marketplaces
# (farmers'/flea/fish/street/night market). "short interest" is a market datum.
MARKET_TERMS = {
    # English
    "stock", "stocks", "shares", "index", "exchange", "turnover", "volume", "foreign investors", "institutional investors", "net selling", "net buying", "selloff", "rally", "yield", "currency", "fund managers", "funds", "short interest",
    # English plurals / common forms (FIX 3). Only unambiguous market plurals are
    # added; bare "bond"/"equity" are intentionally omitted (chemical bond, home
    # equity, social equity) to avoid non-market false positives.
    "yields", "equities", "bonds", "treasuries", "futures",
    # Korean (descriptive market-data vocabulary — NOT advice)
    "코스피", "코스닥", "증시", "주가", "주식", "지수", "환율", "금리", "채권", "선물",
    "외국인", "기관", "개미", "개인 투자자", "거래소", "상장",
    "순매수", "순매도", "공매도", "매도세", "매수세", "매물",
    "거래량", "시가총액", "급락", "급등", "폭락", "폭등", "랠리", "하락장", "상승장", "펀드", "종목",
    # Korean sector / sentiment vocabulary (FIX 5) so a causal claim like
    # "반도체 업황 개선 덕분에 …" fires the finance market-causality gate.
    "반도체", "업종", "섹터", "투자심리", "투자 심리",
}

# Bare English "market" as a financial term, EXCLUDING physical marketplaces.
_FINANCIAL_MARKET_RE = re.compile(r"(?<![a-z0-9])market(?![a-z0-9])")
_PHYSICAL_MARKET_RE = re.compile(
    r"(?:farmers?'?|flea|fish|street|night|wet|meat|flower|super|open[\s-]?air)\s*market"
)
# Korean market-session forms of 장 (NEVER bare 장); the lookbehind keeps 시장/공장/
# 상장/입장/등장/개장 from matching.
_KOREAN_MARKET_SESSION_RE = re.compile(r"(?<![가-힣])장\s*(?:초반|중반|후반|막판|초|중|후|시작|마감)")
# Korean stock-position slang ("stuck in a losing position" / "hold on for dear life").
_KOREAN_MARKET_SLANG_PATTERNS = (r"물렸(?:다|는데|음|어|네|고)", r"존버")
FLOW_TERMS = {
    # English
    "foreign investors", "institutional investors", "net selling", "net buying", "fund managers", "flows", "sold heavily", "selling", "investors sold", "coordinating exits",
    # Korean
    "외국인 순매도", "외국인 순매수", "기관 순매도", "기관 순매수", "수급",
}

# ---------------------------------------------------------------------------
# Motive markers (narrowed: bare "headline"/"policy"/"rumor"/"commentary"/
# "interpretation"/"translation"/"translated" removed to stop over-matching;
# specific multi-word motive phrases retained)
# ---------------------------------------------------------------------------
MOTIVE_MARKERS = {
    "investors sold",
    "funds sold",
    "overseas desks",
    "global desks",
    "policy headline",
    "translated policy",
    "market commentary",
}

# ---------------------------------------------------------------------------
# Manipulation markers
# ---------------------------------------------------------------------------
MANIPULATION_MARKERS = {
    # English
    "everyone knows this proves manipulation",
    "allegedly shows",
    "coordinating exits",
    "market drop was planned",
    "the market was planned",
    "media is hiding",
    "media hiding",
    "hiding the evidence",
    "cover up",
    "this proves manipulation",
    "proves manipulation",
    "obvious manipulation",
    "insiders coordinated",
    "insiders coordinated to force liquidations",
    "no primary records",
    "no primary records were posted",
}
# Korean manipulation markers that are unambiguous and trip on their own.
KOREAN_MANIPULATION_STRONG = {"작전주", "주가조작", "시세조종", "개미털기", "은폐"}
KOREAN_MANIPULATION_STRONG_PATTERNS = (
    r"개미.{0,3}털",
    r"짜고\s*치",
    r"미리\s*알고\s*팔",
    r"언론이.{0,20}숨기",  # allow intervening words: 언론이 이 사실을 …숨기고
    r"증거를\s*숨기",
)
# 세력 + 짜고 with a bounded gap (compound particles like 들이 must not defeat it)
# is a collusion accusation only with a market co-signal in the same text, so a
# political faction drafting a budget (여당 세력이 예산안을 짜고) stays out.
_KOREAN_COLLUSION_RE = re.compile(r"세력.{0,10}짜고")
_KOREAN_COLLUSION_CUES = ("개미", "물량", "주가", "종목", "매집", "시세", "주식")
# English manipulation narratives that the phrase lexicon misses. Insiders selling
# on foreknowledge "before" the news is the English analog of 미리 알고 팔.
ENGLISH_MANIPULATION_PATTERNS = (
    r"insiders?\s+(?:\w+\s+){0,3}(?:dumped|sold|unloaded)\s+(?:\w+\s+){0,4}before",
)
# Korean cover-up / statistics-suppression framing (FIX 5): under-reporting a
# figure ("숫자를 축소해서 발표", "통계를 축소") is a manipulation cue ONLY when an
# authority/announcement actor is present, so an innocent "제품 크기를 축소" (shrank
# the product size) does not fire.
_KOREAN_COVERUP_RE = re.compile(
    r"축소\s*(?:해서|하여|해)?\s*발표"
    r"|숫자(?:를|가)?\s*축소"
    r"|통계(?:를|가)?\s*축소"
    r"|수치(?:를|가)?\s*축소"
)
_KOREAN_COVERUP_CUES = ("정부", "당국", "발표", "통계청", "금융위", "감독원", "한국은행", "수치")
# Weak Korean markers require a nearby certainty cue so neutral news
# ("시장 주도 세력이 매수에 나섰다") is not treated as manipulation.
KOREAN_MANIPULATION_WEAK = {"작전", "세력", "조작", "내부자"}
KOREAN_CERTAINTY_CUES = {"무조건", "확실하다", "확실합니다", "분명하다", "누가 봐도", "틀림없", "100프로", "100퍼"}

# ---------------------------------------------------------------------------
# Advice / action language
# ---------------------------------------------------------------------------
# Bare "long"/"short" removed — they require explicit trading context (below).
ADVICE_TERMS = {"buy", "sell", "entry", "exit", "stop loss", "take profit", "position size", "position sizing", "allocate", "allocating", "allocation", "trade this"}

# English long/short only count with explicit trading context.
LONG_SHORT_PATTERNS = (
    r"(?<![a-z0-9])go(?:ing)?\s+long(?![a-z0-9])",
    r"(?<![a-z0-9])go(?:ing)?\s+short(?![a-z0-9])",
    r"(?<![a-z0-9])short\s+the(?![a-z0-9])",
    r"(?<![a-z0-9])long\s+the(?![a-z0-9])",
    r"(?<![a-z0-9])(?:long|short)\s+position(?![a-z0-9])",
    r"(?<![a-z0-9])(?:long|short)\s+(?:the\s+)?(?:stock|shares|index)(?![a-z0-9])",
    r"(?<![a-z0-9])shorting(?![a-z0-9])",
)

# Korean advice patterns that are unambiguous regardless of surrounding context.
# 매수/매도 use a negative lookbehind for 순/공 (순매도/공매도 are neutral market
# data) and require an action suffix so 매도세/매수세 do not match; 풀매도/풀매수
# ("sell/buy everything") ARE advice and are listed explicitly.
# 매수/매도 tolerate internal spacing (매 수/매 도) but the negative lookbehinds
# still keep the neutral market-data terms 순매수/공매도 (spaced or not) from firing.
_MAESU_SUFFIX = r"(?:\s*하|\s*해|\s*는|\s*를|\s*가|\s*추천|\s*의견)"
KOREAN_ADVICE_PATTERNS = (
    r"(?<![순공])(?<!순\s)(?<!공\s)매\s*수" + _MAESU_SUFFIX,
    r"(?<![순공])(?<!순\s)(?<!공\s)매\s*도" + _MAESU_SUFFIX,
    r"풀매수",
    r"풀매도",
    r"몰빵",
    r"손절(?:하|해|은|을|각)?",
    r"익절(?:하|해|은|을|각)?",
    r"사세요",
    r"파세요",
    r"사라(?![가-힣])",
    r"팔아라",
    # NOTE: bare 목표가 is deliberately NOT here (FIX 2). It is handled by the
    # gated _KOREAN_TARGET_PRICE_RE so 목표(goal)+가(particle) usages such as
    # "회사의 목표가 분명하다" / "이번 조치의 목표가 물가 안정" do NOT fire as advice.
    r"(?<![A-Za-z])long\s*잡",  # "long 잡(으면)" — take a long position
    r"(?<![A-Za-z])short\s*잡",
    r"비중\s*(?:확대|축소|조절|줄|늘)",
    r"주식\s*안\s*합니다",
    r"주식안합니다",
    r"사고\s*팔고",
)
# Korean advice patterns that must only fire inside finance/market context to
# avoid false positives ("빙판길 조심하세요", "공을 던졌다", "이 책 강력 추천").
KOREAN_CONTEXT_ADVICE_PATTERNS = (
    r"조심(?:들)?(?:하|해|하세요|해야)",
    r"다\s*던졌(?:다|어요|습니다)?",
    r"던졌(?:다|어요|습니다)?",
    r"들어가라",
    r"들어가세요",
    r"지금\s*들어가",
    r"올라타",
    r"강력\s*추천",
    r"(?:매수|매도|종목)\s*추천",
    r"추천(?:합니다|해요|해라|하라|드립니다|드려요|한다|하는|했)",
    # Public-specific: 권고 (recommend/urge) counts as advice only in finance
    # context, so "건강한 식습관을 권고한다" (general) does not fire.
    r"권고(?:한다|합니다|했다|하라|하며|하고|하는|할|를|을)?",
)

# Terms that establish Korean finance/market context for gating weak cues.
KOREAN_FINANCE_CONTEXT = {
    "환율", "주식", "주가", "증시", "코스피", "코스닥", "지수", "종목", "매매",
    "수익", "수익률", "투자", "펀드", "선물", "채권", "금리", "외국인", "기관",
    "개미", "시장", "증권", "넥장", "익절", "손절", "매수", "매도", "공매도",
    "순매수", "순매도",
}

URGENCY_ACTION_TERMS = {
    "act now",
    "before it is too late",
    "before it's too late",
    "dont miss out",
    "don't miss out",
    "get in before",
    "last chance",
    "load up",
}
TARGET_TERMS = {"target price", "price target", "upside target", "downside target"}
# Korean/hanja price-target forms that the English-only flag lexicon misses.
# FIX 2: 목표주가 / 목표 주가 (target STOCK price — the most common phrasing) always
# fires, as does hanja 目標價. Bare 목표가 (spacing-tolerant) only fires as a PRICE
# target when a price/number co-signal follows in the same sentence, so
# 목표(goal)+가(subject particle) — "회사의 목표가 분명하다", "이번 조치의 목표가 물가
# 안정임을 강조했다" — does NOT fire.
_KOREAN_TARGET_PRICE_PATTERN = (
    r"목\s*표\s*주\s*가"
    r"|目標價"
    r"|목\s*표\s*가(?=[^.!?\n]{0,15}(?:만원|천원|원|억|상향|하향|제시|유지|도달|달성|돌파|\d))"
)
_KOREAN_TARGET_PRICE_RE = re.compile(_KOREAN_TARGET_PRICE_PATTERN)


def _has_korean_target_price(text: str) -> bool:
    return bool(_KOREAN_TARGET_PRICE_RE.search(text))
POSITION_TERMS = {"position size", "position sizing", "allocate", "allocating", "allocation"}
# Korean allocation-advice forms for has_position_sizing (English-only otherwise).
# Tight: 비중 + optional particle/adverb + optional Korean number-word quantity +
# 확대/축소/조절, so descriptive "외국인 보유 비중이 사상 최고로 확대됐다" (ownership
# share expanded) does not fire, while "비중을 삼십 프로 확대하세요" (FIX 1 — a
# number-WORD between 비중 and 확대 that defeats numeric % patterns) does.
# The intervening quantity is restricted to number-words/digits/percent so a
# non-quantity phrase like "사상 최고로" cannot bridge the gap.
_KOREAN_QTY_GAP = r"(?:[영공일이삼사오육륙칠팔구십백천만억조\d]+\s*(?:프로|퍼센트|퍼|%)?\s*)?"
_KOREAN_SIZING_DETECT_RE = re.compile(
    r"비중\s*(?:을|를|이|은|는)?\s*(?:크게\s*|소폭\s*|대폭\s*)?" + _KOREAN_QTY_GAP + r"(?:확대|축소|조절)"
)
# Masking variant additionally covers 줄이/늘리 (reduce/increase) endings.
_KOREAN_SIZING_MASK_RE = re.compile(
    r"비중\s*(?:을|를|이|은|는)?\s*(?:크게\s*|소폭\s*|대폭\s*)?" + _KOREAN_QTY_GAP + r"(?:확대|축소|조절|줄|늘)"
)
# FIX 4: when 비중 is modified by a product/revenue/segment noun it is a
# business-MIX strategy ("고부가가치 제품 비중을 확대"), not portfolio allocation, so
# the sizing pattern must NOT fire. Portfolio nouns (포트폴리오/자산/주식/종목/섹터)
# and bare 비중 확대 still fire.
_PRODUCT_MIX_PRECEDING_RE = re.compile(r"(?:제품군|매출액|제품|매출|사업|부문|원가)\s*$")


def _korean_position_sizing_hits(text: str, regex: re.Pattern[str]) -> list[re.Match[str]]:
    hits: list[re.Match[str]] = []
    for match in regex.finditer(text):
        preceding = text[: match.start()]
        if _PRODUCT_MIX_PRECEDING_RE.search(preceding):
            continue  # product/revenue mix, not portfolio allocation
        hits.append(match)
    return hits


def _has_korean_position_sizing(text: str) -> bool:
    return bool(_korean_position_sizing_hits(text, _KOREAN_SIZING_DETECT_RE))
# English advice paraphrases without a lexicon term. "increase(d) your/their
# exposure to this name/stock" is buy advice; verbs are inflection-tolerant and the
# noun anchor keeps "exposure to sunlight/noise" out.
_EXPOSURE_ADVICE = (
    r"(?<![a-z])(?:increas\w*|rais\w*|add(?:s|ed|ing)?\s+to|boost\w*|upp?ed|up)\s+"
    r"(?:(?:your|their|his|her|my|our|the|its)\s+)?"
    r"(?:market\s+|equity\s+|portfolio\s+)?exposure\s+to\s+(?:this|that|the)\s+"
    r"(?:name|stock|stocks|share|shares|position|sector|trade|company|ticker)"
)
ENGLISH_ADVICE_PATTERNS = (
    _EXPOSURE_ADVICE,
    # Public-specific: buy-side inflections (buys/buying/bought) are trading
    # action. Deliberately NOT long/short inflections here — bare long/short must
    # stay non-advice ("a long history of short supply"). Inert on the gold set.
    r"(?<![a-z0-9])(?:buys|buying|bought)(?![a-z0-9])",
)
INVESTMENT_RATING_PATTERNS = (
    r"(?<![a-z0-9])(?:overweight|underweight|outperform|underperform)\s+(?:rating|view|call|stance)(?![a-z0-9])",
    r"(?<![a-z0-9])(?:maintain|maintains|maintained|upgrade|upgrades|downgrade|downgrades|initiate|initiates)\s+(?:an?\s+)?(?:overweight|underweight|outperform|underperform)(?![a-z0-9])",
    r"(?<![a-z0-9])(?:strong\s+buy|buy\s+rating|sell\s+rating|hold\s+rating)(?![a-z0-9])",
)
TRUE_CAUSE_TERMS = {"true reason", "real reason", "true cause", "the market moved because", "caused the selloff"}
# Korean "the real reason/cause" framing.
KOREAN_TRUE_CAUSE_MARKERS = {"진짜 이유", "진짜 원인", "실제 이유", "실제 원인"}

# ---------------------------------------------------------------------------
# Public-specific finance-hype / security-price-projection heuristics
# ---------------------------------------------------------------------------
# These are PUBLIC-lineage safety detectors that the private lineage does not
# ship. They are preserved here (they are legitimate advice/target signals, not
# bugs) and are inert on the ported gold set (no gold case matches them).
# Ticker->price ("MU is going to $1300") and floor-teaser ("still under 800").
SECURITY_PRICE_PROJECTION_PATTERNS = (
    r"\b[A-Z]{1,6}\b\s+(?:is\s+)?(?:going\s+to|goes\s+to|will\s+(?:go\s+to|reach|hit)|to)\s+\$?\d{2,6}(?:,\d{3})?(?:\.\d+)?\b",
    r"\b(?:while\s+it\s+is\s+)?still\s+under\s+\$?\d{2,6}(?:,\d{3})?(?:\.\d+)?\b",
)
FINANCE_HYPE_ACTION_PATTERNS = (
    r"\bbetter\s+(?:hop|jump|get)\s+(?:on|in)\b",
    r"\bhop\s+on\s+the\s+ride\b",
    r"\bgo(?:es|ing)?\s+to\s+the\s+moon\b",
)


def has_security_price_projection(text: str) -> bool:
    normalized = normalize_for_matching(text)
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in SECURITY_PRICE_PROJECTION_PATTERNS)


def has_finance_hype_action_language(text: str) -> bool:
    normalized = normalize_for_matching(text)
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in FINANCE_HYPE_ACTION_PATTERNS)

# ---------------------------------------------------------------------------
# Probability / return projection patterns
# ---------------------------------------------------------------------------
KOREAN_PROBABILITY_PATTERNS = (
    r"확률\s*\d+",
    r"\d+\s*(?:%|프로|퍼센트)\s*확률",
    r"승률\s*\d+",
)
# "열에 아홉" (nine out of ten) is a common general-language idiom (열에 아홉은
# 감기몸살이 원인이다), so it only counts as verbal win-odds when a finance/profit
# co-signal appears in the same text.
_KOREAN_VERBAL_ODDS_RE = re.compile(r"열\s*에\s*아홉")
_KOREAN_VERBAL_ODDS_CUES = ("오르", "먹", "수익", "익절", "승률", "번다", "자리", "종목")
# English verbal win-odds without a numeric percentage.
ENGLISH_PROBABILITY_PATTERNS = (
    r"(?:nearly|almost)\s+always\s+(?:\w+\s+){0,4}profit",
)
KOREAN_RETURN_PATTERNS = (
    r"수익률\s*\d",
    r"\d+\s*(?:%|프로|퍼센트)?\s*수익률",
    r"\d+배\s*(?:수익|상승)",
    r"목표\s*수익률\s*\d",
)

# Korean temporal words that imply a "now"/recency framing (stale-date risk).
KOREAN_TEMPORAL_MARKERS = {"오늘", "어제", "방금", "최근", "현재", "오늘자"}


def contains_phrase(text: str, phrases: set[str]) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in phrases)


def has_number(text: str) -> bool:
    return bool(re.search(r"\d", text))


def _contains_phrase_boundary(text: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return bool(re.search(pattern, text.lower()))


def _contains_any_boundary(text: str, phrases: set[str]) -> bool:
    # Boundary-safe for English phrases ("policy" won't match "policyholder",
    # "collapse" won't match "collapsed"); harmless for Korean phrases because the
    # [a-z0-9] lookarounds never fire between Hangul syllables.
    return any(_contains_phrase_boundary(text, phrase) for phrase in phrases)


def _has_korean_finance_context(text: str) -> bool:
    if any(term in text for term in KOREAN_FINANCE_CONTEXT):
        return True
    return has_market_terms(text)


def has_causality(text: str) -> bool:
    text = normalize_for_matching(text)
    lower = text.lower()
    if any(marker in lower for marker in NO_CAUSE_MARKERS):
        return False
    if any(re.search(pattern, text) for pattern in KOREAN_NO_CAUSE_PATTERNS):
        return False
    if any(_contains_phrase_boundary(text, marker) for marker in CAUSAL_MARKERS):
        return True
    if any(marker in text for marker in KOREAN_CAUSAL_MARKERS):
        return True
    if any(re.search(pattern, text) for pattern in KOREAN_CAUSAL_PATTERNS):
        return True
    return False


def has_market_terms(text: str) -> bool:
    text = normalize_for_matching(text)
    if _contains_any_boundary(text, MARKET_TERMS):
        return True
    lower = text.lower()
    # Bare English "market" counts, except physical marketplaces (farmers'/flea/…).
    if _FINANCIAL_MARKET_RE.search(lower) and not _PHYSICAL_MARKET_RE.search(lower):
        return True
    if _KOREAN_MARKET_SESSION_RE.search(text):
        return True
    if any(re.search(pattern, text) for pattern in _KOREAN_MARKET_SLANG_PATTERNS):
        return True
    return False


def has_flow_terms(text: str) -> bool:
    return contains_phrase(normalize_for_matching(text), FLOW_TERMS)


def has_motive_markers(text: str) -> bool:
    return _contains_any_boundary(normalize_for_matching(text), MOTIVE_MARKERS)


def has_private_markers(text: str) -> bool:
    text = normalize_for_matching(text)
    if _contains_any_boundary(text, PRIVATE_MARKERS):
        return True
    # A *deleted* screenshot is unobservable; a bare 캡처/screenshot is not.
    if "삭제된" in text and "캡처" in text:
        return True
    # A deleted/erased open-chat room is unobservable (지워진/삭제된 오픈채팅방).
    if ("지워진" in text or "삭제된" in text) and "오픈채팅" in text:
        return True
    return False


def has_manipulation_framing(text: str) -> bool:
    text = normalize_for_matching(text)
    lower = text.lower()
    if _contains_any_boundary(text, MANIPULATION_MARKERS):
        return True
    # Public-specific conspiratorial "hiding" framing (preserved; inert on gold set):
    # "everyone knows … hiding …" and "hiding … (real) crash/risk/truth/evidence".
    if re.search(r"\b(?:everyone knows|we all know)\b.*\b(?:hiding|covering up|concealing)\b", lower):
        return True
    if re.search(r"\b(?:hiding|covering up|concealing)\b.*\b(?:real\s+)?(?:crash|risk|truth|evidence)\b", lower):
        return True
    if any(marker in text for marker in KOREAN_MANIPULATION_STRONG):
        return True
    if any(re.search(pattern, text) for pattern in KOREAN_MANIPULATION_STRONG_PATTERNS):
        return True
    if any(re.search(pattern, lower) for pattern in ENGLISH_MANIPULATION_PATTERNS):
        return True
    if _KOREAN_COLLUSION_RE.search(text) and any(cue in text for cue in _KOREAN_COLLUSION_CUES):
        return True
    # Cover-up / statistics-suppression framing (FIX 5), gated on an authority cue.
    if _KOREAN_COVERUP_RE.search(text) and any(cue in text for cue in _KOREAN_COVERUP_CUES):
        return True
    if any(marker in text for marker in KOREAN_MANIPULATION_WEAK) and any(cue in text for cue in KOREAN_CERTAINTY_CUES):
        return True
    # English progressive forms (manipulating / rigging) added (FIX 5); still gated
    # on a proof/certainty frame so neutral news ("deter market manipulation") stays False.
    return bool(re.search(r"\b(manipulation|manipulated|manipulating|rigged|rigging)\b", lower)) and bool(re.search(r"\b(this proves|proves|obvious|everyone knows)\b", lower))


def has_action_language(text: str) -> bool:
    text = normalize_for_matching(text)
    # FIX 7: remove narrow meta-disclaimer spans before detection so buy/sell
    # tokens INSIDE "not a recommendation to buy or sell" do not read as advice.
    # Any real advice outside the disclaimer phrase still fires.
    text = _strip_advice_disclaimers(text)
    lower = text.lower()
    for term in ADVICE_TERMS:
        # ASCII-aware boundaries so a trailing Korean particle ("buy를") does not
        # defeat the match the way Python's \b does between a Latin letter and Hangul.
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        if re.search(pattern, lower):
            return True
    if any(re.search(pattern, lower) for pattern in LONG_SHORT_PATTERNS):
        return True
    if any(re.search(pattern, lower) for pattern in ENGLISH_ADVICE_PATTERNS):
        return True
    if any(re.search(pattern, text) for pattern in KOREAN_ADVICE_PATTERNS):
        return True
    if _has_korean_finance_context(text) and any(re.search(pattern, text) for pattern in KOREAN_CONTEXT_ADVICE_PATTERNS):
        return True
    if _has_korean_euphemistic_advice(text):
        return True
    if _contains_any_boundary(text, URGENCY_ACTION_TERMS):
        return True
    if has_investment_rating_language(text):
        return True
    return False


def _has_korean_euphemistic_advice(text: str) -> bool:
    """Korean buy/averaging-down urging phrased without an imperative lexicon word.

    Each is a conjunction of pump signals, so literal homographs (drafting a
    schedule 물타기; putting water in a spot 담아야 할 자리; a policy-timing debate
    타이밍) do not fire on their own.
    """
    # "이 종목 담아야 할 자리" (a spot to accumulate) paired with a finance co-signal.
    if re.search(r"담[아을]야?\s*할?\s*자리", text) and re.search(r"(빚내|저점|분할|매수|물타기|풀매수)", text):
        return True
    # "지금이 바로 그 타이밍 … 놓치면 안" (now is THE moment, don't miss it).
    if re.search(r"타이밍", text) and re.search(r"(지금이|바로\s*그|바로\s*지금)", text) and re.search(r"놓치", text):
        return True
    # "물타기 들어갑니다 … 같이 가시죠" (first-person averaging-down + rally cue).
    if re.search(r"물타기", text) and re.search(r"(들어갑니|들어갈|가시죠|가즈아|같이\s*가)", text):
        return True
    return False


def has_investment_rating_language(text: str) -> bool:
    lower = normalize_for_matching(text).lower()
    return any(re.search(pattern, lower) for pattern in INVESTMENT_RATING_PATTERNS)


def has_position_sizing(text: str) -> bool:
    text = normalize_for_matching(text)
    lower = text.lower()
    if contains_phrase(text, POSITION_TERMS):
        return True
    if _has_korean_position_sizing(text):
        return True
    return bool(
        re.search(
            r"(?<![a-z0-9])\d{1,3}\s*(?:%|percent)\s+of\s+(?:a\s+|the\s+|your\s+|my\s+)?portfolio(?![a-z0-9])",
            lower,
        )
    )


def has_trade_probability(text: str) -> bool:
    text = normalize_for_matching(text)
    lower = text.lower()
    if any(re.search(pattern, text) for pattern in KOREAN_PROBABILITY_PATTERNS):
        return True
    if _KOREAN_VERBAL_ODDS_RE.search(text) and any(cue in text for cue in _KOREAN_VERBAL_ODDS_CUES):
        return True
    if any(re.search(pattern, lower) for pattern in ENGLISH_PROBABILITY_PATTERNS):
        return True
    return (
        bool(re.search(r"\b\d{1,3}\s*%\s*(chance|probability|odds)\b", lower))
        or bool(re.search(r"\b\d{1,3}\s*percent\s*(chance|probability|odds)\b", lower))
        or bool(re.search(r"\b\d{1,3}\s*percent\s*chance\s*of\s*(a\s*)?profitable trade\b", lower))
        or "trade probability" in lower
        or "probability of success" in lower
    )


def has_future_return_projection(text: str) -> bool:
    text = normalize_for_matching(text)
    lower = text.lower()
    if any(re.search(pattern, text) for pattern in KOREAN_RETURN_PATTERNS):
        return True
    return bool(
        re.search(r"\b\d+(?:\.\d+)?x\s+(?:return|gain|profit|upside)\b", lower)
        or re.search(r"\b(?:could|may|might|should|expected to|projected to)\s+(?:produce|return|yield|generate|deliver)\b.*\b(?:return|gain|profit|upside)\b", lower)
        or re.search(r"\b(?:return|gain|profit|upside)\s+within\s+\d+\s+(?:day|days|week|weeks|month|months|year|years)\b", lower)
    )


def detect_risk_flags(text: str, source_type: str, mode: str, published_at: str | None = None) -> list[str]:
    text = normalize_for_matching(text)
    flags: list[str] = []
    causal = has_causality(text)
    market = has_market_terms(text)
    motive = has_motive_markers(text)
    manipulation = has_manipulation_framing(text)
    if causal:
        flags.append("unsupported_causality")
    if _contains_any_boundary(text, FRAME_LANGUAGE):
        flags.append("framing_risk")
    if _contains_any_boundary(text, LOADED_LANGUAGE):
        flags.append("loaded_language")
    if manipulation:
        flags.append("loaded_language")
    if _contains_any_boundary(text, STRONG_CERTAINTY):
        flags.append("strong_certainty_language")
    if has_action_language(text):
        flags.append("action_recommendation_language")
    if has_private_markers(text):
        flags.extend(["private_or_inaccessible_source", "unobservable_evidence"])
    if "deleted screenshot" in text.lower() or "deleted staff message" in text.lower():
        flags.extend(["private_or_inaccessible_source", "unobservable_evidence"])
    if "staff message" in text.lower() or "internal chat" in text.lower():
        flags.extend(["private_or_inaccessible_source", "unobservable_evidence"])
    if "inaccessible comments" in text.lower() or "locked group" in text.lower() or "member-only forum" in text.lower():
        flags.extend(["private_or_inaccessible_source", "unobservable_evidence"])
    if source_type == "community":
        flags.append("community_source")
    if source_type == "social":
        flags.append("social_source")
    if not published_at and (
        any(word in text.lower() for word in {"today", "yesterday", "current", "now", "recent", "latest"})
        or any(word in text for word in KOREAN_TEMPORAL_MARKERS)
    ):
        flags.append("stale_or_missing_date")
    if mode == "finance":
        if (causal and (market or motive)) or (manipulation and (market or has_flow_terms(text) or motive)):
            flags.append("market_causality_claim")
        if causal and has_flow_terms(text):
            flags.append("flow_data_overinterpretation")
        if source_type == "official" and causal and (market or motive):
            flags.append("official_data_causality_mismatch")
        if source_type == "analyst":
            flags.append("analyst_interpretation")
        if source_type in {"community", "social"} and market:
            flags.append("community_market_signal_misuse")
        if has_action_language(text):
            flags.append("investment_advice_language")
        # Public-specific hype phrasing ("hop on the ride", "to the moon") is
        # advice; preserved here and inert on the gold set.
        if has_finance_hype_action_language(text):
            flags.append("investment_advice_language")
        if _contains_any_boundary(text, TARGET_TERMS) or _has_korean_target_price(text) or has_security_price_projection(text):
            flags.append("target_price_language")
        if has_position_sizing(text):
            flags.append("position_sizing_language")
        if has_trade_probability(text) or has_future_return_projection(text):
            flags.append("trade_probability_language")
        if _contains_any_boundary(text, TRUE_CAUSE_TERMS) or any(term in text for term in KOREAN_TRUE_CAUSE_MARKERS):
            flags.append("true_cause_market_claim")
        if source_type == "official" and (causal and (market or motive)):
            flags.append("needs_official_confirmation")
    if source_type in {"news", "analyst", "community", "social", "unknown", "user_note"} and source_type != "official":
        if mode == "finance" and (market or causal):
            flags.append("needs_official_confirmation")
        elif causal:
            flags.append("needs_official_confirmation")
    ordered: list[str] = []
    for flag in flags:
        if flag not in ordered:
            ordered.append(flag)
    return ordered


# Public-specific defensive masking applied in EVERY mode (general + finance).
# The private lineage does not mask in general mode; the public lineage does, as a
# fail-safe against advice-like leakage even in general reports. These are a strict
# subset of the finance masking and are inert on the gold set (finance-only).
_GENERAL_RENDER_MASK_PATTERNS = (
    (r"\b(?:buy|buys|buying|bought)\b", "[blocked-investment-action]"),
    (r"\b(?:sell)\b", "[blocked-investment-action]"),
    (r"\b(?:shorts|shorting|shorted)\b", "[blocked-investment-action]"),
    (r"\b(?:longs|longing|longed)\b", "[blocked-investment-action]"),
    (r"\b(?:target price|price target|upside target|downside target)\b", "[blocked-price-level]"),
    (r"\bstop[\s-]?loss\b", "[blocked-risk-order]"),
    (r"\btake[\s-]?profit\b", "[blocked-profit-order]"),
    (r"\b\d{1,3}\s*%\s*(chance|probability|odds)\b", "[blocked-probability-language]"),
    (r"\b\d{1,3}\s*percent\s*(chance|probability|odds)\b", "[blocked-probability-language]"),
    (r"\bchance\s*of\s*(a\s*)?profitable trade(\s+this\s+(week|month|quarter|year))?\b", "[blocked-probability-language]"),
    (r"\bprofitable trade(\s+this\s+(week|month|quarter|year))?\b", "[blocked-trade-outcome-language]"),
    (r"\b\d+(?:\.\d+)?x\s+(?:returns?|gains?|profits?|upsides?)\b", "[blocked-return-projection]"),
)


# Replacements applied to every finance-mode report (English + unambiguous Korean).
#
# NOTE: English patterns use ASCII-aware lookarounds ((?<![a-z0-9]) / (?![a-z0-9]))
# instead of \b so a trailing Korean particle does not defeat the match — Python's
# \b fails between a Latin letter and a Hangul syllable (both are \w), which leaked
# "target price를" / "allocation을" in mixed ko/en text.
_SANITIZE_REPLACEMENTS = [
    (r"(?<![a-z0-9])(buy|sell)(?![a-z0-9])", "[blocked-investment-action]"),
    (r"(?<![a-z0-9])go(?:ing)?\s+long(?![a-z0-9])", "[blocked-investment-action]"),
    (r"(?<![a-z0-9])go(?:ing)?\s+short(?![a-z0-9])", "[blocked-investment-action]"),
    (r"(?<![a-z0-9])short\s+the(?![a-z0-9])", "[blocked-investment-action]"),
    (r"(?<![a-z0-9])long\s+the(?![a-z0-9])", "[blocked-investment-action]"),
    (r"(?<![a-z0-9])(?:long|short)\s+position(?![a-z0-9])", "[blocked-investment-action]"),
    (r"(?<![a-z0-9])(?:long|short)\s+(?:the\s+)?(?:stock|shares|index)(?![a-z0-9])", "[blocked-investment-action]"),
    (r"(?<![a-z0-9])shorting(?![a-z0-9])", "[blocked-investment-action]"),
    (_EXPOSURE_ADVICE, "[blocked-investment-action]"),
    (r"(?<![순공])(?<!순\s)(?<!공\s)매\s*수(?:\s*하|\s*해|\s*는|\s*를|\s*가|\s*추천|\s*의견)", "[blocked-investment-action]"),
    (r"(?<![순공])(?<!순\s)(?<!공\s)매\s*도(?:\s*하|\s*해|\s*는|\s*를|\s*가|\s*추천|\s*의견)", "[blocked-investment-action]"),
    (r"풀매수", "[blocked-investment-action]"),
    (r"풀매도", "[blocked-investment-action]"),
    (r"몰빵", "[blocked-investment-action]"),
    (r"손절(?:하|해|은|을|각)?", "[blocked-investment-action]"),
    (r"익절(?:하|해|은|을|각)?", "[blocked-investment-action]"),
    (r"주식\s*안\s*합니다", "[blocked-investment-action]"),
    (r"주식안합니다", "[blocked-investment-action]"),
    (r"사고\s*팔고", "[blocked-investment-action]"),
    (r"사세요", "[blocked-investment-action]"),
    (r"파세요", "[blocked-investment-action]"),
    (r"사라(?![가-힣])", "[blocked-investment-action]"),  # imperative buy; not 사라지다/사라졌다
    (r"팔아라", "[blocked-investment-action]"),
    (r"(?<![A-Za-z])long\s*잡", "[blocked-investment-action]"),
    (r"(?<![a-z0-9])(?:overweight|underweight|outperform|underperform)\s+(?:rating|view|call|stance)(?![a-z0-9])", "[blocked-investment-rating]"),
    (r"(?<![a-z0-9])(?:maintain|maintains|maintained|upgrade|upgrades|downgrade|downgrades|initiate|initiates)\s+(?:an?\s+)?(?:overweight|underweight|outperform|underperform)(?![a-z0-9])", "[blocked-investment-rating]"),
    (r"(?<![a-z0-9])(?:strong\s+buy|buy\s+rating|sell\s+rating|hold\s+rating)(?![a-z0-9])", "[blocked-investment-rating]"),
    (r"(?<![a-z0-9])load\s+up(?![a-z0-9])", "[blocked-investment-action]"),
    (r"(?<![a-z0-9])act\s+now(?![a-z0-9])", "[blocked-urgency-language]"),
    (r"(?<![a-z0-9])before\s+(?:it\s+is|it's)\s+too\s+late(?![a-z0-9])", "[blocked-urgency-language]"),
    (r"(?<![a-z0-9])last\s+chance(?![a-z0-9])", "[blocked-urgency-language]"),
    (r"(?<![a-z0-9])don'?t\s+miss\s+out(?![a-z0-9])", "[blocked-urgency-language]"),
    (r"(?<![a-z0-9])get\s+in\s+before(?![a-z0-9])", "[blocked-urgency-language]"),
    (r"(?<![a-z0-9])(entry|exit)(?![a-z0-9])", "[blocked-trading-action]"),
    (r"(?<![a-z0-9])stop loss(?![a-z0-9])", "[blocked-risk-order]"),
    (r"(?<![a-z0-9])take profit(?![a-z0-9])", "[blocked-profit-order]"),
    (r"(?<![a-z0-9])(target price|price target|upside target|downside target)(?![a-z0-9])", "[blocked-price-level]"),
    # FIX 2: gated 목표주가/목표가/目標價 (goal-particle usage does not match).
    (_KOREAN_TARGET_PRICE_PATTERN, "[blocked-price-level]"),
    (r"(?<![a-z0-9])(position size|position sizing|allocate|allocating|allocation)(?![a-z0-9])", "[blocked-allocation-language]"),
    # NOTE: Korean 비중 allocation masking is applied separately in
    # sanitize_for_report (product-mix guard + number-word gap; FIX 1/FIX 4).
    (r"(?<![a-z0-9])\d{1,3}\s*(?:%|percent)\s+of\s+(?:a\s+|the\s+|your\s+|my\s+)?portfolio(?![a-z0-9])", "[blocked-allocation-language]"),
    (r"(?<![a-z0-9])\d{1,3}\s*%\s*(chance|probability|odds)(?![a-z0-9])", "[blocked-probability-language]"),
    (r"(?<![a-z0-9])\d{1,3}\s*percent\s*(chance|probability|odds)(?![a-z0-9])", "[blocked-probability-language]"),
    (r"확률\s*\d+", "[blocked-probability-language]"),
    (r"\d+\s*(?:%|프로|퍼센트)\s*확률", "[blocked-probability-language]"),
    (r"승률\s*\d+\s*%?", "[blocked-probability-language]"),  # 승률 N% (was leaking)
    # 열에 아홉 masks only when a finance/profit co-signal follows in the same
    # sentence, mirroring the detection gate; the general idiom stays untouched.
    (r"열\s*에\s*아홉(?=[^.!?]*(?:오르|먹|수익|익절|승률|번다|자리|종목))", "[blocked-probability-language]"),
    (r"(?<![a-z0-9])chance\s*of\s*(a\s*)?profitable trade(\s+this\s+(week|month|quarter|year))?(?![a-z0-9])", "[blocked-probability-language]"),
    (r"(?<![a-z0-9])profitable trade(\s+this\s+(week|month|quarter|year))?(?![a-z0-9])", "[blocked-trade-outcome-language]"),
    (r"(?:nearly|almost)\s+always\s+(?:\w+\s+){0,4}profitab\w*", "[blocked-probability-language]"),
    (r"(?<![a-z0-9])\d+(?:\.\d+)?x\s+(?:return|gain|profit|upside)(?![a-z0-9])", "[blocked-return-projection]"),
    (r"수익률\s*\d", "[blocked-return-projection]"),
    (r"\d+\s*(?:%|프로|퍼센트)\s*수익률", "[blocked-return-projection]"),
    (r"\d+배\s*(?:수익|상승)", "[blocked-return-projection]"),
    (r"(?<![a-z0-9])(?:could|may|might|should|expected to|projected to)\s+(?:produce|return|yield|generate|deliver)\b.*\b(?:return|gain|profit|upside)(?![a-z0-9])", "[blocked-return-projection]"),
    (r"(?<![a-z0-9])(?:return|gain|profit|upside)\s+within\s+\d+\s+(?:day|days|week|weeks|month|months|year|years)(?![a-z0-9])", "[blocked-return-projection]"),
    (r"(?<![a-z0-9])(true reason|real reason|true cause)(?![a-z0-9])", "[redacted-unsupported-true-cause-claim]"),
    (r"(?:진짜|실제)\s*(?:이유|원인)", "[redacted-unsupported-true-cause-claim]"),
]

# Replacements applied only when the text carries Korean finance/market context.
_SANITIZE_KOREAN_CONTEXT_REPLACEMENTS = [
    (r"조심(?:들)?(?:하|해|하세요|해야)", "[blocked-urgency-language]"),
    (r"다\s*던졌(?:다|어요|습니다)?", "[blocked-investment-action]"),
    (r"던졌(?:다|어요|습니다)?", "[blocked-investment-action]"),
    (r"강력\s*추천", "[blocked-investment-action]"),
    (r"(?:매수|매도|종목)\s*추천", "[blocked-investment-action]"),
    (r"추천(?:합니다|해요|해라|하라|드립니다|드려요|한다|하는|했)", "[blocked-investment-action]"),
    (r"들어가라", "[blocked-investment-action]"),
    (r"들어가세요", "[blocked-investment-action]"),
    (r"지금\s*들어가", "[blocked-investment-action]"),
    (r"올라타", "[blocked-investment-action]"),
]


def escape_markdown_inline(text: str) -> str:
    """Neutralize markdown/HTML structure in untrusted claim text.

    claim_text originates from untrusted source documents and is rendered inline
    after a list marker in generated .md reports. Backslash-escape `[`, `]`, and
    backtick so injected links/code spans render literally, and replace `<`/`>`
    with HTML entities so raw tags (e.g. <script>) cannot pass through to viewers
    without sanitizers. Nothing else is escaped: claim text always follows a list
    marker, so line-start constructs (#, *, -, _) are not reachable, and
    over-escaping hurts readability.

    Apply this to RAW text BEFORE sanitize_for_report so the `[blocked-...]` /
    `[excluded-...]` tokens sanitize inserts stay unescaped and render as intended.
    """
    if not text:
        return text
    escaped = text.replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")
    escaped = escaped.replace("<", "&lt;").replace(">", "&gt;")
    return escaped


def _mask_korean_position_sizing(text: str) -> str:
    """Mask 비중 …확대/축소/조절/줄/늘 allocation advice, honoring the FIX 4
    product-mix guard and the FIX 1 number-word gap. Product/revenue-mix
    occurrences (제품 비중을 확대) are left untouched."""
    hits = _korean_position_sizing_hits(text, _KOREAN_SIZING_MASK_RE)
    if not hits:
        return text
    result = []
    last = 0
    for match in hits:
        result.append(text[last : match.start()])
        result.append("[blocked-allocation-language]")
        last = match.end()
    result.append(text[last:])
    return "".join(result)


def sanitize_for_report(text: str, mode: str) -> str:
    # FIX 1: de-obfuscate FIRST so masking runs on normalized text (losing the
    # smuggled zero-width/homoglyph chars in the rendered output is intended).
    # Note: normalize runs in ALL modes now, because the public-lineage general
    # defensive masking below applies in general mode too. normalize is idempotent
    # on clean ASCII / composed Hangul, so plain text is returned unchanged.
    text = normalize_for_matching(text)
    # FIX 7: protect narrow advice-disclaimer spans (buy/sell inside them must be
    # preserved) with private-use sentinels no pattern can match, then restore.
    protected: list[str] = []

    def _protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return chr(0xE000 + len(protected) - 1)

    sanitized = text
    for pattern in _ADVICE_DISCLAIMER_PATTERNS:
        sanitized = re.sub(pattern, _protect, sanitized, flags=re.IGNORECASE)

    # Public-specific general defensive layer (ALL modes): masks buy/target/long-
    # short inflections + ticker->price so even general reports do not leak advice.
    for pattern, repl in _GENERAL_RENDER_MASK_PATTERNS:
        sanitized = re.sub(pattern, repl, sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(SECURITY_PRICE_PROJECTION_PATTERNS[0], "[blocked-price-level]", sanitized, flags=re.IGNORECASE)

    if mode == "finance":
        for pattern, repl in _SANITIZE_REPLACEMENTS:
            sanitized = re.sub(pattern, repl, sanitized, flags=re.IGNORECASE)
        sanitized = _mask_korean_position_sizing(sanitized)
        # Public-specific finance extras: floor-teaser price, hype phrasing, and
        # 권고 (recommendation) sentence masking. Inert on the gold set.
        for pattern in SECURITY_PRICE_PROJECTION_PATTERNS[1:]:
            sanitized = re.sub(pattern, "[blocked-price-level]", sanitized, flags=re.IGNORECASE)
        for pattern in FINANCE_HYPE_ACTION_PATTERNS:
            sanitized = re.sub(pattern, "[blocked-finance-hype-action]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(
            r"[^.\n。]*권고(?:한다|합니다|했다|하라|하며|하고|하는|할|를|을)?",
            "[blocked-investment-recommendation]",
            sanitized,
        )
        if _has_korean_finance_context(text):
            for pattern, repl in _SANITIZE_KOREAN_CONTEXT_REPLACEMENTS:
                sanitized = re.sub(pattern, repl, sanitized, flags=re.IGNORECASE)

    for index, original in enumerate(protected):
        sanitized = sanitized.replace(chr(0xE000 + index), original)
    return sanitized
