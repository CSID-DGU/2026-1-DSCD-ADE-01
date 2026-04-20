from pipeline.retrieval.query_expansion.query_expansion_schema import ClauseQueryExpansion
from pipeline.retrieval.query_expansion.retrieval_adapter import build_retrieval_payload
from tests.pipeline.query_expansion.test.test_query_expansion_schema import _valid_payload


def test_build_retrieval_payload_maps_expansion_to_source_payloads() -> None:
    expansion = ClauseQueryExpansion.model_validate(_valid_payload())

    payload = build_retrieval_payload(expansion)

    assert payload["metadata"]["clause_text"] == expansion.clause_text
    assert payload["metadata"]["domain_scope"] == "residential_lease"

    assert payload["law"]["bm25_keywords"] == expansion.law_query.law_keywords
    assert payload["law"]["dense_query"] == expansion.law_query.law_dense_query
    assert payload["law"]["target_fields"] == ["law_child_text"]

    assert payload["case"]["bm25_keywords"] == expansion.case_query.case_keywords
    assert payload["case"]["issue_query"] == expansion.case_query.case_issue_query
    assert payload["case"]["fact_pattern_query"] == expansion.case_query.case_fact_pattern_query

    assert payload["counsel"]["bm25_keywords"] == expansion.counsel_query.counsel_keywords
    assert payload["counsel"]["question_query"] == expansion.counsel_query.counsel_question_query
    assert payload["counsel"]["answer_query"] == expansion.counsel_query.counsel_answer_query

    assert len(payload["routing"]) == 3
