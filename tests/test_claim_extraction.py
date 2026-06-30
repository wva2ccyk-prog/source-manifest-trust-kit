from source_manifest_kit.core.claim_extraction import extract_claim_texts


def test_sentence_and_bullet_extraction():
    text = "First claim happened. Second claim caused concern.\n- Bullet claim with context\n2. Numbered claim"
    claims = extract_claim_texts(text)
    assert "First claim happened." in claims
    assert "Second claim caused concern." in claims
    assert "Bullet claim with context" in claims
    assert "Numbered claim" in claims


def test_korean_forum_ui_prefixes_are_trimmed_without_dropping_claim():
    text = (
        "로그인 회원가입 | 아이디 비번찾기 증권포럼 입니다. 재테크포럼 보험포럼 "
        "파워링크 등록안내 지금 빠지는 게 이 거 때문인가보네요 39 지르니까편해짐 "
        "등록일 2026-05-21 19:39 조회수 18821 숨만 쉬고 있다고 한 거 같은데.."
    )
    claims = extract_claim_texts(text)
    combined = " ".join(claims)
    assert "로그인 회원가입" not in combined
    assert "재테크포럼" not in combined
    assert "보험포럼" not in combined
    assert "파워링크 등록안내" not in combined
    assert "등록일 2026-05-21" not in combined
    assert "지금 빠지는 게 이 거 때문인가보네요" in combined
    assert "숨만 쉬고 있다고 한 거 같은데" in combined


def test_korean_forum_action_controls_are_trimmed_without_dropping_comment():
    text = (
        "1\n추천하기 다른의견 0\n|\n신고\n첨부파일\nScreenshot_20260521_193758_Samsung Browser .jpg\n"
        "목록보기\n0 0 엑박\n유럽장에 있는 제 주식도 음전했네요."
    )
    claims = extract_claim_texts(text)
    combined = " ".join(claims)
    assert "추천하기" not in combined
    assert "첨부파일" not in combined
    assert "목록보기" not in combined
    assert "0 0 엑박" not in combined
    assert "1 0 0 엑박" not in combined
    assert "엑박 유럽장에 있는 제 주식도 음전했네요." in combined


def test_korean_forum_comment_permalink_controls_are_trimmed():
    text = (
        "numopillasium 이란 최고지도자 뒤진거 같은데 혁명수비대 놈들이 지들 입맛에 맞게 구라 정보 흘리는 듯\n"
        "21:08:13 댓글주소복사 △ 이전글 ▽ 다음글\n"
        "개념이 없으시네 이몰랑 또떡락 21:17:48 댓글주소복사 △ 이전글 ▽ 다음글"
    )
    claims = extract_claim_texts(text)
    combined = " ".join(claims)
    assert "댓글주소복사" not in combined
    assert "△ 이전글" not in combined
    assert "▽ 다음글" not in combined
    assert "21:08:13" not in combined
    assert "21:17:48" not in combined
    assert "혁명수비대" in combined
    assert "개념이 없으시네" in combined
