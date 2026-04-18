"""Vertex AI Gemini query expansion smoke test.

주의:
- 실제 Vertex AI API를 호출하는 integration test다.
- 로컬 ADC 인증과 .env 설정이 필요하다.
- 일반 unit test와 분리해서 실행한다.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv


pytestmark = pytest.mark.integration


REQUIRED_ENV_VARS = [
    "GCP_PROJECT_ID",
    "GCP_LOCATION",
    # shared.config가 fail-fast로 요구하는 값들
    "CLOUD_SQL_CONNECTION",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "GCS_BUCKET",
]


def _skip_if_env_missing() -> None:
    load_dotenv(override=True)

    missing = [key for key in REQUIRED_ENV_VARS if not os.getenv(key)]
    if missing:
        pytest.skip(
            "Vertex integration test skipped. "
            f"Missing required env vars: {', '.join(missing)}"
        )


def test_expand_clause_with_vertex_gemini_smoke() -> None:
    """실제 Vertex AI Gemini로 특약 1개를 query expansion한다."""
    _skip_if_env_missing()

    # shared.config가 import 시점에 fail-fast이므로 env 확인 후 import한다.
    from retrieval.query_expansion import expand_clause
    from retrieval.query_expansion_schema import ClauseQueryExpansion

    clause = "임차인은 계약기간 중 전입신고 및 확정일자를 받지 않는다."

    result = expand_clause(
        clause,
        max_retries=1,
    )

    assert isinstance(result, ClauseQueryExpansion)

    # 원문 보존 확인
    assert result.clause_text == clause

    # 최상위 필드 기본 검증
    assert result.normalized_clause
    assert result.issue_type_candidates_freeform
    assert result.issue_types_normalized
    assert result.risk_hypotheses

    # source별 query 생성 확인
    assert result.law_query.law_keywords
    assert result.law_query.law_dense_query

    assert result.case_query.case_keywords
    assert result.case_query.case_issue_query
    assert result.case_query.case_fact_pattern_query

    assert result.counsel_query.counsel_keywords
    assert result.counsel_query.counsel_question_query
    assert result.counsel_query.counsel_answer_query

    # routing 확인
    assert result.source_routing

    # source별 target_fields가 섞이지 않았는지 간단 확인
    assert all(
        field.value in {"law_child_text", "law_parent_text"}
        for field in result.law_query.target_fields
    )
    assert all(
        field.value
        in {
            "case_issue_summary",
            "case_holding_summary",
            "case_referenced_law",
            "case_full_text",
        }
        for field in result.case_query.target_fields
    )
    assert all(
        field.value in {"counsel_question", "counsel_tags", "counsel_answer"}
        for field in result.counsel_query.target_fields
    )