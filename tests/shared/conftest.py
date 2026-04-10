"""tests/shared/ 범위 전용 fixture.

``shared.config.load_settings()``는 ``BaseSettings(env_file=".env")`` 설정
때문에 현재 작업 디렉터리에 실제 ``.env`` 파일이 있으면 자동으로 해당
값을 병합한다. 테스트는 실제 리포 루트의 ``.env`` 존재 여부에 영향을
받지 않도록 격리된 작업 디렉터리에서 실행해야 한다.

본 모듈은 autouse fixture로 모든 ``tests/shared/`` 테스트의 CWD를 임시
디렉터리로 옮긴다. .env를 적극적으로 사용해야 하는 테스트(예: OS 환경
변수 우선순위 검증)는 해당 디렉터리에 직접 ``.env``를 작성하면 된다.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """각 테스트를 빈 tmp_path에서 실행하여 실제 .env 간섭을 차단한다."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
