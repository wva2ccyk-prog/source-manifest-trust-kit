import json

from source_manifest_kit.core.claim_extraction import extract_claim_texts
from source_manifest_kit.runs import analyze_file


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


def test_negative_number_leading_minus_is_preserved():
    text = "Shares fell sharply. -3.5% decline was reported for the quarter."
    claims = extract_claim_texts(text)
    assert "Shares fell sharply." in claims
    assert "-3.5% decline was reported for the quarter." in claims
    assert "3.5% decline was reported for the quarter." not in claims


def test_generic_forum_metadata_and_footer_rows_are_dropped_generically():
    text = (
        "작성자: 홍길동 작성일: 2026-07-08 15:42 조회 128 댓글 12\n"
        "코스피 지수가 금리 동결 발표 직후 급락했다.\n"
        "닉네임님: 오 진짜요?\n"
        "좋아요 12 | 스크랩 3 | 신고\n"
        "다음글 이전글 목록"
    )
    claims = extract_claim_texts(text)
    combined = " ".join(claims)
    assert "홍길동" not in combined
    assert "작성자" not in combined
    assert "작성일" not in combined
    assert "조회" not in combined
    assert "오 진짜요" not in combined
    assert "좋아요" not in combined
    assert "스크랩" not in combined
    assert "다음글" not in combined
    assert "이전글" not in combined
    assert claims == ["코스피 지수가 금리 동결 발표 직후 급락했다."]


def test_forum_reply_label_keeps_substantial_content_but_drops_trivial_reply():
    substantial = "김민수님: 이번 실적 발표는 예상보다 훨씬 좋았다고 생각합니다"
    trivial = "닉네임님: 오 진짜요?"
    substantial_claims = extract_claim_texts(substantial)
    assert any("이번 실적 발표는 예상보다 훨씬 좋았다고 생각합니다" in c for c in substantial_claims)
    assert "김민수님" not in " ".join(substantial_claims)
    assert extract_claim_texts(trivial) == []


def test_forum_reply_label_heuristic_does_not_drop_ordinary_colon_prose():
    text = "결론: 금리는 계속 오를 것으로 전망된다"
    claims = extract_claim_texts(text)
    assert any("결론:" in c for c in claims)


def test_footer_action_words_inside_real_sentences_are_preserved():
    text = "정부는 신고 접수를 받는다고 발표했다."
    claims = extract_claim_texts(text)
    assert claims == [text]


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


def test_us_abbreviation_does_not_fracture_sentence():
    text = "대형 기술주는 U.S. 국채 금리 하락에 힘입어 상승했으며, S&P500 지수는 0.4% 올랐다."
    claims = extract_claim_texts(text)
    assert claims == [text]


def test_us_abbreviation_sentence_from_acceptance_spec_stays_one_claim():
    text = "대형 기술주는 U.S. 국채 금리 하락에 힘입어 상승했다."
    claims = extract_claim_texts(text)
    assert claims == [text]


def test_vs_abbreviation_does_not_fracture_sentence():
    text = "국내 반도체 vs. 해외 반도체 기업 간 경쟁 구도가 심화되고 있다."
    claims = extract_claim_texts(text)
    assert claims == [text]


def test_multi_sentence_splitting_still_works_with_abbreviation_guard():
    text = "Shares fell sharply. The U.S. Fed held rates steady. Markets recovered afterward today."
    claims = extract_claim_texts(text)
    assert "Shares fell sharply." in claims
    assert "The U.S. Fed held rates steady." in claims
    assert "Markets recovered afterward today." in claims


def test_single_letter_initial_abbreviation_s_dot_korea_not_split():
    text = "S. Korea exports rose sharply. Manufacturing output also improved."
    claims = extract_claim_texts(text)
    assert "S. Korea exports rose sharply." in claims
    assert "Manufacturing output also improved." in claims


def test_comma_grouped_view_count_leaves_no_numeric_residue():
    text = "등록일 2026-07-08 15:42 조회수 1,204\n금리 동결 때문에 장 폭락"
    claims = extract_claim_texts(text)
    assert claims
    assert not claims[0].startswith(",204")
    assert "금리 동결 때문에 장 폭락" in claims


def test_comma_grouped_view_count_from_acceptance_spec_leaves_no_residue():
    text = "조회수 1,204 그 이후 시장은 안정됐다."
    claims = extract_claim_texts(text)
    combined = " ".join(claims)
    assert ",204" not in combined
    assert "그 이후 시장은 안정됐다." in combined


def test_forum_noise_pattern_consumes_comma_grouped_thousands_inline():
    text = "조회수 1,204 그 이후 시장은 안정을 되찾았다."
    claims = extract_claim_texts(text)
    combined = " ".join(claims)
    assert ",204" not in combined
    assert "그 이후 시장은 안정을 되찾았다." in combined


def test_tabular_index_rows_become_separate_claims():
    text = (
        "코스피  2,640  -1.2%\n"
        "코스닥  850  -0.8%\n"
        "S&P500  4,500  +0.3%\n"
        "나스닥  14,000  +0.5%"
    )
    claims = extract_claim_texts(text)
    assert len(claims) == 4
    assert "코스피 2,640 -1.2%" in claims
    assert "코스닥 850 -0.8%" in claims
    assert "S&P500 4,500 +0.3%" in claims
    assert "나스닥 14,000 +0.5%" in claims


def test_tabular_row_detection_does_not_shatter_ordinary_prose():
    text = "First claim happened. Second claim caused concern."
    claims = extract_claim_texts(text)
    assert claims == ["First claim happened.", "Second claim caused concern."]


def test_allcaps_standalone_heading_dropped_but_inline_caps_sentence_kept():
    text = (
        "KEY POINTS\n"
        "The FED and ECB signaled a coordinated pause in tightening.\n"
        "RISKS TO WATCH\n"
        "Inflation could reaccelerate if energy prices spike again.\n"
        "FOOTNOTES"
    )
    claims = extract_claim_texts(text)
    combined = " ".join(claims)
    assert "KEY POINTS" not in combined
    assert "RISKS TO WATCH" not in combined
    assert "FOOTNOTES" not in combined
    assert "The FED and ECB signaled a coordinated pause in tightening." in claims
    assert "Inflation could reaccelerate if energy prices spike again." in claims


def test_allcaps_standalone_heading_from_acceptance_spec_dropped():
    text = 'KEY POINTS\nRISKS TO WATCH\nThe FED and ECB signaled a pause.'
    claims = extract_claim_texts(text)
    combined = " ".join(claims)
    assert "KEY POINTS" not in combined
    assert "RISKS TO WATCH" not in combined
    assert "The FED and ECB signaled a pause." in claims


def test_naver_cafe_style_block_stripped_but_real_claim_survives():
    text = (
        "작성자: 홍길동 작성일: 2026-07-08 15:42 조회 128 댓글 12\n"
        "코스피 지수가 금리 동결 발표 직후 급락했다.\n"
        "닉네임님: 오 진짜요?\n"
        "좋아요 12 | 스크랩 3 | 신고"
    )
    claims = extract_claim_texts(text)
    combined = " ".join(claims)
    assert "작성자" not in combined
    assert "작성일" not in combined
    assert "조회" not in combined
    assert "댓글" not in combined
    assert "오 진짜요" not in combined
    assert "좋아요" not in combined
    assert "스크랩" not in combined
    assert "신고" not in combined
    assert "코스피 지수가 금리 동결 발표 직후 급락했다." in claims


BOM = b"\xef\xbb\xbf"


def test_analyze_file_strips_utf8_bom_from_first_claim(tmp_path):
    input_file = tmp_path / "bom_source.txt"
    input_file.write_bytes(BOM + "First claim after BOM. Second claim follows.".encode("utf-8"))
    run_dir = analyze_file(
        mode="general",
        input_path=input_file,
        source_name="bom_source",
        source_type="news",
        output_root=tmp_path,
    )
    claims_lines = (run_dir / "ledger" / "claims.jsonl").read_text(encoding="utf-8").splitlines()
    claims = [json.loads(line) for line in claims_lines if line.strip()]
    first_claim_text = claims[0]["claim_text"]
    assert not first_claim_text.startswith("﻿")
    assert first_claim_text == "First claim after BOM."

    saved_input = (run_dir / "input" / "source_001.txt").read_text(encoding="utf-8")
    assert not saved_input.startswith("﻿")
