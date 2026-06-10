"""API 요청/응답 스키마."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from pipeline.preprocessing.schema import LeaseContract
from pipeline.retrieval.query_expansion.query_expansion_schema import ClauseQueryExpansion


# ──────────────────────────────────────────────────────────────────────
# 공통
# ──────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str


# ──────────────────────────────────────────────────────────────────────
# 새로운 병렬 아키텍처용 스키마
# ──────────────────────────────────────────────────────────────────────

class DocumentHistoryItem(BaseModel):
    doc_id: str
    file_name: str
    created_at: datetime
    gcs_raw_path: str
    gcs_parsed_path: str


class DocumentHistoryResponse(BaseModel):
    documents: list[DocumentHistoryItem]


class DocumentUploadResponse(BaseModel):
    doc_id: str
    contract: LeaseContract


class AnalyzeClauseRequest(BaseModel):
    client_id: str
    doc_id: str
    clause_index: int
    clause_text: str


class ClauseAnalysisResponse(BaseModel):
    index: int
    clause: str
    expansion: ClauseQueryExpansion
    law_results: list[RankedDocument]   # 법령 (rank 1~TOP_K, 독립)
    prec_results: list[RankedDocument]  # 판례 (rank 1~TOP_K, 독립)


class ClauseWithHits(BaseModel):
    index: int
    clause: str
    laws: list[dict]
    precs: list[dict]


class ReportRequest(BaseModel):
    property_info: dict
    common_terms: list[str]
    clauses_with_hits: list[ClauseWithHits]


# ──────────────────────────────────────────────────────────────────────
# V2 파이프라인 스키마 (완전 비동기/병렬)
# ──────────────────────────────────────────────────────────────────────

class ClauseAnalysisV2Response(BaseModel):
    index: int
    clause: str
    expansion: ClauseQueryExpansion
    law_results: list[RankedDocument]   # 법령 (rank 1~TOP_K, 독립)
    prec_results: list[RankedDocument]  # 판례 (rank 1~TOP_K, 독립)
    llm_related_laws: list[dict]        # LLM 요약 결과
    clause_one_line_summary: str | None = None  # 한 줄 요약
    clause_interpretation: str | None = None    # 특약 해석 (일반인용)

class ClauseWithSummary(BaseModel):
    index: int
    clause: str
    summaries: list[dict]

class ReportV2Request(BaseModel):
    property_info: dict
    common_terms: list[str]
    clauses_with_summaries: list[ClauseWithSummary]

class ChecklistResponse(BaseModel):
    contract_checklist: list[dict]

class RelationsResponse(BaseModel):
    related_clauses_map: dict[str, list[dict]]


# ──────────────────────────────────────────────────────────────────────
# 기존 (레거시)
# ──────────────────────────────────────────────────────────────────────


class LayoutParseResponse(BaseModel):
    contract: LeaseContract


# ──────────────────────────────────────────────────────────────────────
# 2단계: query_expansion  (layout_parse 결과 포함)
# ──────────────────────────────────────────────────────────────────────

class ClauseExpansion(BaseModel):
    index: int
    clause: str
    expansion: ClauseQueryExpansion
    retrieval_payload: dict[str, Any]


class QueryExpansionResponse(BaseModel):
    contract: LeaseContract
    clauses: list[ClauseExpansion]


# ──────────────────────────────────────────────────────────────────────
# 3단계: retrieval  (query_expansion 결과 포함)
# ──────────────────────────────────────────────────────────────────────

class RetrievalHit(BaseModel):
    doc_id: str
    source_type: str          # "law" | "precedent"
    rank: int
    hybrid_score: float | None = None
    bm25_rank: int | None = None
    dense_rank: int | None = None


class ClauseRetrievalResult(BaseModel):
    bm25: list[RetrievalHit]
    dense: list[RetrievalHit]
    law: list[RetrievalHit]   # alpha hybrid 법령 (rank 1~TOP_K, 독립)
    prec: list[RetrievalHit]  # alpha hybrid 판례 (rank 1~TOP_K, 독립)


class ClauseRetrieval(BaseModel):
    index: int
    clause: str
    expansion: ClauseQueryExpansion
    retrieval_payload: dict[str, Any]
    retrieval_results: ClauseRetrievalResult


class RetrievalResponse(BaseModel):
    contract: LeaseContract
    clauses: list[ClauseRetrieval]


# ──────────────────────────────────────────────────────────────────────
# 4단계: reranking  (retrieval 결과 + 문서 내용 포함)
# ──────────────────────────────────────────────────────────────────────

class RankedDocument(BaseModel):
    rank: int
    doc_id: str
    source_type: str          # "law" | "precedent"
    hybrid_score: float
    bm25_rank: int | None = None
    dense_rank: int | None = None
    # 문서 내용 (DB에서 조회)
    title: str                # 법령명+조항 or 사건명
    content: str              # child_text or judgment_summary
    warning: str | None = None
    is_violation: bool = False


class ClauseRanking(BaseModel):
    index: int
    clause: str
    law_results: list[RankedDocument]   # 법령 (rank 1~TOP_K, 독립)
    prec_results: list[RankedDocument]  # 판례 (rank 1~TOP_K, 독립)


class RerankingResponse(BaseModel):
    contract: LeaseContract
    clauses: list[ClauseRanking]

# ──────────────────────────────────────────────────────────────────────
# 챗봇용 스키마
# ──────────────────────────────────────────────────────────────────────

class ClauseRewriteRequest(BaseModel):
    clause_text: str
    violation_laws: list[dict]   # is_violation=True 항목
    all_related_laws: list[dict] # 전체 related_laws

class ClauseRewriteResponse(BaseModel):
    rewritten_clause: str
    reason: str


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: dict[str, Any]

class ChatResponse(BaseModel):
    answer: str
    sources: list[dict] | None = None
