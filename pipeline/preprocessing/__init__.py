"""표준임대차계약서 전처리 패키지.

공개 API
--------
- :func:`parse_lease_contract` : PDF URI → :class:`LeaseContract`.
- :class:`LeaseContract` : 결과 Pydantic 모델.
- :class:`PreprocessingError` : 단계별 오류의 단일 타입.
"""
from pipeline.preprocessing.pipeline import (
    PreprocessingError,
    contract_to_json,
    parse_lease_contract,
    parse_lease_contract_from_text,
)
from pipeline.preprocessing.schema import LeaseContract

__all__ = [
    "LeaseContract",
    "PreprocessingError",
    "contract_to_json",
    "parse_lease_contract",
    "parse_lease_contract_from_text",
]
