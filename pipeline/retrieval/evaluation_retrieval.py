"""Import-safe retrieval helpers for offline legal retrieval evaluation."""

from __future__ import annotations

import re
from typing import Any

from pipeline.retrieval.query_expansion.query_expansion_schema import ClauseQueryExpansion
from pipeline.retrieval.query_expansion.retrieval_adapter import build_retrieval_payload


TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


def tokenize_for_evaluation(text: str) -> list[str]:
    """Return simple normalized tokens without requiring model dependencies."""
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def expand_case_queries_with_llm(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Build query expansion payloads by calling the actual LLM for each clause."""
    from pipeline.retrieval.query_expansion.query_expansion import expand_clause

    expanded_queries: list[dict[str, Any]] = []
    for clause_index, clause in enumerate(case["clauses"]):
        expansion = expand_clause(clause)
        expanded_queries.append(
            {
                "clause_index": clause_index,
                "clause": clause,
                "query": clause,
                "expansion_query": expansion.expansion_query,
                "keywords": expansion.keywords,
                "expansion": expansion.model_dump(),
                "retrieval_payload": build_retrieval_payload(expansion),
            }
        )
    return expanded_queries


def expand_case_queries(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Build deterministic query expansion payloads for a case's clauses."""
    expanded_queries: list[dict[str, Any]] = []
    for clause_index, clause in enumerate(case["clauses"]):
        keywords = _keywords_from_clause(clause)
        clause_summary = _truncate(clause, 200)
        expansion_query = _truncate(
            f"임대차 계약 특약 조항 '{clause_summary}'에 관한 법률 쟁점과 적용 법령 및 판례를 검색한다.",
            300,
        )
        expansion = ClauseQueryExpansion(
            expansion_query=expansion_query,
            keywords=keywords,
        )
        expanded_queries.append(
            {
                "clause_index": clause_index,
                "clause": clause,
                "query": clause,
                "expansion_query": expansion.expansion_query,
                "keywords": expansion.keywords,
                "expansion": expansion.model_dump(),
                "retrieval_payload": build_retrieval_payload(expansion),
            }
        )
    return expanded_queries


def run_hybrid_retrieval(
    *,
    case: dict[str, Any],
    expanded_queries: list[dict[str, Any]],
    top_k: int = 20,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run lightweight keyword and semantic retrieval against case-local documents."""
    documents = collect_case_documents(case)
    keyword_results: list[dict[str, Any]] = []
    semantic_results: list[dict[str, Any]] = []

    for query in expanded_queries:
        keyword_results.extend(_rank_documents_by_keywords(query, documents, top_k))
        semantic_results.extend(_rank_documents_by_overlap(query, documents, top_k))

    return keyword_results, semantic_results


def inspect_retrieved_documents(
    reranked_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expose document bodies and metadata for report-level inspection."""
    inspected: list[dict[str, Any]] = []
    for result in reranked_results:
        inspected.append(
            {
                "rank": result["rank"],
                "result_id": result["result_id"],
                "source_type": result["source_type"],
                "document_body": result.get(
                    "document_body",
                    result.get("document_text", ""),
                ),
                "document_text": result.get("document_text", ""),
                "metadata": result.get("metadata", {}),
                "scores": {
                    "rerank_score": result.get("rerank_score"),
                    "keyword_score": result.get("keyword_score"),
                    "semantic_score": result.get("semantic_score"),
                },
            }
        )
    return inspected


def collect_case_documents(case: dict[str, Any]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    documents.extend(
        _normalize_document(document, "law")
        for document in case.get("law_documents", [])
    )
    documents.extend(
        _normalize_document(document, "precedent")
        for document in case.get("precedent_documents", [])
    )
    documents.extend(
        _normalize_document(document, str(document.get("source_type", "document")))
        for document in case.get("documents", [])
        if isinstance(document, dict)
    )
    return documents


def _keywords_from_clause(clause: str) -> list[str]:
    tokens = []
    seen = set()
    for token in tokenize_for_evaluation(clause):
        if len(token) < 2 or token in seen:
            continue
        tokens.append(token)
        seen.add(token)

    while len(tokens) < 3:
        fallback = f"clause_keyword_{len(tokens) + 1}"
        tokens.append(fallback)
    return tokens[:5]


def _truncate(text: str, max_length: int) -> str:
    stripped = text.strip()
    if len(stripped) <= max_length:
        return stripped
    return stripped[: max_length - 3].rstrip() + "..."


def _normalize_document(document: dict[str, Any], source_type: str) -> dict[str, Any]:
    metadata = {key: value for key, value in document.items() if key not in {"text", "body"}}
    document_text = _document_text(document)
    return {
        "result_id": _document_id(document, source_type),
        "source_type": source_type,
        "document_body": document_text,
        "document_text": document_text,
        "metadata": metadata,
        "search_text": " ".join(
            [
                document_text,
                _flatten_metadata(metadata),
            ]
        ),
    }


def _document_text(document: dict[str, Any]) -> str:
    for field in ("text", "body", "child_text", "judgment_summary", "summary"):
        value = document.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return _flatten_metadata(document)


def _document_id(document: dict[str, Any], source_type: str) -> str:
    if source_type == "law":
        for field in ("clause_key", "article_key", "law_name"):
            value = document.get(field)
            if value:
                return f"law:{value}"

    case_law = document.get("case_law")
    if isinstance(case_law, dict) and case_law.get("case_number"):
        return f"precedent:{case_law['case_number']}"
    if document.get("case_number"):
        return f"precedent:{document['case_number']}"

    return f"{source_type}:{abs(hash(_flatten_metadata(document)))}"


def _flatten_metadata(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_metadata(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_metadata(item) for item in value)
    return "" if value is None else str(value)


def _rank_documents_by_keywords(
    query: dict[str, Any],
    documents: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    keywords = query["retrieval_payload"]["bm25_keywords"]
    scored = []
    for document in documents:
        haystack = document["search_text"].lower()
        score = sum(1 for keyword in keywords if keyword.lower() in haystack)
        result = _result_record(query, document, float(score), "keyword")
        result["keyword_score"] = result["score"]
        scored.append(result)
    return _rank(scored, top_k)


def _rank_documents_by_overlap(
    query: dict[str, Any],
    documents: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    query_tokens = set(tokenize_for_evaluation(query["retrieval_payload"]["dense_query"]))
    scored = []
    for document in documents:
        document_tokens = set(tokenize_for_evaluation(document["search_text"]))
        overlap = query_tokens & document_tokens
        similarity = len(overlap) / max(len(query_tokens), 1)
        result = _result_record(query, document, similarity, "semantic")
        result["similarity"] = result["score"]
        scored.append(result)
    return _rank(scored, top_k)


def _result_record(
    query: dict[str, Any],
    document: dict[str, Any],
    score: float,
    retrieval_method: str,
) -> dict[str, Any]:
    return {
        "clause_index": query["clause_index"],
        "clause": query["clause"],
        "result_id": document["result_id"],
        "source_type": document["source_type"],
        "score": round(score, 6),
        "retrieval_method": retrieval_method,
        "document_body": document["document_body"],
        "document_text": document["document_text"],
        "metadata": document["metadata"],
    }


def _rank(records: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    ranked = sorted(records, key=lambda item: item["score"], reverse=True)[:top_k]
    for rank, record in enumerate(ranked, 1):
        record["rank"] = rank
    return ranked
