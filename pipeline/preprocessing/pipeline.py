"""표준임대차계약서 PDF → LeaseContract 전처리 파이프라인.

흐름
----
1. ``pdf_uri``를 로컬 경로 또는 ``gs://`` URI로 해석해 PDF 바이트를 읽는다.
2. Document AI Layout Parser로 Markdown 유사 chunk 텍스트를 추출한다.
3. 정규식 PII 마스킹을 적용한다.
4. 표준계약서 전용 룰 파서로 ``LeaseContract`` JSON을 생성한다.
5. 옵션으로 결과 JSON을 GCS에 저장한다.
6. ``LeaseContract`` 객체를 반환한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline.preprocessing import layout
from pipeline.preprocessing.masking import mask_pii
from pipeline.preprocessing.rule_parser import RuleParseError, parse_contract_text
from pipeline.preprocessing.schema import LeaseContract


class PreprocessingError(RuntimeError):
    """전처리 파이프라인 실행 중 발생한 모든 오류의 단일 타입."""


# ---------------------------------------------------------------------------
# PDF 로딩
# ---------------------------------------------------------------------------
_GCS_URI_PATTERN = re.compile(r"^gs://(?P<bucket>[^/]+)/(?P<key>.+)$")


def _load_pdf(pdf_uri: str) -> tuple[bytes, str]:
    """``pdf_uri``에서 바이트와 stem(확장자 제외 파일명)을 읽는다."""
    gcs_match = _GCS_URI_PATTERN.match(pdf_uri)
    if gcs_match:
        bucket = gcs_match.group("bucket")
        key = gcs_match.group("key")
        from shared.storage.gcs_client import get_gcs_client

        client = get_gcs_client()
        if client.bucket_name != bucket:
            raise PreprocessingError(
                f"GCS URI bucket '{bucket}'이 설정된 bucket "
                f"'{client.bucket_name}'과 다릅니다."
            )
        return client.download_bytes(key), Path(key).stem

    path = Path(pdf_uri)
    return path.read_bytes(), path.stem


# ---------------------------------------------------------------------------
# GCS 저장
# ---------------------------------------------------------------------------
def _save_to_gcs(contract: LeaseContract, prefix: str, stem: str) -> str:
    """결과 JSON을 ``<prefix><stem>.json``으로 GCS에 업로드한다."""
    from shared.storage.gcs_client import get_gcs_client

    blob_name = f"{prefix}{stem}.json"
    payload = contract.model_dump_json(indent=2).encode("utf-8")
    get_gcs_client().upload_bytes(blob_name, payload, content_type="application/json")
    return blob_name


def _parse_contract_bytes(pdf_bytes: bytes) -> LeaseContract:
    try:
        layout_text = layout.extract_layout_text(pdf_bytes)
        return parse_contract_text(mask_pii(layout_text))
    except (layout.LayoutError, RuleParseError) as error:
        raise PreprocessingError(str(error)) from error


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def parse_lease_contract(
    pdf_uri: str,
    *,
    output_gcs_prefix: str | None = "preprocessing/",
    client: object | None = None,
) -> LeaseContract:
    """표준임대차계약서 PDF를 ``LeaseContract``로 파싱한다.

    Parameters
    ----------
    pdf_uri:
        ``"gs://<bucket>/<key>.pdf"`` 또는 로컬 파일 경로.
    output_gcs_prefix:
        지정 시 결과 JSON을 ``<prefix><source_stem>.json`` 으로 GCS에 저장.
        ``None``이면 저장하지 않는다.
    client:
        이전 Gemini 기반 API 호환용 인자. 새 룰 기반 경로에서는 사용하지 않는다.

    Returns
    -------
    LeaseContract
        검증된 Pydantic 객체.

    Raises
    ------
    PreprocessingError
        PDF 로딩, Layout Parser 호출, 룰 파싱 중 어느 단계든 실패 시.
    """
    del client
    pdf_bytes, stem = _load_pdf(pdf_uri)

    contract = _parse_contract_bytes(pdf_bytes)

    if output_gcs_prefix is not None:
        _save_to_gcs(contract, output_gcs_prefix, stem)

    return contract


def parse_lease_contract_bytes(
    pdf_bytes: bytes,
    *,
    client: object | None = None,
) -> LeaseContract:
    """PDF bytes를 ``LeaseContract``로 파싱한다.

    FastAPI 파일 업로드처럼 이미 메모리에 올라온 PDF를 처리할 때 사용한다.
    """
    del client
    return _parse_contract_bytes(pdf_bytes)


def parse_lease_contract_from_text(
    layout_text: str,
    *,
    client: object | None = None,
) -> LeaseContract:
    """Layout Parser 텍스트로부터 LeaseContract만 추출한다.

    PDF 로딩과 Document AI 호출을 건너뛰고 룰 파서만 확인할 때 쓴다.
    """
    del client
    try:
        return parse_contract_text(mask_pii(layout_text))
    except RuleParseError as error:
        raise PreprocessingError(str(error)) from error


# ---------------------------------------------------------------------------
# 디버깅용: 결과를 JSON 문자열로 직렬화 (model_dump_json 래퍼)
# ---------------------------------------------------------------------------
def contract_to_json(contract: LeaseContract, *, indent: int = 2) -> str:
    """LeaseContract를 ensure_ascii=False JSON 문자열로 직렬화한다."""
    return json.dumps(
        contract.model_dump(),
        ensure_ascii=False,
        indent=indent,
    )
