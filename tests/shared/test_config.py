"""shared.config 단위 테스트.

``shared.config``는 import 시점에 환경변수를 검증하는 fail-fast 모듈이다.
tests/conftest.py가 모듈 로드 이전에 더미 기본값을 OS 환경변수로 주입
하므로 테스트 모듈 최상단에서 안전하게 import할 수 있다.

테스트 전략
-----------
모듈 reload(``importlib.reload`` / ``sys.modules.pop``) 대신 공개 API인
:func:`shared.config.load_settings`를 직접 호출한다. reload는 매번 새로운
``ConfigError`` 클래스 객체를 생성해 ``pytest.raises(ConfigError)``와의
동일성이 깨지기 때문이다. ``load_settings``는 현재 프로세스의 환경변수를
읽어 :class:`~shared.config.Settings` 인스턴스를 반환하므로,
``monkeypatch``로 env를 조작한 뒤 호출하면 원하는 시나리오를 격리 가능하다.
"""
from __future__ import annotations

import pytest

import shared.config as config_module
from shared.config import ConfigError, Settings, load_settings

_ENV_KEYS = (
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
    "DOCAI_LAYOUT_PROCESSOR_ID",
    "DOCAI_LAYOUT_PROCESSOR_VERSION",
)


def _apply_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    """관심 환경변수를 모두 제거한 뒤 주어진 env만 재주입한다."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


# ---------------------------------------------------------------------------
# 정상 로딩
# ---------------------------------------------------------------------------
def test_all_required_env_vars_load_successfully(
    monkeypatch: pytest.MonkeyPatch, env_defaults: dict[str, str]
) -> None:
    """모든 필수 환경변수가 주어지면 Settings가 정상 생성된다."""
    _apply_env(monkeypatch, env_defaults)
    s = load_settings()

    assert s.gcp_project_id == "test-project"
    assert s.gcp_location == "us-central1"
    assert s.cloud_sql_connection == "test-project:us-central1:test-db"
    assert s.db_user == "test-user"
    assert s.db_password == "test-pass"
    assert s.db_name == "test-db"
    assert s.gcs_bucket == "test-bucket"
    assert s.docai_location == "us"
    assert s.docai_processor_id == "test-processor"
    assert s.docai_layout_processor_id == "test-layout-processor"
    assert (
        s.docai_layout_processor_version
        == "pretrained-layout-parser-v1.5-2025-08-25"
    )


def test_load_settings_returns_settings_instance(
    monkeypatch: pytest.MonkeyPatch, env_defaults: dict[str, str]
) -> None:
    """load_settings는 Settings 타입 인스턴스를 반환한다."""
    _apply_env(monkeypatch, env_defaults)
    assert isinstance(load_settings(), Settings)


# ---------------------------------------------------------------------------
# 필수값 누락 → ConfigError
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "missing_key",
    [
        "GCP_PROJECT_ID",
        "GCP_LOCATION",
        "CLOUD_SQL_CONNECTION",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
        "GCS_BUCKET",
        "DOCAI_LOCATION",
        "DOCAI_PROCESSOR_ID",
        "DOCAI_LAYOUT_PROCESSOR_ID",
    ],
)
def test_missing_required_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
    env_defaults: dict[str, str],
    missing_key: str,
) -> None:
    """필수 환경변수 중 하나라도 누락되면 ConfigError가 발생한다.

    에러 메시지에 누락된 키 이름이 포함되는지도 함께 검증한다.
    """
    partial = {k: v for k, v in env_defaults.items() if k != missing_key}
    _apply_env(monkeypatch, partial)

    with pytest.raises(ConfigError) as exc_info:
        load_settings()

    assert missing_key in str(exc_info.value)
    assert "Missing required env var" in str(exc_info.value)


def test_config_error_wraps_validation_error(
    monkeypatch: pytest.MonkeyPatch, env_defaults: dict[str, str]
) -> None:
    """ConfigError는 pydantic ValidationError를 __cause__로 래핑한다."""
    from pydantic import ValidationError

    partial = {k: v for k, v in env_defaults.items() if k != "GCP_PROJECT_ID"}
    _apply_env(monkeypatch, partial)

    with pytest.raises(ConfigError) as exc_info:
        load_settings()

    assert isinstance(exc_info.value.__cause__, ValidationError)


# ---------------------------------------------------------------------------
# 선택값 기본 폴백
# ---------------------------------------------------------------------------
def test_optional_gemini_model_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, env_defaults: dict[str, str]
) -> None:
    """GEMINI_MODEL 미지정 시 Settings 기본값 'gemini-2.5-flash'로 폴백."""
    _apply_env(monkeypatch, env_defaults)  # GEMINI_MODEL 미포함
    s = load_settings()

    assert s.gemini_model == "gemini-2.5-flash"


def test_optional_gemini_model_override(
    monkeypatch: pytest.MonkeyPatch, env_defaults: dict[str, str]
) -> None:
    """GEMINI_MODEL이 주어지면 기본값을 덮어쓴다."""
    _apply_env(monkeypatch, {**env_defaults, "GEMINI_MODEL": "gemini-2.5-pro"})
    s = load_settings()

    assert s.gemini_model == "gemini-2.5-pro"


def test_optional_docai_layout_processor_version_override(
    monkeypatch: pytest.MonkeyPatch, env_defaults: dict[str, str]
) -> None:
    _apply_env(
        monkeypatch,
        {
            **env_defaults,
            "DOCAI_LAYOUT_PROCESSOR_VERSION": "custom-layout-version",
        },
    )
    s = load_settings()

    assert s.docai_layout_processor_version == "custom-layout-version"


# ---------------------------------------------------------------------------
# OS 환경변수 우선순위
# ---------------------------------------------------------------------------
def test_os_env_takes_precedence_over_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    env_defaults: dict[str, str],
    tmp_path,
) -> None:
    """OS 환경변수가 .env 파일보다 우선한다.

    임시 작업 디렉터리에 .env 파일을 작성해 ``BaseSettings``의 ``env_file``
    로딩을 유도한 뒤, 동일 키가 OS 환경변수에도 설정된 경우 OS 측 값이
    반영되는지 확인한다.
    """
    dotenv = tmp_path / ".env"
    dotenv.write_text("GCP_PROJECT_ID=dotenv-value\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    _apply_env(monkeypatch, {**env_defaults, "GCP_PROJECT_ID": "os-env-value"})
    s = load_settings()

    assert s.gcp_project_id == "os-env-value"


# ---------------------------------------------------------------------------
# re-export 상수 일관성
# ---------------------------------------------------------------------------
def test_reexported_constants_match_module_settings_instance() -> None:
    """모듈 레벨 상수와 import 시점에 고정된 settings 인스턴스 값이 일치한다.

    본 테스트는 monkeypatch를 쓰지 않는다. 테스트 대상은 ``shared.config``
    모듈이 최초 로드될 때 conftest의 기본값으로 채워진 상수들이 settings와
    동일한지이다.
    """
    assert config_module.GCP_PROJECT_ID == config_module.settings.gcp_project_id
    assert config_module.GCP_LOCATION == config_module.settings.gcp_location
    assert (
        config_module.CLOUD_SQL_CONNECTION == config_module.settings.cloud_sql_connection
    )
    assert config_module.DB_USER == config_module.settings.db_user
    assert config_module.DB_PASSWORD == config_module.settings.db_password
    assert config_module.DB_NAME == config_module.settings.db_name
    assert config_module.GCS_BUCKET == config_module.settings.gcs_bucket
    assert config_module.GEMINI_MODEL == config_module.settings.gemini_model
    assert config_module.DOCAI_LOCATION == config_module.settings.docai_location
    assert config_module.DOCAI_PROCESSOR_ID == config_module.settings.docai_processor_id
    assert (
        config_module.DOCAI_LAYOUT_PROCESSOR_ID
        == config_module.settings.docai_layout_processor_id
    )
    assert (
        config_module.DOCAI_LAYOUT_PROCESSOR_VERSION
        == config_module.settings.docai_layout_processor_version
    )


def test_config_error_is_runtime_error_subclass() -> None:
    """ConfigError는 RuntimeError를 상속한다."""
    assert issubclass(ConfigError, RuntimeError)
