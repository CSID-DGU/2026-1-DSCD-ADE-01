"""표준임대차계약서 전처리 파이프라인 단위 테스트."""
from __future__ import annotations

from tests.preprocessing.test_rule_parser import SAMPLE_LAYOUT_TEXT


def test_parse_lease_contract_from_text_uses_rule_parser() -> None:
    from pipeline.preprocessing.pipeline import parse_lease_contract_from_text

    contract = parse_lease_contract_from_text(SAMPLE_LAYOUT_TEXT)

    assert contract.lease_type == "전세"
    assert contract.property_info.address == "서울특별시 마포구 아현동 700"


def test_parse_lease_contract_uses_layout_mask_and_rule_parser(
    monkeypatch, tmp_path
) -> None:
    from pipeline.preprocessing import pipeline

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"pdf")

    called = {}

    def fake_extract_layout_text(pdf_bytes: bytes) -> str:
        called["pdf_bytes"] = pdf_bytes
        return SAMPLE_LAYOUT_TEXT

    monkeypatch.setattr(pipeline.layout, "extract_layout_text", fake_extract_layout_text)

    contract = pipeline.parse_lease_contract(str(pdf_path), output_gcs_prefix=None)

    assert called["pdf_bytes"] == b"pdf"
    assert contract.lease_type == "전세"
    assert contract.general_terms.art1.details.deposit == 20000000


def test_parse_lease_contract_saves_to_gcs_when_prefix_given(
    monkeypatch, tmp_path
) -> None:
    from pipeline.preprocessing import pipeline

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"pdf")
    uploaded = {}

    monkeypatch.setattr(
        pipeline.layout,
        "extract_layout_text",
        lambda pdf_bytes: SAMPLE_LAYOUT_TEXT,
    )

    def fake_save_to_gcs(contract, prefix: str, stem: str) -> str:
        uploaded["prefix"] = prefix
        uploaded["stem"] = stem
        uploaded["lease_type"] = contract.lease_type
        return f"{prefix}{stem}.json"

    monkeypatch.setattr(pipeline, "_save_to_gcs", fake_save_to_gcs)

    pipeline.parse_lease_contract(str(pdf_path), output_gcs_prefix="out/")

    assert uploaded == {
        "prefix": "out/",
        "stem": "sample",
        "lease_type": "전세",
    }
