"""표준임대차계약서 PDF → LeaseContract 전처리 파이프라인.

흐름
----
1. ``pdf_uri``를 로컬 경로 또는 ``gs://`` URI로 해석해 PDF 바이트를 읽는다.
2. Document AI Document OCR로 평문 텍스트를 추출한다.
3. 정규식 PII 마스킹을 적용한다.
4. Vertex Gemini structured output으로 ``LeaseContract`` JSON을 생성한다.
5. 옵션으로 결과 JSON을 GCS에 저장한다.
6. ``LeaseContract`` 객체를 반환한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pipeline.preprocessing import ocr
from pipeline.preprocessing.masking import mask_pii
from pipeline.preprocessing.prompts import SYSTEM_PROMPT, build_user_prompt
from pipeline.preprocessing.schema import LeaseContract
from shared.llm.gemini_client import GeminiClient, LLMError, gemini_client
from shared.storage.gcs_client import get_gcs_client


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
# Gemini 응답 정규화 (query_expansion과 같은 방식)
# ---------------------------------------------------------------------------
def _strip_json_code_fence(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(
        r"```(?:json|JSON)?\s*(.*?)\s*```",
        stripped,
        flags=re.DOTALL,
    )
    if fence:
        return fence.group(1).strip()
    return stripped


def _extract_json_object(text: str) -> str:
    stripped = _strip_json_code_fence(text)
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return stripped
    return stripped[start : end + 1].strip()


def _parse_contract_result(result: Any) -> LeaseContract:
    if isinstance(result, LeaseContract):
        return result
    if isinstance(result, dict):
        return LeaseContract.model_validate(result)
    if isinstance(result, str):
        return LeaseContract.model_validate_json(_extract_json_object(result))
    raise PreprocessingError(
        f"지원하지 않는 Gemini 응답 타입입니다: {type(result).__name__}"
    )


def _extract_with_llm(masked_text: str, *, client: GeminiClient) -> LeaseContract:
    user_prompt = build_user_prompt(masked_text)
    try:
        result = client.generate(
            contents=user_prompt,
            system_instruction=SYSTEM_PROMPT,
            response_schema=LeaseContract,
        )
    except LLMError as error:
        raise PreprocessingError(f"Gemini 호출 실패: {error}") from error

    try:
        return _parse_contract_result(result)
    except ValidationError as error:
        raise PreprocessingError(
            f"LeaseContract 검증 실패: {error}"
        ) from error


# ---------------------------------------------------------------------------
# GCS 저장
# ---------------------------------------------------------------------------
def _save_to_gcs(contract: LeaseContract, prefix: str, stem: str) -> str:
    """결과 JSON을 ``<prefix><stem>.json``으로 GCS에 업로드한다."""
    blob_name = f"{prefix}{stem}.json"
    payload = contract.model_dump_json(indent=2).encode("utf-8")
    get_gcs_client().upload_bytes(blob_name, payload, content_type="application/json")
    return blob_name


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def parse_lease_contract(
    pdf_uri: str,
    *,
    output_gcs_prefix: str | None = "preprocessing/",
    client: GeminiClient | None = None,
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
        주입할 Gemini 클라이언트. 기본은 모듈 싱글턴 ``gemini_client``.

    Returns
    -------
    LeaseContract
        검증된 Pydantic 객체.

    Raises
    ------
    PreprocessingError
        PDF 로딩, OCR, LLM 호출, 스키마 검증 중 어느 단계든 실패 시.
    """
    pdf_bytes, stem = _load_pdf(pdf_uri)

    raw_text = ocr.extract_text(pdf_bytes)
    masked_text = mask_pii(raw_text)

    contract = _extract_with_llm(masked_text, client=client or gemini_client)

    if output_gcs_prefix is not None:
        _save_to_gcs(contract, output_gcs_prefix, stem)

    return contract


def parse_lease_contract_from_text(
    masked_text: str,
    *,
    client: GeminiClient | None = None,
) -> LeaseContract:
    """이미 OCR·마스킹된 텍스트로부터 LeaseContract만 추출한다.

    OCR/마스킹을 따로 수행한 뒤 LLM 단계만 재사용하고 싶을 때 쓴다.
    """
    return _extract_with_llm(masked_text, client=client or gemini_client)


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
