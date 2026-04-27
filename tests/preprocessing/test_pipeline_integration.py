"""표준임대차계약서 전처리 파이프라인 통합 테스트.

실제 Document AI / Vertex Gemini를 호출하므로 평소 ``pytest``에서는
``integration`` 마커가 걸려 자동 실행되지 않는다. 다음과 같이 명시적으로
실행한다::

    pytest tests/preprocessing/test_pipeline_integration.py -m integration -v -s

선행 조건
---------
- ``.env``에 ``DOCAI_LOCATION``, ``DOCAI_PROCESSOR_ID``, ``GCP_PROJECT_ID`` 등이
  실제 값으로 채워져 있을 것.
- ``gcloud auth application-default login`` 등으로 ADC 인증이 완료되어 있을 것.
- 입력 PDF: ``docs/주택임대차_표준계약서 - 13.pdf``.
"""
from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


SAMPLE_PDF = Path("docs/주택임대차_표준계약서 - 13.pdf")


@pytest.fixture(scope="module")
def parsed_contract():
    """모듈 내 모든 케이스가 같은 파싱 결과를 공유하도록 한 번만 호출한다."""
    from pipeline.preprocessing import parse_lease_contract

    assert SAMPLE_PDF.exists(), f"샘플 PDF가 없습니다: {SAMPLE_PDF}"

    return parse_lease_contract(
        str(SAMPLE_PDF),
        output_gcs_prefix=None,  # 통합 테스트에서는 GCS 저장 비활성화
    )


def test_lease_type_is_valid_literal(parsed_contract) -> None:
    assert parsed_contract.lease_type in {"보증금있는월세", "전세", "월세"}


def test_property_info_address_is_present(parsed_contract) -> None:
    info = parsed_contract.property_info
    assert info is not None
    assert info.address is not None
    assert info.address.strip() != ""


def test_general_terms_articles_present(parsed_contract) -> None:
    """art1, art12, art13 등 핵심 조항 본문이 추출되었는지 확인."""
    terms = parsed_contract.general_terms
    assert terms is not None
    for art_name in ("art1", "art12", "art13"):
        art = getattr(terms, art_name)
        assert art is not None, f"{art_name}이 없습니다"
        assert art.text is not None and art.text.strip() != "", (
            f"{art_name}.text가 비어 있습니다"
        )


def test_art1_deposit_is_positive(parsed_contract) -> None:
    """제1조의 보증금 금액이 정수로 추출되는지 확인."""
    details = parsed_contract.general_terms.art1.details
    assert details is not None
    assert details.deposit is not None
    assert details.deposit > 0


def test_art13_issue_date_present(parsed_contract) -> None:
    """제13조의 계약서 작성일이 추출되었는지 확인."""
    details = parsed_contract.general_terms.art13.details
    assert details is not None
    assert details.issue_date is not None
    assert details.issue_date.strip() != ""


def test_dump_full_json_for_inspection(parsed_contract, tmp_path) -> None:
    """디버깅·시연용으로 전체 결과 JSON을 임시 경로에 저장하고 콘솔에 출력."""
    from pipeline.preprocessing import contract_to_json

    out_path = tmp_path / "lease_contract.json"
    out_path.write_text(contract_to_json(parsed_contract), encoding="utf-8")

    print("\n[integration] full contract JSON:\n")
    print(out_path.read_text(encoding="utf-8"))
    assert out_path.exists() and out_path.stat().st_size > 0
