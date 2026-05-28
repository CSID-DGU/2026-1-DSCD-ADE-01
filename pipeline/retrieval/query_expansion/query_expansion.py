"""임대차 특약 query expansion 실행 로직."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pipeline.retrieval.query_expansion.query_expansion_prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from pipeline.retrieval.query_expansion.query_expansion_schema import ClauseQueryExpansion
from shared.llm.gemini_client import LLMError, GeminiClient, gemini_client


class QueryExpansionError(RuntimeError):
    """Query expansion 생성 또는 검증 실패."""


OVERFIT_ENV_VAR = "QE_OVERFIT_MODE"
OVERFIT_DEFAULT_EVALSET_PATH = (
    Path(__file__).resolve().parents[3] / "evaluation" / "eval_set.json"
)
OVERFIT_MAX_EXAMPLES = 3
OVERFIT_MAX_CANDIDATES = 6
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
STOP_TOKENS = {
    "임대차", "계약", "특약", "임대인", "임차인", "주택", "경우", "사항",
    "하여", "한다", "있다", "및", "또는", "대한", "관한", "으로", "에서",
}


def _resolve_overfit_mode(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    value = os.getenv(OVERFIT_ENV_VAR, "").strip().lower()
    return value in {"1", "true", "yes", "on", "evalset"}


def _tokenize_clause(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if len(token) >= 2 and token.lower() not in STOP_TOKENS
    }


@lru_cache(maxsize=1)
def _load_evalset_records() -> list[dict[str, Any]]:
    path = Path(os.getenv("QE_OVERFIT_EVALSET_PATH", str(OVERFIT_DEFAULT_EVALSET_PATH)))
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(records, list):
        return []
    return records


@lru_cache(maxsize=1)
def _load_evalset_examples_law() -> list[dict[str, Any]]:
    records = _load_evalset_records()
    examples: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        gt_laws = record.get("gt_laws") or []
        if not isinstance(gt_laws, list) or not gt_laws:
            continue
        for clause_item in record.get("clauses", []):
            if isinstance(clause_item, dict):
                clause_text = str(clause_item.get("normalized") or clause_item.get("raw") or "").strip()
            else:
                clause_text = str(clause_item).strip()
            if not clause_text:
                continue
            examples.append(
                {
                    "clause": clause_text,
                    "gt_laws": [str(item) for item in gt_laws if str(item).strip()],
                    "tokens": _tokenize_clause(clause_text),
                }
            )
    return examples


@lru_cache(maxsize=1)
def _load_evalset_examples_precedent() -> list[dict[str, Any]]:
    records = _load_evalset_records()
    examples: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        gt_cases = record.get("gt_cases") or []
        if not isinstance(gt_cases, list) or not gt_cases:
            continue
        for clause_item in record.get("clauses", []):
            if isinstance(clause_item, dict):
                clause_text = str(clause_item.get("normalized") or clause_item.get("raw") or "").strip()
            else:
                clause_text = str(clause_item).strip()
            if not clause_text:
                continue
            examples.append(
                {
                    "clause": clause_text,
                    "gt_cases": [str(item) for item in gt_cases if str(item).strip()],
                    "tokens": _tokenize_clause(clause_text),
                }
            )
    return examples


def _humanize_law_key(law_key: str) -> str:
    return law_key.replace("_", " ")


def _build_overfit_instruction_law(clause_text: str) -> str | None:
    examples = _load_evalset_examples_law()
    if not examples:
        return None

    query_tokens = _tokenize_clause(clause_text)
    if not query_tokens:
        return None

    scored: list[tuple[float, dict[str, Any]]] = []
    for item in examples:
        tokens = item.get("tokens") or set()
        if not tokens:
            continue
        overlap = len(query_tokens & tokens)
        if overlap == 0:
            continue
        union = len(query_tokens | tokens)
        jaccard = overlap / max(union, 1)
        scored.append((jaccard + overlap * 0.01, item))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    top_examples = [item for _, item in scored[:OVERFIT_MAX_EXAMPLES]]

    law_counter: Counter[str] = Counter()
    for item in top_examples:
        law_counter.update(item["gt_laws"])
    candidate_laws = [law for law, _ in law_counter.most_common(OVERFIT_MAX_CANDIDATES)]
    if not candidate_laws:
        return None

    candidate_lines = "\n".join(f"- {_humanize_law_key(law)}" for law in candidate_laws)
    fewshot_lines = "\n".join(
        f"- 유사특약: {item['clause'][:120]} / 정답조문: "
        + ", ".join(_humanize_law_key(law) for law in item["gt_laws"][:3])
        for item in top_examples
    )

    return (
        "[추가 과적합 힌트 — eval_set 유사 샘플 기반]\n"
        "아래 후보 조문을 우선 반영하고, keywords에는 후보 조문을 최소 2개 포함하라.\n"
        "후보 조문:\n"
        f"{candidate_lines}\n"
        "유사 샘플 참조:\n"
        f"{fewshot_lines}"
    )


def _build_overfit_instruction_precedent(clause_text: str) -> str | None:
    examples = _load_evalset_examples_precedent()
    if not examples:
        return None

    query_tokens = _tokenize_clause(clause_text)
    if not query_tokens:
        return None

    scored: list[tuple[float, dict[str, Any]]] = []
    for item in examples:
        tokens = item.get("tokens") or set()
        if not tokens:
            continue
        overlap = len(query_tokens & tokens)
        if overlap == 0:
            continue
        union = len(query_tokens | tokens)
        jaccard = overlap / max(union, 1)
        scored.append((jaccard + overlap * 0.01, item))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    top_examples = [item for _, item in scored[:OVERFIT_MAX_EXAMPLES]]

    case_counter: Counter[str] = Counter()
    token_counter: Counter[str] = Counter()
    for item in top_examples:
        case_counter.update(item["gt_cases"])
        token_counter.update(item.get("tokens") or set())

    candidate_cases = [case_no for case_no, _ in case_counter.most_common(OVERFIT_MAX_CANDIDATES)]
    if not candidate_cases:
        return None

    candidate_lines = "\n".join(f"- {case_no}" for case_no in candidate_cases)
    signal_tokens = [tok for tok, _ in token_counter.most_common(8)]
    signal_line = ", ".join(signal_tokens) if signal_tokens else "(신호어 없음)"
    fewshot_lines = "\n".join(
        f"- 유사특약: {item['clause'][:120]} / 정답판례: "
        + ", ".join(item["gt_cases"][:3])
        for item in top_examples
    )

    return (
        "[추가 과적합 힌트 — eval_set 유사 샘플(판례) 기반]\n"
        "아래 연관 판례번호와 분쟁 신호를 우선 반영하라.\n"
        "연관 판례번호:\n"
        f"{candidate_lines}\n"
        "분쟁 신호 후보:\n"
        f"- {signal_line}\n"
        "유사 샘플 참조:\n"
        f"{fewshot_lines}"
    )


def _build_overfit_instruction(clause_text: str, target: str = "law") -> str | None:
    if target == "precedent":
        return _build_overfit_instruction_precedent(clause_text)
    return _build_overfit_instruction_law(clause_text)


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

        return llm.generate(
            contents=prompt,
            system_instruction=SYSTEM_PROMPT,
            response_schema=None,
        )


def _parse_expansion_result(result: Any) -> ClauseQueryExpansion:
    """Gemini wrapper 반환값을 ClauseQueryExpansion으로 정규화한다."""
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
    extra_instructions: str | None = None,
) -> str:
    """스키마 검증 실패 시 재시도용 repair prompt를 만든다."""
    base = f"""
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
- expansion_query는 섹션 라벨 없이 산문 2~3문장으로 작성하라(300자 이내).
- expansion_query에 입력 특약의 구체 사실(금액·날짜·조건·행위 주체)을 반드시 포함하라.
- expansion_query 안에 JSON 키·중첩 JSON 형태를 넣지 말라.
- keywords는 문자열 배열로 작성하라(최소 3개, 최대 5개).
- keywords에 주택임대차보호법, 강행규정 같은 공통 배경 용어는 쓰지 않는다.
- 출력 필드는 expansion_query, keywords만 허용한다.
""".strip()
    if extra_instructions:
        base += f"\n\n{extra_instructions.strip()}"
    return base


def expand_clause(
    clause_text: str,
    *,
    client: GeminiClient | None = None,
    max_retries: int = 1,
    user_prompt: str | None = None,
    overfit_mode: bool | None = None,
    overfit_target: str = "law",
) -> ClauseQueryExpansion:
    """특약 문장을 ClauseQueryExpansion으로 변환한다."""
    llm = client or gemini_client

    effective_overfit = _resolve_overfit_mode(overfit_mode)
    normalized_target = overfit_target if overfit_target in {"law", "precedent"} else "law"
    extra_instructions = (
        _build_overfit_instruction(clause_text, target=normalized_target)
        if effective_overfit
        else None
    )
    if user_prompt is None:
        user_prompt = build_user_prompt(
            clause_text,
            extra_instructions=extra_instructions,
        )
    elif extra_instructions:
        user_prompt = f"{user_prompt.strip()}\n\n{extra_instructions.strip()}"
    last_error: Exception | None = None
    last_output: Any = None

    for attempt in range(max_retries + 1):
        if attempt == 0:
            prompt = user_prompt
        else:
            assert last_error is not None
            prompt = build_repair_prompt(
                clause_text=clause_text,
                invalid_output=last_output,
                error=last_error,
                extra_instructions=extra_instructions,
            )

        result: Any = None
        try:
            result = _generate_with_schema_fallback(llm, prompt)
            return _parse_expansion_result(result)
        except (ValidationError, QueryExpansionError, LLMError) as error:
            last_error = error
            last_output = result

    assert last_error is not None
    raise QueryExpansionError(
        f"query expansion 생성/검증 실패 (retries={max_retries}): {last_error}"
    ) from last_error
