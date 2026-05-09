"""Document AI Layout Parser 래퍼 테스트."""
from __future__ import annotations

import pytest


class _FakeChunk:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeClient:
    last_request = None
    last_name_args = None

    def processor_version_path(
        self, project_id: str, location: str, processor_id: str, version: str
    ) -> str:
        self.__class__.last_name_args = (project_id, location, processor_id, version)
        return f"{project_id}/{location}/{processor_id}/{version}"

    def process_document(self, request):
        self.__class__.last_request = request
        chunks = [_FakeChunk("# 제목"), _FakeChunk(""), _FakeChunk("| 표 | 값 |")]
        document = type("Document", (), {})()
        document.chunked_document = type("Chunked", (), {"chunks": chunks})()
        return type("Result", (), {"document": document})()


class _FakeDocumentAi:
    class RawDocument:
        def __init__(self, content: bytes, mime_type: str) -> None:
            self.content = content
            self.mime_type = mime_type

    class ProcessOptions:
        class LayoutConfig:
            class ChunkingConfig:
                def __init__(
                    self, chunk_size: int, include_ancestor_headings: bool
                ) -> None:
                    self.chunk_size = chunk_size
                    self.include_ancestor_headings = include_ancestor_headings

            def __init__(
                self,
                enable_table_annotation: bool,
                enable_image_annotation: bool,
                chunking_config,
            ) -> None:
                self.enable_table_annotation = enable_table_annotation
                self.enable_image_annotation = enable_image_annotation
                self.chunking_config = chunking_config

        def __init__(self, layout_config) -> None:
            self.layout_config = layout_config

    class ProcessRequest:
        def __init__(self, name: str, raw_document, process_options) -> None:
            self.name = name
            self.raw_document = raw_document
            self.process_options = process_options

    DocumentProcessorServiceClient = _FakeClient


def test_extract_layout_text_joins_non_empty_chunks(monkeypatch) -> None:
    from pipeline.preprocessing import layout

    monkeypatch.setattr(layout, "_get_documentai", lambda: _FakeDocumentAi)

    text = layout.extract_layout_text(b"pdf-bytes")

    assert text == "# 제목\n\n| 표 | 값 |"


def test_extract_layout_text_uses_layout_processor_version(monkeypatch) -> None:
    from pipeline.preprocessing import layout

    monkeypatch.setattr(layout, "_get_documentai", lambda: _FakeDocumentAi)

    layout.extract_layout_text(b"pdf-bytes")

    assert _FakeClient.last_name_args == (
        "test-project",
        "us",
        "test-layout-processor",
        "pretrained-layout-parser-v1.5-2025-08-25",
    )
    assert _FakeClient.last_request.raw_document.content == b"pdf-bytes"
    config = _FakeClient.last_request.process_options.layout_config
    assert config.enable_table_annotation is True
    assert config.enable_image_annotation is True
    assert config.chunking_config.chunk_size == 1024
    assert config.chunking_config.include_ancestor_headings is True


def test_extract_layout_text_raises_when_chunks_empty(monkeypatch) -> None:
    from pipeline.preprocessing import layout

    class EmptyClient(_FakeClient):
        def process_document(self, request):
            document = type("Document", (), {})()
            document.chunked_document = type("Chunked", (), {"chunks": []})()
            return type("Result", (), {"document": document})()

    fake_docai = type(
        "FakeDocumentAi",
        (_FakeDocumentAi,),
        {"DocumentProcessorServiceClient": EmptyClient},
    )
    monkeypatch.setattr(layout, "_get_documentai", lambda: fake_docai)

    with pytest.raises(layout.LayoutError):
        layout.extract_layout_text(b"pdf-bytes")
