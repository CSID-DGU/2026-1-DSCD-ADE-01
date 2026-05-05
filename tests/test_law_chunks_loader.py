from pathlib import Path
import subprocess
import sys

import pytest

from scripts.load_law_chunks import (
    EXPECTED_CHILD_COLUMNS,
    EXPECTED_PARENT_COLUMNS,
    make_postgres_copy_stream,
    map_child_row,
    map_parent_row,
    parse_bool_flag,
    parse_date_yyyymmdd,
    read_csv,
    to_nullable_int,
    to_nullable_text,
    validate_rows,
)


def test_parse_date_yyyymmdd():
    assert parse_date_yyyymmdd("20260102").isoformat() == "2026-01-02"


def test_parse_date_yyyymmdd_rejects_bad_value():
    with pytest.raises(ValueError, match="YYYYMMDD"):
        parse_date_yyyymmdd("2026-01-02")


def test_parse_bool_flag():
    assert parse_bool_flag("1") is True
    assert parse_bool_flag("0") is False


def test_parse_bool_flag_rejects_bad_value():
    with pytest.raises(ValueError, match="0 or 1"):
        parse_bool_flag("true")


def test_to_nullable_text():
    assert to_nullable_text("") is None
    assert to_nullable_text("주택임대차법") == "주택임대차법"


def test_to_nullable_int():
    assert to_nullable_int("") is None
    assert to_nullable_int("12") == 12


def test_make_postgres_copy_stream_converts_values_for_copy():
    rows = [
        {
            "name": "민법",
            "empty_value": None,
            "enabled": True,
            "disabled": False,
            "created_date": parse_date_yyyymmdd("20260102"),
        }
    ]

    stream = make_postgres_copy_stream(
        rows,
        ["name", "empty_value", "enabled", "disabled", "created_date"],
    )

    assert stream.getvalue() == "민법,,true,false,2026-01-02\r\n"


def test_validate_rows_accepts_matching_parent_child_keys():
    parents = [
        {
            "article_key": "주택임대차보호법_제3조",
            "law_name": "주택임대차보호법",
            "law_abbr": "주택임대차법",
            "ministry": "법무부",
            "enforcement_date": "20260102",
            "article_no": "3",
            "article_title": "대항력 등",
            "article_date": "20260102",
            "is_amended": "0",
            "is_deleted": "0",
            "parent_text": "대항력 등 제3조(대항력 등)",
            "is_article_only": "0",
        }
    ]
    children = [
        {
            "clause_key": "주택임대차보호법_제3조_제1항",
            "article_key": "주택임대차보호법_제3조",
            "law_name": "주택임대차보호법",
            "article_no": "3",
            "paragraph_no": "1",
            "child_text": "임대차는 그 등기가 없는 경우에도 효력이 생긴다.",
        }
    ]

    validate_rows(parents, children)


def test_validate_rows_rejects_duplicate_article_key():
    parents = [
        {
            "article_key": "민법_제1조",
            "law_name": "민법",
            "law_abbr": "",
            "ministry": "법무부",
            "enforcement_date": "20260102",
            "article_no": "1",
            "article_title": "목적",
            "article_date": "20260102",
            "is_amended": "0",
            "is_deleted": "0",
            "parent_text": "목적",
            "is_article_only": "1",
        },
        {
            "article_key": "민법_제1조",
            "law_name": "민법",
            "law_abbr": "",
            "ministry": "법무부",
            "enforcement_date": "20260102",
            "article_no": "1",
            "article_title": "목적",
            "article_date": "20260102",
            "is_amended": "0",
            "is_deleted": "0",
            "parent_text": "목적",
            "is_article_only": "1",
        },
    ]

    with pytest.raises(ValueError, match="duplicate article_key"):
        validate_rows(parents, [])


def test_validate_rows_rejects_child_without_parent():
    parents = []
    children = [
        {
            "clause_key": "민법_제1조",
            "article_key": "민법_제1조",
            "law_name": "민법",
            "article_no": "1",
            "paragraph_no": "",
            "child_text": "내용",
        }
    ]

    with pytest.raises(ValueError, match="missing parent article_key"):
        validate_rows(parents, children)


def test_map_parent_row_converts_csv_types():
    row = {
        "article_key": "주택임대차보호법_제1조",
        "law_name": "주택임대차보호법",
        "law_abbr": "",
        "ministry": "법무부",
        "enforcement_date": "20260102",
        "article_no": "1",
        "article_title": "",
        "article_date": "20260102",
        "is_amended": "0",
        "is_deleted": "1",
        "parent_text": "제1조 삭제 <1989.12.30>",
        "is_article_only": "1",
    }

    mapped = map_parent_row(row)

    assert mapped["law_abbr"] is None
    assert mapped["article_title"] is None
    assert mapped["enforcement_date"].isoformat() == "2026-01-02"
    assert mapped["article_date"].isoformat() == "2026-01-02"
    assert mapped["is_amended"] is False
    assert mapped["is_deleted"] is True
    assert mapped["is_article_only"] is True


def test_map_child_row_converts_paragraph_no():
    row = {
        "clause_key": "주택임대차보호법_제3조_제1항",
        "article_key": "주택임대차보호법_제3조",
        "law_name": "주택임대차보호법",
        "article_no": "3",
        "paragraph_no": "1",
        "child_text": "내용",
    }

    mapped = map_child_row(row, parent_id=10)

    assert mapped["parent_id"] == 10
    assert mapped["paragraph_no"] == 1
    assert "embedding" not in mapped
    assert "embed_vertex" not in mapped
    assert "embed_kure" not in mapped


def test_law_child_schema_has_separate_embedding_columns():
    root = Path(__file__).resolve().parents[1]
    schema = root / "infra" / "cloud_sql" / "init_law_chunks.sql"

    sql = schema.read_text(encoding="utf-8")

    assert "embedding vector(768)" not in sql
    assert "embed_vertex vector(3072)" in sql
    assert "embed_kure vector(1024)" in sql


def test_real_law_chunk_csv_files_are_loadable():
    root = Path(__file__).resolve().parents[1]
    parent_csv = root / "data" / "law_chunks" / "law_parent.csv"
    child_csv = root / "data" / "law_chunks" / "law_child.csv"

    parents = read_csv(parent_csv, EXPECTED_PARENT_COLUMNS)
    children = read_csv(child_csv, EXPECTED_CHILD_COLUMNS)

    validate_rows(parents, children)

    assert len(parents) == 8646
    assert len(children) == 16145


def test_script_direct_run_can_import_project_modules():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "load_law_chunks.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--parent-csv",
            str(root / "missing_parent.csv"),
            "--child-csv",
            str(root / "missing_child.csv"),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "No module named 'shared'" not in result.stderr
