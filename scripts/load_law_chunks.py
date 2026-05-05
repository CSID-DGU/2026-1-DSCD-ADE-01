"""법령 parent/child CSV를 DB에 적재하기 위한 도우미 함수."""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import date
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 이 파일은 `python scripts/load_law_chunks.py`처럼 직접 실행한다.
# 그 경우 Python 경로가 scripts/로 잡혀 shared/ 패키지를 못 찾을 수 있다.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_PARENT_CSV = PROJECT_ROOT / "data" / "law_chunks" / "law_parent.csv"
DEFAULT_CHILD_CSV = PROJECT_ROOT / "data" / "law_chunks" / "law_child.csv"

EXPECTED_PARENT_COLUMNS = [
    "article_key",
    "law_name",
    "law_abbr",
    "ministry",
    "enforcement_date",
    "article_no",
    "article_title",
    "article_date",
    "is_amended",
    "is_deleted",
    "parent_text",
    "is_article_only",
]

EXPECTED_CHILD_COLUMNS = [
    "clause_key",
    "article_key",
    "law_name",
    "article_no",
    "paragraph_no",
    "child_text",
]

PARENT_DB_COLUMNS = [
    "article_key",
    "law_name",
    "law_abbr",
    "ministry",
    "enforcement_date",
    "article_no",
    "article_title",
    "article_date",
    "is_amended",
    "is_deleted",
    "parent_text",
    "is_article_only",
]

CHILD_DB_COLUMNS = [
    "clause_key",
    "article_key",
    "parent_id",
    "law_name",
    "article_no",
    "paragraph_no",
    "child_text",
]


def parse_date_yyyymmdd(value: str) -> date:
    """CSV의 YYYYMMDD 문자열을 DB date 타입에 맞는 값으로 바꾼다."""
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"date must be YYYYMMDD: {value!r}")

    year = int(value[:4])
    month = int(value[4:6])
    day = int(value[6:8])
    return date(year, month, day)


def parse_bool_flag(value: str) -> bool:
    """CSV의 0/1 값을 Python boolean 값으로 바꾼다."""
    if value == "1":
        return True
    if value == "0":
        return False

    raise ValueError(f"boolean flag must be 0 or 1: {value!r}")


def to_nullable_text(value: str) -> str | None:
    """빈 문자열은 DB에 NULL로 저장하기 위해 None으로 바꾼다."""
    if value == "":
        return None
    return value


def to_nullable_int(value: str) -> int | None:
    """비어 있을 수 있는 숫자 문자열을 int 또는 None으로 바꾼다."""
    if value == "":
        return None
    return int(value)


def make_postgres_copy_stream(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> io.StringIO:
    """Postgres COPY에 넘길 CSV 문자열을 만든다."""
    stream = io.StringIO()
    writer = csv.writer(stream)

    for row in rows:
        values = []
        for column in columns:
            value = row[column]

            if value is None:
                values.append("")
            elif isinstance(value, bool):
                values.append("true" if value else "false")
            elif isinstance(value, date):
                values.append(value.isoformat())
            else:
                values.append(value)

        writer.writerow(values)

    stream.seek(0)
    return stream


def copy_rows(
    raw_connection: Any,
    table_name: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> None:
    """pg8000의 COPY stream 기능으로 여러 row를 빠르게 적재한다."""
    if not rows:
        return

    column_text = ", ".join(columns)
    stream = make_postgres_copy_stream(rows, columns)
    cursor = raw_connection.cursor()
    cursor.execute(
        f"COPY {table_name} ({column_text}) FROM STDIN WITH (FORMAT csv, NULL '')",
        stream=stream,
    )


def read_csv(path: Path, expected_columns: list[str]) -> list[dict[str, str]]:
    """CSV를 읽고 헤더가 예상한 컬럼과 같은지 확인한다."""
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames != expected_columns:
            raise ValueError(
                f"{path} columns mismatch: expected {expected_columns}, "
                f"got {reader.fieldnames}"
            )

        rows = []
        for row in reader:
            rows.append(row)

    return rows


def _find_duplicates(values: list[str]) -> list[str]:
    """중복된 값을 처음 발견한 순서대로 반환한다."""
    seen = set()
    duplicates = []

    for value in values:
        if value in seen:
            if value not in duplicates:
                duplicates.append(value)
        seen.add(value)

    return duplicates


def validate_rows(
    parent_rows: list[dict[str, str]],
    child_rows: list[dict[str, str]],
) -> None:
    """CSV row들이 DB에 들어가기 전에 기본 조건을 만족하는지 확인한다."""
    article_keys = []
    for row in parent_rows:
        article_keys.append(row["article_key"])

    clause_keys = []
    for row in child_rows:
        clause_keys.append(row["clause_key"])

    duplicate_article_keys = _find_duplicates(article_keys)
    if duplicate_article_keys:
        raise ValueError(f"duplicate article_key: {duplicate_article_keys[:5]}")

    duplicate_clause_keys = _find_duplicates(clause_keys)
    if duplicate_clause_keys:
        raise ValueError(f"duplicate clause_key: {duplicate_clause_keys[:5]}")

    # child는 반드시 parent 조문 아래에 있어야 parent_id를 만들 수 있다.
    parent_key_set = set(article_keys)
    missing_parent_keys = []
    for row in child_rows:
        article_key = row["article_key"]
        if article_key not in parent_key_set:
            if article_key not in missing_parent_keys:
                missing_parent_keys.append(article_key)

    if missing_parent_keys:
        raise ValueError(f"missing parent article_key: {missing_parent_keys[:5]}")

    # DB 타입으로 변환하기 전에 날짜와 boolean 형식을 미리 확인한다.
    for row in parent_rows:
        parse_date_yyyymmdd(row["enforcement_date"])
        parse_date_yyyymmdd(row["article_date"])
        parse_bool_flag(row["is_amended"])
        parse_bool_flag(row["is_deleted"])
        parse_bool_flag(row["is_article_only"])

    # paragraph_no는 항이 없으면 비어 있고, 있으면 숫자여야 한다.
    for row in child_rows:
        to_nullable_int(row["paragraph_no"])


def map_parent_row(row: dict[str, str]) -> dict[str, Any]:
    """parent CSV 한 행을 DB insert에 사용할 값으로 바꾼다."""
    return {
        "article_key": row["article_key"],
        "law_name": row["law_name"],
        "law_abbr": to_nullable_text(row["law_abbr"]),
        "ministry": row["ministry"],
        "enforcement_date": parse_date_yyyymmdd(row["enforcement_date"]),
        "article_no": row["article_no"],
        "article_title": to_nullable_text(row["article_title"]),
        "article_date": parse_date_yyyymmdd(row["article_date"]),
        "is_amended": parse_bool_flag(row["is_amended"]),
        "is_deleted": parse_bool_flag(row["is_deleted"]),
        "parent_text": row["parent_text"],
        "is_article_only": parse_bool_flag(row["is_article_only"]),
    }


def map_child_row(row: dict[str, str], parent_id: int) -> dict[str, Any]:
    """child CSV 한 행에 DB parent_id를 붙여 insert 값으로 바꾼다."""
    return {
        "clause_key": row["clause_key"],
        "article_key": row["article_key"],
        "parent_id": parent_id,
        "law_name": row["law_name"],
        "article_no": row["article_no"],
        "paragraph_no": to_nullable_int(row["paragraph_no"]),
        "child_text": row["child_text"],
    }


def load_law_chunks(
    parent_csv: Path = DEFAULT_PARENT_CSV,
    child_csv: Path = DEFAULT_CHILD_CSV,
    *,
    truncate: bool = False,
) -> dict[str, int]:
    """법령 parent/child CSV를 DB에 적재한다."""
    from shared.db.connection import get_db_client

    # 1. CSV를 읽고 DB에 넣기 전에 기본 형식을 확인한다.
    parent_rows = read_csv(parent_csv, EXPECTED_PARENT_COLUMNS)
    child_rows = read_csv(child_csv, EXPECTED_CHILD_COLUMNS)
    validate_rows(parent_rows, child_rows)

    db = get_db_client()
    raw_connection = db.engine.raw_connection()

    try:
        cursor = raw_connection.cursor()

        if truncate:
            # 재적재할 때는 child가 parent를 참조하므로 두 테이블을 같이 비운다.
            cursor.execute("TRUNCATE TABLE law_child, law_parent RESTART IDENTITY CASCADE")

        # 2. child가 parent_id를 필요로 하므로 parent를 먼저 넣는다.
        mapped_parents = []
        for row in parent_rows:
            mapped_parents.append(map_parent_row(row))

        print(f"copying law_parent rows: {len(mapped_parents)}", flush=True)
        copy_rows(raw_connection, "law_parent", PARENT_DB_COLUMNS, mapped_parents)

        # 3. article_key 기준으로 parent id를 찾는다.
        cursor.execute("SELECT id, article_key FROM law_parent")
        parent_id_rows = cursor.fetchall()
        parent_ids = {}
        for row in parent_id_rows:
            parent_id = row[0]
            article_key = row[1]
            parent_ids[article_key] = parent_id

        # 4. 임베딩 컬럼은 CSV에 없으므로 여기서는 넣지 않는다.
        mapped_children = []
        for row in child_rows:
            parent_id = parent_ids[row["article_key"]]
            mapped_children.append(map_child_row(row, parent_id=parent_id))

        print(f"copying law_child rows: {len(mapped_children)}", flush=True)
        copy_rows(raw_connection, "law_child", CHILD_DB_COLUMNS, mapped_children)
        raw_connection.commit()
    except Exception:
        raw_connection.rollback()
        raise
    finally:
        raw_connection.close()

    return {
        "parent_count": len(parent_rows),
        "child_count": len(child_rows),
    }


def parse_args() -> argparse.Namespace:
    """CLI 인자를 읽는다."""
    parser = argparse.ArgumentParser(description="Load law chunk CSV files into DB")
    parser.add_argument("--parent-csv", type=Path, default=DEFAULT_PARENT_CSV)
    parser.add_argument("--child-csv", type=Path, default=DEFAULT_CHILD_CSV)
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Clear law_child and law_parent before loading",
    )
    return parser.parse_args()


def main() -> None:
    """CLI 실행 함수."""
    args = parse_args()
    stats = load_law_chunks(
        parent_csv=args.parent_csv,
        child_csv=args.child_csv,
        truncate=args.truncate,
    )
    print(f"law_parent loaded: {stats['parent_count']}")
    print(f"law_child loaded: {stats['child_count']}")
    print("embed_vertex and embed_kure columns remain NULL until embedding batches run")


if __name__ == "__main__":
    main()
