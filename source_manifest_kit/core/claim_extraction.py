from __future__ import annotations

import re

FORUM_UI_NOISE_PATTERNS = (
    r"로그인\s+회원가입\s*\|\s*아이디\s+비번찾기",
    r"(?:증권포럼|재테크포럼|보험포럼)\s*입니다\.",
    r"\b(?:재테크포럼|보험포럼)\b",
    r"파워링크\s+등록안내",
    r"등록일\s+\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}\s+조회수\s+\d{1,3}(?:[,.]\d{3})*",
    r"등록일\s+\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}",
    r"조회수\s+\d{1,3}(?:[,.]\d{3})*",
    r"^\d+\s+추천하기\s+다른의견\s+\d+\s*\|\s*신고\s*",
    r"추천하기\s+다른의견\s+\d+\s*\|\s*신고",
    r"첨부파일\s+.*?\s+목록보기",
    r"목록보기\s+\d+\s+\d+",
    r"^\d+\s+\d+\s+\d+\s+",
    r"^\d+\s+\d+\s+",
    r"\d{1,2}:\d{2}:\d{2}\s+댓글주소복사(?:\s+\d+\s+\d+)?",
    r"댓글주소복사",
    r"△\s*이전글\s*▽\s*다음글",
    r"△\s*이전글\s*▽\s*다음글\s*목록보기",
    r"\s+\d{1,2}:\d{2}:\d{2}$",
    # --- Generic (site-agnostic) additions below ---
    # These generalize the forum-specific patterns above so that any
    # Naver-Cafe / DCInside / Clien style post has its header/footer chrome
    # stripped, not just the one forum this module was originally built
    # against. Numeric counts consume comma/period-grouped thousands
    # (e.g. "1,204") so no numeric residue leaks into the next claim.
    r"(?:작성일|등록일)\s*:?\s*\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?",
    r"작성자\s*:?\s*\S{1,20}",
    r"(?:조회수|조회|추천|댓글|스크랩|신고|목록)\s*:?\s*\d{1,3}(?:[,.]\d{3})*",
)
FORUM_UI_ONLY_PATTERNS = (
    r"^\|$",
    r"^신고$",
    r"^첨부파일$",
    r"^목록보기$",
    r"^\d{1,3}$",
    r"^\d+\s+\d+$",
    r"^추천하기\s+다른의견\s+\d+$",
    r"^댓글주소복사$",
    r"^△\s*이전글\s*▽\s*다음글$",
    r"^[\w.-]+\.(?:jpg|jpeg|png|gif|webp)$",
    r"^Screenshot_.*$",
)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _strip_forum_ui_noise(text: str) -> str:
    cleaned = text
    for _ in range(2):
        for pattern in FORUM_UI_NOISE_PATTERNS:
            cleaned = re.sub(pattern, " ", cleaned)
    return normalize_whitespace(cleaned)


def _is_forum_ui_only_line(text: str) -> bool:
    cleaned = normalize_whitespace(text)
    return bool(cleaned and any(re.search(pattern, cleaned, flags=re.IGNORECASE) for pattern in FORUM_UI_ONLY_PATTERNS))


# --- Generic metadata-header / footer-action-row detection (FIX 1) ---
#
# These operate on the RAW (pre-noise-strip) line and are conservative by
# design: they only drop a line wholesale when it is basically nothing BUT
# forum chrome. If real content is glued onto the same physical line as a
# header/footer, the substitution-based FORUM_UI_NOISE_PATTERNS above still
# do a best-effort partial cleanup instead, so a genuine claim never gets
# thrown away just because it shares a line with noise.

_METADATA_LABELS = ("작성일", "등록일", "작성자")
_METADATA_COUNT_RE = re.compile(r"(?:조회수|조회|추천|댓글|스크랩|신고|목록)\s*:?\s*\d")
_METADATA_TOKEN_RE = re.compile(
    r"(?:작성일|등록일|작성자)\s*:?\s*\S*"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}:\d{2}(?::\d{2})?"
    r"|(?:조회수|조회|추천|댓글|스크랩|신고|목록)\s*:?\s*\d{1,3}(?:[,.]\d{3})*"
)


def _looks_like_metadata_line(line: str) -> bool:
    """Detect a post-metadata header line (author/date + view/comment counts).

    Generalizes beyond the single forum this module was built against: any
    line combining an author/date label (or a bare date) with a view/comment/
    recommend count is metadata, regardless of exact site wording.
    """
    if not line:
        return False
    has_label = any(marker in line for marker in _METADATA_LABELS)
    has_count = bool(_METADATA_COUNT_RE.search(line))
    if not (has_label and has_count):
        return False
    residual = _METADATA_TOKEN_RE.sub("", line)
    residual = re.sub(r"[\s:|/,.\-]", "", residual)
    return len(residual) <= 2


_FOOTER_ACTION_WORDS = ("좋아요", "스크랩", "신고", "공유", "목록", "이전글", "다음글", "추천하기")


def _looks_like_footer_action_row(line: str) -> bool:
    """Detect a forum footer action row, e.g. "좋아요 12 | 스크랩 3 | 신고".

    Only drops the line when nothing but action-button words, counts, and
    separators remain. If real text remains after stripping those words out,
    they are likely part of an ordinary sentence (e.g. "정부에 신고했다") and
    the line is left alone.
    """
    if not line:
        return False
    hits = sum(1 for word in _FOOTER_ACTION_WORDS if word in line)
    if not hits:
        return False
    residual = line
    for word in _FOOTER_ACTION_WORDS:
        residual = residual.replace(word, "")
    residual = re.sub(r"[\d,.\s|/·:\-]", "", residual)
    return residual == ""


# --- Reply/quote UI header stripping (FIX 1) ---
#
# Matches "<nick>님: text" or "<nick>: text" reply headers. Only the label is
# chrome; substantial trailing content is kept. Without the "님" honorific we
# cannot reliably tell a UI nickname label from ordinary prose that uses a
# colon (e.g. "결론: ..."), so in that case we require the leading token to
# look like an account handle (alnum/underscore/dot/dash) rather than a
# normal word before treating it as a reply header.

_REPLY_LABEL_RE = re.compile(r"^(?P<nick>[^\s:]{1,20}?)(?P<honorific>님)?\s*:\s*(?P<rest>.+)$")
_REPLY_HANDLE_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,20}$")


def _strip_reply_label(line: str) -> str | None:
    match = _REPLY_LABEL_RE.match(line)
    if not match:
        return line
    nick = match.group("nick")
    honorific = match.group("honorific")
    rest = match.group("rest").strip()
    if not honorific and not _REPLY_HANDLE_RE.match(nick):
        return line
    if len(rest) < 10:
        return None
    return rest


def _looks_like_table_row(line: str) -> bool:
    """Detect an aligned tabular row (label + column-separated numbers).

    Minimal, conservative heuristic (FIX 4): a line with a multi-space
    column gap and at least one digit, not ending in sentence punctuation,
    and short enough to plausibly be a row rather than prose. This
    intentionally will not catch every tabular layout (e.g. single-space
    aligned tables) -- only clearly columnar rows are split out, so ordinary
    prose is never shattered.
    """
    if not line or not re.search(r"\d", line):
        return False
    if line[-1:] in {".", "!", "?", "。", "！", "？"}:
        return False
    if not re.search(r" {2,}", line):
        return False
    return len(line.split()) <= 6


def _looks_like_allcaps_heading(line: str) -> bool:
    """Detect a standalone ALL-CAPS section heading without a trailing colon.

    Only short (<=5 word) lines with no sentence-ending punctuation and
    every alphabetic word fully uppercase qualify, so a sentence merely
    containing an all-caps acronym/ticker (e.g. "The FED and ECB...") is
    never mistaken for a heading.
    """
    words = line.split()
    if not words or len(words) > 5:
        return False
    if line[-1:] in {".", "!", "?", "。", "！", "？"}:
        return False
    if not re.search(r"[A-Za-z]", line):
        return False
    for word in words:
        letters = [ch for ch in word if ch.isalpha()]
        if letters and not all(ch.isupper() for ch in letters):
            return False
    return True


_NEGATIVE_NUMBER_PREFIX = re.compile(r"^-(?=[\d$€£¥₩])")


def _trim_fragment(text: str) -> str:
    """Trim bullet/whitespace clutter from a sentence fragment.

    A leading '-' immediately followed by a digit or currency symbol is a
    negative number/amount (e.g. "-3.5%", "-$12"), not bullet-list noise, and
    must be preserved rather than stripped away.
    """
    stripped = text.strip(" \t")
    if _NEGATIVE_NUMBER_PREFIX.match(stripped):
        return "-" + stripped[1:].strip(" \t-*")
    return stripped.strip(" \t-*")


# --- Abbreviation guard for the sentence splitter (FIX 2) ---
#
# `_split_sentences` splits after ".", "!", "?" etc. when followed by
# whitespace. That fires in the middle of common abbreviations (U.S., vs.,
# Inc., ...), producing orphan fragments. We mask the trailing period of
# known abbreviations before splitting, then restore it afterward.

_ABBREVIATION_TOKENS = (
    "U.S.", "U.K.", "vs.", "Inc.", "Corp.", "Ltd.", "Co.", "No.",
    "Mr.", "Ms.", "Mrs.", "Dr.", "Prof.", "St.", "Jr.", "Sr.",
    "e.g.", "i.e.", "etc.", "a.m.", "p.m.",
)
_ABBREV_TOKEN_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(tok) for tok in sorted(_ABBREVIATION_TOKENS, key=len, reverse=True)) + r")",
    re.IGNORECASE,
)
# Single-letter initials common in finance/news wire copy (e.g. "S. Korea",
# "N. Africa") -- kept narrow (specific following word) rather than a bare
# "[A-Z]\." rule, since the latter would also mask genuine sentence
# boundaries that happen to end in a single capital letter.
_ABBREV_INITIAL_RE = re.compile(r"\b([SN])\.(?=\s(?:Korea|Africa)\b)")
_ABBREV_PLACEHOLDER = ""


def _mask_abbreviation_periods(text: str) -> str:
    def _mask_token(match: "re.Match[str]") -> str:
        token = match.group(0)
        return token[:-1] + _ABBREV_PLACEHOLDER

    masked = _ABBREV_TOKEN_RE.sub(_mask_token, text)
    masked = _ABBREV_INITIAL_RE.sub(lambda m: m.group(1) + _ABBREV_PLACEHOLDER, masked)
    return masked


def _restore_abbreviation_periods(text: str) -> str:
    return text.replace(_ABBREV_PLACEHOLDER, ".")


def _split_sentences(block: str) -> list[str]:
    block = _strip_forum_ui_noise(block)
    if not block:
        return []
    masked = _mask_abbreviation_periods(block)
    parts = re.split(r"(?<=[.!?。！？])\s+", masked)
    parts = [_restore_abbreviation_periods(p) for p in parts]
    trimmed = [_trim_fragment(p) for p in parts]
    return [p for p in trimmed if len(p) >= 8]


def extract_claim_texts(text: str) -> list[str]:
    candidates: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            candidates.extend(_split_sentences(" ".join(paragraph)))
            paragraph.clear()

    for raw_line in text.splitlines():
        stripped_raw = raw_line.strip()
        if not stripped_raw:
            flush_paragraph()
            continue

        # FIX 4: tabular rows (label + column-separated numbers) become their
        # own claim rather than being paragraph-joined into a run-on blob.
        # Checked on the raw (pre-normalize) line since whitespace collapsing
        # would erase the column gaps this heuristic relies on.
        if _looks_like_table_row(stripped_raw):
            flush_paragraph()
            row = _strip_forum_ui_noise(stripped_raw)
            if row and len(row) >= 8:
                candidates.append(row)
            continue

        # FIX 1: generic metadata header / footer action rows are dropped
        # wholesale when the line is basically nothing but forum chrome.
        if _looks_like_metadata_line(stripped_raw) or _looks_like_footer_action_row(stripped_raw):
            flush_paragraph()
            continue

        line = _strip_forum_ui_noise(stripped_raw)
        if not line:
            flush_paragraph()
            continue

        # FIX 1: reply/quote UI headers ("<nick>님: text") -- strip the label,
        # keep substantial trailing content, drop trivial reactions entirely.
        reply_result = _strip_reply_label(line)
        if reply_result is None:
            continue
        line = reply_result

        if _is_forum_ui_only_line(line):
            continue
        if line.endswith(":") and len(line.split()) <= 8:
            flush_paragraph()
            continue
        # FIX 5: standalone ALL-CAPS section headings without a trailing colon.
        if _looks_like_allcaps_heading(line):
            flush_paragraph()
            continue
        bullet = re.match(r"^([-*•]|\d+[.)])\s+(.*)$", line)
        if bullet:
            flush_paragraph()
            item = bullet.group(2).strip()
            if len(item) >= 8:
                candidates.append(item)
        else:
            paragraph.append(line)
    flush_paragraph()

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        cleaned = normalize_whitespace(candidate)
        key = cleaned.lower()
        if cleaned and key not in seen:
            unique.append(cleaned)
            seen.add(key)
    return unique
