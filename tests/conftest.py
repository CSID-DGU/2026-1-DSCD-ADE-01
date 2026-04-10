"""테스트 공통 fixture 및 초기 환경 설정.

``shared.config``는 import 시점에 필수 환경변수를 검증하며 실패 시
``ConfigError``를 raise한다(fail-fast 정책). 테스트 모듈이 로드될 때
환경변수가 없으면 테스트 수집 단계에서 ImportError가 발생하므로, 본
conftest.py는 **테스트 모듈이 import되기 이전**에 더미 환경변수를 OS에
주입한다.

개별 테스트에서 값을 변경하려는 경우 :func:`env_defaults` fixture와
``monkeypatch.setenv`` / ``monkeypatch.delenv``를 조합해 격리된 환경을
구성한 뒤 ``importlib.reload(shared.config)``로 재로딩한다.
"""
from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# 테스트 수집 이전에 OS 환경변수 기본값 주입.
# os.environ.setdefault를 사용하여 외부에서 이미 값이 설정된 경우에는
# 덮어쓰지 않는다(로컬 개발자가 실제 값으로 테스트하려는 시나리오 보존).
# ---------------------------------------------------------------------------
_REQUIRED_ENV_DEFAULTS: dict[str, str] = {
    "GCP_PROJECT_ID": "test-project",
    "GCP_LOCATION": "us-central1",
    "CLOUD_SQL_CONNECTION": "test-project:us-central1:test-db",
    "DB_USER": "test-user",
    "DB_PASSWORD": "test-pass",
    "DB_NAME": "test-db",
    "GCS_BUCKET": "test-bucket",
}

for _key, _value in _REQUIRED_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture
def env_defaults() -> dict[str, str]:
    """필수 환경변수의 더미 기본값을 반환.

    conftest.py 모듈 로드 시 이미 ``os.environ``에 주입되어 있으므로 본
    fixture는 그 내용을 dict로 노출한다. 테스트는 이를 바탕으로 부분 주입
    시나리오(일부 값 제거 등)를 구성할 수 있다.
    """
    return dict(_REQUIRED_ENV_DEFAULTS)
