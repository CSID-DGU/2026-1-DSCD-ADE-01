"""Query expansion 결과를 retrieval layer 입력 payload로 변환한다."""

from __future__ import annotations

from typing import Any

from pipeline.retrieval.query_expansion.query_expansion_schema import ClauseQueryExpansion


def build_retrieval_payload(
    expansion: ClauseQueryExpansion,
    clause_text: str | None = None,
) -> dict[str, Any]:
    """ClauseQueryExpansion을 hybrid retrieval 입력으로 변환한다."""
    dense_query = (
        f"{clause_text}\n\n{expansion.expansion_query}"
        if clause_text
        else expansion.expansion_query
    )
    return {
        "dense_query": dense_query,
        "bm25_keywords": expansion.keywords,
    }
