"""query_expansion_schema Pydantic 검증 테스트."""
from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from retrieval.query_expansion_schema import ClauseQueryExpansion


def _valid_payload() -> dict:
    return {
        "schema_version": "qe_v1",
        "clause_text": "임차인은 계약 만료 2개월 전 해지 의사를 통보한다.",
        "normalized_clause": "임차인의 해지 통지 시점과 계약 종료 효력 판단이 필요한 특약",
        "domain_scope": "residential_lease",
        "issue_type_candidates_freeform": ["해지 통지 시점", "묵시적 갱신 충돌 가능성"],
        "issue_types_normalized": ["갱신·해지·계약종료"],
        "risk_hypotheses": ["해지 통지 시점 분쟁 가능성", "묵시적 갱신 주장 가능성"],
        "compound_clause_detected": False,
        "sub_issue_summaries": [],
        "law_query": {
            "legal_issue": "해지 통지 시점과 계약 종료 효력",
            "applicable_rules": ["해지 통보의 도달 시점", "묵시적 갱신 요건"],
            "law_article_candidates": [
                {
                    "law_name": "주택임대차보호법",
                    "article_no": "6조",
                    "article_title": "계약의 갱신",
                    "confidence": "medium",
                    "reason": "해지 통지 및 묵시적 갱신 판단에 직접 관련된다.",
                }
            ],
            "law_keywords": ["해지 통보", "묵시적 갱신", "계약 종료"],
            "law_dense_query": "주택임대차에서 해지 통지 시점과 묵시적 갱신 성립 요건을 확인한다.",
            "retrieval_terms": {
                "must_terms": ["해지 통보"],
                "should_terms": ["묵시적 갱신", "계약 종료"],
                "exclude_terms": [],
                "synonyms": ["해지 통지", "해지 의사 통지"],
                "query_variants": ["임차인 해지 통보 시 계약 종료 시점"],
            },
            "target_fields": ["law_child_text"],
        },
        "case_query": {
            "case_issue_query": "임차인의 해지 통보 시점과 계약 종료 효력에 관한 판시사항을 찾는다.",
            "case_fact_pattern_query": "만료 전 통지 여부와 묵시적 갱신 주장이 충돌하는 임대차 분쟁 사실관계를 찾는다.",
            "case_keywords": ["해지 통보", "묵시적 갱신", "계약 종료"],
            "referenced_law_candidates": [
                {
                    "law_name": "주택임대차보호법",
                    "article_no": "6조",
                    "confidence": "medium",
                }
            ],
            "retrieval_terms": {
                "must_terms": ["해지 통보"],
                "should_terms": ["묵시적 갱신", "효력"],
                "exclude_terms": [],
                "synonyms": ["해지 통지"],
                "query_variants": ["해지 통보의 효력 관련 판례"],
            },
            "target_fields": ["case_issue_summary", "case_holding_summary"],
        },
        "counsel_query": {
            "counsel_question_query": "해지 통보 시점을 둘러싼 임차인 유사 상담 사례를 찾는다.",
            "counsel_answer_query": "묵시적 갱신과 해지 통보 효력에 대한 상담 답변 방향을 찾는다.",
            "user_question_intent": "해지 통보의 효력과 분쟁 리스크 확인",
            "counsel_keywords": ["해지 통보", "묵시적 갱신", "임대차"],
            "expected_tags": ["#임대차", "#계약", "#퇴거"],
            "expected_answer_points": ["해지 통보 기한", "묵시적 갱신 성립 요건"],
            "retrieval_terms": {
                "must_terms": ["해지 통보"],
                "should_terms": ["묵시적 갱신", "임차인"],
                "exclude_terms": [],
                "synonyms": ["해지 통지"],
                "query_variants": ["해지 통보 관련 상담 사례"],
            },
            "target_fields": ["counsel_question", "counsel_answer"],
        },
        "source_routing": [
            {"source_type": "law", "priority": "high", "reason": "조문 확인이 필요하다."},
            {"source_type": "case", "priority": "medium", "reason": "쟁점 유사 판례가 필요하다."},
            {"source_type": "counsel", "priority": "medium", "reason": "유사 상담 맥락이 유용하다."},
        ],
        "expansion_notes": None,
    }


def test_valid_mock_json_passes_clause_query_expansion_validation() -> None:
    payload = _valid_payload()
    model = ClauseQueryExpansion.model_validate(payload)
    assert model.schema_version == "qe_v1"


def test_law_query_target_fields_rejects_counsel_answer() -> None:
    payload = _valid_payload()
    payload["law_query"]["target_fields"] = ["counsel_answer"]

    with pytest.raises(ValidationError) as exc_info:
        ClauseQueryExpansion.model_validate(payload)

    assert "law_query.target_fields" in str(exc_info.value)


def test_case_query_target_fields_rejects_law_child_text() -> None:
    payload = _valid_payload()
    payload["case_query"]["target_fields"] = ["law_child_text"]

    with pytest.raises(ValidationError) as exc_info:
        ClauseQueryExpansion.model_validate(payload)

    assert "case_query.target_fields" in str(exc_info.value)


def test_counsel_query_target_fields_rejects_case_full_text() -> None:
    payload = _valid_payload()
    payload["counsel_query"]["target_fields"] = ["case_full_text"]

    with pytest.raises(ValidationError) as exc_info:
        ClauseQueryExpansion.model_validate(payload)

    assert "counsel_query.target_fields" in str(exc_info.value)


def test_source_routing_duplicate_source_type_fails() -> None:
    payload = _valid_payload()
    payload["source_routing"] = [
        {"source_type": "law", "priority": "high", "reason": "조문 확인"},
        {"source_type": "law", "priority": "medium", "reason": "중복 테스트"},
    ]

    with pytest.raises(ValidationError) as exc_info:
        ClauseQueryExpansion.model_validate(payload)

    assert "source_routing에 중복 source_type" in str(exc_info.value)


def test_law_article_candidate_missing_reason_fails() -> None:
    payload = _valid_payload()
    candidate = copy.deepcopy(payload["law_query"]["law_article_candidates"][0])
    candidate.pop("reason")
    payload["law_query"]["law_article_candidates"] = [candidate]

    with pytest.raises(ValidationError) as exc_info:
        ClauseQueryExpansion.model_validate(payload)

    assert "reason" in str(exc_info.value)


def test_residential_domain_with_commercial_issue_adds_warning_note() -> None:
    payload = _valid_payload()
    payload["domain_scope"] = "residential_lease"
    payload["issue_types_normalized"] = ["상가·권리금·시설비"]
    payload["expansion_notes"] = None

    model = ClauseQueryExpansion.model_validate(payload)
    assert model.expansion_notes is not None
    assert "mixed 가능성을 재검토" in model.expansion_notes
