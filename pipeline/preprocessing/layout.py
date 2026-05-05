"""Document AI Layout Parser 래퍼."""
from __future__ import annotations

from shared.config import settings


class LayoutError(RuntimeError):
    """Layout Parser 처리 중 발생한 오류."""


def _get_documentai():
    from google.cloud import documentai

    return documentai


def extract_layout_text(
    pdf_bytes: bytes,
    *,
    mime_type: str = "application/pdf",
) -> str:
    """PDF 바이트를 Layout Parser chunk Markdown 텍스트로 변환한다."""
    documentai = _get_documentai()
    client = documentai.DocumentProcessorServiceClient()
    name = client.processor_version_path(
        settings.gcp_project_id,
        settings.docai_location,
        settings.docai_layout_processor_id,
        settings.docai_layout_processor_version,
    )

    process_options = documentai.ProcessOptions(
        layout_config=documentai.ProcessOptions.LayoutConfig(
            enable_table_annotation=True,
            enable_image_annotation=True,
            chunking_config=documentai.ProcessOptions.LayoutConfig.ChunkingConfig(
                chunk_size=1024,
                include_ancestor_headings=True,
            ),
        ),
    )
    request = documentai.ProcessRequest(
        name=name,
        raw_document=documentai.RawDocument(
            content=pdf_bytes,
            mime_type=mime_type,
        ),
        process_options=process_options,
    )

    try:
        result = client.process_document(request=request)
    except Exception as exc:
        raise LayoutError(str(exc)) from exc

    chunks = getattr(result.document.chunked_document, "chunks", [])
    text = "\n\n".join(chunk.content.strip() for chunk in chunks if chunk.content.strip())
    if not text:
        raise LayoutError("Layout Parser가 빈 chunk를 반환했습니다.")
    return text
