"""Reusable reranking helpers for evaluation reports."""

from __future__ import annotations

from typing import Any


RRF_K = 60


def rerank_hybrid_results(
    *,
    keyword_results: list[dict[str, Any]],
    semantic_results: list[dict[str, Any]],
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Fuse keyword and semantic rankings with reciprocal rank fusion."""
    grouped: dict[tuple[int, str], dict[str, Any]] = {}

    for result in keyword_results:
        item = _group_item(grouped, result)
        item["keyword_rank"] = result["rank"]
        item["keyword_score"] = result["score"]

    for result in semantic_results:
        item = _group_item(grouped, result)
        item["semantic_rank"] = result["rank"]
        item["semantic_score"] = result["score"]

    reranked = []
    for item in grouped.values():
        keyword_rank = item.get("keyword_rank")
        semantic_rank = item.get("semantic_rank")
        item["rerank_score"] = round(
            _rrf(keyword_rank) + _rrf(semantic_rank),
            6,
        )
        item["score"] = item["rerank_score"]
        reranked.append(item)

    reranked.sort(key=lambda result: result["rerank_score"], reverse=True)
    for rank, result in enumerate(reranked[:top_k], 1):
        result["rank"] = rank
    return reranked[:top_k]


def _group_item(
    grouped: dict[tuple[int, str], dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, Any]:
    key = (result["clause_index"], result["result_id"])
    if key not in grouped:
        grouped[key] = {
            "clause_index": result["clause_index"],
            "clause": result["clause"],
            "result_id": result["result_id"],
            "source_type": result["source_type"],
            "document_body": result.get(
                "document_body",
                result.get("document_text", ""),
            ),
            "document_text": result.get("document_text", ""),
            "metadata": result.get("metadata", {}),
            "keyword_rank": None,
            "semantic_rank": None,
            "keyword_score": 0.0,
            "semantic_score": 0.0,
        }
    return grouped[key]


def _rrf(rank: int | None) -> float:
    if rank is None:
        return 0.0
    return 1 / (RRF_K + rank)
