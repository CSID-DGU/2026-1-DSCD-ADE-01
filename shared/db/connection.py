"""Cloud SQL 연결 관리 및 범용 CRUD 유틸리티.

사용 예
-------
DDL:
    >>> from shared.db.connection import get_db_client
    >>> db = get_db_client()
    >>> db.execute_ddl("CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name TEXT)")

INSERT:
    >>> from sqlalchemy import text
    >>> db = get_db_client()
    >>> db.execute(text("INSERT INTO users (name) VALUES (:name)"), {"name": "홍길동"})

SELECT:
    >>> db = get_db_client()
    >>> rows = db.fetch_all(text("SELECT * FROM users"))
    >>> row = db.fetch_one(text("SELECT * FROM users WHERE id = :id"), {"id": 1})
"""
from __future__ import annotations

from typing import Any

import sqlalchemy
from google.cloud.sql.connector import Connector
from sqlalchemy import text
from sqlalchemy.engine import Engine

from shared.config import settings


class DBError(RuntimeError):
    """DB 관련 모든 오류의 단일 타입."""


class DBClient:
    """Cloud SQL 연결 풀 관리 및 범용 CRUD 유틸리티.

    Cloud SQL Python Connector로 비밀번호 기반 보안 연결을 수립하고,
    SQLAlchemy Core Engine으로 커넥션 풀을 관리한다.
    """

    def __init__(
        self,
        *,
        instance_connection_name: str | None = None,
        db_user: str | None = None,
        db_password: str | None = None,
        db_name: str | None = None,
    ) -> None:
        self._instance = instance_connection_name or settings.cloud_sql_connection
        self._db_user = db_user or settings.db_user
        self._db_password = db_password or settings.db_password
        self._db_name = db_name or settings.db_name
        self._connector = Connector(refresh_strategy="lazy")
        self._engine: Engine = self._create_engine()
        self._closed = False

    def _getconn(self) -> Any:
        """Cloud SQL Python Connector를 통해 pg8000 연결을 반환한다."""
        return self._connector.connect(
            self._instance,
            "pg8000",
            user=self._db_user,
            password=self._db_password,
            db=self._db_name,
        )

    def _create_engine(self) -> Engine:
        """SQLAlchemy Engine을 생성한다."""
        return sqlalchemy.create_engine(
            "postgresql+pg8000://",
            creator=self._getconn,
            pool_size=30,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )

    @property
    def engine(self) -> Engine:
        """SQLAlchemy Engine 인스턴스를 반환한다."""
        return self._engine

    @property
    def closed(self) -> bool:
        """엔진과 커넥터가 닫혔는지 반환한다."""
        return self._closed

    def execute(
        self, statement: Any, params: dict[str, Any] | None = None
    ) -> None:
        """INSERT, UPDATE, DELETE 등 변경 쿼리를 실행한다.

        Parameters
        ----------
        statement:
            SQLAlchemy ``text()`` 객체.
        params:
            바인드 파라미터 딕셔너리.

        Raises
        ------
        DBError
            쿼리 실행 중 예외 발생 시.
        """
        try:
            with self._engine.begin() as conn:
                conn.execute(statement, params or {})
        except Exception as exc:
            raise DBError(str(exc)) from exc

    def fetch_one(
        self, statement: Any, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """단일 행을 조회하여 딕셔너리로 반환한다. 결과 없으면 None.

        Parameters
        ----------
        statement:
            SQLAlchemy ``text()`` 객체.
        params:
            바인드 파라미터 딕셔너리.

        Raises
        ------
        DBError
            쿼리 실행 중 예외 발생 시.
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(statement, params or {})
                row = result.mappings().first()
                return dict(row) if row is not None else None
        except Exception as exc:
            raise DBError(str(exc)) from exc

    def fetch_all(
        self, statement: Any, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """다중 행을 조회하여 딕셔너리 리스트로 반환한다.

        Parameters
        ----------
        statement:
            SQLAlchemy ``text()`` 객체.
        params:
            바인드 파라미터 딕셔너리.

        Raises
        ------
        DBError
            쿼리 실행 중 예외 발생 시.
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(statement, params or {})
                return [dict(row) for row in result.mappings().all()]
        except Exception as exc:
            raise DBError(str(exc)) from exc

    def execute_ddl(self, statement: str) -> None:
        """CREATE TABLE, DROP TABLE 등 DDL을 실행한다.

        Parameters
        ----------
        statement:
            DDL SQL 문자열.

        Raises
        ------
        DBError
            DDL 실행 중 예외 발생 시.
        """
        try:
            with self._engine.begin() as conn:
                conn.execute(text(statement))
        except Exception as exc:
            raise DBError(str(exc)) from exc

    def close(self) -> None:
        """엔진과 커넥터를 정리한다."""
        if self._closed:
            return

        self._engine.dispose()
        self._connector.close()
        self._closed = True


_db_client: DBClient | None = None


def get_db_client() -> DBClient:
    """DBClient 싱글턴을 반환한다. 최초 호출 시 1회만 생성."""
    global _db_client  # noqa: PLW0603
    if _db_client is None or _db_client.closed:
        _db_client = DBClient()
    return _db_client
