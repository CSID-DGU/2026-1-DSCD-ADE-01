"""law_parent의 is_article_only 조문을 law_child 테이블에 추가한다.

단문 조문(항 없음)은 기존 파이프라인에서 law_child에 포함되지 않는다.
이 스크립트는 그 조문들을 law_child에 추가하여 Dense/BM25 검색 대상으로 만든다.

실행:
    cd 2026-1-DSCD-ADE-01
    python data/processors/article_only_uploader.py           # 전체 실행
    python data/processors/article_only_uploader.py --dry-run # 대상 목록만 출력 (INSERT 없음)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.db.connection import get_db_client

# ── 상수 ──────────────────────────────────────────────────────────────

VERTEX_MODEL = "gemini-embedding-001"
KURE_MODEL   = "nlpai-lab/KURE-v1"
E5_MODEL     = "intfloat/multilingual-e5-large"

VERTEX_BATCH = 100
KURE_BATCH   = 64
E5_BATCH     = 32

INSERT_BATCH = 50   # DB INSERT 배치 크기


# ── 벡터 유틸 ─────────────────────────────────────────────────────────


def vec_to_str(arr: np.ndarray) -> str:
    """numpy array를 pgvector 문자열 형식으로 변환한다."""
    return "[" + ",".join(f"{x}" for x in arr.tolist()) + "]"


# ── 임베딩 함수 ───────────────────────────────────────────────────────


def embed_vertex(texts: list[str]) -> list[np.ndarray]:
    import vertexai
    from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

    project_id = os.getenv("GCP_PROJECT_ID")
    region = os.getenv("GCP_LOCATION", "us-central1")
    vertexai.init(project=project_id, location=region)
    model = TextEmbeddingModel.from_pretrained(VERTEX_MODEL)

    results: list[np.ndarray] = []
    total = len(texts)
    for i in range(0, total, VERTEX_BATCH):
        batch = texts[i : i + VERTEX_BATCH]
        n = i // VERTEX_BATCH + 1
        total_b = (total - 1) // VERTEX_BATCH + 1
        print(f"    [vertex] 배치 {n}/{total_b} ({len(batch)}건) ...", end=" ", flush=True)
        inputs = [TextEmbeddingInput(t, task_type="RETRIEVAL_DOCUMENT") for t in batch]
        embeddings = model.get_embeddings(inputs)
        results.extend(np.array(e.values, dtype=np.float32) for e in embeddings)
        print("완료")
        if i + VERTEX_BATCH < total:
            time.sleep(0.5)
    return results


def embed_kure(texts: list[str]) -> list[np.ndarray]:
    from sentence_transformers import SentenceTransformer

    print(f"  KURE 모델 로딩 중 ({KURE_MODEL}) ...", end=" ", flush=True)
    model = SentenceTransformer(KURE_MODEL)
    print("완료")

    results: list[np.ndarray] = []
    total = len(texts)
    for i in range(0, total, KURE_BATCH):
        batch = texts[i : i + KURE_BATCH]
        n = i // KURE_BATCH + 1
        total_b = (total - 1) // KURE_BATCH + 1
        print(f"    [kure] 배치 {n}/{total_b} ({len(batch)}건) ...", end=" ", flush=True)
        vecs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        results.extend(np.array(v, dtype=np.float32) for v in vecs)
        print("완료")
    return results


def embed_e5(texts: list[str]) -> list[np.ndarray]:
    from sentence_transformers import SentenceTransformer

    print(f"  E5 모델 로딩 중 ({E5_MODEL}) ...", end=" ", flush=True)
    model = SentenceTransformer(E5_MODEL)
    print("완료")

    prefixed = ["passage: " + t for t in texts]
    results: list[np.ndarray] = []
    total = len(prefixed)
    for i in range(0, total, E5_BATCH):
        batch = prefixed[i : i + E5_BATCH]
        n = i // E5_BATCH + 1
        total_b = (total - 1) // E5_BATCH + 1
        print(f"    [e5] 배치 {n}/{total_b} ({len(batch)}건) ...", end=" ", flush=True)
        vecs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        results.extend(np.array(v, dtype=np.float32) for v in vecs)
        print("완료")
    return results


# ── DB 헬퍼 ───────────────────────────────────────────────────────────


def fetch_article_only_from_db(db) -> list[dict[str, Any]]:
    """law_parent에서 is_article_only=true이고 삭제되지 않은 조문을 조회한다."""
    rows = db.fetch_all(text(
        "SELECT id, article_key, law_name, article_no, parent_text "
        "FROM law_parent WHERE is_article_only = true AND is_deleted = false ORDER BY id"
    ))
    return rows


def fetch_existing_clause_keys(db) -> set[str]:
    """law_child에 이미 존재하는 clause_key 집합을 반환한다."""
    rows = db.fetch_all(text("SELECT clause_key FROM law_child"))
    return {r["clause_key"] for r in rows}


def insert_rows(db, rows: list[dict[str, Any]], dry_run: bool = False) -> int:
    """rows를 INSERT_BATCH 단위로 law_child에 삽입한다."""
    if dry_run:
        return 0

    insert_sql = text("""
        INSERT INTO law_child
            (clause_key, article_key, parent_id, law_name, article_no,
             paragraph_no, child_text, embed_vertex, embed_kure, embed_e5)
        VALUES
            (:clause_key, :article_key, :parent_id, :law_name, :article_no,
             NULL, :child_text,
             CAST(:embed_vertex AS vector),
             CAST(:embed_kure   AS vector),
             CAST(:embed_e5     AS vector))
        ON CONFLICT (clause_key) DO NOTHING
    """)

    inserted = 0
    total = len(rows)
    for i in range(0, total, INSERT_BATCH):
        batch = rows[i : i + INSERT_BATCH]
        for row in batch:
            db.execute(insert_sql, row)
            inserted += 1
        pct = min(i + INSERT_BATCH, total)
        print(f"  INSERT {pct}/{total} ...", end="\r", flush=True)

    print()
    return inserted


# ── 메인 ──────────────────────────────────────────────────────────────


def main(dry_run: bool = False) -> None:
    print("=== is_article_only 조문 law_child 추가 ===\n")

    db = get_db_client()

    # 1. DB에서 대상 조문 조회
    print("[1] law_parent에서 is_article_only=true 조문 조회 중...")
    candidates = fetch_article_only_from_db(db)
    print(f"    총 {len(candidates)}개\n")

    # 2. 이미 존재하는 clause_key 조회
    print("[2] law_child 기존 clause_key 조회 중...")
    existing = fetch_existing_clause_keys(db)
    print(f"    기존 law_child: {len(existing)}행\n")

    # 3. 미존재 조문 필터링
    # article_only 조문의 clause_key = article_key (paragraph 없으므로)
    to_add = [
        r for r in candidates
        if r["article_key"] not in existing
    ]
    print(f"[3] 추가 대상: {len(to_add)}개 (기존에 없는 것)")

    if not to_add:
        print("\n추가할 조문 없음. 완료.")
        return

    # 대상 목록 출력 (상위 20개)
    print()
    print("    법령별 추가 건수:")
    from collections import Counter
    cnt = Counter(r["law_name"] for r in to_add)
    for law, n in sorted(cnt.items(), key=lambda x: -x[1]):
        print(f"      {law}: {n}개")

    if dry_run:
        print("\n[--dry-run] INSERT 건너뜀. 완료.")
        return

    print()

    # 4. 텍스트 목록
    texts = [r["parent_text"] for r in to_add]

    # 5. 임베딩 생성
    print("[4] embed_vertex 생성 중...")
    vecs_vertex = embed_vertex(texts)
    print(f"    완료: {len(vecs_vertex)}건\n")

    print("[5] embed_kure 생성 중...")
    vecs_kure = embed_kure(texts)
    print(f"    완료: {len(vecs_kure)}건\n")

    print("[6] embed_e5 생성 중...")
    vecs_e5 = embed_e5(texts)
    print(f"    완료: {len(vecs_e5)}건\n")

    # 6. INSERT 행 구성
    insert_rows_data = []
    for row, v_vtx, v_kure, v_e5 in zip(to_add, vecs_vertex, vecs_kure, vecs_e5):
        insert_rows_data.append({
            "clause_key":   row["article_key"],
            "article_key":  row["article_key"],
            "parent_id":    row["id"],
            "law_name":     row["law_name"],
            "article_no":   row["article_no"],
            "child_text":   row["parent_text"],
            "embed_vertex": vec_to_str(v_vtx),
            "embed_kure":   vec_to_str(v_kure),
            "embed_e5":     vec_to_str(v_e5),
        })

    # 7. DB INSERT
    print("[7] DB INSERT 중...")
    n_inserted = insert_rows(db, insert_rows_data, dry_run=False)
    print(f"    완료: {n_inserted}행 삽입\n")

    print("=== 완료 ===")
    print(f"추가된 조문: {n_inserted}개")
    print()
    print("※ 남은 edge case 2건 (항 단위 누락)은 별도 처리 필요:")
    print("  - 주택임대차보호법_제6조의3_제7항")
    print("  - 주택임대차보호법 시행령_제3조_제4항")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="is_article_only 조문을 law_child에 추가한다.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 INSERT 없이 대상 목록만 출력한다.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
