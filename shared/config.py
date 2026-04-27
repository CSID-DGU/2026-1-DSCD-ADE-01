"""공통 환경설정 모듈.

프로젝트 전반에서 사용하는 환경변수를 pydantic-settings의 ``BaseSettings``
기반으로 정의·검증·노출한다.

정책
----
- **Fail-Fast at Import**: 본 모듈이 최초로 import되는 시점에 단 1회
  ``.env`` 로딩 및 필수값 검증을 수행하며, 실패 시 즉시 :class:`ConfigError`를
  raise하여 애플리케이션 부팅을 중단한다. 런타임 중 재로딩은 지원하지 않는다.
- **OS 우선**: OS 환경변수가 ``.env`` 파일보다 우선 적용된다
  (pydantic-settings 기본 동작). 배포 환경(Cloud Run 등)에서 주입된 값이
  로컬 ``.env``에 의해 덮어써지는 사고를 방지한다.
- **에러 타입 통일**: 모든 설정 관련 오류는 단일 커스텀 예외
  :class:`ConfigError`로 통일한다. pydantic의 ``ValidationError``는 포착
  하여 :class:`ConfigError`로 래핑된다.
- **비포함**: DB 연결 객체, GCS 클라이언트, Gemini 클라이언트 등
  인프라 클라이언트 인스턴스는 본 모듈에서 생성하지 않는다. 각 래퍼 모듈
  (``shared/db/``, ``shared/storage/``, ``shared/llm/``)이 본 모듈에서
  설정값만 참조하여 자체적으로 클라이언트를 초기화한다.

사용 예
-------
권장: :data:`settings` 인스턴스를 직접 참조한다.

    >>> from shared.config import settings
    >>> settings.gcp_project_id
    'dcsd-ade'

편의: 모듈 레벨 상수로 re-export된 값을 사용해도 된다.

    >>> from shared.config import GCP_PROJECT_ID, GEMINI_MODEL
    >>> GCP_PROJECT_ID
    'dcsd-ade'
"""
from __future__ import annotations

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """설정 로딩·검증 과정에서 발생한 모든 오류의 단일 타입.

    필수 환경변수 누락, 타입 변환 실패, 유효하지 않은 값 형식 등 모든
    설정 관련 예외는 본 클래스로 통일한다.
    """


class Settings(BaseSettings):
    """프로젝트 공통 환경 설정.

    모든 필드는 대응하는 환경변수(대소문자 무시)로부터 주입된다. 필수
    필드가 누락되면 인스턴스 생성 시 ``ValidationError``가 발생하며, 이는
    모듈 로딩 단계에서 :class:`ConfigError`로 래핑된다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- GCP ----
    gcp_project_id: str
    gcp_location: str

    # ---- Cloud SQL (pgvector) ----
    cloud_sql_connection: str
    db_user: str
    db_password: str
    db_name: str

    # ---- Cloud Storage ----
    gcs_bucket: str

    # ---- Models (선택값, 기본값 존재) ----
    gemini_model: str = "gemini-2.5-flash"

    # ---- Document AI (Document OCR processor) ----
    docai_location: str
    docai_processor_id: str


def _format_validation_errors(exc: ValidationError) -> str:
    """Pydantic ValidationError를 사람이 읽기 쉬운 메시지로 변환.

    각 오류에 대해 환경변수 이름(대문자)과 원인을 명시한다.
    """
    messages: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) if err["loc"] else "<unknown>"
        env_name = loc.upper()
        err_type = err.get("type", "")
        if err_type == "missing":
            messages.append(f"Missing required env var '{env_name}'")
        else:
            detail = err.get("msg", "invalid value")
            messages.append(f"Invalid value for '{env_name}': {detail}")
    return "; ".join(messages) if messages else str(exc)


def load_settings() -> Settings:
    """Settings 인스턴스를 생성하며 ValidationError를 ConfigError로 래핑.

    일반 사용에서는 본 함수를 직접 호출할 필요가 없다. 모듈 import 시점에
    1회 실행된 결과가 :data:`settings`에 담겨있기 때문이다. 단위 테스트에서
    특정 환경변수 조합에 대한 동작을 검증하고자 할 때 공개 API로 사용할
    수 있도록 underscore를 붙이지 않았다.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise ConfigError(_format_validation_errors(exc)) from exc


# ---------------------------------------------------------------------------
# Fail-fast: 모듈 import 시점에 1회 로드 및 검증.
# ---------------------------------------------------------------------------
settings: Settings = load_settings()

# ---------------------------------------------------------------------------
# 모듈 레벨 re-export (편의용 상수).
# 대규모 리팩터링 없이 ``from shared.config import GCP_PROJECT_ID`` 형태로
# 직접 사용 가능하게 한다. 동적 변경은 발생하지 않는다(모듈 import 시 고정).
# ---------------------------------------------------------------------------
GCP_PROJECT_ID: str = settings.gcp_project_id
GCP_LOCATION: str = settings.gcp_location
CLOUD_SQL_CONNECTION: str = settings.cloud_sql_connection
DB_USER: str = settings.db_user
DB_PASSWORD: str = settings.db_password
DB_NAME: str = settings.db_name
GCS_BUCKET: str = settings.gcs_bucket
GEMINI_MODEL: str = settings.gemini_model
DOCAI_LOCATION: str = settings.docai_location
DOCAI_PROCESSOR_ID: str = settings.docai_processor_id


__all__ = [
    "ConfigError",
    "Settings",
    "load_settings",
    "settings",
    "GCP_PROJECT_ID",
    "GCP_LOCATION",
    "CLOUD_SQL_CONNECTION",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "GCS_BUCKET",
    "GEMINI_MODEL",
    "DOCAI_LOCATION",
    "DOCAI_PROCESSOR_ID",
]
