"""표준 주택임대차계약서 Layout Markdown 룰 파서."""
from __future__ import annotations

import re

from pydantic import ValidationError

from pipeline.preprocessing.schema import (
    Art1,
    Art1Details,
    Art12,
    Art12Details,
    Art13,
    Art13Details,
    Art3,
    Art4,
    Balance,
    Building,
    ContractKind,
    GeneralTerms,
    LeaseContract,
    LeasedPart,
    MgmtFee,
    FixedDetails,
    PropertyInfo,
    Land,
    TextOnlyArticle,
)


class RuleParseError(RuntimeError):
    """룰 기반 파싱 실패."""


LAND_TYPES = {"대", "잡종지", "전", "답", "기타"}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _find_row(text: str, label: str) -> list[str]:
    for line in text.splitlines():
        if line.strip().startswith("|") and label in line:
            return _cells(line)
    return []


def _number(text: str) -> int | None:
    match = re.search(r"₩\s*([0-9,]+)", text)
    if not match:
        match = re.search(r"([0-9,]+)\s*원", text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _area(text: str) -> float | None:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:m|㎡)", text)
    return float(match.group(1)) if match else None


def _value_after_label(row: list[str], label_words: set[str]) -> str | None:
    for index, cell in enumerate(row):
        if any(label in cell for label in label_words) and index + 1 < len(row):
            value = row[index + 1].strip()
            return value or None
    return None


def _values_after_label(
    row: list[str], label_words: set[str], stop_words: set[str]
) -> str | None:
    for index, cell in enumerate(row):
        if any(label in cell for label in label_words):
            values: list[str] = []
            for value in row[index + 1 :]:
                if any(stop in value for stop in stop_words):
                    break
                if value:
                    values.append(value)
            return " ".join(values).strip() or None
    return None


def _date(text: str) -> str | None:
    match = re.search(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일", text)
    return re.sub(r"\s+", " ", match.group(0)) if match else None


def _checked(text: str, label: str) -> bool:
    pattern = rf"[☑■✓]\s*{re.escape(label)}"
    return re.search(pattern, text) is not None


def _lease_type(text: str) -> str:
    if _checked(text, "보증금 있는 월세"):
        return "보증금있는월세"
    if _checked(text, "전세"):
        return "전세"
    if _checked(text, "월세"):
        return "월세"
    raise RuleParseError("lease_type not found")


def _contract_kind(text: str) -> ContractKind:
    if re.search(r"[☑■✓]\s*신규\s*계약", text):
        return ContractKind(type="신규", renewal_info=None)
    if re.search(r"[☑■✓]\s*합의에 의한 재계약", text):
        return ContractKind(type="재계약")
    if re.search(r"[☑■✓].*계약갱신요구권", text):
        return ContractKind(type="갱신")
    return ContractKind(type=None)


def _property_info(text: str) -> PropertyInfo:
    address_row = _find_row(text, "소재지")
    land_row = _find_row(text, "토지")
    building_row = _find_row(text, "건물")
    leased_row = _find_row(text, "임차할부분")

    address = _values_after_label(address_row, {"소재지"}, {"면적"})

    land_type = next((cell for cell in land_row if cell in LAND_TYPES), None)
    land_area = _area(" ".join(address_row)) or _area(" ".join(land_row))

    structure = None
    use = None
    building_value = next((cell for cell in building_row if "/" in cell), None)
    if building_value is None:
        building_value = _value_after_label(building_row, {"구조·용도", "건물"})
    if building_value:
        parts = [part.strip() for part in building_value.split("/", 1)]
        structure = parts[0] if parts else None
        use = parts[1] if len(parts) > 1 else None

    building = Building(
        structure=structure,
        use=use,
        area_m2=_area(" ".join(building_row)),
    )
    leased_part = LeasedPart(
        detail_address=leased_row[1] if len(leased_row) > 1 else None,
        area_m2=_area(" ".join(leased_row)),
    )

    tax_arrears = "없음" if "미납 국세" in text and _checked(text, "없음") else None
    prior_fixdate = (
        "해당없음" if "선순위 확정일자" in text and _checked(text, "해당 없음") else None
    )

    return PropertyInfo(
        address=address,
        land=Land(land_type=land_type, land_area_m2=land_area),
        building=building,
        leased_part=leased_part,
        contract_kind=_contract_kind(text),
        tax_arrears=tax_arrears,
        prior_fixdate=prior_fixdate,
    )


def _article_map(text: str) -> dict[int, str]:
    end_marker = text.find("[특약사항]")
    if end_marker != -1:
        text = text[:end_marker]
    matches = list(
        re.finditer(r"제(\d{1,2})조(?![의항0-9])\s*(?:\([^)]*\))?", text)
    )
    articles: dict[int, str] = {}
    for index, match in enumerate(matches):
        number = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = re.sub(r"\s+", " ", text[start:end]).strip()
        articles[number] = body
    if not articles:
        raise RuleParseError("general terms not found")
    return articles


def _art1_details(text: str) -> Art1Details:
    deposit_row = " ".join(_find_row(text, "보증금"))
    down_row = " ".join(_find_row(text, "계약금"))
    balance_row = " ".join(_find_row(text, "잔금"))
    rent_row = " ".join(_find_row(text, "차임"))
    mgmt_row = " ".join(_find_row(text, "관리비"))

    rent_amount = _number(rent_row)
    mgmt_total = _number(mgmt_row)
    return Art1Details(
        deposit=_number(deposit_row),
        down_payment=_number(down_row),
        balance=Balance(amount=_number(balance_row), date=_date(balance_row)),
        monthly_rent=None if rent_amount is None else {"amount": rent_amount, "date": None},
        mgmt_fee=None
        if mgmt_total is None
        else MgmtFee(type="정액", fixed_details=FixedDetails(total=mgmt_total)),
    )


def _art12_details(text: str) -> Art12Details:
    rate_match = re.search(r"([0-9]+(?:\.[0-9]+)?)%", text)
    return Art12Details(
        broker_fee_rate=float(rate_match.group(1)) if rate_match else None,
        broker_fee_amount=_number(text),
        vat_included="불포함" if _checked(text, "불포함") else None,
    )


def _general_terms(text: str) -> GeneralTerms:
    articles = _article_map(text)
    kwargs = {}
    for number in range(1, 14):
        body = articles.get(number)
        if body is None:
            continue
        if number == 1:
            kwargs["art1"] = Art1(text=body, details=_art1_details(text))
        elif number == 3:
            kwargs["art3"] = Art3(text=body, details=None)
        elif number == 4:
            kwargs["art4"] = Art4(text=body, details=None)
        elif number == 12:
            kwargs["art12"] = Art12(text=body, details=_art12_details(body))
        elif number == 13:
            kwargs["art13"] = Art13(
                text=body,
                details=Art13Details(issue_date=_date(body)),
            )
        else:
            kwargs[f"art{number}"] = TextOnlyArticle(text=body)
    return GeneralTerms(**kwargs)


def _special_terms(text: str) -> list[str]:
    marker = text.find("[특약사항]")
    if marker == -1:
        return []

    terms: list[str] = []
    lines_after_marker = text[marker:].splitlines()[1:]
    
    current_term_lines: list[str] = [] # 현재 처리 중인 특약의 여러 줄을 저장할 리스트

    for raw_line in lines_after_marker:
        line = raw_line.strip()

        if not line: # 빈 라인은 무시
            continue

        # 특약 섹션의 종료 조건
        if line.startswith("|") or line.startswith("[MASKED_"):
            break
        if any(word in line for word in ("주민등록번호", "전화", "이메일", "본 계약을 증명")):
            break

        # 새로운 특약의 시작 ( '*' 또는 '-' 로 시작)
        if line.startswith(("*", "-")):
            # 이전에 모아둔 특약이 있다면 리스트에 추가 (새로운 특약이 시작되었으므로)
            if current_term_lines:
                terms.append(" ".join(current_term_lines).strip())
            
            # 새로운 특약 시작
            current_term_lines = [line[1:].strip()] # '*' 또는 '-' 기호 제거
        else:
            # '*' 또는 '-'로 시작하지 않는 줄은 이전 특약의 내용에 이어붙임
            if current_term_lines: # 현재 처리 중인 특약이 있는 경우에만 이어붙임
                current_term_lines.append(line)
            # current_term_lines가 비어 있다면 (즉, '*'나 '-'로 시작하는 특약이 아직 없는데
            # 내용만 있는 줄이 나타난다면) 이 줄은 무시됩니다. (사용자 요청에 부합)

    # 루프 종료 후 마지막 특약을 리스트에 추가
    if current_term_lines:
        terms.append(" ".join(current_term_lines).strip())
            
    return terms


def parse_contract_text(masked_text: str) -> LeaseContract:
    """마스킹된 Layout Markdown을 LeaseContract로 변환한다."""
    try:
        return LeaseContract(
            lease_type=_lease_type(masked_text),
            property_info=_property_info(masked_text),
            general_terms=_general_terms(masked_text),
            special_terms=_special_terms(masked_text),
        )
    except ValidationError as exc:
        raise RuleParseError(str(exc)) from exc
