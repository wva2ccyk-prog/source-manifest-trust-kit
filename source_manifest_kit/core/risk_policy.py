from __future__ import annotations

import re

CAUSAL_MARKERS = {"because", "caused", "triggered", "led to", "as a result", "therefore", "due to", "the reason", "the real reason", "true cause", "true reason", "explains the move", "immediately reacted"}
NO_CAUSE_MARKERS = {"did not state a cause", "did not provide a cause", "without stating a cause", "no cause was stated"}
STRONG_CERTAINTY = {"true reason", "real reason", "confirmed truth", "everyone knows", "no doubt", "guaranteed", "certain", "inevitable", "this proves", "obvious"}
LOADED_LANGUAGE = {"shock", "bombshell", "disaster", "panic", "collapse", "crash", "treason", "traitor", "rigged", "manipulated", "propaganda", "destroyed confidence"}
FRAME_LANGUAGE = LOADED_LANGUAGE | {"far right", "far left", "policy disaster", "political risk"}
PRIVATE_MARKERS = {"private chat", "private group", "members-only", "member-only", "closed community", "deleted post", "deleted comments", "inaccessible", "paywalled", "internal desk", "proprietary"}
MARKET_TERMS = {"market", "stock", "stocks", "shares", "index", "exchange", "turnover", "volume", "foreign investors", "institutional investors", "net selling", "net buying", "selloff", "rally", "yield", "currency", "fund managers", "funds"}
FLOW_TERMS = {"foreign investors", "institutional investors", "net selling", "net buying", "fund managers", "flows", "sold heavily", "selling", "investors sold", "coordinating exits"}
MOTIVE_MARKERS = {
    "headline",
    "policy",
    "translation",
    "translated",
    "rumor",
    "commentary",
    "interpretation",
    "investors sold",
    "funds sold",
    "overseas desks",
    "global desks",
}
MANIPULATION_MARKERS = {
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
ADVICE_TERMS = {"buy", "sell", "short", "long", "entry", "exit", "stop loss", "take profit", "position size", "position sizing", "allocate", "allocating", "allocation", "trade this"}
INVESTMENT_ACTION_PATTERNS = (
    r"\b(?:buy|buys|buying|bought)\b",
    r"\b(?:short|shorts|shorting|shorted)\b",
    r"\b(?:long|longs|longing|longed)\b",
)
GENERAL_RENDER_MASK_PATTERNS = (
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
KOREAN_ADVICE_PATTERNS = (
    r"매수(?:하|해|는|를|가|추천|의견)?",
    r"매도(?:하|해|는|를|가|추천|의견)?",
    r"손절(?:하|해|은|을)?",
    r"익절(?:하|해|은|을)?",
    r"던졌(?:다|어요|습니다)?",
    r"다\s*던졌(?:다|어요|습니다)?",
    r"주식\s*안\s*합니다",
    r"주식안합니다",
    r"조심(?:들)?(?:하|해|하세요|해야)",
    r"사고\s*팔고",
    r"목표가",
    r"비중\s*(?:확대|축소|조절|줄|늘)",
    r"추천(?!하기)",
    r"권고",
    r"수익률\s*\d",
)
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
POSITION_TERMS = {"position size", "position sizing", "allocate", "allocating", "allocation"}
SECURITY_PRICE_PROJECTION_PATTERNS = (
    r"\b[A-Z]{1,6}\b\s+(?:is\s+)?(?:going\s+to|goes\s+to|will\s+(?:go\s+to|reach|hit)|to)\s+\$?\d{2,6}(?:,\d{3})?(?:\.\d+)?\b",
    r"\b(?:while\s+it\s+is\s+)?still\s+under\s+\$?\d{2,6}(?:,\d{3})?(?:\.\d+)?\b",
)
FINANCE_HYPE_ACTION_PATTERNS = (
    r"\bbetter\s+(?:hop|jump|get)\s+(?:on|in)\b",
    r"\bhop\s+on\s+the\s+ride\b",
    r"\bgo(?:es|ing)?\s+to\s+the\s+moon\b",
)
INVESTMENT_RATING_PATTERNS = (
    r"\b(?:overweight|underweight|outperform|underperform)\s+(?:rating|view|call|stance)\b",
    r"\b(?:maintain|maintains|maintained|upgrade|upgrades|downgrade|downgrades|initiate|initiates)\s+(?:an?\s+)?(?:overweight|underweight|outperform|underperform)\b",
    r"\b(?:strong\s+buy|buy\s+rating|sell\s+rating|hold\s+rating)\b",
)
TRUE_CAUSE_TERMS = {"true reason", "real reason", "true cause", "the market moved because", "caused the selloff"}


def contains_phrase(text: str, phrases: set[str]) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in phrases)


def has_number(text: str) -> bool:
    return bool(re.search(r"\d", text))


def _contains_phrase_boundary(text: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return bool(re.search(pattern, text.lower()))


def has_causality(text: str) -> bool:
    lower = text.lower()
    if any(marker in lower for marker in NO_CAUSE_MARKERS):
        return False
    return any(_contains_phrase_boundary(text, marker) for marker in CAUSAL_MARKERS)


def has_market_terms(text: str) -> bool:
    return contains_phrase(text, MARKET_TERMS)


def has_flow_terms(text: str) -> bool:
    return contains_phrase(text, FLOW_TERMS)


def has_motive_markers(text: str) -> bool:
    return contains_phrase(text, MOTIVE_MARKERS)


def has_manipulation_framing(text: str) -> bool:
    lower = text.lower()
    if contains_phrase(text, MANIPULATION_MARKERS):
        return True
    if re.search(r"\b(?:everyone knows|we all know)\b.*\b(?:hiding|covering up|concealing)\b", lower):
        return True
    if re.search(r"\b(?:hiding|covering up|concealing)\b.*\b(?:real\s+)?(?:crash|risk|truth|evidence)\b", lower):
        return True
    return bool(re.search(r"\b(manipulation|manipulated|rigged)\b", lower)) and bool(re.search(r"\b(this proves|proves|obvious|everyone knows)\b", lower))


def has_action_language(text: str) -> bool:
    lower = text.lower()
    if any(re.search(pattern, lower) for pattern in INVESTMENT_ACTION_PATTERNS):
        return True
    for term in ADVICE_TERMS:
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, lower):
            return True
    if any(re.search(pattern, text) for pattern in KOREAN_ADVICE_PATTERNS):
        return True
    if contains_phrase(text, URGENCY_ACTION_TERMS):
        return True
    if has_investment_rating_language(text):
        return True
    return False


def has_investment_rating_language(text: str) -> bool:
    lower = text.lower()
    return any(re.search(pattern, lower) for pattern in INVESTMENT_RATING_PATTERNS)


def has_security_price_projection(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in SECURITY_PRICE_PROJECTION_PATTERNS)


def has_finance_hype_action_language(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in FINANCE_HYPE_ACTION_PATTERNS)


def has_position_sizing(text: str) -> bool:
    lower = text.lower()
    if contains_phrase(text, POSITION_TERMS):
        return True
    return bool(
        re.search(
            r"\b\d{1,3}\s*(?:%|percent)\s+of\s+(?:a\s+|the\s+|your\s+|my\s+)?portfolio\b",
            lower,
        )
    )


def has_trade_probability(text: str) -> bool:
    lower = text.lower()
    return (
        bool(re.search(r"\b\d{1,3}\s*%\s*(chance|probability|odds)\b", lower))
        or bool(re.search(r"\b\d{1,3}\s*percent\s*(chance|probability|odds)\b", lower))
        or bool(re.search(r"\b\d{1,3}\s*percent\s*chance\s*of\s*(a\s*)?profitable trade\b", lower))
        or "trade probability" in lower
        or "probability of success" in lower
    )


def has_future_return_projection(text: str) -> bool:
    lower = text.lower()
    return bool(
        re.search(r"\b\d+(?:\.\d+)?x\s+(?:returns?|gains?|profits?|upsides?)\b", lower)
        or re.search(r"\b(?:could|may|might|should|expected to|projected to)\s+(?:produce|return|yield|generate|deliver)\b.*\b(?:return|gain|profit|upside)\b", lower)
        or re.search(r"\b(?:return|gain|profit|upside)\s+within\s+\d+\s+(?:day|days|week|weeks|month|months|year|years)\b", lower)
    )


def detect_risk_flags(text: str, source_type: str, mode: str, published_at: str | None = None) -> list[str]:
    flags: list[str] = []
    causal = has_causality(text)
    market = has_market_terms(text)
    motive = has_motive_markers(text)
    manipulation = has_manipulation_framing(text)
    if causal:
        flags.append("unsupported_causality")
    if contains_phrase(text, FRAME_LANGUAGE):
        flags.append("framing_risk")
    if contains_phrase(text, LOADED_LANGUAGE):
        flags.append("loaded_language")
    if manipulation:
        flags.append("loaded_language")
    if contains_phrase(text, STRONG_CERTAINTY):
        flags.append("strong_certainty_language")
    if has_action_language(text):
        flags.append("action_recommendation_language")
    if contains_phrase(text, PRIVATE_MARKERS):
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
    if not published_at and any(word in text.lower() for word in {"today", "yesterday", "current", "now", "recent", "latest"}):
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
        if contains_phrase(text, TARGET_TERMS) or has_security_price_projection(text):
            flags.append("target_price_language")
        if has_finance_hype_action_language(text):
            flags.append("investment_advice_language")
        if has_position_sizing(text):
            flags.append("position_sizing_language")
        if has_trade_probability(text) or has_future_return_projection(text):
            flags.append("trade_probability_language")
        if contains_phrase(text, TRUE_CAUSE_TERMS):
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


def sanitize_for_report(text: str, mode: str) -> str:
    sanitized = text
    replacements = list(GENERAL_RENDER_MASK_PATTERNS)
    replacements.extend(
        (pattern, "[blocked-price-level]")
        for pattern in SECURITY_PRICE_PROJECTION_PATTERNS[:1]
    )
    if mode == "finance":
        replacements.extend(
            [
        (r"\b(?:short|long)\b", "[blocked-investment-action]"),
        (r"매수(?:하|해|는|를|가|추천|의견)?", "[blocked-investment-action]"),
        (r"매도(?:하|해|는|를|가|추천|의견)?", "[blocked-investment-action]"),
        (r"손절(?:하|해|은|을)?", "[blocked-investment-action]"),
        (r"익절(?:하|해|은|을)?", "[blocked-investment-action]"),
        (r"다\s*던졌(?:다|어요|습니다)?", "[blocked-investment-action]"),
        (r"던졌(?:다|어요|습니다)?", "[blocked-investment-action]"),
        (r"주식\s*안\s*합니다", "[blocked-investment-action]"),
        (r"주식안합니다", "[blocked-investment-action]"),
        (r"조심(?:들)?(?:하|해|하세요|해야)", "[blocked-urgency-language]"),
        (r"사고\s*팔고", "[blocked-investment-action]"),
        (r"추천(?!하기)", "[blocked-investment-action]"),
        (r"[^.\n。]*권고(?:한다|합니다|했다|하라|하며|하고|하는|할|를|을)?", "[blocked-investment-recommendation]"),
        (r"\b(?:overweight|underweight|outperform|underperform)\s+(?:rating|view|call|stance)\b", "[blocked-investment-rating]"),
        (r"\b(?:maintain|maintains|maintained|upgrade|upgrades|downgrade|downgrades|initiate|initiates)\s+(?:an?\s+)?(?:overweight|underweight|outperform|underperform)\b", "[blocked-investment-rating]"),
        (r"\b(?:strong\s+buy|buy\s+rating|sell\s+rating|hold\s+rating)\b", "[blocked-investment-rating]"),
        (r"\bload\s+up\b", "[blocked-investment-action]"),
        (r"\bact\s+now\b", "[blocked-urgency-language]"),
        (r"\bbefore\s+(?:it\s+is|it's)\s+too\s+late\b", "[blocked-urgency-language]"),
        (r"\blast\s+chance\b", "[blocked-urgency-language]"),
        (r"\bdon'?t\s+miss\s+out\b", "[blocked-urgency-language]"),
        (r"\bget\s+in\s+before\b", "[blocked-urgency-language]"),
        (r"\b(?:entry|entries|entering|entered|exit|exits|exiting|exited)\b", "[blocked-trading-action]"),
        (r"\b(target price|price target|upside target|downside target)\b", "[blocked-price-level]"),
        (r"목표가", "[blocked-price-level]"),
        (r"\b(position size|position sizing|allocate|allocating|allocation)\b", "[blocked-allocation-language]"),
        (r"비중\s*(?:확대|축소|조절|줄|늘)", "[blocked-allocation-language]"),
        (r"\b\d{1,3}\s*(?:%|percent)\s+of\s+(?:a\s+|the\s+|your\s+|my\s+)?portfolio\b", "[blocked-allocation-language]"),
        *(
            (pattern, "[blocked-price-level]")
            for pattern in SECURITY_PRICE_PROJECTION_PATTERNS[1:]
        ),
        (r"\b\d{1,3}\s*%\s*(chance|probability|odds)\b", "[blocked-probability-language]"),
        (r"\b\d{1,3}\s*percent\s*(chance|probability|odds)\b", "[blocked-probability-language]"),
        (r"\bchance\s*of\s*(a\s*)?profitable trade(\s+this\s+(week|month|quarter|year))?\b", "[blocked-probability-language]"),
        (r"\bprofitable trade(\s+this\s+(week|month|quarter|year))?\b", "[blocked-trade-outcome-language]"),
        (r"수익률\s*\d", "[blocked-return-projection]"),
        (r"\b(?:could|may|might|should|expected to|projected to)\s+(?:produce|return|yield|generate|deliver)\b.*\b(?:return|gain|profit|upside)\b", "[blocked-return-projection]"),
        (r"\b(?:return|gain|profit|upside)\s+within\s+\d+\s+(?:day|days|week|weeks|month|months|year|years)\b", "[blocked-return-projection]"),
        (r"\b(true reason|real reason|true cause)\b", "[redacted-unsupported-true-cause-claim]"),
        *(
            (pattern, "[blocked-finance-hype-action]")
            for pattern in FINANCE_HYPE_ACTION_PATTERNS
        ),
            ]
        )
    for pattern, repl in replacements:
        sanitized = re.sub(pattern, repl, sanitized, flags=re.IGNORECASE)
    return sanitized
