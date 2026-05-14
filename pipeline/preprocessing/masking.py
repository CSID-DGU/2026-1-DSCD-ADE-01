"""정규식 기반 PII 마스킹.

계약서 텍스트를 파싱하기 전에 이번 전처리 범위에서 필요한 식별자만
``[MASKED_*]`` 토큰으로 치환한다.

- 주민등록번호 (``RRN``)
- 이메일 (``EMAIL``)
- 휴대폰 번호 (``PHONE_MOBILE``)
- 일반(시내) 전화번호 (``PHONE_LANDLINE``)
- 서명란의 개인 주소 라인 (``ADDRESS``)

이름은 다루지 않는다. 임차주택 소재지는 스키마 추출 대상이라 보존하고,
``주 소 ...``처럼 서명란에 가까운 개인 주소 라인만 단순 마스킹한다.
"""
from __future__ import annotations

import re

PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("RRN", re.compile(r"\b\d{6}\s*-\s*\d{7}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE_MOBILE", re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b")),
    ("PHONE_LANDLINE", re.compile(r"\b0\d{1,2}-\d{3,4}-\d{4}\b")),
    ("ADDRESS", re.compile(r"(?m)^\s*주\s*소\s+.+$")),
]


def mask_pii(text: str) -> str:
    """평문에서 이번 전처리 범위의 PII를 ``[MASKED_<TYPE>]``으로 치환한다."""
    for label, pattern in PII_PATTERNS:
        text = pattern.sub(f"[MASKED_{label}]", text)
    return text
