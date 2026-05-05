"""표준임대차계약서 전처리 패키지."""
from pipeline.preprocessing.schema import LeaseContract

__all__ = [
    "LeaseContract",
    "PreprocessingError",
    "contract_to_json",
    "parse_lease_contract",
    "parse_lease_contract_from_text",
]


def __getattr__(name: str):
    if name in {
        "PreprocessingError",
        "contract_to_json",
        "parse_lease_contract",
        "parse_lease_contract_from_text",
    }:
        from pipeline.preprocessing import pipeline

        return getattr(pipeline, name)
    raise AttributeError(name)
