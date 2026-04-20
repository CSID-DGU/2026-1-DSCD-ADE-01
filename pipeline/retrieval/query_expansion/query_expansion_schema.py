import re
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# =========================
# Enum definitions
# =========================

class SourceType(str, Enum): # 검색 대상 -> 법령, 판례, 상담사례
    LAW = "law"
    CASE = "case"
    COUNSEL = "counsel"


class DomainScope(str, Enum): # 상가임대차 섞인 사례 분리 or 경고
    RESIDENTIAL_LEASE = "residential_lease"
    COMMERCIAL_LEASE = "commercial_lease"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SearchTarget(str, Enum): # 검색 대상 필드 (법령, 판례, 상담사례 구조에 따라 다름)
    # Law
    LAW_CHILD_TEXT = "law_child_text"
    LAW_PARENT_TEXT = "law_parent_text"

    # Case law
    CASE_ISSUE_SUMMARY = "case_issue_summary"
    CASE_HOLDING_SUMMARY = "case_holding_summary"
    CASE_REFERENCED_LAW = "case_referenced_law"
    CASE_FULL_TEXT = "case_full_text"

    # Counsel / Q&A
    COUNSEL_QUESTION = "counsel_question"
    COUNSEL_TAGS = "counsel_tags"
    COUNSEL_ANSWER = "counsel_answer"


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueType(str, Enum):
    """
    상담사례 분석 결과를 반영한 1차 쟁점 유형

    주의:
    - 최종 확정 카테고리가 아니라 query expansion용 1차 라벨
    - 추후 더 정교한 군집 분석 결과에 따라 수정 가능
    - 이중 구조로 LLM 자유 추출 우선
    """
    DEPOSIT_RETURN = "보증금 반환·보전"
    RENEWAL_TERMINATION = "갱신·해지·계약종료"
    RENT_INCREASE = "차임·월세·보증금 증액"
    LOAN_CONDITION = "대출·계약금·조건부 해제"
    EARLY_MOVE_OUT_COST = "중도퇴거·중개보수·관리비"
    OWNERSHIP_TRANSFER = "매매·신탁·등기·임대인지위승계"
    OPPOSABILITY_PRIORITY = "전입신고·확정일자·대항력"
    REPAIR_RESTORATION = "하자·수선·원상회복"
    COMMERCIAL_RIGHT_PREMIUM = "상가·권리금·시설비"
    USE_RESTRICTION = "사용제한·반려동물·용도제한"
    PAYMENT_CLAIM = "약정금·지급명령·금전채권"
    OTHER = "기타"


# =========================
# Utility validator
# =========================

def _clean_str_list(values: List[str]) -> List[str]:
    """
    LLM 출력에서 자주 발생하는 문제를 정리한다.
    - 앞뒤 공백 제거
    - 빈 문자열 제거
    - 순서 유지 중복 제거
    """
    cleaned: List[str] = []
    seen = set()

    for value in values:
        if not isinstance(value, str):
            continue

        value = value.strip()
        if not value:
            continue

        if value not in seen:
            cleaned.append(value)
            seen.add(value)

    return cleaned


def _normalize_article_no(value: Any) -> str | None:
    """조문번호 입력값을 스키마 친화적인 문자열 형태로 정규화한다."""
    if value is None:
        return None

    if isinstance(value, bool):
        raise ValueError("article_no는 boolean일 수 없습니다.")

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        raise ValueError("article_no는 소수일 수 없습니다.")

    if not isinstance(value, str):
        raise ValueError("article_no는 문자열, 정수 또는 null이어야 합니다.")

    text = value.strip()
    if not text:
        return None

    text = re.sub(r"\s+", "", text)

    match = re.search(r"제?(\d+)조(?:의(\d+))?", text)
    if match:
        main = match.group(1)
        sub = match.group(2)
        return f"{main}의{sub}" if sub else main

    match = re.fullmatch(r"(\d+)의(\d+)", text)
    if match:
        return f"{match.group(1)}의{match.group(2)}"

    if re.fullmatch(r"\d+", text):
        return text

    return text


# =========================
# Retrieval control terms
# =========================

class RetrievalTerms(BaseModel):
    """
    BM25/Dense 검색 제어를 위한 공통 용어 집합 (표현 다양성과 활용 데이터 혼재 문제를 반영)
    - 반드시 포함되어야 할 단어
    - 있으면 좋은 단어
    - 제외해야 할 단어
    - 동의어
    - 질의 변형
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    must_terms: List[str] = Field(default_factory=list, max_length=8)
    should_terms: List[str] = Field(default_factory=list, max_length=12)
    exclude_terms: List[str] = Field(default_factory=list, max_length=8)
    synonyms: List[str] = Field(default_factory=list, max_length=12)
    query_variants: List[str] = Field(default_factory=list, max_length=5)

    @field_validator(
        "must_terms",
        "should_terms",
        "exclude_terms",
        "synonyms",
        "query_variants",
    )
    @classmethod
    def clean_lists(cls, values: List[str]) -> List[str]:
        return _clean_str_list(values)


# =========================
# Law query expansion
# =========================

class LawArticleCandidate(BaseModel):
    """
    법령 parent 데이터와 연결하기 위한 조문 후보.

    법령 parent 데이터 기준:
    - law_name
    - article_no
    - article_title
    - parent_text

    법령 child 데이터 기준:
    - child_id
    - parent_id
    - child_text
    - embedding
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    law_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="후보 법령명. 예: 주택임대차보호법, 민법, 주민등록법",
    )
    article_no: Optional[str] = Field(
        default=None,
        max_length=30,
        description="후보 조문번호. 예: 3, 3의2, 6의2, 623",
    )
    article_title: Optional[str] = Field(
        default=None,
        max_length=100,
        description="후보 조문 제목. 예: 대항력 등, 보증금의 회수",
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.MEDIUM,
        description="후보 조문이 실제로 관련 있을 가능성",
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=150,
        description="이 법령/조문 후보를 제시한 이유(선택)",
    )

    @field_validator("article_no", mode="before")
    @classmethod
    def normalize_article_no(cls, value: Any) -> str | None:
        return _normalize_article_no(value)


class LawQueryExpansion(BaseModel):
    """
    법령 검색용 query expansion.

    현재 법령 retrieval 기본 단위는 child_text다.
    검색 결과는 child_id -> parent_id -> parent_text로 연결한다.
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    legal_issue: str = Field(
        ...,
        min_length=5,
        max_length=300,
        description="특약의 핵심 법적 쟁점을 법령 검색 관점에서 요약",
    )
    applicable_rules: List[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="검색해야 할 법적 규칙, 권리, 의무, 효력 판단 포인트",
    )

    law_article_candidates: List[LawArticleCandidate] = Field(
        default_factory=list,
        max_length=5,
        description=(
            "법령명/조문번호/조문제목 후보. "
            "조문번호가 불확실하면 article_no는 null로 둔다."
        ),
    )

    law_keywords: List[str] = Field(
        ...,
        min_length=3,
        max_length=10,
        description="BM25 법령 검색에 사용할 짧은 법률 키워드",
    )
    law_dense_query: str = Field(
        ...,
        min_length=15,
        max_length=700,
        description="law_child.child_text 임베딩 검색에 사용할 문장형 질의",
    )
    retrieval_terms: RetrievalTerms = Field(
        default_factory=RetrievalTerms,
        description="법령 검색용 must/should/exclude/synonym/query variant 제어",
    )

    target_fields: List[SearchTarget] = Field(
        default_factory=lambda: [SearchTarget.LAW_CHILD_TEXT],
        min_length=1,
        max_length=2,
        description="법령 검색 대상. 기본은 child_text",
    )

    @field_validator("applicable_rules", "law_keywords")
    @classmethod
    def validate_string_lists(cls, values: List[str]) -> List[str]:
        cleaned = _clean_str_list(values)
        if not cleaned:
            raise ValueError("리스트 항목이 비어 있습니다.")
        return cleaned

    @field_validator("target_fields")
    @classmethod
    def validate_law_target_fields(cls, values: List[SearchTarget]) -> List[SearchTarget]:
        allowed = {SearchTarget.LAW_CHILD_TEXT, SearchTarget.LAW_PARENT_TEXT}
        invalid = [v for v in values if v not in allowed]
        if invalid:
            raise ValueError(
                f"law_query.target_fields에 법령 source와 맞지 않는 값이 있습니다: {invalid}"
            )
        return values


# =========================
# Case query expansion
# =========================

class ReferencedLawCandidate(BaseModel):
    """
    판례의 참조조문 필드와 연결하기 위한 후보.

    case_law.csv에는 참조조문 필드가 있으므로,
    판례 검색 시 이 필드에 boost를 줄 수 있다.
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    law_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="참조될 가능성이 있는 법령명",
    )
    article_no: Optional[str] = Field(
        default=None,
        max_length=30,
        description="참조될 가능성이 있는 조문번호",
    )
    article_title: Optional[str] = Field(
        default=None,
        max_length=100,
        description="참조될 가능성이 있는 조문 제목",
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.MEDIUM,
        description="참조조문 후보의 신뢰도",
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=150,
        description="이 참조조문 후보를 제시한 이유",
    )

    @field_validator("article_no", mode="before")
    @classmethod
    def normalize_article_no(cls, value: Any) -> str | None:
        return _normalize_article_no(value)


class CaseQueryExpansion(BaseModel):
    """
    판례 검색용 query expansion.

    판례 데이터 기준 주요 검색 필드:
    - 사건명
    - 판시사항
    - 판결요지
    - 참조조문
    - 판례내용
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_issue_query: str = Field(
        ...,
        min_length=10,
        max_length=600,
        description="판시사항/판결요지 검색에 사용할 법적 쟁점 중심 질의",
    )
    case_fact_pattern_query: str = Field(
        ...,
        min_length=10,
        max_length=800,
        description="판례내용 검색에 사용할 사실관계 중심 질의",
    )
    case_keywords: List[str] = Field(
        ...,
        min_length=3,
        max_length=10,
        description="BM25 판례 검색에 사용할 짧은 키워드",
    )

    referenced_law_candidates: List[ReferencedLawCandidate] = Field(
        default_factory=list,
        max_length=5,
        description="판례 참조조문 필드와 연결할 법령/조문 후보",
    )
    retrieval_terms: RetrievalTerms = Field(
        default_factory=RetrievalTerms,
        description="판례 검색용 must/should/exclude/synonym/query variant 제어",
    )

    target_fields: List[SearchTarget] = Field(
        default_factory=lambda: [
            SearchTarget.CASE_ISSUE_SUMMARY,
            SearchTarget.CASE_HOLDING_SUMMARY,
            SearchTarget.CASE_REFERENCED_LAW,
        ],
        min_length=1,
        max_length=4,
        description="판례 검색 대상 필드",
    )

    @field_validator("case_keywords")
    @classmethod
    def validate_case_keywords(cls, values: List[str]) -> List[str]:
        cleaned = _clean_str_list(values)
        if not cleaned:
            raise ValueError("case_keywords가 비어 있습니다.")
        return cleaned

    @field_validator("target_fields")
    @classmethod
    def validate_case_target_fields(cls, values: List[SearchTarget]) -> List[SearchTarget]:
        allowed = {
            SearchTarget.CASE_ISSUE_SUMMARY,
            SearchTarget.CASE_HOLDING_SUMMARY,
            SearchTarget.CASE_REFERENCED_LAW,
            SearchTarget.CASE_FULL_TEXT,
        }
        invalid = [v for v in values if v not in allowed]
        if invalid:
            raise ValueError(
                f"case_query.target_fields에 판례 source와 맞지 않는 값이 있습니다: {invalid}"
            )
        return values


# =========================
# Counsel query expansion
# =========================

class CounselQueryExpansion(BaseModel):
    """
    상담사례 검색용 query expansion.

    상담사례 데이터 기준:
    - question_title
    - question_body
    - tags
    - all_answers[].answer

    상담사례는 법령/판례와 달리 '유사 사용자 상황'을 찾는 데 중요하다.
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    counsel_question_query: str = Field(
        ...,
        min_length=10,
        max_length=800,
        description="상담사례 question_title/question_body 검색용 사용자 상황 질의",
    )
    counsel_answer_query: str = Field(
        ...,
        min_length=10,
        max_length=800,
        description="상담사례 answer 검색용 기대 법리/대응 방향 질의",
    )
    user_question_intent: str = Field(
        ...,
        min_length=5,
        max_length=300,
        description="사용자가 확인하고 싶은 법적 질문 의도",
    )

    counsel_keywords: List[str] = Field(
        ...,
        min_length=3,
        max_length=12,
        description="상담사례 질문/태그 검색에 사용할 키워드",
    )
    expected_tags: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="상담사례 tags 필드와 매칭될 가능성이 있는 태그 후보",
    )
    expected_answer_points: List[str] = Field(
        default_factory=list,
        max_length=6,
        description="상담 답변에서 기대되는 법리/대응 포인트",
    )
    retrieval_terms: RetrievalTerms = Field(
        default_factory=RetrievalTerms,
        description="상담사례 검색용 must/should/exclude/synonym/query variant 제어",
    )

    target_fields: List[SearchTarget] = Field(
        default_factory=lambda: [
            SearchTarget.COUNSEL_QUESTION,
            SearchTarget.COUNSEL_TAGS,
            SearchTarget.COUNSEL_ANSWER,
        ],
        min_length=1,
        max_length=3,
        description="상담사례 검색 대상 필드",
    )

    @field_validator("counsel_keywords", "expected_tags", "expected_answer_points")
    @classmethod
    def validate_string_lists(cls, values: List[str]) -> List[str]:
        return _clean_str_list(values)

    @field_validator("target_fields")
    @classmethod
    def validate_counsel_target_fields(cls, values: List[SearchTarget]) -> List[SearchTarget]:
        allowed = {
            SearchTarget.COUNSEL_QUESTION,
            SearchTarget.COUNSEL_TAGS,
            SearchTarget.COUNSEL_ANSWER,
        }
        invalid = [v for v in values if v not in allowed]
        if invalid:
            raise ValueError(
                f"counsel_query.target_fields에 상담사례 source와 맞지 않는 값이 있습니다: {invalid}"
            )
        return values


# =========================
# Source routing
# =========================

class SourceRoutingHint(BaseModel):
    """
    source-aware retrieval을 위한 검색 우선순위 힌트.

    최종 점수 가중치는 retrieval 단계에서 결정하고,
    query expansion 단계에서는 어떤 source가 중요한지만 제안한다.
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: SourceType = Field(
        ...,
        description="검색 대상 source",
    )
    priority: Priority = Field(
        ...,
        description="검색 우선순위 힌트",
    )
    reason: str = Field(
        ...,
        min_length=3,
        max_length=300,
        description="해당 source를 검색해야 하는 이유",
    )


# =========================
# Final query expansion schema
# =========================

class ClauseQueryExpansion(BaseModel):
    """
    특약 1개에 대한 source-aware query expansion 최종 출력 스키마.

    이 스키마는 최종 법적 판단 결과가 아니라,
    법령/판례/상담사례 검색을 위한 중간 산출물이다.
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["qe_v1"] = Field(
        default="qe_v1",
        description="query expansion schema version",
    )

    clause_text: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="입력된 원본 특약 문장",
    )
    normalized_clause: str = Field(
        ...,
        min_length=5,
        max_length=600,
        description="검색에 유리하도록 정규화한 특약 설명",
    )

    domain_scope: DomainScope = Field(
        default=DomainScope.UNKNOWN,
        description="주택임대차/상가임대차/혼합 여부",
    )
    issue_type_candidates_freeform: List[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="LLM이 추출한 자유형 쟁점 후보(정규화 전)",
    )
    issue_types_normalized: List[IssueType] = Field(
        ...,
        min_length=1,
        max_length=4,
        description="IssueType 기준으로 정규화된 1차 쟁점 유형",
    )
    risk_hypotheses: List[str] = Field(
        ...,
        min_length=1,
        max_length=6,
        description=(
            "최종 위험 판정이 아니라 검색 시 확인해야 할 위험 가설. "
            "예: 임차인 권리 제한 가능성, 비용 전가 가능성"
        ),
    )

    compound_clause_detected: bool = Field(
        default=False,
        description="하나의 입력에 여러 특약/쟁점이 섞여 있는지 여부",
    )
    sub_issue_summaries: List[str] = Field(
        default_factory=list,
        max_length=6,
        description="복합 특약인 경우 분리 가능한 하위 쟁점 요약",
    )

    law_query: LawQueryExpansion = Field(
        ...,
        description="법령 검색용 확장 질의",
    )
    case_query: CaseQueryExpansion = Field(
        ...,
        description="판례 검색용 확장 질의",
    )
    counsel_query: CounselQueryExpansion = Field(
        ...,
        description="상담사례 검색용 확장 질의",
    )

    source_routing: List[SourceRoutingHint] = Field(
        default_factory=list,
        max_length=3,
        description="법령/판례/상담사례 검색 우선순위 힌트",
    )

    expansion_notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="검색 시 주의할 점 또는 불확실성 메모",
    )

    @field_validator("risk_hypotheses", "sub_issue_summaries")
    @classmethod
    def validate_top_level_string_lists(cls, values: List[str]) -> List[str]:
        return _clean_str_list(values)

    @field_validator("risk_hypotheses")
    @classmethod
    def validate_risk_hypotheses_not_empty(cls, values: List[str]) -> List[str]:
        if not values:
            raise ValueError("risk_hypotheses가 비어 있습니다.")
        return values

    @field_validator("issue_type_candidates_freeform")
    @classmethod
    def validate_issue_type_candidates_freeform(cls, values: List[str]) -> List[str]:
        cleaned = _clean_str_list(values)
        if not cleaned:
            raise ValueError("issue_type_candidates_freeform이 비어 있습니다.")
        return cleaned

    @model_validator(mode="after")
    def validate_domain_issue_consistency(self):
        if (
            self.domain_scope == DomainScope.RESIDENTIAL_LEASE
            and IssueType.COMMERCIAL_RIGHT_PREMIUM in self.issue_types_normalized
        ):
            warning_note = (
                "[warning] domain_scope=RESIDENTIAL_LEASE 이지만 "
                "issue_types_normalized에 상가 권리금 쟁점이 포함되어 "
                "mixed 가능성을 재검토해야 합니다."
            )
            self.expansion_notes = (
                warning_note
                if not self.expansion_notes
                else f"{self.expansion_notes} | {warning_note}"
            )
        return self

    @model_validator(mode="after")
    def validate_source_routing_unique(self):
        if not self.source_routing:
            self.source_routing = [
                SourceRoutingHint(
                    source_type=SourceType.LAW,
                    priority=Priority.HIGH,
                    reason="조문 확인이 필요합니다.",
                ),
                SourceRoutingHint(
                    source_type=SourceType.CASE,
                    priority=Priority.MEDIUM,
                    reason="쟁점 유사 판례를 확인합니다.",
                ),
                SourceRoutingHint(
                    source_type=SourceType.COUNSEL,
                    priority=Priority.MEDIUM,
                    reason="유사 상담 맥락을 확인합니다.",
                ),
            ]

        source_types = [route.source_type for route in self.source_routing]
        if len(source_types) != len(set(source_types)):
            raise ValueError("source_routing에 중복 source_type이 있습니다.")
        return self
