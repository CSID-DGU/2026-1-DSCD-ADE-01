"""임대차 특약 query expansion 실행 로직."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from retrieval.query_expansion_prompt import SYSTEM_PROMPT, build_user_prompt
from retrieval.query_expansion_schema import ClauseQueryExpansion
from shared.llm.gemini_client import LLMError, GeminiClient, gemini_client


class QueryExpansionError(RuntimeError):
    """Query expansion 생성 또는 검증 실패."""


def _is_schema_state_limit_error(error: LLMError) -> bool:
    """Vertex structured output 스키마 상태 수 제한 오류인지 판별한다."""
    message = str(error).lower()
    return (
        "invalid_argument" in message
        and (
            "too many states for serving" in message
            or "specified schema produces a constraint" in message
        )
    )


def _generate_with_schema_fallback(llm: GeminiClient, prompt: str) -> Any:
    """가능하면 structured output을 사용하고, 스키마 한도 오류 시 text 모드로 폴백."""
    try:
        return llm.generate(
            contents=prompt,
            system_instruction=SYSTEM_PROMPT,
            response_schema=ClauseQueryExpansion,
        )
    except LLMError as error:
        if not _is_schema_state_limit_error(error):
            raise

        # Vertex가 스키마 제약 수 초과로 structured output을 거부하면
        # text(JSON) 응답으로 받아 로컬 Pydantic 검증으로 이어간다.
        return llm.generate(
            contents=prompt,
            system_instruction=SYSTEM_PROMPT,
            response_schema=None,
        )


def _parse_expansion_result(result: Any) -> ClauseQueryExpansion:
    """Gemini wrapper 반환값을 ClauseQueryExpansion으로 정규화한다.

    shared.llm.gemini_client.GeminiClient.generate는 response_schema가 있으면
    response.parsed를 반환하므로, 일반적으로 이미 ClauseQueryExpansion 객체가 온다.
    다만 SDK/호출 방식 차이에 대비해 dict/str도 처리한다.
    """
    if isinstance(result, ClauseQueryExpansion):
        return result

    if isinstance(result, dict):
        return ClauseQueryExpansion.model_validate(result)

    if isinstance(result, str):
        return ClauseQueryExpansion.model_validate_json(_extract_json_object(result))

    raise QueryExpansionError(
        f"지원하지 않는 Gemini 응답 타입입니다: {type(result).__name__}"
    )


def _strip_json_code_fence(text: str) -> str:
    """```json ... ``` 형태 응답을 순수 JSON 텍스트로 정리한다."""
    stripped = text.strip()
    fence_match = re.fullmatch(
        r"```(?:json|JSON)?\s*(.*?)\s*```",
        stripped,
        flags=re.DOTALL,
    )
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


def _extract_json_object(text: str) -> str:
    """응답에 설명문이 섞여 있어도 가장 바깥 JSON object를 추출한다."""
    stripped = _strip_json_code_fence(text)
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return stripped
    return stripped[start : end + 1].strip()


def build_repair_prompt(
    *,
    clause_text: str,
    invalid_output: Any,
    error: Exception,
) -> str:
    """스키마 검증 실패 시 재시도용 repair prompt를 만든다."""
    return f"""
이전 응답은 ClauseQueryExpansion Pydantic schema 검증에 실패했다.

입력 특약:
{clause_text}

이전 응답:
{invalid_output}

검증 오류:
{repr(error)}

수정 지시:
- 순수 JSON 객체 하나만 다시 출력하라.
- markdown 코드블록이나 설명문을 붙이지 말라.
- schema에 없는 필드는 제거하라.
- 누락된 필수 필드는 채워라.
- enum 값은 허용된 문자열 값만 사용하라.
- issue_types_normalized에는 Enum 이름이 아니라 한글 문자열 값을 사용하라.
- legal_issue, law_dense_query, case_issue_query, case_fact_pattern_query, counsel_question_query, counsel_answer_query, user_question_intent는 반드시 문자열로 작성하라.
- applicable_rules, law_keywords, case_keywords, counsel_keywords는 반드시 문자열 배열로 작성하라.
- query_text 같은 래퍼 객체를 만들지 말고 필드 값 자체를 직접 채워라.
- law_article_candidates에 객체가 있으면 law_name, article_no, article_title, confidence를 정확히 채우고 reason은 알 수 있을 때만 작성하라.
- law_name이 불확실하면 law_article_candidates는 빈 배열로 둔다.
- referenced_law_candidates도 law_name이 불확실하면 빈 배열로 둔다.
- law_query.target_fields에는 law_child_text 또는 law_parent_text만 사용하라.
- case_query.target_fields에는 case_issue_summary, case_holding_summary, case_referenced_law, case_full_text만 사용하라.
- counsel_query.target_fields에는 counsel_question, counsel_tags, counsel_answer만 사용하라.
- source_routing은 불확실하면 빈 배열 []로 둔다.
- source_routing을 작성할 때는 source_type, priority, reason만 사용하고 confidence는 절대 넣지 말라.
- article_no_candidates, priority, confidence 같은 스키마 외 필드는 생성하지 말라.
""".strip()


def expand_clause(
    clause_text: str,
    *,
    client: GeminiClient | None = None,
    max_retries: int = 1,
) -> ClauseQueryExpansion:
    """특약 문장을 ClauseQueryExpansion으로 변환한다.

    Parameters
    ----------
    clause_text:
        계약서 특약 원문.
    client:
        테스트/주입용 GeminiClient. None이면 공통 gemini_client 사용.
    max_retries:
        검증 실패 시 repair retry 횟수.

    Returns
    -------
    ClauseQueryExpansion
        법령/판례/상담사례 검색용 query expansion 결과.
    """
    llm = client or gemini_client

    user_prompt = build_user_prompt(clause_text)
    last_error: Exception | None = None
    last_output: Any = None

    for attempt in range(max_retries + 1):
        if attempt == 0:
            prompt = user_prompt
        else:
            assert last_error is not None  # for type checkers
            prompt = build_repair_prompt(
                clause_text=clause_text,
                invalid_output=last_output,
                error=last_error,
            )

        result: Any = None
        try:
            result = _generate_with_schema_fallback(llm, prompt)
            return _parse_expansion_result(result)
        except (ValidationError, QueryExpansionError, LLMError) as error:
            last_error = error
            last_output = result

    # loop가 종료되면 모든 시도를 소진한 상태다.
    assert last_error is not None
    raise QueryExpansionError(
        f"query expansion 생성/검증 실패 (retries={max_retries}): {last_error}"
    ) from last_error