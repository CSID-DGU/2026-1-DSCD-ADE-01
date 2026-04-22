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
    특약 1개에 대한 query expansion2 최종 스키마.

    출력 필드는 expansion_query + keywords 두 개만 유지한다.
    expansion_query에는 예전 다필드 스키마의 reasoning을 섹션형 텍스트로 압축해 넣는다
    (dense/semantic 임베딩 입력용).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expansion_query: str = Field(
        ...,
        min_length=40,
        max_length=3000,
        description=(
            "Dense/Semantic 검색용 구조화 reasoning 텍스트. "
            "[쟁점 유형], [자유 쟁점], [관련 법률 개념 및 규칙], [유사 분쟁 사실관계] 네 섹션을 반드시 포함한다."
        ),
    )
    keywords: List[str] = Field(
        ...,
        min_length=3,
        max_length=15,
        description="BM25 검색에 사용할 짧은 핵심 법률 키워드만 포함한다.",
    )

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, values: List[str]) -> List[str]:
        cleaned = _clean_str_list(values)
        if len(cleaned) < 3:
            raise ValueError("keywords는 중복 제거 후 최소 3개 이상이어야 합니다.")
        return cleaned
