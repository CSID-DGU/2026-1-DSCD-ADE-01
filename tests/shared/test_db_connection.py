"""shared.db.connection 단위 테스트."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from shared.db.connection import DBClient, DBError, get_db_client


def _make_client() -> DBClient:
    """Connector와 Engine 생성을 mock한 DBClient 인스턴스를 반환한다."""
    with patch("shared.db.connection.Connector"), \
         patch("shared.db.connection.sqlalchemy.create_engine") as mock_engine:
        mock_engine.return_value = MagicMock()
        client = DBClient()
    return client


# --- DBError ---

def test_db_error_is_runtime_error_subclass() -> None:
    assert issubclass(DBError, RuntimeError)


# --- get_db_client (lazy factory) ---

def test_get_db_client_returns_db_client_instance() -> None:
    """get_db_client()가 DBClient 인스턴스를 반환한다."""
    import shared.db.connection as mod
    with patch("shared.db.connection.Connector"), \
         patch("shared.db.connection.sqlalchemy.create_engine") as mock_engine:
        mock_engine.return_value = MagicMock()
        mod._db_client = None  # 리셋하여 lazy 생성 검증
        client = get_db_client()
        assert isinstance(client, DBClient)
        mod._db_client = None  # 테스트 후 정리


def test_get_db_client_returns_same_instance() -> None:
    """get_db_client()가 동일 인스턴스를 반환한다 (싱글턴)."""
    import shared.db.connection as mod
    with patch("shared.db.connection.Connector"), \
         patch("shared.db.connection.sqlalchemy.create_engine") as mock_engine:
        mock_engine.return_value = MagicMock()
        mod._db_client = None
        first = get_db_client()
        second = get_db_client()
        assert first is second
        mod._db_client = None


# --- execute ---

def test_execute_calls_engine_begin() -> None:
    """execute()가 engine.begin() 컨텍스트 내에서 쿼리를 실행한다."""
    client = _make_client()
    mock_conn = MagicMock()
    client._engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    client._engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    stmt = text("INSERT INTO users (name) VALUES (:name)")
    client.execute(stmt, {"name": "홍길동"})

    mock_conn.execute.assert_called_once_with(stmt, {"name": "홍길동"})


def test_execute_wraps_exception_as_db_error() -> None:
    """execute() 중 예외 발생 시 DBError로 래핑한다."""
    client = _make_client()
    client._engine.begin.side_effect = RuntimeError("DB 오류")

    with pytest.raises(DBError) as exc_info:
        client.execute(text("INSERT INTO t VALUES (1)"))

    assert "DB 오류" in str(exc_info.value)


def test_execute_db_error_has_cause() -> None:
    """DBError는 원본 예외를 __cause__로 보존한다."""
    client = _make_client()
    original = RuntimeError("원본 오류")
    client._engine.begin.side_effect = original

    with pytest.raises(DBError) as exc_info:
        client.execute(text("DELETE FROM t"))

    assert exc_info.value.__cause__ is original


# --- fetch_one ---

def test_fetch_one_returns_dict() -> None:
    """fetch_one()이 결과를 딕셔너리로 반환한다."""
    client = _make_client()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_row = {"id": 1, "name": "홍길동"}
    mock_result.mappings.return_value.first.return_value = mock_row
    mock_conn.execute.return_value = mock_result
    client._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    client._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    result = client.fetch_one(text("SELECT * FROM users WHERE id = :id"), {"id": 1})

    assert result == {"id": 1, "name": "홍길동"}


def test_fetch_one_returns_none_when_no_result() -> None:
    """fetch_one()이 결과 없으면 None을 반환한다."""
    client = _make_client()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None
    mock_conn.execute.return_value = mock_result
    client._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    client._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    result = client.fetch_one(text("SELECT * FROM users WHERE id = :id"), {"id": 999})

    assert result is None


def test_fetch_one_wraps_exception_as_db_error() -> None:
    """fetch_one() 중 예외 발생 시 DBError로 래핑한다."""
    client = _make_client()
    client._engine.connect.side_effect = RuntimeError("연결 실패")

    with pytest.raises(DBError):
        client.fetch_one(text("SELECT 1"))


# --- fetch_all ---

def test_fetch_all_returns_list_of_dicts() -> None:
    """fetch_all()이 딕셔너리 리스트를 반환한다."""
    client = _make_client()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"id": 1, "name": "홍길동"},
        {"id": 2, "name": "김철수"},
    ]
    mock_conn.execute.return_value = mock_result
    client._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    client._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    result = client.fetch_all(text("SELECT * FROM users"))

    assert len(result) == 2
    assert result[0] == {"id": 1, "name": "홍길동"}
    assert result[1] == {"id": 2, "name": "김철수"}


def test_fetch_all_returns_empty_list_when_no_results() -> None:
    """fetch_all()이 결과 없으면 빈 리스트를 반환한다."""
    client = _make_client()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_conn.execute.return_value = mock_result
    client._engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    client._engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    result = client.fetch_all(text("SELECT * FROM users WHERE 1=0"))

    assert result == []


def test_fetch_all_wraps_exception_as_db_error() -> None:
    """fetch_all() 중 예외 발생 시 DBError로 래핑한다."""
    client = _make_client()
    client._engine.connect.side_effect = RuntimeError("타임아웃")

    with pytest.raises(DBError):
        client.fetch_all(text("SELECT * FROM users"))


# --- execute_ddl ---

def test_execute_ddl_calls_engine_begin() -> None:
    """execute_ddl()이 engine.begin() 컨텍스트 내에서 DDL을 실행한다."""
    client = _make_client()
    mock_conn = MagicMock()
    client._engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    client._engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    client.execute_ddl("CREATE TABLE test (id SERIAL PRIMARY KEY)")

    mock_conn.execute.assert_called_once()


def test_execute_ddl_wraps_exception_as_db_error() -> None:
    """execute_ddl() 중 예외 발생 시 DBError로 래핑한다."""
    client = _make_client()
    client._engine.begin.side_effect = RuntimeError("권한 없음")

    with pytest.raises(DBError) as exc_info:
        client.execute_ddl("DROP TABLE important")

    assert "권한 없음" in str(exc_info.value)


# --- execute with default params ---

def test_execute_uses_empty_dict_when_no_params() -> None:
    """params 미전달 시 빈 딕셔너리로 실행한다."""
    client = _make_client()
    mock_conn = MagicMock()
    client._engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    client._engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    stmt = text("DELETE FROM logs")
    client.execute(stmt)

    mock_conn.execute.assert_called_once_with(stmt, {})


# --- close ---

def test_close_disposes_engine_and_connector() -> None:
    """close()가 engine.dispose()와 connector.close()를 호출한다."""
    client = _make_client()

    client.close()

    client._engine.dispose.assert_called_once()
    client._connector.close.assert_called_once()


# --- engine property ---

def test_engine_property_returns_engine() -> None:
    """engine 프로퍼티가 SQLAlchemy Engine을 반환한다."""
    client = _make_client()

    assert client.engine is client._engine
