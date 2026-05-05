"""표준계약서 Layout Markdown 룰 파서 테스트."""
from __future__ import annotations

from pipeline.preprocessing.masking import mask_pii


SAMPLE_LAYOUT_TEXT = """
□보증금 있는 월세

# 주택임대차표준계약서

☑ 전세

□월세

[임차주택의 표시]

| 소재지 | 서울특별시 | 마포구 아현동 700 |  |  |
| 토지 | 지목 | 대 | 면적 | 84.0m |
| 건물 | 구조·용도 | 철근콘크리트조 / 아파트 | 면적 | 50.0m |
| 임차할부분 | 101동 502호 |  | 면적 | 50.0m |

■ 신규 계약

□ 합의에 의한 재계약

미납 국세·지방세
☑ 없음

선순위 확정일자 현황
☑ 해당 없음

[계약내용]

| 보증금 | 금 이천만원정(₩20000000 ) |
| 계약금 | 금 이백만원정(₩2000000)은 계약시에 지불하고 영수함. |
| 잔금 | 금 천팔백만원정(₩18000000)은 2023년 04월 19일에 지불한다 |
| 차임(월세) | 금 원정은 매월 일에 지불한다(입금계좌: ) |
| 관리비 | 정액인 경우 금 100000원 |

제1조(보증금과 차임 및 관리비)
위 부동산의 임대차에 관하여 임대인과 임차인은 합의에 의하여 보증금과 차임 및 관리비를 아래와 같이 지불하기로 한다.
제2조(임대차기간)
임대인은 임차주택을 임대차 목적대로 사용·수익할 수 있는 상태로 인도한다.
제3조(입주 전 수리)
수리가 필요한 시설 없음.
제4조(임차주택의 사용·관리·수선)
임대인은 목적물을 사용하기에 필요한 상태를 유지하게 하여야 한다.
제5조(계약의 해제)
중도금 지급 전까지 계약을 해제할 수 있다.
제6조(채무불이행과 손해배상)
채무를 이행하지 않으면 손해배상을 청구할 수 있다.
제7조(계약의 해지)
임차주택을 사용할 수 없는 경우 계약을 해지할 수 있다.
제8조(갱신요구와 거절)
임차인은 계약갱신을 요구할 수 있다.
제9조(계약의 종료)
계약 종료 시 보증금을 반환하여야 한다.
제10조(비용의 정산)
계약 종료 시 공과금과 관리비를 정산한다.
제11조(분쟁의 해결)
분쟁은 협의 또는 조정으로 해결한다.
제12조(중개보수 등)
중개보수는 거래 가액의 0.005%인 100000원(☐ 부가가치세 포함 ☑ 불포함)으로 한다.
제13조(중개대상물확인․설명서 교부)
개업공인중개사는 2023년 04월 19일 임대인과 임차인에게 교부한다.

[특약사항]
* 주택을 인도받은 임차인은 2023년 04월 19일까지 전입신고와 확정일자를 받기로 한다.
* 임대인은 임차인의 보증 보험 가입을 위해 필요한 절차에 적극 협조한다.

주 소 서울특별시 마포구 개인주소 1
주민등록번호 900101-1234567
전화 010-1234-5678
이메일 test@example.com
"""


def _parse_sample():
    from pipeline.preprocessing.rule_parser import parse_contract_text

    return parse_contract_text(mask_pii(SAMPLE_LAYOUT_TEXT))


def test_rule_parser_extracts_basic_property_info() -> None:
    contract = _parse_sample()

    assert contract.lease_type == "전세"
    assert contract.property_info.address == "서울특별시 마포구 아현동 700"
    assert contract.property_info.land.land_type == "대"
    assert contract.property_info.land.land_area_m2 == 84.0
    assert contract.property_info.building.structure == "철근콘크리트조"
    assert contract.property_info.building.use == "아파트"
    assert contract.property_info.building.area_m2 == 50.0
    assert contract.property_info.leased_part.detail_address == "101동 502호"
    assert contract.property_info.contract_kind.type == "신규"


def test_rule_parser_ignores_missing_land_type_cell() -> None:
    from pipeline.preprocessing.rule_parser import parse_contract_text

    text = SAMPLE_LAYOUT_TEXT.replace(
        "| 토지 | 지목 | 대 | 면적 | 84.0m |",
        "| 토지 | 지목 | 면적 | 84.0m |",
    )

    contract = parse_contract_text(mask_pii(text))

    assert contract.property_info.land.land_type is None
    assert contract.property_info.land.land_area_m2 == 84.0


def test_rule_parser_handles_actual_layout_table_shape() -> None:
    from pipeline.preprocessing.rule_parser import parse_contract_text

    text = SAMPLE_LAYOUT_TEXT.replace(
        "| 소재지 | 서울특별시 | 마포구 아현동 700 |  |  |",
        "| 소재지 | 서울특별시 마포구 아현동 700 | 면적 | 84.0m |",
    ).replace(
        "| 토지 | 지목 | 대 | 면적 | 84.0m |",
        "| 토지 지목 | 대 | 면적 | 50.0m |",
    ).replace(
        "| 건물 | 구조·용도 | 철근콘크리트조 / 아파트 | 면적 | 50.0m |",
        "| 건물 구조·용도 | 철근콘크리트조 / 아파트 | 면적 | 50.0m |",
    )

    contract = parse_contract_text(mask_pii(text))

    assert contract.property_info.address == "서울특별시 마포구 아현동 700"
    assert contract.property_info.land.land_type == "대"
    assert contract.property_info.land.land_area_m2 == 84.0
    assert contract.property_info.building.structure == "철근콘크리트조"
    assert contract.property_info.building.use == "아파트"


def test_rule_parser_outputs_nested_land_schema() -> None:
    contract = _parse_sample()
    dumped = contract.model_dump()

    assert "land" in dumped["property_info"]
    assert "land_type" not in dumped["property_info"]
    assert "land_area_m2" not in dumped["property_info"]
    assert dumped["property_info"]["land"] == {
        "land_type": "대",
        "land_area_m2": 84.0,
    }


def test_rule_parser_does_not_split_law_references_as_contract_articles() -> None:
    from pipeline.preprocessing.rule_parser import parse_contract_text

    text = SAMPLE_LAYOUT_TEXT.replace(
        "제13조(중개대상물확인․설명서 교부)\n"
        "개업공인중개사는 2023년 04월 19일 임대인과 임차인에게 교부한다.",
        "제13조(중개대상물확인․설명서 교부)\n"
        "개업공인중개사는 2023년 04월 19일 임대인과 임차인에게 교부한다. "
        "주택임대차보호법 제3조의6 제3항과 제6항은 계약 조항이 아니다.",
    )

    contract = parse_contract_text(mask_pii(text))

    assert "주택임대차보호법 제3조의6 제3항과 제6항" in (
        contract.general_terms.art13.text
    )
    assert contract.general_terms.art3.text.startswith("수리가 필요한 시설")


def test_rule_parser_extracts_money_and_articles() -> None:
    contract = _parse_sample()

    art1 = contract.general_terms.art1
    assert art1.text.startswith("위 부동산의 임대차에 관하여")
    assert art1.details.deposit == 20000000
    assert art1.details.down_payment == 2000000
    assert art1.details.balance.amount == 18000000
    assert art1.details.balance.date == "2023년 04월 19일"
    assert contract.general_terms.art13.details.issue_date == "2023년 04월 19일"
    assert contract.general_terms.art8.text.startswith("임차인은 계약갱신")


def test_rule_parser_splits_special_terms_and_excludes_pii() -> None:
    contract = _parse_sample()

    assert contract.special_terms == [
        "주택을 인도받은 임차인은 2023년 04월 19일까지 전입신고와 확정일자를 받기로 한다.",
        "임대인은 임차인의 보증 보험 가입을 위해 필요한 절차에 적극 협조한다.",
    ]
    dumped = contract.model_dump_json()
    assert "900101-1234567" not in dumped
    assert "010-1234-5678" not in dumped
    assert "test@example.com" not in dumped
    assert "개인주소" not in dumped
