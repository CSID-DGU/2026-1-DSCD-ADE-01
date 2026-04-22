from pipeline.retrieval.query_expansion2.query_expansion_schema import ClauseQueryExpansion
from pipeline.retrieval.query_expansion2.retrieval_adapter import build_retrieval_payload
from tests.pipeline.query_expansion2.test.test_query_expansion_schema import _valid_payload


def test_build_retrieval_payload_maps_expansion_to_hybrid_payload() -> None:
    expansion = ClauseQueryExpansion.model_validate(_valid_payload())

    payload = build_retrieval_payload(expansion)

    assert payload["dense_query"] == expansion.expansion_query
    assert payload["bm25_keywords"] == expansion.keywords
