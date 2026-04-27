"""pipeline.preprocessing.masking 단위 테스트."""
from __future__ import annotations

import pytest

from pipeline.preprocessing.masking import mask_pii


# ---------------------------------------------------------------------------
# 양성 케이스: 각 PII 종류가 [MASKED_*]로 치환되는가
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected_token",
    [
        ("주민등록번호 900101-1234567 입니다.", "[MASKED_RRN]"),
        ("사업자등록번호 123-45-67890 입니다.", "[MASKED_BUSINESS_REG]"),
        ("문의: foo.bar+contract@example.com", "[MASKED_EMAIL]"),
        ("연락처 010-1234-5678", "[MASKED_PHONE_MOBILE]"),
        ("연락처 01012345678", "[MASKED_PHONE_MOBILE]"),
        ("사무실 02-555-1234", "[MASKED_PHONE_LANDLINE]"),
        ("계좌 110-1234-567890", "[MASKED_ACCOUNT]"),
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
# 우선순위: 주민·사업자번호가 ACCOUNT 정규식에 잡히기 전에 먼저 치환되는가
# ---------------------------------------------------------------------------
def test_rrn_takes_priority_over_account_pattern() -> None:
    """주민등록번호 ``900101-1234567``은 ``ACCOUNT`` 정규식
    (``\\d{2,6}-\\d{2,6}-\\d{2,7}``)에도 일부 일치할 수 있는 형태다.
    더 구체적인 RRN 패턴이 먼저 적용되어야 ``[MASKED_RRN]``으로 잡힌다.
    """
    masked = mask_pii("주민등록번호 900101-1234567 입니다.")

    assert "[MASKED_RRN]" in masked
    assert "[MASKED_ACCOUNT]" not in masked


def test_business_reg_takes_priority_over_account_pattern() -> None:
    masked = mask_pii("사업자등록번호 123-45-67890")

    assert "[MASKED_BUSINESS_REG]" in masked
    assert "[MASKED_ACCOUNT]" not in masked


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
        "계좌 110-1234-567890\n"
        "사업자번호 123-45-67890\n"
    )

    masked = mask_pii(raw)

    assert "[MASKED_RRN]" in masked
    assert "[MASKED_PHONE_MOBILE]" in masked
    assert "[MASKED_PHONE_LANDLINE]" in masked
    assert "[MASKED_EMAIL]" in masked
    assert "[MASKED_ACCOUNT]" in masked
    assert "[MASKED_BUSINESS_REG]" in masked
    # 비-PII인 이름은 그대로 남아야 한다 (이번 범위는 이름 마스킹 안 함).
    assert "홍길동" in masked
