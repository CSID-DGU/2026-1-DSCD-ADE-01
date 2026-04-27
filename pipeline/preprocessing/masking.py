"""정규식 기반 PII 마스킹.

LLM에 OCR 텍스트를 넘기기 전에 다음 5종 식별자를 ``[MASKED_*]`` 토큰으로
치환한다.

- 주민등록번호 (``RRN``)
- 사업자등록번호 (``BUSINESS_REG``)
- 이메일 (``EMAIL``)
- 휴대폰 번호 (``PHONE_MOBILE``)
- 일반(시내) 전화번호 (``PHONE_LANDLINE``)
- 계좌번호 (``ACCOUNT``)

이름·개인주소는 정규식으로 안전하게 식별할 수 없어 본 모듈에서는 다루지
않는다 (부동산 주소 오마스킹 위험). NER 기반 확장은 추후 과제.
"""
from __future__ import annotations

import re

# 패턴 적용 순서가 정확도에 직결된다.
# 더 길고 구체적인 패턴(주민번호, 사업자번호 등)을 먼저 치환해야
# 마지막 ``ACCOUNT`` 정규식이 substring을 잘못 잡지 않는다.
PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("RRN", re.compile(r"\b\d{6}\s*-\s*\d{7}\b")),
    ("BUSINESS_REG", re.compile(r"\b\d{3}-\d{2}-\d{5}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE_MOBILE", re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b")),
    ("PHONE_LANDLINE", re.compile(r"\b0\d{1,2}-\d{3,4}-\d{4}\b")),
    ("ACCOUNT", re.compile(r"\b\d{2,6}-\d{2,6}-\d{2,7}\b")),
]


def mask_pii(text: str) -> str:
    """평문에서 PII 5종을 ``[MASKED_<TYPE>]``으로 치환한다."""
    for label, pattern in PII_PATTERNS:
        text = pattern.sub(f"[MASKED_{label}]", text)
    return text
