"""Vertex AI Gemini 공통 래퍼.

사용 예
-------
텍스트 입력:
    >>> from shared.llm.gemini_client import gemini_client
    >>> answer = gemini_client.generate("안녕하세요!")

멀티모달 입력 — 로컬 파일:
    >>> from pathlib import Path
    >>> part = GeminiClient.part_from_path(Path("contract.pdf"), mime_type="application/pdf")
    >>> answer = gemini_client.generate(["이 계약서를 요약해.", part])

멀티모달 입력 — GCS 파일:
    >>> from google.genai import types
    >>> part = types.Part.from_uri(file_uri="gs://bucket/contract.pdf", mime_type="application/pdf")
    >>> answer = gemini_client.generate(["이 계약서를 요약해.", part])

구조화 출력 (Pydantic 스키마):
    >>> from pydantic import BaseModel
    >>> class Summary(BaseModel):
    ...     title: str
    ...     points: list[str]
    >>> result = gemini_client.generate("요약해줘.", response_schema=Summary)
    >>> isinstance(result, Summary)
    True
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from google import genai

from shared.config import settings


class LLMError(RuntimeError):
    """Gemini API 호출 중 발생한 모든 오류의 단일 타입."""


class GeminiClient:
    """Vertex AI Gemini API 호출 래퍼.

    vertexai=True 고정. ADC(Application Default Credentials)로 인증한다.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str | None = None,
        model: str | None = None,
    ) -> None:
        self._project = project or settings.gcp_project_id
        self._location = location or settings.gcp_location
        self._default_model = model or settings.gemini_model
        self._client = genai.Client(
            vertexai=True,
            project=self._project,
            location=self._location,
        )

    @staticmethod
    def part_from_path(path: str | Path, mime_type: str) -> Any:
        """로컬 파일을 읽어 ``types.Part``로 변환한다.

        Parameters
        ----------
        path:
            로컬 파일 경로 (``str`` 또는 ``pathlib.Path``).
        mime_type:
            파일 MIME 타입. 예: ``"application/pdf"``, ``"image/jpeg"``,
            ``"text/csv"``.
        """
        from google.genai import types

        return types.Part.from_bytes(
            data=Path(path).read_bytes(),
            mime_type=mime_type,
        )

    def generate(
        self,
        contents: str | list,
        *,
        model: str | None = None,
        system_instruction: str | None = None,
        response_schema: type | None = None,
    ) -> Any:
        """텍스트 또는 파일을 입력받아 생성 결과를 반환한다.

        Parameters
        ----------
        contents:
            프롬프트 문자열, 또는 문자열과 ``types.Part``를 혼합한 리스트.
            로컬 파일은 :meth:`part_from_path` 로, GCS 파일은
            ``types.Part.from_uri()`` 로 변환하여 전달한다.
        model:
            사용할 모델 ID. None이면 생성자의 기본 모델 사용.
        system_instruction:
            시스템 프롬프트. None이면 전달하지 않음.
        response_schema:
            Pydantic ``BaseModel`` 서브클래스. 전달 시 구조화 JSON 출력을
            요청하고 ``response.parsed`` (Pydantic 인스턴스)를 반환한다.
            None이면 ``response.text`` (str)를 반환한다.

        Raises
        ------
        LLMError
            API 호출 중 예외 발생 시.
        """
        from google.genai import types

        config_kwargs: dict[str, Any] = {}
        if system_instruction is not None:
            config_kwargs["system_instruction"] = system_instruction
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        try:
            response = self._client.models.generate_content(
                model=model or self._default_model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            raise LLMError(str(exc)) from exc

        return response.parsed if response_schema is not None else response.text


gemini_client: GeminiClient = GeminiClient()
