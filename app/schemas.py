from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from pipeline.preprocessing.schema import LeaseContract
from pipeline.retrieval.query_expansion.query_expansion_schema import ClauseQueryExpansion


class HealthResponse(BaseModel):
    status: str


class SpecialTermExpansionResult(BaseModel):
    index: int
    special_term: str
    expansion: ClauseQueryExpansion
    retrieval_payload: dict[str, Any]


class ContractAnalysisResponse(BaseModel):
    contract: LeaseContract
    special_term_expansions: list[SpecialTermExpansionResult]

