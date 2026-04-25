"""query_expansion_v1 스키마 Pydantic 검증 테스트."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipeline.retrieval.query_expansion_v1.query_expansion_schema import ClauseQueryExpansion


def _valid_payload() -> dict:
    return {
        "expansion_query": (
            "주택임대차 계약에서 임차인의 전입신고 및 확정일자 취득을 제한하는 특약의 효력, "
            "대항력과 우선변제권 제한 가능성, 임차인에게 불리한 약정의 강행규정 위반 여부를 확인한다."
        ),
        "keywords": [
            "전입신고",
            "확정일자",
            "대항력",
            "우선변제권",
            "강행규정",
            "주택임대차보호법",
        ],
    }


def test_valid_mock_json_passes_clause_query_expansion_validation() -> None:
    model = ClauseQueryExpansion.model_validate(_valid_payload())
    assert model.expansion_query
    assert len(model.keywords) >= 3


def test_keywords_are_trimmed_and_deduplicated() -> None:
    payload = _valid_payload()
    payload["keywords"] = [" 전입신고 ", "확정일자", "전입신고", "대항력"]

    model = ClauseQueryExpansion.model_validate(payload)
    assert model.keywords == ["전입신고", "확정일자", "대항력"]


def test_keywords_fail_when_less_than_three_after_cleanup() -> None:
    payload = _valid_payload()
    payload["keywords"] = ["전입신고", "전입신고", " "]

    with pytest.raises(ValidationError) as exc_info:
        ClauseQueryExpansion.model_validate(payload)

    assert "keywords는 중복 제거 후 최소 3개 이상" in str(exc_info.value)


def test_extra_fields_are_forbidden() -> None:
    payload = _valid_payload()
    payload["law_query"] = {}

    with pytest.raises(ValidationError):
        ClauseQueryExpansion.model_validate(payload)
