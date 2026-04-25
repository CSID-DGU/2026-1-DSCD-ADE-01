import re
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _split_free_issue_phrases(body: str) -> List[str]:
    """[자유 쟁점] 본문을 짧은 구(쉼표·중점·줄바꿈 등) 단위로 분해한다."""
    parts = re.split(r"[,，·;；]\s*|\n+", body.strip())
    return [p.strip() for p in parts if p.strip()]


def _sentence_segments(body: str) -> List[str]:
    """느슨하게 문장 단위로 분할한다(마침표·물음표 등 기준). 구분자가 없으면 본문 1문장으로 본다."""
    text = body.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    segments = [p.strip() for p in parts if p.strip()]
    return segments if segments else [text]


REQUIRED_SECTION_LABELS = [
    "[쟁점 유형]",
    "[자유 쟁점]",
    "[관련 법률 개념 및 규칙]",
    "[유사 분쟁 사실관계]",
]


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
    특약 1개에 대한 query expansion 최종 스키마.

    출력 필드는 expansion_query + keywords 두 개만 유지한다.
    expansion_query에는 예전 다필드 스키마의 reasoning을 섹션형 텍스트로 압축해 넣는다
    (dense/semantic 임베딩 입력용).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expansion_query: str = Field(
        ...,
        min_length=40,
        max_length=700,
        description=(
            "Dense/Semantic 검색용 구조화 reasoning 텍스트(전체 700자 이내). "
            "[쟁점 유형], [자유 쟁점], [관련 법률 개념 및 규칙], [유사 분쟁 사실관계] 네 섹션을 반드시 포함한다."
        ),
    )
    keywords: List[str] = Field(
        ...,
        min_length=3,
        max_length=15,
        description="BM25 검색에 사용할 짧은 핵심 법률 키워드만 포함한다.",
    )

    @field_validator("expansion_query")
    @classmethod
    def validate_expansion_query_sections(cls, value: str) -> str:
        missing = [label for label in REQUIRED_SECTION_LABELS if label not in value]
        if missing:
            raise ValueError(f"expansion_query에 필수 섹션이 없습니다: {missing}")

        positions = [value.index(label) for label in REQUIRED_SECTION_LABELS]
        if positions != sorted(positions):
            raise ValueError("expansion_query의 섹션 순서가 올바르지 않습니다.")

        pattern = (
            r"\[쟁점 유형\](.*?)"
            r"\[자유 쟁점\](.*?)"
            r"\[관련 법률 개념 및 규칙\](.*?)"
            r"\[유사 분쟁 사실관계\](.*)"
        )
        match = re.search(pattern, value, flags=re.DOTALL)
        if not match:
            raise ValueError("expansion_query 섹션 구문을 파싱할 수 없습니다.")

        bodies = [part.strip() for part in match.groups()]
        if any(not body for body in bodies):
            raise ValueError("expansion_query의 각 섹션은 비어 있지 않아야 합니다.")

        issue_type, free_issues, rules, dispute = bodies

        if "\n" in issue_type:
            raise ValueError("[쟁점 유형]은 한 줄만 작성해야 합니다.")

        free_parts = _split_free_issue_phrases(free_issues)
        if not (3 <= len(free_parts) <= 5):
            raise ValueError(
                "[자유 쟁점]은 쉼표·중점 등으로 구분된 짧은 명사구 또는 짧은 문장 3~5개여야 합니다."
            )

        rule_sents = _sentence_segments(rules)
        if len(rule_sents) > 2:
            raise ValueError("[관련 법률 개념 및 규칙]은 문장 2개 이내로 작성해야 합니다.")

        dispute_sents = _sentence_segments(dispute)
        if len(dispute_sents) > 2:
            raise ValueError("[유사 분쟁 사실관계]는 문장 2개 이내로 작성해야 합니다.")

        return value

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, values: List[str]) -> List[str]:
        cleaned = _clean_str_list(values)
        if len(cleaned) < 3:
            raise ValueError("keywords는 중복 제거 후 최소 3개 이상이어야 합니다.")
        return cleaned
