"""shared.llm.gemini_client 단위 테스트."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shared.llm.gemini_client import GeminiClient, LLMError, gemini_client


def _make_client() -> GeminiClient:
    """genai.Client 생성을 mock한 GeminiClient 인스턴스를 반환한다."""
    with patch("shared.llm.gemini_client.genai.Client"):
        client = GeminiClient()
    client._client = MagicMock()
    return client


def test_llm_error_is_runtime_error_subclass() -> None:
    assert issubclass(LLMError, RuntimeError)


def test_gemini_client_module_singleton_exists() -> None:
    assert isinstance(gemini_client, GeminiClient)


def test_generate_returns_response_text() -> None:
    """generate()가 response.text를 반환한다."""
    client = _make_client()
    mock_response = MagicMock()
    mock_response.text = "생성된 답변"
    client._client.models.generate_content.return_value = mock_response

    assert client.generate("질문입니다") == "생성된 답변"


def test_generate_uses_default_model() -> None:
    """model 인자를 생략하면 생성자의 기본 모델을 사용한다."""
    client = _make_client()
    client._default_model = "gemini-2.5-flash"
    mock_response = MagicMock()
    mock_response.text = "응답"
    client._client.models.generate_content.return_value = mock_response

    client.generate("질문")

    call_kwargs = client._client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash"


def test_generate_uses_overridden_model() -> None:
    """model 인자를 명시하면 기본 모델 대신 해당 모델을 사용한다."""
    client = _make_client()
    mock_response = MagicMock()
    mock_response.text = "응답"
    client._client.models.generate_content.return_value = mock_response

    client.generate("질문", model="gemini-2.5-pro")

    call_kwargs = client._client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-pro"


def test_generate_passes_contents() -> None:
    """generate()가 contents를 그대로 API에 전달한다."""
    client = _make_client()
    mock_response = MagicMock()
    mock_response.text = "응답"
    client._client.models.generate_content.return_value = mock_response

    client.generate("테스트 프롬프트")

    call_kwargs = client._client.models.generate_content.call_args.kwargs
    assert call_kwargs["contents"] == "테스트 프롬프트"


def test_generate_wraps_api_exception_as_llm_error() -> None:
    """API 호출 중 예외 발생 시 LLMError로 래핑한다."""
    client = _make_client()
    client._client.models.generate_content.side_effect = RuntimeError("API 오류")

    with pytest.raises(LLMError) as exc_info:
        client.generate("질문")

    assert "API 오류" in str(exc_info.value)


def test_generate_llm_error_has_cause() -> None:
    """LLMError는 원본 예외를 __cause__로 보존한다."""
    client = _make_client()
    original = RuntimeError("원본 오류")
    client._client.models.generate_content.side_effect = original

    with pytest.raises(LLMError) as exc_info:
        client.generate("질문")

    assert exc_info.value.__cause__ is original


def test_generate_passes_system_instruction() -> None:
    """system_instruction이 주어지면 GenerateContentConfig에 담아 전달한다."""
    from google.genai import types

    client = _make_client()
    mock_response = MagicMock()
    mock_response.text = "응답"
    client._client.models.generate_content.return_value = mock_response

    client.generate("질문", system_instruction="당신은 법률 전문가입니다.")

    call_kwargs = client._client.models.generate_content.call_args.kwargs
    config = call_kwargs["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.system_instruction == "당신은 법률 전문가입니다."


def test_generate_no_config_when_no_options() -> None:
    """system_instruction과 response_schema 모두 생략 시 config=None으로 호출한다."""
    client = _make_client()
    mock_response = MagicMock()
    mock_response.text = "응답"
    client._client.models.generate_content.return_value = mock_response

    client.generate("질문")

    call_kwargs = client._client.models.generate_content.call_args.kwargs
    assert call_kwargs["config"] is None


def test_generate_returns_parsed_when_response_schema_given() -> None:
    """response_schema 전달 시 response.parsed를 반환한다."""
    from pydantic import BaseModel

    class Summary(BaseModel):
        title: str
        points: list[str]

    client = _make_client()
    expected = Summary(title="계약서 요약", points=["항목1", "항목2"])
    mock_response = MagicMock()
    mock_response.parsed = expected
    client._client.models.generate_content.return_value = mock_response

    result = client.generate("요약해줘.", response_schema=Summary)

    assert result is expected


def test_generate_sets_json_mime_type_when_response_schema_given() -> None:
    """response_schema 전달 시 GenerateContentConfig에 response_mime_type='application/json'이 설정된다."""
    from google.genai import types
    from pydantic import BaseModel

    class Tag(BaseModel):
        label: str

    client = _make_client()
    mock_response = MagicMock()
    mock_response.parsed = Tag(label="계약")
    client._client.models.generate_content.return_value = mock_response

    client.generate("분류해줘.", response_schema=Tag)

    call_kwargs = client._client.models.generate_content.call_args.kwargs
    config = call_kwargs["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.response_mime_type == "application/json"
    assert config.response_schema is Tag


def test_generate_returns_text_when_no_response_schema() -> None:
    """response_schema 미전달 시 response.text를 반환한다."""
    client = _make_client()
    mock_response = MagicMock()
    mock_response.text = "텍스트 응답"
    client._client.models.generate_content.return_value = mock_response

    result = client.generate("질문")

    assert result == "텍스트 응답"


def test_generate_accepts_multimodal_contents_gcs() -> None:
    """contents에 GCS URI Part를 혼합한 리스트를 전달할 수 있다."""
    from google.genai import types

    client = _make_client()
    mock_response = MagicMock()
    mock_response.text = "분석 결과"
    client._client.models.generate_content.return_value = mock_response

    part = types.Part.from_uri(
        file_uri="gs://test-bucket/contract.pdf", mime_type="application/pdf"
    )
    contents = ["이 계약서를 요약해.", part]

    result = client.generate(contents)

    call_kwargs = client._client.models.generate_content.call_args.kwargs
    assert call_kwargs["contents"] is contents
    assert result == "분석 결과"


def test_part_from_path_reads_local_file(tmp_path) -> None:
    """part_from_path()가 로컬 파일을 읽어 types.Part를 반환한다."""
    from google.genai import types

    local_file = tmp_path / "sample.pdf"
    local_file.write_bytes(b"%PDF-sample")

    part = GeminiClient.part_from_path(local_file, mime_type="application/pdf")

    assert isinstance(part, types.Part)


def test_generate_accepts_local_file_part(tmp_path) -> None:
    """part_from_path()로 만든 Part를 generate()에 전달할 수 있다."""
    client = _make_client()
    mock_response = MagicMock()
    mock_response.text = "요약 결과"
    client._client.models.generate_content.return_value = mock_response

    local_file = tmp_path / "contract.pdf"
    local_file.write_bytes(b"%PDF-sample")
    part = GeminiClient.part_from_path(local_file, mime_type="application/pdf")
    contents = ["요약해줘.", part]

    result = client.generate(contents)

    call_kwargs = client._client.models.generate_content.call_args.kwargs
    assert call_kwargs["contents"] is contents
    assert result == "요약 결과"
