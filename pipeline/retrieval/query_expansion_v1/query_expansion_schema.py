from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_str_list(values: List[str]) -> List[str]:
    """문자열 리스트를 trim/중복제거하여 정리한다."""
    cleaned: List[str] = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        cleaned.append(normalized)
        seen.add(normalized)
    return cleaned


class ClauseQueryExpansion(BaseModel):
    """
    특약 1개에 대한 단순 query expansion 최종 스키마.

    내부 reasoning은 자유롭게 수행하되, 출력은 retrieval 입력 두 필드만 반환한다.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expansion_query: str = Field(
        ...,
        min_length=20,
        max_length=800,
        description="Dense/Semantic 검색에 사용할 법률 reasoning 기반 확장 질의문",
    )
    keywords: List[str] = Field(
        ...,
        min_length=3,
        max_length=15,
        description="BM25 검색에 사용할 핵심 법률 키워드 리스트",
    )

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, values: List[str]) -> List[str]:
        cleaned = _clean_str_list(values)
        if len(cleaned) < 3:
            raise ValueError("keywords는 중복 제거 후 최소 3개 이상이어야 합니다.")
        return cleaned
