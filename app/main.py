from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile, status

from app.schemas import (
    ContractAnalysisResponse,
    HealthResponse,
    SpecialTermExpansionResult,
)
from pipeline.preprocessing.schema import LeaseContract
from pipeline.retrieval.query_expansion.query_expansion_schema import ClauseQueryExpansion

app = FastAPI(title="ADE Contract Analysis API")


@app.get("/health", response_model=HealthResponse)
@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/v1/contracts/parse", response_model=LeaseContract)
async def parse_contract(file: UploadFile = File(...)) -> LeaseContract:
    pdf_bytes = await _read_pdf(file)
    try:
        return _parse_contract_from_pdf(pdf_bytes)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"계약서 전처리에 실패했습니다: {error}",
        ) from error


@app.post("/v1/contracts/analyze", response_model=ContractAnalysisResponse)
async def analyze_contract(file: UploadFile = File(...)) -> ContractAnalysisResponse:
    pdf_bytes = await _read_pdf(file)

    try:
        contract = _parse_contract_from_pdf(pdf_bytes)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"계약서 전처리에 실패했습니다: {error}",
        ) from error

    results: list[SpecialTermExpansionResult] = []
    for index, special_term in enumerate(contract.special_terms):
        clean_term = special_term.strip()
        if not clean_term:
            continue

        try:
            expansion = _expand_special_term(clean_term)
            retrieval_payload = _build_retrieval_payload(expansion)
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"query expansion에 실패했습니다: {error}",
            ) from error

        results.append(
            SpecialTermExpansionResult(
                index=index,
                special_term=clean_term,
                expansion=expansion,
                retrieval_payload=retrieval_payload,
            )
        )

    return ContractAnalysisResponse(
        contract=contract,
        special_term_expansions=results,
    )


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


def _parse_contract_from_pdf(pdf_bytes: bytes) -> LeaseContract:
    from pipeline.preprocessing.pipeline import parse_lease_contract_bytes

    return parse_lease_contract_bytes(pdf_bytes)


def _expand_special_term(special_term: str) -> ClauseQueryExpansion:
    from pipeline.retrieval.query_expansion.query_expansion import expand_clause

    return expand_clause(special_term)


def _build_retrieval_payload(expansion: ClauseQueryExpansion) -> dict:
    from pipeline.retrieval.query_expansion.retrieval_adapter import build_retrieval_payload

    return build_retrieval_payload(expansion)
