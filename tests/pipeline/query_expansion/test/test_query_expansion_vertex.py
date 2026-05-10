"""Vertex AI Gemini query_expansion 메인 패키지 smoke test.

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
    _skip_if_env_missing()

    from pipeline.retrieval.query_expansion.query_expansion import expand_clause
    from pipeline.retrieval.query_expansion.query_expansion_schema import (
        ClauseQueryExpansion,
    )

    clause = "임차인은 계약기간 중 전입신고 및 확정일자를 받지 않는다."
    result = expand_clause(clause, max_retries=1)

    assert isinstance(result, ClauseQueryExpansion)
    assert result.expansion_query
    assert len(result.keywords) >= 3
    for label in (
        "[쟁점 유형]",
        "[자유 쟁점]",
        "[관련 법률 개념 및 규칙]",
        "[유사 분쟁 사실관계]",
    ):
        assert label in result.expansion_query, f"expansion_query에 {label} 섹션이 없습니다."
