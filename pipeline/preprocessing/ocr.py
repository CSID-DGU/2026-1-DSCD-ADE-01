"""Document AI Document OCR 래퍼.

PDF/이미지 바이트를 받아 평문 텍스트로 변환한다. Processor는 GCP 콘솔에서
미리 생성하고 ``DOCAI_LOCATION`` / ``DOCAI_PROCESSOR_ID`` 환경변수로
지정한다.

사용 예
-------
    >>> from pathlib import Path
    >>> from pipeline.preprocessing.ocr import extract_text
    >>> text = extract_text(Path("contract.pdf").read_bytes())
"""
from __future__ import annotations

from google.api_core.client_options import ClientOptions
from google.cloud import documentai

from shared.config import settings


class OCRError(RuntimeError):
    """Document AI 호출 중 발생한 모든 오류의 단일 타입."""


_client: documentai.DocumentProcessorServiceClient | None = None


def _get_client() -> documentai.DocumentProcessorServiceClient:
    """Document AI 클라이언트 싱글턴을 반환한다.

    리전별로 endpoint가 다르므로 ``DOCAI_LOCATION`` 값으로 endpoint를
    구성한다. 예: ``us-documentai.googleapis.com``.
    """
    global _client  # noqa: PLW0603
    if _client is None:
        endpoint = f"{settings.docai_location}-documentai.googleapis.com"
        _client = documentai.DocumentProcessorServiceClient(
            client_options=ClientOptions(api_endpoint=endpoint)
        )
    return _client


def _processor_path() -> str:
    """Processor의 전체 리소스 경로."""
    return (
        f"projects/{settings.gcp_project_id}"
        f"/locations/{settings.docai_location}"
        f"/processors/{settings.docai_processor_id}"
    )


def extract_text(pdf_bytes: bytes, *, mime_type: str = "application/pdf") -> str:
    """PDF/이미지 바이트로부터 평문 텍스트를 추출한다.

    Parameters
    ----------
    pdf_bytes:
        Document AI에 전송할 원본 바이트.
    mime_type:
        ``"application/pdf"`` (기본), ``"image/jpeg"``, ``"image/png"`` 등.

    Raises
    ------
    OCRError
        Document AI 호출 또는 응답 처리 중 예외 발생 시.
    """
    try:
        client = _get_client()
        request = documentai.ProcessRequest(
            name=_processor_path(),
            raw_document=documentai.RawDocument(
                content=pdf_bytes,
                mime_type=mime_type,
            ),
        )
        response = client.process_document(request=request)
    except Exception as exc:
        raise OCRError(str(exc)) from exc

    return response.document.text
