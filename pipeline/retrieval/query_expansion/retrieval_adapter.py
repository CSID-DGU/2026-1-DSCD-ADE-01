"""Query expansion 결과를 retrieval layer 입력 payload로 변환한다."""

from __future__ import annotations

from typing import Any

from pipeline.retrieval.query_expansion.query_expansion_schema import ClauseQueryExpansion


def _enum_values(values: list[Any]) -> list[str]:
    """Enum 리스트를 문자열 value 리스트로 변환한다."""
    return [value.value if hasattr(value, "value") else str(value) for value in values]


def build_retrieval_payload(expansion: ClauseQueryExpansion) -> dict[str, Any]:
    """ClauseQueryExpansion을 source별 retrieval 입력으로 변환한다."""

    return {
        "metadata": {
            "schema_version": expansion.schema_version,
            "clause_text": expansion.clause_text,
            "normalized_clause": expansion.normalized_clause,
            "domain_scope": expansion.domain_scope.value,
            "issue_type_candidates_freeform": expansion.issue_type_candidates_freeform,
            "issue_types_normalized": [
                issue.value for issue in expansion.issue_types_normalized
            ],
            "risk_hypotheses": expansion.risk_hypotheses,
            "compound_clause_detected": expansion.compound_clause_detected,
            "sub_issue_summaries": expansion.sub_issue_summaries,
            "expansion_notes": expansion.expansion_notes,
        },
        "law": {
            "bm25_keywords": expansion.law_query.law_keywords,
            "dense_query": expansion.law_query.law_dense_query,
            "legal_issue": expansion.law_query.legal_issue,
            "applicable_rules": expansion.law_query.applicable_rules,
            "article_candidates": [
                candidate.model_dump(mode="json")
                for candidate in expansion.law_query.law_article_candidates
            ],
            "retrieval_terms": expansion.law_query.retrieval_terms.model_dump(mode="json"),
            "target_fields": _enum_values(expansion.law_query.target_fields),
        },
        "case": {
            "bm25_keywords": expansion.case_query.case_keywords,
            "issue_query": expansion.case_query.case_issue_query,
            "fact_pattern_query": expansion.case_query.case_fact_pattern_query,
            "referenced_law_candidates": [
                candidate.model_dump(mode="json")
                for candidate in expansion.case_query.referenced_law_candidates
            ],
            "retrieval_terms": expansion.case_query.retrieval_terms.model_dump(mode="json"),
            "target_fields": _enum_values(expansion.case_query.target_fields),
        },
        "counsel": {
            "bm25_keywords": expansion.counsel_query.counsel_keywords,
            "question_query": expansion.counsel_query.counsel_question_query,
            "answer_query": expansion.counsel_query.counsel_answer_query,
            "user_question_intent": expansion.counsel_query.user_question_intent,
            "expected_tags": expansion.counsel_query.expected_tags,
            "expected_answer_points": expansion.counsel_query.expected_answer_points,
            "retrieval_terms": expansion.counsel_query.retrieval_terms.model_dump(mode="json"),
            "target_fields": _enum_values(expansion.counsel_query.target_fields),
        },
        "routing": [
            route.model_dump(mode="json")
            for route in expansion.source_routing
        ],
    }
