from __future__ import annotations

import re

FORUM_UI_NOISE_PATTERNS = (
    r"로그인\s+회원가입\s*\|\s*아이디\s+비번찾기",
    r"(?:증권포럼|재테크포럼|보험포럼)\s*입니다\.",
    r"\b(?:재테크포럼|보험포럼)\b",
    r"파워링크\s+등록안내",
    r"등록일\s+\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}\s+조회수\s+\d+",
    r"등록일\s+\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}",
    r"조회수\s+\d+",
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


def _split_sentences(block: str) -> list[str]:
    block = _strip_forum_ui_noise(block)
    if not block:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", block)
    return [p.strip(" \t-*") for p in parts if len(p.strip(" \t-*")) >= 8]


def extract_claim_texts(text: str) -> list[str]:
    candidates: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            candidates.extend(_split_sentences(" ".join(paragraph)))
            paragraph.clear()

    for raw_line in text.splitlines():
        line = _strip_forum_ui_noise(raw_line.strip())
        if not line:
            flush_paragraph()
            continue
        if _is_forum_ui_only_line(line):
            continue
        if line.endswith(":") and len(line.split()) <= 8:
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
