"""법령/판례 검색 평가 — 실제 DB 임베딩 pipeline 사용."""
from __future__ import annotations

import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rank_bm25 import BM25Okapi

CLAUSE_WORKERS = 4   # 특약 동시 처리 수 (API rate limit에 맞게 조절)
EMBED_WORKERS = 2    # embed_vertex + embed_kure 병렬 처리

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.retrieval.bm25_retrieval import (
    build_query_tokens,
    load_case_law_from_db,
    load_law_child_from_db,
    tokenize,
)
from pipeline.retrieval import dense_retrieval
from pipeline.retrieval.query_expansion.query_expansion import expand_clause
from pipeline.retrieval.query_expansion.retrieval_adapter import build_retrieval_payload

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

EVAL_SET_PATH = Path(__file__).resolve().parent / "eval_set.json"
TOP_K = 20
RRF_K = 60
RECALL_K_VALUES = [1, 3, 5, 10, 20]
EMBED_COLS = ["embed_vertex", "embed_kure"]
LAW_KEEP_COLS = ["clause_key", "child_text"]
PREC_KEEP_COLS = ["case_id", "case_number", "judgment_summary"]


def load_corpus() -> dict:
    """BM25 + Dense 검색에 필요한 코퍼스를 DB에서 로드한다."""
    log.info("▶ BM25 코퍼스 로드 중...")
    law_df = load_law_child_from_db()
    prec_df = load_case_law_from_db()

    law_docs = [
        {"clause_key": str(r["clause_key"]), "text": str(r["child_text"] or "")}
        for _, r in law_df.iterrows()
    ]
    prec_docs = [
        {"case_number": str(r["case_number"]), "text": str(r.get("bm25_target") or "")}
        for _, r in prec_df.iterrows()
    ]

    log.info("  법령 BM25 인덱스 구축 중 (%d건)...", len(law_docs))
    law_bm25 = BM25Okapi([tokenize(d["text"]) for d in law_docs])
    log.info("  판례 BM25 인덱스 구축 중 (%d건)...", len(prec_docs))
    prec_bm25 = BM25Okapi([tokenize(d["text"]) for d in prec_docs])

    log.info("▶ Dense 임베딩 청크 로드 중 (%s)...", ", ".join(EMBED_COLS))
    law_chunks = {
        col: dense_retrieval.load_chunks(dense_retrieval.LAW_TABLE, col, LAW_KEEP_COLS)
        for col in EMBED_COLS
    }
    prec_chunks = {
        col: dense_retrieval.load_chunks(dense_retrieval.PREC_TABLE, col, PREC_KEEP_COLS)
        for col in EMBED_COLS
    }

    log.info("▶ 코퍼스 로드 완료 (법령 %d건, 판례 %d건)", len(law_docs), len(prec_docs))
    return {
        "law_docs": law_docs, "law_bm25": law_bm25,
        "prec_docs": prec_docs, "prec_bm25": prec_bm25,
        "law_chunks": law_chunks, "prec_chunks": prec_chunks,
    }


def retrieve_clause(clause: str, corpus: dict) -> dict:
    """단일 특약에 대해 Query Expansion → BM25 → Dense → RRF를 실행한다."""
    # Query Expansion
    expansion = expand_clause(clause)
    payload = build_retrieval_payload(expansion, clause_text=clause)
    log.info("    QE keywords: %s", payload["bm25_keywords"])

    # BM25
    query_tokens = build_query_tokens(payload["bm25_keywords"])
    bm25_hits: dict[str, tuple[int, str]] = {}
    for docs, bm25, source_type, id_field in [
        (corpus["law_docs"], corpus["law_bm25"], "law", "clause_key"),
        (corpus["prec_docs"], corpus["prec_bm25"], "precedent", "case_number"),
    ]:
        scores = bm25.get_scores(query_tokens)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:TOP_K]
        for rank, idx in enumerate(top_idx, 1):
            bm25_hits[docs[idx][id_field]] = (rank, source_type)
    log.info(
        "    BM25: 법령 %d건, 판례 %d건",
        sum(1 for _, st in bm25_hits.values() if st == "law"),
        sum(1 for _, st in bm25_hits.values() if st == "precedent"),
    )

    # Dense (embed_vertex + embed_kure 병렬 임베딩, 동일 doc_id는 최고 rank 유지)
    def _embed_and_search(col: str) -> list[tuple[str, int, str]]:
        query_vec = dense_retrieval.embed_query(payload["dense_query"], col)
        hits = []
        for chunks, source_type, id_field in [
            (corpus["law_chunks"][col], "law", "clause_key"),
            (corpus["prec_chunks"][col], "precedent", "case_number"),
        ]:
            rows = dense_retrieval.search_similar(query_vec, chunks, col, TOP_K)
            for rank, (_, row) in enumerate(rows.iterrows(), 1):
                hits.append((str(row[id_field]), rank, source_type))
        return hits

    dense_hits: dict[str, tuple[int, str]] = {}
    with ThreadPoolExecutor(max_workers=EMBED_WORKERS) as pool:
        for hit_list in pool.map(_embed_and_search, EMBED_COLS):
            for doc_id, rank, source_type in hit_list:
                if doc_id not in dense_hits or rank < dense_hits[doc_id][0]:
                    dense_hits[doc_id] = (rank, source_type)
    log.info(
        "    Dense: 법령 %d건, 판례 %d건",
        sum(1 for _, st in dense_hits.values() if st == "law"),
        sum(1 for _, st in dense_hits.values() if st == "precedent"),
    )

    # RRF
    all_ids = set(bm25_hits) | set(dense_hits)
    scored = []
    for doc_id in all_ids:
        b_rank = bm25_hits[doc_id][0] if doc_id in bm25_hits else 1000
        d_rank = dense_hits[doc_id][0] if doc_id in dense_hits else 1000
        source_type = (bm25_hits.get(doc_id) or dense_hits.get(doc_id))[1]
        scored.append({
            "doc_id": doc_id,
            "source_type": source_type,
            "rrf_score": round(1 / (RRF_K + b_rank) + 1 / (RRF_K + d_rank), 6),
            "bm25_rank": b_rank if b_rank != 1000 else None,
            "dense_rank": d_rank if d_rank != 1000 else None,
        })

    scored.sort(key=lambda x: (
        -x["rrf_score"],
        x["bm25_rank"] if x["bm25_rank"] is not None else 1000,
        x["dense_rank"] if x["dense_rank"] is not None else 1000,
        x["doc_id"],
    ))

    results = scored[:TOP_K]
    for rank, item in enumerate(results, 1):
        item["rank"] = rank

    bm25_results = sorted(
        [{"doc_id": doc_id, "source_type": st, "rank": rank} for doc_id, (rank, st) in bm25_hits.items()],
        key=lambda x: x["rank"],
    )
    dense_results = sorted(
        [{"doc_id": doc_id, "source_type": st, "rank": rank} for doc_id, (rank, st) in dense_hits.items()],
        key=lambda x: x["rank"],
    )

    log.info("    RRF 최종: %d건", len(results))
    return {"bm25": bm25_results, "dense": dense_results, "rrf": results}


RESULTS_PATH = Path(__file__).resolve().parent / "eval_results.json"


def _recall_at_k(
    per_clause: list[dict],
    method: str,
    k: int,
    gt_laws: set[str],
    gt_cases: set[str],
) -> dict:
    pool_laws: set[str] = set()
    pool_cases: set[str] = set()
    for clause_result in per_clause:
        for r in clause_result[method][:k]:
            if r["source_type"] == "law":
                pool_laws.add(r["doc_id"])
            else:
                pool_cases.add(r["doc_id"])
    law_hits = _count_hits(gt_laws, pool_laws)
    prec_hits = _count_hits(gt_cases, pool_cases)
    law_total = len(gt_laws)
    prec_total = len(gt_cases)
    return {
        "law_hits": law_hits,
        "law_total": law_total,
        "law_recall": round(law_hits / law_total, 4) if law_total else None,
        "precedent_hits": prec_hits,
        "precedent_total": prec_total,
        "precedent_recall": round(prec_hits / prec_total, 4) if prec_total else None,
    }


def _count_hits(gt_set: set[str], pool: set[str]) -> int:
    """GT 항목 중 pool에서 prefix 매칭되는 항목 수를 반환한다.

    검색 결과 doc_id가 GT의 하위 조항일 수 있으므로 (예: GT=제7조, 결과=제7조_제1항)
    GT가 retrieved doc_id의 접두어인 경우도 hit으로 처리한다.
    """
    count = 0
    for gt in gt_set:
        if any(doc_id == gt or doc_id.startswith(gt + "_") for doc_id in pool):
            count += 1
    return count


def _write_results(results: list[dict]) -> None:
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    log.info("▶ eval_set.json 로드: %s", EVAL_SET_PATH)
    cases = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
    log.info("  케이스 %d개", len(cases))

    corpus = load_corpus()

    case_results = []
    for i, case in enumerate(cases):
        case_id = case["id"]
        clauses = [c["normalized"] for c in case["clauses"]]
        gt_laws = set(case["gt_laws"])
        gt_cases = set(case["gt_cases"])
        log.info(
            "[%d/%d] %s: 특약 %d개, gt_laws=%d, gt_cases=%d",
            i + 1, len(cases), case_id, len(clauses), len(gt_laws), len(gt_cases),
        )

        per_clause: list[dict] = [{"bm25": [], "dense": [], "rrf": []} for _ in clauses]
        def _retrieve(args: tuple[int, str]) -> tuple[int, dict]:
            j, clause = args
            log.info("  특약 [%d/%d]: %s...", j + 1, len(clauses), clause[:60])
            return j, retrieve_clause(clause, corpus)

        with ThreadPoolExecutor(max_workers=CLAUSE_WORKERS) as pool:
            futures = {pool.submit(_retrieve, (j, c)): j for j, c in enumerate(clauses)}
            for future in as_completed(futures):
                try:
                    j, results = future.result()
                    per_clause[j] = results
                except Exception as exc:
                    log.error("  특약 검색 실패: %s", exc)

        # Recall@K: BM25 / Dense / RRF 각각 계산
        recall_at_k: dict[int, dict] = {}
        for k in RECALL_K_VALUES:
            recall_at_k[k] = {
                method: _recall_at_k(per_clause, method, k, gt_laws, gt_cases)
                for method in ("bm25", "dense", "rrf")
            }

        rrf20 = recall_at_k[20]["rrf"]
        log.info(
            "  Recall@20 [RRF]  법령: %.3f (%d/%d)  판례: %.3f (%d/%d)",
            rrf20["law_recall"] or 0, rrf20["law_hits"], rrf20["law_total"],
            rrf20["precedent_recall"] or 0, rrf20["precedent_hits"], rrf20["precedent_total"],
        )
        clause_records = [
            {
                "clause": clauses[j],
                "bm25": per_clause[j]["bm25"],
                "dense": per_clause[j]["dense"],
                "rrf": per_clause[j]["rrf"],
            }
            for j in range(len(clauses))
        ]
        case_results.append({
            "id": case_id,
            "gt_laws": list(gt_laws),
            "gt_cases": list(gt_cases),
            "recall_at_k": recall_at_k,
            "clauses": clause_records,
        })
        _write_results(case_results)
        log.info("  결과 저장: %s (%d/%d)", RESULTS_PATH, i + 1, len(cases))

    # 전체 집계
    print("\n" + "=" * 70)
    print(f"전체 Recall 집계 ({len(case_results)}케이스)")
    print("=" * 70)
    for k in RECALL_K_VALUES:
        print(f"  Recall@{k:2d}")
        for method in ("bm25", "dense", "rrf"):
            lh = sum(r["recall_at_k"][k][method]["law_hits"] for r in case_results)
            lt = sum(r["recall_at_k"][k][method]["law_total"] for r in case_results)
            ph = sum(r["recall_at_k"][k][method]["precedent_hits"] for r in case_results)
            pt = sum(r["recall_at_k"][k][method]["precedent_total"] for r in case_results)
            print(
                f"    [{method:5s}]  법령: {lh/lt:.3f} ({lh}/{lt})  "
                f"판례: {ph/pt:.3f} ({ph}/{pt})"
            )


if __name__ == "__main__":
    main()
