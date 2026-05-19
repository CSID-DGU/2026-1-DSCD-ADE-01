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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expansion_query: str = Field(
        ...,
        min_length=40,
        max_length=300,
        description=(
            "Dense/Semantic 검색용 산문 텍스트(300자 이내). "
            "특약의 구체적 사실(금액, 날짜, 조건, 행위 주체 등)을 보존하면서 "
            "이 특약에서 발생하는 구체 법률 쟁점을 2~3문장으로 서술한다. "
            "섹션 라벨 없이 자연스러운 산문으로 작성한다."
        ),
    )
    keywords: List[str] = Field(
        ...,
        min_length=3,
        max_length=7,
        description=(
            "BM25 검색에 사용할 이 특약에 특화된 구체 명사구 3~7개. "
            "다른 특약과 구별되는 이 특약만의 구체적 상황을 반영한다."
        ),
    )

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, values: List[str]) -> List[str]:
        cleaned = _clean_str_list(values)
        if len(cleaned) < 3:
            raise ValueError("keywords는 중복 제거 후 최소 3개 이상이어야 합니다.")
        return cleaned
