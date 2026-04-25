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
    from pipeline.retrieval.query_expansion_v1.query_expansion import expand_clause
    from pipeline.retrieval.query_expansion_v1.query_expansion_schema import (
        ClauseQueryExpansion,
    )

    clause = "임차인은 계약기간 중 전입신고 및 확정일자를 받지 않는다."

    result = expand_clause(
        clause,
        max_retries=1,
    )

    assert isinstance(result, ClauseQueryExpansion)
    assert result.expansion_query
    assert len(result.keywords) >= 3
