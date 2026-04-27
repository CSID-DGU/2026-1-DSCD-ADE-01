"""주택임대차 표준계약서 추출 결과 Pydantic 스키마.

Vertex Gemini의 ``response_schema`` 인자에 그대로 전달되며, 동일 스키마로
LLM 응답 검증도 수행한다. 누락 가능한 모든 필드는 ``| None``으로 선언하고
기본값 ``None``을 둔다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# property_info
# ---------------------------------------------------------------------------
class Building(BaseModel):
    structure: str | None = None
    use: str | None = None
    area_m2: float | None = None


class LeasedPart(BaseModel):
    detail_address: str | None = None
    area_m2: float | None = None


class Term(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


class RenewalInfo(BaseModel):
    term: Term | None = None
    deposit: int | None = None
    rent: int | None = None


class ContractKind(BaseModel):
    type: Literal["신규", "재계약", "갱신"] | None = None
    renewal_info: RenewalInfo | None = None


class PropertyInfo(BaseModel):
    address: str | None = None
    building_type: Literal[
        "아파트",
        "오피스텔",
        "빌라",
        "단독주택",
        "상업용건물",
        "토지",
        "다세대주택",
        "다가구주택",
        "기타",
    ] | None = None
    land_type: Literal["대", "잡종지", "전", "답", "기타"] | None = None
    land_area_m2: float | None = None
    building: Building | None = None
    leased_part: LeasedPart | None = None
    contract_kind: ContractKind | None = None
    tax_arrears: Literal["없음", "있음"] | None = None
    prior_fixdate: Literal["없음", "있음", "해당없음"] | None = None
    fixdate_note: str | None = None


# ---------------------------------------------------------------------------
# general_terms — art1
# ---------------------------------------------------------------------------
class InterimPayment(BaseModel):
    amount: int | None = None
    date: str | None = None


class Balance(BaseModel):
    amount: int | None = None
    date: str | None = None


class MonthlyRent(BaseModel):
    amount: int | None = None
    date: str | None = None


class FixedDetails(BaseModel):
    total: int | None = None
    general: int | None = None
    electricity: int | None = None
    water: int | None = None
    gas: int | None = None
    heating: int | None = None
    internet: int | None = None
    tv: int | None = None
    other: int | None = None


class MgmtFee(BaseModel):
    type: Literal["정액", "변동", "포함"] | None = None
    fixed_details: FixedDetails | None = None
    variable_details: str | None = None


class Art1Details(BaseModel):
    deposit: int | None = None
    down_payment: int | None = None
    interim_payment: InterimPayment | None = None
    balance: Balance | None = None
    monthly_rent: MonthlyRent | None = None
    mgmt_fee: MgmtFee | None = None


class Art1(BaseModel):
    text: str | None = None
    details: Art1Details | None = None


# ---------------------------------------------------------------------------
# general_terms — art3
# ---------------------------------------------------------------------------
class RepairDue(BaseModel):
    type: Literal["잔금지급기일", "기타"] | None = None
    date: str | None = None
    other_text: str | None = None


class IfNotRepaired(BaseModel):
    type: Literal["차임공제", "기타"] | None = None
    other_text: str | None = None


class Art3Details(BaseModel):
    repair_needed: bool | None = None
    repair_items: str | None = None
    repair_due: RepairDue | None = None
    if_not_repaired: IfNotRepaired | None = None


class Art3(BaseModel):
    text: str | None = None
    details: Art3Details | None = None


# ---------------------------------------------------------------------------
# general_terms — art4
# ---------------------------------------------------------------------------
class Art4Details(BaseModel):
    landlord_cost: list[str] | None = None
    tenant_cost: list[str] | None = None


class Art4(BaseModel):
    text: str | None = None
    details: Art4Details | None = None


# ---------------------------------------------------------------------------
# general_terms — art12, art13
# ---------------------------------------------------------------------------
class Art12Details(BaseModel):
    broker_fee_rate: float | None = None
    broker_fee_amount: int | None = None
    vat_included: Literal["포함", "불포함"] | None = None


class Art12(BaseModel):
    text: str | None = None
    details: Art12Details | None = None


class Art13Details(BaseModel):
    issue_date: str | None = None


class Art13(BaseModel):
    text: str | None = None
    details: Art13Details | None = None


# ---------------------------------------------------------------------------
# 본문만 있는 단순 조항 (art2, art5~art11, special_terms.art1~art5)
# ---------------------------------------------------------------------------
class TextOnlyArticle(BaseModel):
    text: str | None = None


# ---------------------------------------------------------------------------
# 최상위
# ---------------------------------------------------------------------------
class GeneralTerms(BaseModel):
    art1: Art1 | None = None
    art2: TextOnlyArticle | None = None
    art3: Art3 | None = None
    art4: Art4 | None = None
    art5: TextOnlyArticle | None = None
    art6: TextOnlyArticle | None = None
    art7: TextOnlyArticle | None = None
    art8: TextOnlyArticle | None = None
    art9: TextOnlyArticle | None = None
    art10: TextOnlyArticle | None = None
    art11: TextOnlyArticle | None = None
    art12: Art12 | None = None
    art13: Art13 | None = None


class LeaseContract(BaseModel):
    """표준임대차계약서 추출 결과 최상위 모델.

    ``special_terms``는 특약 조항이 자유 기재 영역(개수 가변)이므로 조항별
    문자열의 리스트로 둔다. 각 원소가 하나의 특약 본문이며 다음 모듈은
    원소 단위로 순회한다. 특약이 없으면 빈 리스트.
    """

    lease_type: Literal["보증금있는월세", "전세", "월세"]
    property_info: PropertyInfo
    general_terms: GeneralTerms
    special_terms: list[str]
