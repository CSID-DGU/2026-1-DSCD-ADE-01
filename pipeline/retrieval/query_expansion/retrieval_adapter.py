"""Query expansion 결과를 retrieval layer 입력 payload로 변환한다."""

from __future__ import annotations

from typing import Any

from pipeline.retrieval.query_expansion2.query_expansion_schema import ClauseQueryExpansion


def build_retrieval_payload(expansion: ClauseQueryExpansion) -> dict[str, Any]:
    """ClauseQueryExpansion을 hybrid retrieval 입력으로 변환한다."""
    return {
        "dense_query": expansion.expansion_query,
        "bm25_keywords": expansion.keywords,
    }
