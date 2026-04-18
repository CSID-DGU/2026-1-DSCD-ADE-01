"""query_expansion 실행 로직 단위 테스트.

실제 Vertex AI Gemini를 호출하지 않고 fake client를 주입해 테스트한다.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from retrieval.query_expansion import QueryExpansionError, expand_clause
from retrieval.query_expansion_schema import ClauseQueryExpansion
from shared.llm.gemini_client import LLMError


def _valid_payload() -> dict:
    return {
        "schema_version": "qe_v1",
        "clause_text": "임차인은 계약 만료 2개월 전 해지 의사를 통보한다.",
        "normalized_clause": "임차인의 해지 통지 시점과 계약 종료 효력 판단이 필요한 특약",
        "domain_scope": "residential_lease",
        "issue_type_candidates_freeform": ["해지 통지 시점", "묵시적 갱신 충돌 가능성"],
        "issue_types_normalized": ["갱신·해지·계약종료"],
        "risk_hypotheses": ["해지 통지 시점 분쟁 가능성", "묵시적 갱신 주장 가능성"],
        "compound_clause_detected": False,
        "sub_issue_summaries": [],
        "law_query": {
            "legal_issue": "해지 통지 시점과 계약 종료 효력",
            "applicable_rules": ["해지 통보의 도달 시점", "묵시적 갱신 요건"],
            "law_article_candidates": [
                {
                    "law_name": "주택임대차보호법",
                    "article_no": "6조",
                    "article_title": "계약의 갱신",
                    "confidence": "medium",
                    "reason": "해지 통지 및 묵시적 갱신 판단에 직접 관련된다.",
                }
            ],
            "law_keywords": ["해지 통보", "묵시적 갱신", "계약 종료"],
            "law_dense_query": "주택임대차에서 해지 통지 시점과 묵시적 갱신 성립 요건을 확인한다.",
            "retrieval_terms": {
                "must_terms": ["해지 통보"],
                "should_terms": ["묵시적 갱신", "계약 종료"],
                "exclude_terms": [],
                "synonyms": ["해지 통지", "해지 의사 통지"],
                "query_variants": ["임차인 해지 통보 시 계약 종료 시점"],
            },
            "target_fields": ["law_child_text"],
        },
        "case_query": {
            "case_issue_query": "임차인의 해지 통보 시점과 계약 종료 효력에 관한 판시사항을 찾는다.",
            "case_fact_pattern_query": "만료 전 통지 여부와 묵시적 갱신 주장이 충돌하는 임대차 분쟁 사실관계를 찾는다.",
            "case_keywords": ["해지 통보", "묵시적 갱신", "계약 종료"],
            "referenced_law_candidates": [
                {
                    "law_name": "주택임대차보호법",
                    "article_no": "6조",
                    "confidence": "medium",
                }
            ],
            "retrieval_terms": {
                "must_terms": ["해지 통보"],
                "should_terms": ["묵시적 갱신", "효력"],
                "exclude_terms": [],
                "synonyms": ["해지 통지"],
                "query_variants": ["해지 통보의 효력 관련 판례"],
            },
            "target_fields": ["case_issue_summary", "case_holding_summary"],
        },
        "counsel_query": {
            "counsel_question_query": "해지 통보 시점을 둘러싼 임차인 유사 상담 사례를 찾는다.",
            "counsel_answer_query": "묵시적 갱신과 해지 통보 효력에 대한 상담 답변 방향을 찾는다.",
            "user_question_intent": "해지 통보의 효력과 분쟁 리스크 확인",
            "counsel_keywords": ["해지 통보", "묵시적 갱신", "임대차"],
            "expected_tags": ["#임대차", "#계약", "#퇴거"],
            "expected_answer_points": ["해지 통보 기한", "묵시적 갱신 성립 요건"],
            "retrieval_terms": {
                "must_terms": ["해지 통보"],
                "should_terms": ["묵시적 갱신", "임차인"],
                "exclude_terms": [],
                "synonyms": ["해지 통지"],
                "query_variants": ["해지 통보 관련 상담 사례"],
            },
            "target_fields": ["counsel_question", "counsel_answer"],
        },
        "source_routing": [
            {"source_type": "law", "priority": "high", "reason": "조문 확인이 필요하다."},
            {"source_type": "case", "priority": "medium", "reason": "쟁점 유사 판례가 필요하다."},
            {"source_type": "counsel", "priority": "medium", "reason": "유사 상담 맥락이 유용하다."},
        ],
        "expansion_notes": None,
    }


def _invalid_payload() -> dict:
    payload = copy.deepcopy(_valid_payload())
    payload["law_query"]["target_fields"] = ["counsel_answer"]
    return payload


class FakeGeminiClient:
    """generate 호출 결과를 순서대로 반환하는 fake client."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        contents: str | list,
        *,
        model: str | None = None,
        system_instruction: str | None = None,
        response_schema: type | None = None,
    ) -> Any:
        self.calls.append(
            {
                "contents": contents,
                "model": model,
                "system_instruction": system_instruction,
                "response_schema": response_schema,
            }
        )

        if not self.responses:
            raise RuntimeError("FakeGeminiClient responses exhausted")

        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_expand_clause_accepts_parsed_model_response() -> None:
    payload = _valid_payload()
    model = ClauseQueryExpansion.model_validate(payload)
    client = FakeGeminiClient([model])

    result = expand_clause(payload["clause_text"], client=client)

    assert isinstance(result, ClauseQueryExpansion)
    assert result.clause_text == payload["clause_text"]
    assert len(client.calls) == 1
    assert client.calls[0]["response_schema"] is ClauseQueryExpansion


def test_expand_clause_accepts_dict_response() -> None:
    payload = _valid_payload()
    client = FakeGeminiClient([payload])

    result = expand_clause(payload["clause_text"], client=client)

    assert isinstance(result, ClauseQueryExpansion)
    assert result.law_query.law_keywords == ["해지 통보", "묵시적 갱신", "계약 종료"]


def test_expand_clause_accepts_json_string_response() -> None:
    payload = _valid_payload()
    raw_json = json.dumps(payload, ensure_ascii=False)
    client = FakeGeminiClient([raw_json])

    result = expand_clause(payload["clause_text"], client=client)

    assert isinstance(result, ClauseQueryExpansion)
    assert result.case_query.case_keywords == ["해지 통보", "묵시적 갱신", "계약 종료"]


def test_expand_clause_retries_after_invalid_response_and_succeeds() -> None:
    invalid_payload = _invalid_payload()
    valid_payload = _valid_payload()
    client = FakeGeminiClient([invalid_payload, valid_payload])

    result = expand_clause(valid_payload["clause_text"], client=client, max_retries=1)

    assert isinstance(result, ClauseQueryExpansion)
    assert result.clause_text == valid_payload["clause_text"]
    assert len(client.calls) == 2

    repair_prompt = client.calls[1]["contents"]
    assert "검증에 실패" in repair_prompt
    assert "source_type" in repair_prompt
    assert "target_fields" in repair_prompt


def test_expand_clause_raises_after_retry_exhausted() -> None:
    invalid_payload_1 = _invalid_payload()
    invalid_payload_2 = _invalid_payload()
    client = FakeGeminiClient([invalid_payload_1, invalid_payload_2])

    with pytest.raises(QueryExpansionError) as exc_info:
        expand_clause(
            _valid_payload()["clause_text"],
            client=client,
            max_retries=1,
        )

    assert "query expansion 생성/검증 실패" in str(exc_info.value)
    assert len(client.calls) == 2


def test_expand_clause_respects_max_retries_value() -> None:
    client = FakeGeminiClient(
        [
            _invalid_payload(),
            _invalid_payload(),
            _valid_payload(),
        ]
    )

    result = expand_clause(
        _valid_payload()["clause_text"],
        client=client,
        max_retries=2,
    )

    assert isinstance(result, ClauseQueryExpansion)
    assert len(client.calls) == 3


def test_expand_clause_falls_back_when_vertex_schema_too_complex() -> None:
    """structured output 한도 오류 시 response_schema=None으로 폴백한다."""
    payload = _valid_payload()
    raw_json = json.dumps(payload, ensure_ascii=False)
    client = FakeGeminiClient(
        [
            LLMError(
                "400 INVALID_ARGUMENT. The specified schema produces a constraint "
                "that has too many states for serving."
            ),
            raw_json,
        ]
    )

    result = expand_clause(payload["clause_text"], client=client, max_retries=0)

    assert isinstance(result, ClauseQueryExpansion)
    assert len(client.calls) == 2
    assert client.calls[0]["response_schema"] is ClauseQueryExpansion
    assert client.calls[1]["response_schema"] is None