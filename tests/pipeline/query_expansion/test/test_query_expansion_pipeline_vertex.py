from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration


def _skip_if_env_missing() -> None:
    load_dotenv(override=True)

    required = [
        "GCP_PROJECT_ID",
        "GCP_LOCATION",
        "CLOUD_SQL_CONNECTION",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
        "GCS_BUCKET",
    ]

    missing = [key for key in required if not os.getenv(key)]
    if missing:
        pytest.skip(f"Missing env vars: {', '.join(missing)}")


def test_query_expansion_to_retrieval_payload_with_vertex() -> None:
    _skip_if_env_missing()

    from pipeline.retrieval.query_expansion.query_expansion import expand_clause
    from pipeline.retrieval.query_expansion.retrieval_adapter import (
        build_retrieval_payload,
    )

    clause = "임차인은 계약기간 중 전입신고 및 확정일자를 받지 않는다."
    expansion = expand_clause(clause, max_retries=1)
    payload = build_retrieval_payload(expansion)

    assert payload["dense_query"]
    assert len(payload["bm25_keywords"]) >= 3
