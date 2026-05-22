"""DB law_child 테이블의 GT 법령 커버리지를 진단한다.

실행:
    cd 2026-1-DSCD-ADE-01
    python evaluation/db_coverage_check.py

출력:
    evaluation/results/db_coverage_report.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.db.connection import get_db_client

EVAL_SET_PATH = Path(__file__).parent / "eval_set.json"
OUTPUT_PATH = Path(__file__).parent / "results" / "db_coverage_report.json"

EMBED_COLS = ["embed_vertex", "embed_kure", "embed_e5"]


# ── 유틸 ──────────────────────────────────────────────────────────────


def normalize(value: str) -> str:
    return "".join(str(value).strip().casefold().replace("_", " ").split())


def gt_matches_clause_key(gt_ref: str, clause_key: str) -> bool:
    """GT article 참조(예: 민법_제390조)가 clause_key와 매칭되는지 확인.

    GT는 조문 단위(제390조)이고 DB는 항 단위(제390조_제1항)일 수 있으므로
    clause_key가 gt_ref로 시작하면 매칭으로 본다.
    """
    norm_gt = normalize(gt_ref)
    norm_ck = normalize(clause_key)
    return norm_ck.startswith(norm_gt)


# ── GT 로드 ───────────────────────────────────────────────────────────


def load_gt_laws(path: Path) -> dict[str, list[str]]:
    """eval_set.json에서 GT 법령 참조를 수집한다.

    반환: {gt_ref → [case_id, ...]}
    """
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)

    gt_ref_cases: dict[str, list] = defaultdict(list)
    for case in cases:
        for ref in case.get("gt_laws", []):
            gt_ref_cases[ref].append(case["id"])
    return dict(gt_ref_cases)


# ── DB 쿼리 ───────────────────────────────────────────────────────────


def query_law_child_stats(db) -> dict:
    """law_child 테이블의 법령별 행 수 및 임베딩 NULL 통계를 조회한다."""
    count_rows = db.fetch_all(text(
        "SELECT law_name, COUNT(*) AS total "
        "FROM law_child GROUP BY law_name ORDER BY total DESC"
    ))
    counts = {r["law_name"]: int(r["total"]) for r in count_rows}

    null_sql = """
        SELECT law_name,
               SUM(CASE WHEN embed_vertex IS NULL THEN 1 ELSE 0 END) AS null_vertex,
               SUM(CASE WHEN embed_kure   IS NULL THEN 1 ELSE 0 END) AS null_kure,
               SUM(CASE WHEN embed_e5     IS NULL THEN 1 ELSE 0 END) AS null_e5
        FROM law_child
        GROUP BY law_name
    """
    null_rows = db.fetch_all(text(null_sql))
    nulls = {
        r["law_name"]: {
            "null_vertex": int(r["null_vertex"]),
            "null_kure":   int(r["null_kure"]),
            "null_e5":     int(r["null_e5"]),
        }
        for r in null_rows
    }

    return {"counts": counts, "nulls": nulls}


def query_all_clause_keys(db) -> list[str]:
    """law_child 테이블의 모든 clause_key를 조회한다."""
    rows = db.fetch_all(text("SELECT clause_key FROM law_child"))
    return [r["clause_key"] for r in rows]


# ── 메인 ──────────────────────────────────────────────────────────────


def main() -> None:
    print("=== DB 법령 커버리지 진단 ===\n")

    # GT 로드
    gt_ref_cases = load_gt_laws(EVAL_SET_PATH)
    all_gt_refs = sorted(gt_ref_cases)
    total_gt_case_refs = sum(len(v) for v in gt_ref_cases.values())

    gt_by_law: dict[str, list] = defaultdict(list)
    for ref in all_gt_refs:
        gt_by_law[ref.split("_")[0]].append(ref)

    print(f"GT 법령 참조: {len(all_gt_refs)}개 고유 조문 / 케이스 참조 {total_gt_case_refs}건")
    print(f"GT 법령명:    {len(gt_by_law)}개\n")

    # DB 연결
    print("DB 연결 중...")
    db = get_db_client()

    # 통계 조회
    print("law_child 통계 조회 중...")
    stats = query_law_child_stats(db)
    db_total = sum(stats["counts"].values())
    print(f"DB law_child: {db_total}행, 법령명 {len(stats['counts'])}개\n")

    # clause_key 전체 로드
    print("clause_key 전체 로드 중...")
    all_clause_keys = query_all_clause_keys(db)
    clause_key_set = set(all_clause_keys)
    print(f"clause_key: {len(all_clause_keys)}개\n")

    # GT vs DB 매칭
    print("GT 법령 vs DB 매칭 분석 중...")
    matched_refs: list[str] = []
    missing_refs: list[str] = []

    for gt_ref in all_gt_refs:
        hit = any(gt_matches_clause_key(gt_ref, ck) for ck in clause_key_set)
        (matched_refs if hit else missing_refs).append(gt_ref)

    # 임베딩 NULL 있는 법령
    null_laws = [
        {"law_name": law, **nulls, "total": stats["counts"].get(law, 0)}
        for law, nulls in stats["nulls"].items()
        if any(v > 0 for v in nulls.values())
    ]

    # 법령별 누락 조문
    missing_by_law: dict[str, list] = defaultdict(list)
    for ref in missing_refs:
        missing_by_law[ref.split("_")[0]].append(ref)

    # ── 콘솔 출력 ────────────────────────────────────────────────────

    print()
    print("=" * 55)
    pct_matched = len(matched_refs) / len(all_gt_refs) * 100 if all_gt_refs else 0
    pct_missing = len(missing_refs) / len(all_gt_refs) * 100 if all_gt_refs else 0
    print(f"GT 법령 매칭 결과")
    print(f"  총 GT 참조: {len(all_gt_refs)}개")
    print(f"  DB에 있음:  {len(matched_refs)}개 ({pct_matched:.1f}%)")
    print(f"  DB에 없음:  {len(missing_refs)}개 ({pct_missing:.1f}%)")
    print()

    if missing_refs:
        print("[ 누락 법령 조문 ]")
        for law, refs in sorted(missing_by_law.items(), key=lambda x: -len(x[1])):
            print(f"  {law}: {len(refs)}개 조문 누락")
            for r in sorted(refs)[:5]:
                print(f"    - {r}")
            if len(refs) > 5:
                print(f"    ... 외 {len(refs) - 5}개")
        print()

    if null_laws:
        print("[ 임베딩 NULL 있는 법령 ]")
        for law in sorted(null_laws, key=lambda x: -x["total"])[:15]:
            print(
                f"  {law['law_name']}: total={law['total']}, "
                f"null_vertex={law['null_vertex']}, "
                f"null_kure={law['null_kure']}, "
                f"null_e5={law['null_e5']}"
            )
        print()

    print("[ DB 법령별 행 수 (상위 20) ]")
    for law, cnt in sorted(stats["counts"].items(), key=lambda x: -x[1])[:20]:
        gt_mark = "★" if law in gt_by_law else " "
        print(f"  {gt_mark} {law}: {cnt}행")

    # ── JSON 저장 ─────────────────────────────────────────────────────

    report = {
        "summary": {
            "gt_refs_total":             len(all_gt_refs),
            "gt_refs_matched":           len(matched_refs),
            "gt_refs_missing":           len(missing_refs),
            "db_total_rows":             db_total,
            "db_law_names_count":        len(stats["counts"]),
            "laws_with_null_embeddings": len(null_laws),
        },
        "missing_by_law":      {k: sorted(v) for k, v in missing_by_law.items()},
        "gt_missing_refs":     sorted(missing_refs),
        "gt_matched_refs":     sorted(matched_refs),
        "db_law_counts":       stats["counts"],
        "null_embedding_laws": sorted(null_laws, key=lambda x: -x["total"]),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n리포트 저장: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
