"""query_expansion2_schema Pydantic 검증 테스트."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipeline.retrieval.query_expansion2.query_expansion_schema import ClauseQueryExpansion


def _valid_payload() -> dict:
    return {
        "expansion_query": (
            "[쟁점 유형]\n"
            "전입신고·확정일자·대항력\n\n"
            "[자유 쟁점]\n"
            "전입신고 제한, 확정일자 취득 제한, 대항력 상실 가능성, 우선변제권 제한, 임차인에게 불리한 특약\n\n"
            "[관련 법률 개념 및 규칙]\n"
            "주택임대차에서 전입신고는 대항력 취득과 관련되고, 확정일자는 우선변제권 확보와 관련된다. "
            "임차인의 권리 확보 절차를 제한하거나 포기하게 하는 특약은 임차인에게 불리한 약정의 효력 제한 및 "
            "강행규정 적용 가능성과 연결된다.\n\n"
            "[유사 분쟁 사실관계]\n"
            "임대인이 계약서 특약을 근거로 임차인의 전입신고 또는 확정일자 취득을 제한하고, "
            "이후 보증금 회수, 우선순위, 대항력 인정 여부가 문제되는 상황."
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
