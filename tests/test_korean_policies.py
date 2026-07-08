"""Acceptance tests for the Korean-language policy engine and the English
long/short + boundary-safety false-positive fixes ported into risk_policy.py,
plus explicit pins for the hardening attack vectors (unicode/homoglyph advice,
gated 목표가/목표주가, 공매도 preservation, 인해-inside-확인해 non-causality).

Ported from the private lineage's test_korean_policies.py (imports renamed).
The private bundle-integration case is intentionally omitted here — bundle.py is
out of scope for this port; report/masking is covered via sanitize_for_report.
"""

from source_manifest_kit.core.classification import classify_claim
from source_manifest_kit.core.risk_policy import (
    detect_risk_flags,
    has_action_language,
    has_causality,
    has_future_return_projection,
    has_manipulation_framing,
    has_market_terms,
    has_position_sizing,
    has_private_markers,
    has_trade_probability,
    sanitize_for_report,
)
from source_manifest_kit.core.schema import SourceRecord, utc_now


def source(source_type):
    return SourceRecord("src_001", "run", source_type, "demo", None, None, None, utc_now(), "observable", "input/source_001.txt")


# ---------------------------------------------------------------------------
# (A) Korean coverage — previously-undetected Korean risk text
# ---------------------------------------------------------------------------
def test_korean_causality_and_market_terms_detected():
    text = "외국인 순매도 때문에 코스피 지수가 3% 급락했다."
    assert has_causality(text) is True
    assert has_market_terms(text) is True


def test_korean_market_causality_flag_in_finance_news():
    text = "외국인 순매도 때문에 코스피 지수가 3% 급락했다."
    flags = detect_risk_flags(text, "news", "finance", None)
    assert "unsupported_causality" in flags
    assert "market_causality_claim" in flags


def test_korean_manipulation_and_certainty_detected():
    text = "이건 누가 봐도 작전이다. 세력이 개미를 털려고 만든 하락이 분명하다."
    assert has_manipulation_framing(text) is True
    flags = detect_risk_flags(text, "community", "finance", None)
    assert "loaded_language" in flags  # manipulation framing
    assert "strong_certainty_language" in flags


def test_korean_deleted_chatroom_screenshot_is_unobservable():
    text = "삭제된 단톡방 캡처에 따르면 내부자들이 미리 팔았다고 한다."
    flags = detect_risk_flags(text, "community", "finance", None)
    assert "private_or_inaccessible_source" in flags
    assert "unobservable_evidence" in flags


def test_korean_deleted_screenshot_combo_flag():
    text = "삭제된 캡처만 돌아다닌다."
    flags = detect_risk_flags(text, "community", "finance", None)
    assert "unobservable_evidence" in flags


def test_korean_probability_reaches_trade_probability():
    text = "이 전략은 성공 확률 70% 라고 홍보한다."
    assert has_trade_probability(text) is True
    flags = detect_risk_flags(text, "community", "finance", None)
    assert "trade_probability_language" in flags


def test_korean_return_projection_reaches_trade_probability():
    text = "연 30% 수익률을 기대할 수 있다고 한다."
    assert has_future_return_projection(text) is True
    flags = detect_risk_flags(text, "community", "finance", None)
    assert "trade_probability_language" in flags


def test_korean_multiple_of_return_projection():
    text = "이 종목은 3배 수익이 난다고 주장한다."
    assert has_future_return_projection(text) is True


def test_korean_stale_date_temporal_words():
    for word in ["오늘", "어제", "방금", "최근", "현재", "오늘자"]:
        text = f"{word} 코스피가 급락했다."
        flags = detect_risk_flags(text, "news", "finance", None)
        assert "stale_or_missing_date" in flags, word


def test_korean_no_cause_disclaimer_suppresses_causality():
    text = "당국은 급락의 원인을 밝히지 않았다."
    assert has_causality(text) is False


def test_korean_various_causal_connectives():
    for marker in ["때문에", "탓에", "영향으로", "여파로"]:
        text = f"악재 {marker} 증시가 흔들렸다."
        assert has_causality(text) is True, marker


def test_korean_enter_now_guaranteed_profit_is_advice():
    text = "지금 들어가면 무조건 수익 납니다."
    assert has_action_language(text) is True
    flags = detect_risk_flags(text, "social", "finance", None)
    assert "investment_advice_language" in flags


def test_korean_full_buy_is_advice():
    assert has_action_language("삼성전자 풀매수 각입니다.") is True


def test_korean_explicit_imperatives_are_advice():
    for text in ["지금 사세요", "당장 파세요", "이 종목 강력 추천합니다"]:
        assert has_action_language(text) is True, text


# ---------------------------------------------------------------------------
# (B) Korean false positives — neutral market data must NOT be flagged/masked
# ---------------------------------------------------------------------------
def test_short_selling_balance_not_advice_and_not_masked():
    text = "공매도 잔고가 전일 대비 5% 증가했다."
    assert has_action_language(text) is False
    sanitized = sanitize_for_report(text, "finance")
    assert "공매도 잔고" in sanitized
    assert "[blocked" not in sanitized


def test_institutional_net_buying_not_advice_and_not_masked():
    text = "기관 순매수 규모는 1200억원이다."
    assert has_action_language(text) is False
    sanitized = sanitize_for_report(text, "finance")
    assert "순매수" in sanitized
    assert "[blocked" not in sanitized


def test_net_selling_not_masked():
    text = "외국인 순매도가 이어졌다."
    sanitized = sanitize_for_report(text, "finance")
    assert "순매도" in sanitized
    assert "[blocked" not in sanitized


def test_selling_pressure_terms_not_advice():
    for text in ["매도세가 강했다.", "매수세가 유입됐다.", "매물이 쏟아졌다."]:
        assert has_action_language(text) is False, text


def test_short_selling_terms_are_market_terms():
    assert has_market_terms("공매도 잔고가 늘었다.") is True
    assert has_market_terms("기관 순매수 규모가 컸다.") is True


def test_official_short_selling_resumption_is_not_advice():
    text = "금융위원회는 공매도 전면 재개를 검토 중이라고 발표했다."
    assert has_action_language(text) is False
    flags = detect_risk_flags(text, "official", "finance", None)
    assert "investment_advice_language" not in flags
    claim = classify_claim(text, source("official"), "finance")
    assert claim.claim_type != "excluded"
    assert has_market_terms(text) is True


def test_recommended_stock_disclosure_policy_not_flagged():
    text = "개인 투자자 보호를 위한 추천 종목 공시 제도가 논의됐다."
    assert has_action_language(text) is False
    sanitized = sanitize_for_report(text, "finance")
    assert "추천 종목" in sanitized
    assert "[blocked" not in sanitized


def test_icy_road_caution_is_clean():
    text = "빙판길 조심하세요."
    assert has_action_language(text) is False
    sanitized = sanitize_for_report(text, "finance")
    assert sanitized == text


def test_threw_a_ball_non_finance_not_advice():
    text = "아이가 공을 던졌다."
    assert has_action_language(text) is False
    sanitized = sanitize_for_report(text, "finance")
    assert sanitized == text


def test_strong_recommend_in_finance_context_is_advice():
    text = "이 종목 강력 추천합니다."
    assert has_action_language(text) is True
    flags = detect_risk_flags(text, "community", "finance", None)
    assert "investment_advice_language" in flags


def test_bare_recommend_book_not_advice():
    assert has_action_language("이 책 강력 추천합니다.") is False


# ---------------------------------------------------------------------------
# Pinned-sentence regressions
# ---------------------------------------------------------------------------
def test_pinned_korean_community_sentence_still_masked():
    text = "조심들하세요. 저는 환율보고 넥장에서 다 던졌어요. 뉴스마다 사고 팔고 할 필요는 없고 큰손들은 아무도 주식안합니다."
    assert has_action_language(text) is True
    sanitized = sanitize_for_report(text, "finance")
    assert "조심들하세요" not in sanitized
    assert "다 던졌어요" not in sanitized
    assert "사고 팔고" not in sanitized
    assert "주식안합니다" not in sanitized
    assert "[blocked-investment-action]" in sanitized
    assert "[blocked-urgency-language]" in sanitized


def test_pinned_korean_sentence_classified_excluded():
    text = "조심들하세요. 저는 환율보고 넥장에서 다 던졌어요. 뉴스마다 사고 팔고 할 필요는 없고 큰손들은 아무도 주식안합니다."
    claim = classify_claim(text, source("community"), "finance")
    assert claim.claim_type == "excluded"
    assert "investment_advice_language" in claim.risk_flags


# ---------------------------------------------------------------------------
# English boundary safety + long/short false-positive fixes
# ---------------------------------------------------------------------------
def test_policyholder_not_framing_or_motive():
    text = "The policyholder filed a routine claim."
    flags = detect_risk_flags(text, "news", "general", "2026-01-01")
    assert "framing_risk" not in flags
    assert has_market_terms(text) is False


def test_collapsed_word_not_loaded_language():
    text = "The old shed collapsed during the storm overnight."
    flags = detect_risk_flags(text, "news", "general", "2026-01-01")
    assert "loaded_language" not in flags


def test_collapse_still_flags_loaded_language():
    text = "The market collapse was a total disaster."
    flags = detect_risk_flags(text, "news", "finance", "2026-01-01")
    assert "loaded_language" in flags


def test_english_bare_long_short_not_advice():
    text = "The company has a long history of short supply chains."
    assert has_action_language(text) is False
    sanitized = sanitize_for_report(text, "finance")
    assert "long history" in sanitized
    assert "short supply" in sanitized
    assert "[blocked" not in sanitized


def test_english_trading_long_short_is_advice():
    for text in [
        "I would go long here.",
        "Time to short the index.",
        "Take a long position now.",
        "He is shorting the stock.",
    ]:
        assert has_action_language(text) is True, text


def test_english_go_long_masked_in_report():
    text = "The analyst said to go long."
    sanitized = sanitize_for_report(text, "finance")
    assert "go long" not in sanitized
    assert "[blocked-investment-action]" in sanitized


def test_english_buy_sell_still_flagged():
    assert has_action_language("Buy the stock now.") is True
    assert has_action_language("You should sell everything.") is True


# ---------------------------------------------------------------------------
# Classification outcomes / tiers
# ---------------------------------------------------------------------------
def test_korean_causal_market_flags_not_excluded():
    text = "외국인 순매도 때문에 코스피가 급락했다."
    assert has_causality(text)
    assert has_market_terms(text)
    claim = classify_claim(text, source("news"), "finance")
    assert claim.claim_type != "excluded"
    assert "unsupported_causality" in claim.risk_flags
    assert "market_causality_claim" in claim.risk_flags


def test_korean_manipulation_framing_routes_to_rumor():
    text = "이건 작전 세력이 분명하다. 개미털기 하는 거다."
    assert has_manipulation_framing(text)
    claim = classify_claim(text, source("community"), "finance")
    assert claim.claim_type != "reported_claim"
    assert claim.risk_tier == "high"


def test_korean_neutral_market_report_not_manipulation():
    assert not has_manipulation_framing("코스피가 외국인 순매수에 힘입어 상승했다.")


def test_korean_target_and_buy_recommendation_excluded():
    text = "지금 매수 추천합니다. 목표가 12만원."
    claim = classify_claim(text, source("user_note"), "finance")
    assert claim.claim_type == "excluded"
    assert claim.output_level == "excluded"
    assert "investment_advice_language" in claim.risk_flags


def test_korean_general_safety_caution_not_action():
    text = "빙판길 조심하세요."
    assert has_action_language(text) is False
    flags = detect_risk_flags(text, "news", "general", None)
    assert "action_recommendation_language" not in flags


def test_korean_success_probability_excluded():
    text = "이 종목 성공 확률 70%라고 홍보합니다."
    claim = classify_claim(text, source("community"), "finance")
    assert claim.claim_type == "excluded"
    assert "trade_probability_language" in claim.risk_flags


def test_korean_deleted_group_chat_capture_unobservable():
    text = "삭제된 단톡방 캡처를 봤습니다."
    flags = detect_risk_flags(text, "community", "finance", None)
    assert "private_or_inaccessible_source" in flags
    assert "unobservable_evidence" in flags
    claim = classify_claim(text, source("community"), "finance")
    assert claim.claim_type == "unobservable"


# ---------------------------------------------------------------------------
# (C) Goldset gap closures — positive + tricky negative
# ---------------------------------------------------------------------------
def test_imperative_buy_sara_masked_but_disappear_preserved():
    assert "[blocked" in sanitize_for_report("이 종목 지금 사라.", "finance")
    for text in ["악재가 모두 사라졌다.", "불안이 사라져 안심이다."]:
        sanitized = sanitize_for_report(text, "finance")
        assert "[blocked" not in sanitized, text
        assert "사라" in sanitized


def test_imperative_sell_palara_masked():
    sanitized = sanitize_for_report("지금 다 팔아라, 이 종목 물렸다.", "finance")
    assert "팔아라" not in sanitized
    assert "[blocked-investment-action]" in sanitized


def test_win_rate_percent_masked():
    sanitized = sanitize_for_report("이 종목 승률 90% 라던데.", "finance")
    assert "승률 90%" not in sanitized
    assert "[blocked-probability-language]" in sanitized
    assert has_trade_probability("승률 90% 전략") is True


def test_latin_hangul_particle_does_not_defeat_masking():
    sanitized = sanitize_for_report("이 리포트는 target price를 20만원으로 상향했다.", "finance")
    assert "target price" not in sanitized
    assert "[blocked-price-level]" in sanitized
    sanitized2 = sanitize_for_report("이 종목 allocation을 늘리라고 한다.", "finance")
    assert "allocation을" not in sanitized2
    assert "[blocked-allocation-language]" in sanitized2


def test_korean_and_hanja_target_price_flag_and_mask():
    for text in ["이 종목 목표가는 12만원", "이 종목 목 표 가 12만원", "삼성전자 目標價 12만원으로 상향"]:
        flags = detect_risk_flags(text, "analyst", "finance")
        assert "target_price_language" in flags, text
        assert "[blocked-price-level]" in sanitize_for_report(text, "finance"), text
    assert "target_price_language" not in detect_risk_flags("목표 수익률 50% 달성", "news", "finance")


def test_spaced_buy_recommendation_is_advice():
    assert has_action_language("이 종목 매 수 추천 드립니다.") is True


def test_spaced_short_selling_not_advice_and_preserved():
    text = "규제 당국은 공 매 도 를 단계적으로 재개하기로 했다."
    assert has_action_language(text) is False
    sanitized = sanitize_for_report(text, "finance")
    assert "공 매 도" in sanitized
    assert "[blocked" not in sanitized


def test_korean_weighting_increase_is_position_sizing():
    assert has_position_sizing("이 섹터 비중을 크게 확대하라는 의견이다.") is True


def test_passive_weighting_expansion_not_position_sizing():
    assert has_position_sizing("외국인 보유 비중이 사상 최고로 확대됐다.") is False


def test_korean_new_causal_connectives():
    assert has_causality("코스피가 외국인 매수세에 힘입어 반등했다.") is True
    assert has_causality("회사는 실적 부진이 환율 급등 때문이라고 설명했다.") is True


def test_unknown_cause_disclaimer_suppresses_causality():
    assert has_causality("급락의 원인은 아직 밝혀지지 않았다.") is False


def test_manipulation_intervening_words_and_collusion():
    assert has_manipulation_framing("언론이 이 사실을 조직적으로 숨기고 있는 게 틀림없다.") is True
    assert has_manipulation_framing("세력이 짜고 개미들 물량 뺏는 그림이지.") is True


def test_manipulation_negatives_drafting_and_neutral_insider_report():
    assert has_manipulation_framing("여당 세력이 예산안을 짜고 있다.") is False
    assert has_manipulation_framing("Regulators reviewed whether insiders traded on information before earnings.") is False


def test_english_insider_foreknowledge_is_manipulation():
    assert has_manipulation_framing("Insiders quietly dumped their shares before the news.") is True


def test_deleted_open_chat_is_unobservable_but_public_is_not():
    assert has_private_markers("지금은 지워진 오픈채팅방에서 돌던 얘기다.") is True
    assert has_private_markers("공개 오픈채팅방 공지를 인용해 보도했다.") is False


def test_market_term_additions():
    assert has_market_terms("SK하이닉스 short interest가 늘었다.") is True
    assert has_market_terms("거래소 공시 자료를 인용해 보도했다.") is True
    assert has_market_terms("상장기념식은 오전 9시에 열립니다.") is True
    assert has_market_terms("장 초반부터 분위기가 영 안 좋네요.") is True
    assert has_market_terms("물렸는데 그냥 존버 중입니다.") is True


def test_physical_and_word_internal_jang_not_market():
    assert has_market_terms("The farmers' market opens every Saturday.") is False
    assert has_market_terms("전통시장 야시장 골목이 붐볐다.") is False
    assert has_market_terms("공장 가동률이 높아 생산이 늘었다.") is False
    assert has_market_terms("The stock market fell on the day.") is True


def test_verbal_win_odds_are_trade_probability():
    assert has_trade_probability("이건 열에 아홉은 오르는 자리다.") is True
    assert has_trade_probability("This setup nearly always works out profitably.") is True
    assert has_trade_probability("The morning train nearly always runs on time.") is False


def test_english_increase_exposure_is_advice():
    assert has_action_language("It might be wise to increase your exposure to this name here.") is True
    assert has_action_language("Doctors advise limiting your exposure to strong sunlight.") is False


def test_korean_long_position_slang_is_advice():
    assert has_action_language("이 stock 지금 long 잡으면 무조건 먹는다.") is True
    assert has_action_language("장기 투자자는 long term 관점에서 접근한다.") is False


def test_korean_timing_pump_vs_macro_timing():
    assert has_action_language("지금이 바로 그 타이밍입니다. 이 기회 놓치면 안 됩니다.") is True
    assert has_action_language("금리 인하는 지금이 바로 그 타이밍이라는 분석이다.") is False


def test_korean_averaging_down_pump_vs_political_deflection():
    assert has_action_language("삼전 물타기 들어갑니다, 같이 가시죠.") is True
    assert has_action_language("야당이 물타기 들어간다고 비판했다.") is False


def test_korean_accumulate_spot_pump_vs_literal():
    assert has_action_language("빚내서라도 지금 담아야 할 자리라고 봅니다.") is True
    assert has_action_language("이삿짐을 담아야 할 자리를 먼저 정해야 한다.") is False


# ---------------------------------------------------------------------------
# (D) Co-signal gates and inflection tolerance
# ---------------------------------------------------------------------------
def test_verbal_odds_idiom_requires_finance_co_signal():
    assert has_trade_probability("열에 아홉은 감기몸살이 원인이다") is False
    assert has_trade_probability("이건 열에 아홉은 오르는 자리다.") is True
    assert "열에 아홉" in sanitize_for_report("열에 아홉은 감기몸살이 원인이다.", "finance")
    assert "[blocked-probability-language]" in sanitize_for_report("이건 열에 아홉은 오르는 자리다.", "finance")


def test_collusion_bounded_gap_with_market_co_signal():
    assert has_manipulation_framing("세력들이 짜고 개미들 물량 뺏는 거다") is True
    assert has_manipulation_framing("세력이 짜고 개미들 물량 뺏는 그림이지.") is True
    assert has_manipulation_framing("여당 세력이 예산안을 짜고 있다.") is False
    assert has_manipulation_framing("여당 세력이 예산안을 짜고 있다고 보도됐다.") is False


def test_exposure_advice_inflected_verbs_and_possessives():
    assert has_action_language("foreign desks increased their exposure to this name") is True
    assert "[blocked-investment-action]" in sanitize_for_report(
        "Foreign desks increased their exposure to this name.", "finance"
    )
    assert has_action_language("Prolonged exposure to loud noise damages hearing.") is False
    assert has_action_language("Doctors advise limiting your exposure to strong sunlight.") is False


# ---------------------------------------------------------------------------
# (E) FIX 6 — Korean causal markers must not substring-match innocent words.
# ---------------------------------------------------------------------------
def test_bare_인해_인한_do_not_fire_inside_innocent_words():
    assert has_causality("확인해보세요") is False
    assert has_causality("확인해 주세요") is False
    assert has_causality("확인했습니다") is False
    assert has_causality("이 사실을 확인한 결과입니다") is False


def test_connective_인해_인한_still_causal():
    assert has_causality("수요 감소로 인해 주가가 하락했다.") is True
    assert has_causality("규제 강화로 인한 불확실성이 커졌다.") is True
    assert has_causality("악재로 인해 투매가 나왔다.") is True


# ---------------------------------------------------------------------------
# (F) FIX 5 — Korean cover-up framing + market-sector vocabulary.
# ---------------------------------------------------------------------------
def test_korean_statistics_coverup_is_manipulation():
    assert has_manipulation_framing("정부가 실업률 숫자를 축소해서 발표했다는 의혹이 제기됐다.") is True
    assert has_manipulation_framing("당국이 통계를 축소 발표했다는 지적이 나왔다.") is True


def test_korean_innocent_size_reduction_not_manipulation():
    assert has_manipulation_framing("제품 크기를 축소했다.") is False
    assert has_manipulation_framing("배차 간격을 축소해 운행 효율을 높였다.") is False


def test_korean_sector_terms_are_market_terms():
    assert has_market_terms("반도체 업황이 개선됐다.") is True
    assert has_market_terms("이 섹터 실적이 좋다.") is True
    assert has_market_terms("업종 대표주가 강세다.") is True
    assert has_market_terms("투자심리가 위축됐다.") is True


# ---------------------------------------------------------------------------
# (G) FIX 1/2/4 — detector-level gap + guard checks.
# ---------------------------------------------------------------------------
def test_number_word_gap_position_sizing_detector():
    assert has_position_sizing("비중을 삼십 프로 확대하세요.") is True
    assert has_position_sizing("주식 비중을 이십 퍼센트 축소하라는 의견.") is True
    assert has_position_sizing("외국인 보유 비중이 사상 최고로 확대됐다.") is False


def test_product_mix_weighting_detector_guard():
    assert has_position_sizing("고부가가치 제품 비중을 확대해 수익성을 개선하겠다.") is False
    assert has_position_sizing("매출 비중을 크게 확대했다.") is False
    assert has_position_sizing("종목 비중을 확대하라는 조언이다.") is True


def test_korean_target_stock_price_gated():
    assert "target_price_language" in detect_risk_flags("목표주가를 32만원으로 상향했다.", "analyst", "finance")
    assert "target_price_language" in detect_risk_flags("이 종목 목표가 도달이 임박했다.", "analyst", "finance")
    assert "target_price_language" not in detect_risk_flags("이번 조치의 목표가 물가 안정임을 강조했다.", "news", "finance")
    assert "target_price_language" not in detect_risk_flags("회사의 목표가 분명하다.", "news", "finance")


# ---------------------------------------------------------------------------
# (H) Attack-vector pins required by the hardening port acceptance.
# ---------------------------------------------------------------------------
def test_unicode_zero_width_buy_is_excluded():
    # U+200B zero-width space inside "buy" must de-obfuscate and exclude.
    text = "Analysts say you should b​uy this stock immediately."
    claim = classify_claim(text, source("community"), "finance")
    assert claim.claim_type == "excluded"
    assert "investment_advice_language" in claim.risk_flags


def test_cyrillic_homoglyph_buy_is_excluded():
    # Cyrillic 'у' in "bуy" / 'е' in "sеll" fold to ASCII and exclude.
    text = "You should bуy the index and sеll bonds today."
    claim = classify_claim(text, source("community"), "finance")
    assert claim.claim_type == "excluded"
    assert "investment_advice_language" in claim.risk_flags


def test_soft_hyphen_buy_sell_is_excluded():
    text = "Time to bu­y the dip and se­ll losers."
    claim = classify_claim(text, source("community"), "finance")
    assert claim.claim_type == "excluded"


def test_target_stock_price_masked_goal_particle_preserved():
    # 목표주가 => masked; 목표가(goal-particle) => preserved and not flagged.
    masked = sanitize_for_report("증권사는 목표주가를 32만원으로 상향했다.", "finance")
    assert "목표주가" not in masked
    assert "[blocked-price-level]" in masked
    preserved = sanitize_for_report("이번 조치의 목표가 물가 안정임을 강조했다.", "finance")
    assert "목표가" in preserved
    assert "[blocked-price-level]" not in preserved


def test_short_selling_preserved_not_masked():
    # 공매도 is neutral market data and must survive sanitize.
    for text in ["공매도 잔고가 전일 대비 4.2% 늘었다.", "금융위원회는 공매도 전면 재개를 검토 중이라고 발표했다."]:
        sanitized = sanitize_for_report(text, "finance")
        assert "공매도" in sanitized
        assert "[blocked" not in sanitized


def test_인해_inside_확인해_not_causal():
    assert has_causality("자세한 내용은 링크에서 확인해보세요.") is False
    assert has_causality("담당자에게 문의해 확인한 뒤 처리하겠습니다.") is False
    # connective form still causal
    assert has_causality("수요 감소로 인해 반도체 주가가 하락했다.") is True
