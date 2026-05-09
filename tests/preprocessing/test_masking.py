"""pipeline.preprocessing.masking 단위 테스트."""
from __future__ import annotations

import pytest

from pipeline.preprocessing.masking import mask_pii


# ---------------------------------------------------------------------------
# 양성 케이스: 이번 전처리 범위의 PII가 [MASKED_*]로 치환되는가
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected_token",
    [
        ("주민등록번호 900101-1234567 입니다.", "[MASKED_RRN]"),
        ("문의: foo.bar+contract@example.com", "[MASKED_EMAIL]"),
        ("연락처 010-1234-5678", "[MASKED_PHONE_MOBILE]"),
        ("연락처 01012345678", "[MASKED_PHONE_MOBILE]"),
        ("사무실 02-555-1234", "[MASKED_PHONE_LANDLINE]"),
        ("주 소 서울특별시 마포구 아현동 700", "[MASKED_ADDRESS]"),
    ],
)
def test_mask_pii_replaces_each_kind(raw: str, expected_token: str) -> None:
    masked = mask_pii(raw)
    assert expected_token in masked
    # 원본 식별자는 사라져야 한다.
    digits_only = "".join(ch for ch in raw if ch.isdigit())
    if expected_token != "[MASKED_EMAIL]":
        # 이메일은 숫자 비교로 확인하기 어려워 별도 검증.
        assert digits_only not in masked.replace(expected_token, "")
    else:
        assert "@" not in masked


# ---------------------------------------------------------------------------
# 범위 제한: 사업자번호와 계좌번호는 이번 기능의 마스킹 대상이 아니다
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        "사업자등록번호 123-45-67890",
        "계좌 110-1234-567890",
    ],
)
def test_mask_pii_does_not_mask_out_of_scope_numbers(raw: str) -> None:
    masked = mask_pii(raw)

    assert masked == raw


# ---------------------------------------------------------------------------
# 음성 케이스: 본문 내 일반 숫자/주소 토큰을 잘못 잡지 않는가
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    [
        # 도로명 주소 번지 — `\b\d{2,6}-\d{2,6}-\d{2,7}\b`에는 맞지 않음 (세 그룹 아님).
        "서울특별시 강남구 테헤란로 123-45",
        # 단순 면적·금액 표기.
        "전용면적 84.21제곱미터, 보증금 100,000,000원",
        "차임 월 800,000원",
        # 임차주택 소재지는 스키마 추출 대상이라 보존한다.
        "| 소재지 | 서울특별시 | 마포구 아현동 700 |",
        # 조항 번호.
        "제1조 제2항",
        # 단일 하이픈 숫자(전화·계좌 정규식 모두 3그룹 요구).
        "주차장 B-2 구역",
    ],
)
def test_mask_pii_preserves_non_pii_text(raw: str) -> None:
    masked = mask_pii(raw)

    assert "[MASKED_" not in masked
    assert masked == raw


# ---------------------------------------------------------------------------
# 다중 PII가 섞인 문서
# ---------------------------------------------------------------------------
def test_mask_pii_handles_multiple_kinds_in_one_text() -> None:
    raw = (
        "임대인 홍길동\n"
        "주민등록번호 900101-1234567\n"
        "휴대폰 010-1234-5678\n"
        "사무실 02-555-9999\n"
        "이메일 hong@example.com\n"
        "주 소 서울특별시 마포구 아현동 700\n"
    )

    masked = mask_pii(raw)

    assert "[MASKED_RRN]" in masked
    assert "[MASKED_PHONE_MOBILE]" in masked
    assert "[MASKED_PHONE_LANDLINE]" in masked
    assert "[MASKED_EMAIL]" in masked
    assert "[MASKED_ADDRESS]" in masked
    # 비-PII인 이름은 그대로 남아야 한다 (이번 범위는 이름 마스킹 안 함).
    assert "홍길동" in masked
