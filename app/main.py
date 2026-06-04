"""ADE Contract Analysis API.

엔드포인트 구성:
  GET  /health, /healthz         — 헬스 체크
  POST /api/layout_parse         — PDF → 계약서 구조 파싱
  POST /api/query_expansion      — layout_parse + 특약별 쿼리 확장
  POST /api/retrieval            — query_expansion + BM25/Dense/RRF 검색
  POST /api/reranking            — retrieval + 상위 문서 내용 조회 (enrichment)

각 단계는 이전 단계를 모두 포함하여 누적 실행한다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, status, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.schemas import (
    AnalyzeClauseRequest,
    ClauseAnalysisResponse,
    ClauseAnalysisV2Response,
    ClauseExpansion,
    ClauseRanking,
    ClauseRetrieval,
    ClauseRetrievalResult,
    DocumentHistoryItem,
    DocumentHistoryResponse,
    DocumentUploadResponse,
    HealthResponse,
    LayoutParseResponse,
    QueryExpansionResponse,
    RankedDocument,
    ReportRequest,
    ReportV2Request,
    RerankingResponse,
    RetrievalHit,
    RetrievalResponse,
)
from pipeline.preprocessing.schema import LeaseContract
from pipeline.retrieval.query_expansion.query_expansion_schema import ClauseQueryExpansion
from pipeline.retrieval.retrieval_service import retrieval_service
from pipeline.generation.report_generator import generate_report_from_data, ReportOutput
from pipeline.generation.report_generator_v2 import generate_clause_summary, generate_final_report, FinalReportOutput, COMMON_TERMS_COUNT
from shared.db.connection import get_db_client
from shared.storage.gcs_client import get_gcs_client

log = logging.getLogger(__name__)

# 특약 병렬 처리 스레드 수
CLAUSE_WORKERS = 50
# reranking 단계에서 반환할 상위 문서 수
RERANKING_TOP_N = 20

_clause_executor = ThreadPoolExecutor(max_workers=CLAUSE_WORKERS, thread_name_prefix="clause")


# ──────────────────────────────────────────────────────────────────────
# Lifespan: BM25 코퍼스 로드
# ──────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """BM25 코퍼스를 백그라운드 스레드에서 로드 — /healthz가 즉시 응답하도록."""
    def _load():
        # Cloud SQL Connector가 asyncio를 내부적으로 사용하므로
        # 새 이벤트 루프를 생성해 준다.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            print("서버 시작: BM25 코퍼스 로딩 중...", flush=True)
            retrieval_service.load()
            print("BM25 코퍼스 로딩 완료.", flush=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"코퍼스 로딩 실패: {e}", flush=True)
            loop.close()

    threading.Thread(target=_load, daemon=True).start()
    yield
    log.info("서버 종료.")


# ──────────────────────────────────────────────────────────────────────
# 앱 초기화
# ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="ADE Contract Analysis API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_origin_regex=r"https://.*\.(web\.app|firebaseapp\.com)$",
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────
# 헬스 체크
# ──────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    if not retrieval_service.is_ready:
        raise HTTPException(status_code=503, detail="코퍼스 로딩 중")
    return HealthResponse(status="ok")


# ──────────────────────────────────────────────────────────────────────
# 새로운 아키텍처: 병렬 처리 및 스토리지 연동
# ──────────────────────────────────────────────────────────────────────

def _save_document_data_background(
    client_id: str,
    doc_id: str,
    file_name: str,
    pdf_bytes: bytes,
    contract: LeaseContract,
):
    """백그라운드에서 GCS에 파일들을 업로드하고 DB에 히스토리를 기록한다."""
    gcs = get_gcs_client()
    db = get_db_client()

    raw_blob_name = f"clients/{client_id}/raw/{doc_id}.pdf"
    parsed_blob_name = f"clients/{client_id}/parsed/{doc_id}.json"

    try:
        # GCS 업로드
        gcs.upload_bytes(raw_blob_name, pdf_bytes, content_type="application/pdf")
        gcs.upload_bytes(
            parsed_blob_name,
            contract.model_dump_json().encode("utf-8"),
            content_type="application/json"
        )

        # DB 기록
        db.execute(
            text("""
                INSERT INTO document_history
                (client_id, doc_id, file_name, gcs_raw_path, gcs_parsed_path)
                VALUES (:client_id, :doc_id, :file_name, :gcs_raw_path, :gcs_parsed_path)
            """),
            {
                "client_id": client_id,
                "doc_id": doc_id,
                "file_name": file_name,
                "gcs_raw_path": f"gs://{gcs.bucket_name}/{raw_blob_name}",
                "gcs_parsed_path": f"gs://{gcs.bucket_name}/{parsed_blob_name}"
            }
        )
        log.info(f"문서 저장 완료: client={client_id}, doc={doc_id}")
    except Exception as e:
        log.error(f"백그라운드 저장 실패 (doc={doc_id}): {e}")


@app.post("/api/documents", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    client_id: str = Form(...),
    file: UploadFile = File(...)
) -> DocumentUploadResponse:
    """PDF를 업로드받아 즉시 파싱 후 결과를 반환하며, 백그라운드에서 원본/파싱결과를 저장한다."""
    doc_id = str(uuid.uuid4())
    file_name = file.filename or "unknown.pdf"
    pdf_bytes = await _read_pdf(file)

    # Document AI 파싱 (연산 집중)
    contract = await _run_in_executor(_parse_contract, pdf_bytes)

    # 백그라운드 저장 태스크 예약
    background_tasks.add_task(
        _save_document_data_background,
        client_id,
        doc_id,
        file_name,
        pdf_bytes,
        contract
    )

    return DocumentUploadResponse(doc_id=doc_id, contract=contract)


@app.get("/api/documents", response_model=DocumentHistoryResponse)
async def get_document_history(client_id: str) -> DocumentHistoryResponse:
    """해당 클라이언트의 문서 분석 히스토리를 조회한다."""
    db = get_db_client()
    rows = db.fetch_all(
        text("""
            SELECT doc_id, file_name, created_at, gcs_raw_path, gcs_parsed_path
            FROM document_history
            WHERE client_id = :client_id
            ORDER BY created_at DESC
        """),
        {"client_id": client_id}
    )
    return DocumentHistoryResponse(
        documents=[DocumentHistoryItem(**r) for r in rows]
    )


@app.get("/api/documents/{doc_id}")
async def get_parsed_document(doc_id: str, client_id: str):
    """GCS에서 파싱된 계약서 JSON 데이터를 가져와 반환한다."""
    gcs = get_gcs_client()
    blob_name = f"clients/{client_id}/parsed/{doc_id}.json"
    try:
        content = gcs.download_bytes(blob_name)
        return json.loads(content)
    except Exception as e:
        log.error(f"문서 조회 실패: {e}")
        raise HTTPException(status_code=404, detail="과거 분석 데이터를 찾을 수 없습니다.")


@app.post("/api/analyze/clause", response_model=ClauseAnalysisResponse)
async def analyze_single_clause(request: AnalyzeClauseRequest) -> ClauseAnalysisResponse:
    """단일 특약에 대해 쿼리 확장 -> 하이브리드 검색 -> 리랭킹 파이프라인을 실행한다."""
    if not retrieval_service.is_ready:
        raise HTTPException(status_code=503, detail="코퍼스 로딩 중")

    # 1. 쿼리 확장 (상위 COMMON_TERMS_COUNT개 특약은 건너뜀)
    if request.clause_index < COMMON_TERMS_COUNT:
        return ClauseAnalysisResponse(
            index=request.clause_index,
            clause=request.clause_text,
            expansion=ClauseQueryExpansion(expansion_query="", keywords=[]),
            law_results=[],
            prec_results=[],
        )
    
    expansion = await _run_in_executor(_expand_clause, request.clause_index, request.clause_text)


@app.post("/api/analyze/report", response_model=ReportOutput)
async def analyze_report(request: ReportRequest) -> ReportOutput:
    """모든 특약의 분석 결과를 취합하여 최종 체크리스트와 보고서를 생성한다."""
    if not retrieval_service.is_ready:
        raise HTTPException(status_code=503, detail="코퍼스 로딩 중")

    def _run_report_gen():
        clauses_with_hits_dict = [c.model_dump() for c in request.clauses_with_hits]
        return generate_report_from_data(
            property_info=request.property_info,
            common_terms=request.common_terms,
            clauses_with_hits=clauses_with_hits_dict
        )

    return await _run_in_executor(_run_report_gen)


# ──────────────────────────────────────────────────────────────────────
# V2 비동기/병렬 파이프라인 엔드포인트
# ──────────────────────────────────────────────────────────────────────

@app.post("/api/analyze/clause_v2", response_model=ClauseAnalysisV2Response)
async def analyze_single_clause_v2(request: AnalyzeClauseRequest) -> ClauseAnalysisV2Response:
    """단일 특약에 대해 [QE -> 검색 -> LLM 요약]까지 논스톱으로 실행한다."""
    if not retrieval_service.is_ready:
        raise HTTPException(status_code=503, detail="코퍼스 로딩 중")

    # 1. 쿼리 확장 (상위 COMMON_TERMS_COUNT개 특약은 건너뜀)
    if request.clause_index < COMMON_TERMS_COUNT:
        return ClauseAnalysisV2Response(
            index=request.clause_index,
            clause=request.clause_text,
            expansion=ClauseQueryExpansion(expansion_query="", keywords=[]),
            law_results=[],
            prec_results=[],
            llm_related_laws=[],
        )
    
    expansion = await _run_in_executor(_expand_clause, request.clause_index, request.clause_text)

    # 2. 하이브리드 검색
    retrieval_res = await _run_in_executor(_retrieve_clause, expansion)

    # 3. 리랭킹 및 문서 내용 병합
    ranking_res = await _run_in_executor(_rerank_all, [retrieval_res])
    
    law_results = ranking_res[0].law_results if ranking_res else []
    prec_results = ranking_res[0].prec_results if ranking_res else []

    # 4. LLM 요약 (개별)
    def _run_llm_summary():
        laws_dict = [d.model_dump() for d in law_results]
        precs_dict = [d.model_dump() for d in prec_results]
        # lru_cache를 위해 hashable한 타입(str)으로 변환
        laws_json = json.dumps(laws_dict, sort_keys=True)
        precs_json = json.dumps(precs_dict, sort_keys=True)
        return generate_clause_summary(request.clause_text, laws_json, precs_json)
    
    llm_related_laws = await _run_in_executor(_run_llm_summary)

    return ClauseAnalysisV2Response(
        index=request.clause_index,
        clause=request.clause_text,
        expansion=expansion.expansion,
        law_results=law_results,
        prec_results=prec_results,
        llm_related_laws=llm_related_laws,
    )


@app.post("/api/analyze/report_v2", response_model=FinalReportOutput)
async def analyze_report_v2(request: ReportV2Request) -> FinalReportOutput:
    """모든 특약의 요약 결과를 바탕으로 최종 체크리스트와 연관성 분석을 수행한다."""
    def _run_final_report_gen():
        clauses_with_summaries_dict = [c.model_dump() for c in request.clauses_with_summaries]
        return generate_final_report(
            property_info=request.property_info,
            common_terms=request.common_terms,
            clauses_with_hits_and_summaries=clauses_with_summaries_dict
        )

    return await _run_in_executor(_run_final_report_gen)

# ──────────────────────────────────────────────────────────────────────
# 기존 (레거시) API 들 - 필요시 삭제 가능
# ──────────────────────────────────────────────────────────────────────

@app.post("/api/layout_parse", response_model=LayoutParseResponse)
async def layout_parse(file: UploadFile = File(...)) -> LayoutParseResponse:
    """PDF를 파싱해 계약서 구조(특약 목록 포함)를 반환한다."""
    pdf_bytes = await _read_pdf(file)
    contract = await _run_in_executor(_parse_contract, pdf_bytes)
    return LayoutParseResponse(contract=contract)


# ──────────────────────────────────────────────────────────────────────
# 2단계: query_expansion
# ──────────────────────────────────────────────────────────────────────

@app.post("/api/query_expansion", response_model=QueryExpansionResponse)
async def query_expansion(file: UploadFile = File(...)) -> QueryExpansionResponse:
    """layout_parse 후 각 특약에 대해 쿼리 확장을 실행한다."""
    pdf_bytes = await _read_pdf(file)
    contract = await _run_in_executor(_parse_contract, pdf_bytes)
    clauses = await _expand_all(contract)
    return QueryExpansionResponse(contract=contract, clauses=clauses)


# ──────────────────────────────────────────────────────────────────────
# 3단계: retrieval
# ──────────────────────────────────────────────────────────────────────

@app.post("/api/retrieval", response_model=RetrievalResponse)
async def retrieval(file: UploadFile = File(...)) -> RetrievalResponse:
    """query_expansion 후 각 특약에 대해 BM25 + Dense + RRF 검색을 실행한다."""
    if not retrieval_service.is_ready:
        raise HTTPException(status_code=503, detail="코퍼스 로딩 중")

    pdf_bytes = await _read_pdf(file)
    contract = await _run_in_executor(_parse_contract, pdf_bytes)
    clauses_exp = await _expand_all(contract)
    clauses_ret = await _retrieve_all(clauses_exp)
    return RetrievalResponse(contract=contract, clauses=clauses_ret)


# ──────────────────────────────────────────────────────────────────────
# 4단계: reranking
# ──────────────────────────────────────────────────────────────────────

@app.post("/api/reranking", response_model=RerankingResponse)
async def reranking(file: UploadFile = File(...)) -> RerankingResponse:
    """retrieval 후 RRF 상위 결과에 실제 문서 내용을 조회하여 반환한다."""
    if not retrieval_service.is_ready:
        raise HTTPException(status_code=503, detail="코퍼스 로딩 중")

    pdf_bytes = await _read_pdf(file)
    contract = await _run_in_executor(_parse_contract, pdf_bytes)
    clauses_exp = await _expand_all(contract)
    clauses_ret = await _retrieve_all(clauses_exp)
    clauses_ranked = await _run_in_executor(_rerank_all, clauses_ret)
    return RerankingResponse(contract=contract, clauses=clauses_ranked)




# ──────────────────────────────────────────────────────────────────────
# 내부 헬퍼 — 단계별 실행 함수
# ──────────────────────────────────────────────────────────────────────

async def _expand_all(contract: LeaseContract) -> list[ClauseExpansion]:
    """모든 특약에 대해 쿼리 확장을 병렬 실행한다."""
    special_terms = [t.strip() for t in contract.special_terms if t.strip()]

    loop = asyncio.get_event_loop()
    
    # Pre-allocate a list for all expansions, with placeholders for skipped terms
    all_expansions: list[ClauseExpansion | Any] = [None] * len(special_terms)
    
    tasks = []
    task_indices = [] # To keep track of original indices for tasks

    for i, term in enumerate(special_terms):
        if i < COMMON_TERMS_COUNT:
            # For the first COMMON_TERMS_COUNT terms, create a placeholder
            all_expansions[i] = ClauseExpansion(
                index=i,
                clause=term,
                expansion=ClauseQueryExpansion(expansion_query="", keywords=[]),
                retrieval_payload={},
            )
        else:
            # For other terms, create a task for expansion
            tasks.append(loop.run_in_executor(_clause_executor, _expand_clause, i, term))
            task_indices.append(i)

    # Execute tasks for non-common terms
    expanded_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Populate all_expansions list with results from executor
    for task_idx, result in zip(task_indices, expanded_results):
        if isinstance(result, Exception):
            log.error("특약 %d 쿼리 확장 실패: %s", task_idx, result)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"특약 {task_idx} 쿼리 확장 실패: {result}",
            )
        all_expansions[task_idx] = result
            
    # Ensure all elements are ClauseExpansion and handle potential None if something went wrong
    final_clauses: list[ClauseExpansion] = []
    for item in all_expansions:
        if item is not None:
            final_clauses.append(item)
        else:
            # This case should ideally not happen if logic is correct, but for safety
            log.warning("Unexpected None in all_expansions list, skipping.")
            
    return sorted(final_clauses, key=lambda c: c.index)


async def _retrieve_all(clauses: list[ClauseExpansion]) -> list[ClauseRetrieval]:
    """모든 특약에 대해 검색을 병렬 실행한다."""
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(_clause_executor, _retrieve_clause, clause)
        for clause in clauses
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    retrieved: list[ClauseRetrieval] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            log.error("특약 %d 검색 실패: %s", clauses[i].index, result)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"특약 {clauses[i].index} 검색 실패: {result}",
            )
        retrieved.append(result)
    return retrieved


# ──────────────────────────────────────────────────────────────────────
# 내부 헬퍼 — 동기 작업 (executor에서 실행)
# ──────────────────────────────────────────────────────────────────────

def _parse_contract(pdf_bytes: bytes) -> LeaseContract:
    from pipeline.preprocessing.pipeline import parse_lease_contract_bytes
    return parse_lease_contract_bytes(pdf_bytes)


def _expand_clause(index: int, clause: str) -> ClauseExpansion:
    from pipeline.retrieval.query_expansion.query_expansion import expand_clause
    from pipeline.retrieval.query_expansion.retrieval_adapter import build_retrieval_payload

    expansion = expand_clause(clause)
    payload = build_retrieval_payload(expansion, clause_text=clause)
    return ClauseExpansion(
        index=index,
        clause=clause,
        expansion=expansion,
        retrieval_payload=payload,
    )


def _retrieve_clause(clause: ClauseExpansion) -> ClauseRetrieval:
    raw = retrieval_service.retrieve(clause.retrieval_payload)
    return ClauseRetrieval(
        index=clause.index,
        clause=clause.clause,
        expansion=clause.expansion,
        retrieval_payload=clause.retrieval_payload,
        retrieval_results=ClauseRetrievalResult(
            bm25=[RetrievalHit(**h) for h in raw["bm25"]],
            dense=[RetrievalHit(**h) for h in raw["dense"]],
            law=[RetrievalHit(**h) for h in raw["law"]],
            prec=[RetrievalHit(**h) for h in raw["prec"]],
        ),
    )


def _rerank_all(clauses: list[ClauseRetrieval]) -> list[ClauseRanking]:
    """법령/판례 각각 상위 RERANKING_TOP_N 결과에 문서 내용을 조회해 반환한다.

    법령/판례는 독립 랭킹(각자 rank 1~N)이므로 분리하여 반환한다.
    """
    # 1) 모든 특약의 법령/판례 top-N 결과에서 doc_id 수집
    law_ids: set[str] = set()
    prec_ids: set[str] = set()
    for clause in clauses:
        for hit in clause.retrieval_results.law[:RERANKING_TOP_N]:
            law_ids.add(hit.doc_id)
        for hit in clause.retrieval_results.prec[:RERANKING_TOP_N]:
            prec_ids.add(hit.doc_id)

    # 2) 배치 조회
    law_content = _fetch_law_content(list(law_ids))
    prec_content = _fetch_prec_content(list(prec_ids))

    # 3) 결과 조합 (법령/판례 분리)
    ranked_clauses: list[ClauseRanking] = []
    for clause in clauses:
        law_top: list[RankedDocument] = []
        for hit in clause.retrieval_results.law[:RERANKING_TOP_N]:
            doc = law_content.get(hit.doc_id, {})
            title = (
                f"{doc.get('law_name', '')} "
                f"제{doc.get('article_no', '')}조"
                f"{' 제' + str(doc.get('paragraph_no', '')) + '항' if doc.get('paragraph_no') else ''}"
            ).strip()

            parent_txt = doc.get("parent_text") or ""
            child_txt = doc.get("child_text") or ""
            if not parent_txt:
                content = child_txt
            elif child_txt in parent_txt:
                content = parent_txt
            else:
                content = f"{parent_txt}\n\n{child_txt}"

            law_top.append(
                RankedDocument(
                    rank=hit.rank,
                    doc_id=hit.doc_id,
                    source_type=hit.source_type,
                    hybrid_score=hit.hybrid_score or 0.0,
                    bm25_rank=hit.bm25_rank,
                    dense_rank=hit.dense_rank,
                    title=title,
                    content=content,
                )
            )

        prec_top: list[RankedDocument] = []
        for hit in clause.retrieval_results.prec[:RERANKING_TOP_N]:
            doc = prec_content.get(hit.doc_id, {})
            title = doc.get("case_name") or hit.doc_id
            content = doc.get("judgment_summary") or doc.get("issue") or ""

            prec_top.append(
                RankedDocument(
                    rank=hit.rank,
                    doc_id=hit.doc_id,
                    source_type=hit.source_type,
                    hybrid_score=hit.hybrid_score or 0.0,
                    bm25_rank=hit.bm25_rank,
                    dense_rank=hit.dense_rank,
                    title=title,
                    content=content,
                )
            )

        ranked_clauses.append(
            ClauseRanking(
                index=clause.index,
                clause=clause.clause,
                law_results=law_top,
                prec_results=prec_top,
            )
        )

    return ranked_clauses


def _fetch_law_content(clause_keys: list[str]) -> dict[str, dict[str, Any]]:
    """law_child 테이블에서 조항 내용을 배치 조회한다."""
    if not clause_keys:
        return {}
    from sqlalchemy import text
    from shared.db.connection import get_db_client

    placeholders = ", ".join(f":k{i}" for i in range(len(clause_keys)))
    params: dict[str, Any] = {f"k{i}": k for i, k in enumerate(clause_keys)}
    rows = get_db_client().fetch_all(
        text(f"""
            SELECT c.clause_key::text, c.law_name, c.article_no, c.paragraph_no,
                   c.child_text, p.parent_text
            FROM   law_child c
            LEFT JOIN law_parent p ON c.parent_id = p.id
            WHERE  c.clause_key::text IN ({placeholders})
        """),
        params,
    )
    return {r["clause_key"]: r for r in rows}


def _fetch_prec_content(case_numbers: list[str]) -> dict[str, dict[str, Any]]:
    """case_law 테이블에서 판례 내용을 배치 조회한다."""
    if not case_numbers:
        return {}
    from sqlalchemy import text
    from shared.db.connection import get_db_client

    placeholders = ", ".join(f":n{i}" for i in range(len(case_numbers)))
    params: dict[str, Any] = {f"n{i}": n for i, n in enumerate(case_numbers)}
    rows = get_db_client().fetch_all(
        text(f"""
            SELECT case_number, case_name, issue, judgment_summary
            FROM   case_law
            WHERE  case_number IN ({placeholders})
        """),
        params,
    )
    return {r["case_number"]: r for r in rows}


# ──────────────────────────────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────────────────────────────

async def _read_pdf(file: UploadFile) -> bytes:
    if file.content_type not in {None, "", "application/pdf"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF 파일만 업로드할 수 있습니다.",
        )
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="업로드된 PDF 파일이 비어 있습니다.",
        )
    return pdf_bytes


async def _run_in_executor(func, *args):
    """동기 함수를 clause executor에서 실행한다."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_clause_executor, func, *args)
