"""query_expansion 메인 패키지 실행 로직 단위 테스트.

실제 Vertex AI Gemini를 호출하지 않고 fake client를 주입해 테스트한다.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from pipeline.retrieval.query_expansion.query_expansion import (
    QueryExpansionError,
    expand_clause,
)
from pipeline.retrieval.query_expansion.query_expansion_schema import ClauseQueryExpansion
from shared.llm.gemini_client import LLMError


def _valid_payload() -> dict:
    return {
        "expansion_query": (
            "[쟁점 유형]\n"
            "갱신·해지·계약종료\n\n"
            "[자유 쟁점]\n"
            "임차인 해지 통보 시점, 계약 만료 전 의사 통지, 묵시적 갱신 성립 여부, 계약 종료 시점 분쟁\n\n"
            "[관련 법률 개념 및 규칙]\n"
            "해지 의사의 통지와 도달, 계약갱신요구권·갱신거절, 묵시적 갱신의 요건과 효력이 충돌할 때 "
            "계약 종료 시점을 어떻게 판단할지에 대한 검색 포인트.\n\n"
            "[유사 분쟁 사실관계]\n"
            "임차인이 만료 전 해지 통보를 했으나 임대인이 묵시적 갱신을 주장하거나, "
            "통지 시점·방법을 두고 계약 존속 여부가 다투어지는 임대차 분쟁."
        ),
        "keywords": ["해지 통보", "묵시적 갱신", "계약 종료", "임대차"],
    }


def _invalid_payload() -> dict:
    payload = copy.deepcopy(_valid_payload())
    payload["keywords"] = ["해지 통보"]
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

    clause_text = "임차인은 계약 만료 2개월 전 해지 의사를 통보한다."
    result = expand_clause(clause_text, client=client)

    assert isinstance(result, ClauseQueryExpansion)
    assert result.expansion_query == payload["expansion_query"]
    assert len(client.calls) == 1
    assert client.calls[0]["response_schema"] is ClauseQueryExpansion


def test_expand_clause_accepts_dict_response() -> None:
    payload = _valid_payload()
    client = FakeGeminiClient([payload])

    result = expand_clause("임차인은 계약 만료 2개월 전 해지 의사를 통보한다.", client=client)

    assert isinstance(result, ClauseQueryExpansion)
    assert result.keywords == ["해지 통보", "묵시적 갱신", "계약 종료", "임대차"]


def test_expand_clause_accepts_json_string_response() -> None:
    payload = _valid_payload()
    raw_json = json.dumps(payload, ensure_ascii=False)
    client = FakeGeminiClient([raw_json])

    result = expand_clause("임차인은 계약 만료 2개월 전 해지 의사를 통보한다.", client=client)

    assert isinstance(result, ClauseQueryExpansion)
    assert result.keywords == ["해지 통보", "묵시적 갱신", "계약 종료", "임대차"]


def test_expand_clause_accepts_json_code_fence_response() -> None:
    payload = _valid_payload()
    raw_json = json.dumps(payload, ensure_ascii=False, indent=2)
    fenced = f"```json\n{raw_json}\n```"
    client = FakeGeminiClient([fenced])

    result = expand_clause("임차인은 계약 만료 2개월 전 해지 의사를 통보한다.", client=client)

    assert isinstance(result, ClauseQueryExpansion)
    assert result.expansion_query == payload["expansion_query"]


def test_expand_clause_retries_after_invalid_response_and_succeeds() -> None:
    invalid_payload = _invalid_payload()
    valid_payload = _valid_payload()
    client = FakeGeminiClient([invalid_payload, valid_payload])

    result = expand_clause("임차인은 계약 만료 2개월 전 해지 의사를 통보한다.", client=client, max_retries=1)

    assert isinstance(result, ClauseQueryExpansion)
    assert result.expansion_query == valid_payload["expansion_query"]
    assert len(client.calls) == 2

    repair_prompt = client.calls[1]["contents"]
    assert "검증에 실패" in repair_prompt
    assert "expansion_query" in repair_prompt
    assert "keywords" in repair_prompt


def test_expand_clause_raises_after_retry_exhausted() -> None:
    invalid_payload_1 = _invalid_payload()
    invalid_payload_2 = _invalid_payload()
    client = FakeGeminiClient([invalid_payload_1, invalid_payload_2])

    with pytest.raises(QueryExpansionError) as exc_info:
        expand_clause(
            "임차인은 계약 만료 2개월 전 해지 의사를 통보한다.",
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
        "임차인은 계약 만료 2개월 전 해지 의사를 통보한다.",
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

    result = expand_clause("임차인은 계약 만료 2개월 전 해지 의사를 통보한다.", client=client, max_retries=0)

    assert isinstance(result, ClauseQueryExpansion)
    assert len(client.calls) == 2
    assert client.calls[0]["response_schema"] is ClauseQueryExpansion
    assert client.calls[1]["response_schema"] is None
