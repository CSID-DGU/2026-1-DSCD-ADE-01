"""Dense 검색 후보 수(dense_top_k) 스윕 평가

dense_top_k를 변화시키며 Recall Ceiling을 측정한다.
  - ceiling_recall@N : 상위 N개 후보를 모두 정답으로 간주했을 때의 recall
                       (해당 후보 수에서 도달 가능한 최대 recall)
  - recall@eval_k    : 고정 eval_k (5/10/20) 기준 recall — dense_top_k에 무관하게
                       일정 구간에선 동일하므로 "천장이 어디서 막히는지" 확인용

사용 예:
    python evaluation/top_k_sweep_eval.py
    python evaluation/top_k_sweep_eval.py --top-k-candidates 50 100 200 300 500
    python evaluation/top_k_sweep_eval.py --eval-k 5 10 20 --threshold 0.0
    python evaluation/top_k_sweep_eval.py --qe-cache evaluation/results/<기존결과>.json
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.legal_retrieval_eval_multi import (
    RESULTS_DIR,
    DatasetValidationError,
    PipelineImportError,
    count_law_hits,
    count_precedent_hits,
    load_dataset,
    load_qe_cache,
    log_progress,
    make_cached_expand_fn,
    ratio,
    average,
    select_cases,
)
from pipeline.retrieval import dense_retrieval
from pipeline.retrieval.dense_retrieval import EMBED_COL, LAW_TABLE, PREC_TABLE
from pipeline.retrieval.evaluation_retrieval import expand_case_queries_with_llm

TOP_K_SWEEP_WORKERS = 3

# 청크 캐시 (케이스마다 CSV 재로드 방지)
_law_chunks  = None
_prec_chunks = None
_chunks_lock = threading.Lock()


def _get_chunks():
    global _law_chunks, _prec_chunks
    if _law_chunks is None:
        with _chunks_lock:
            if _law_chunks is None:
                log_progress("chunks_load_start")
                _law_chunks  = dense_retrieval.load_chunks(LAW_TABLE)
                _prec_chunks = dense_retrieval.load_chunks(PREC_TABLE)
                log_progress("chunks_load_done")
    return _law_chunks, _prec_chunks


# ── 케이스 단위 평가 ──────────────────────────────────────────────────────────

def evaluate_case(
    case: dict[str, Any],
    candidate_counts: list[int],
    eval_k_values: list[int],
    threshold: float = 0.0,
    expand_fn=None,
) -> dict[str, Any]:
    """Dense 검색 1회(max_candidates) 수행 후 모든 candidate_count × eval_k 조합 평가.

    Args:
        candidate_counts: 스윕할 dense_top_k 후보 수 목록 (예: [50, 100, 200, 300, 500])
        eval_k_values:    고정 평가 K 목록 (예: [5, 10, 20])
        threshold:        유사도 최솟값 (천장 측정 목적이면 0.0 권장)
    """
    if expand_fn is None:
        expand_fn = expand_case_queries_with_llm
    expanded_queries = expand_fn(case)
    law_chunks, prec_chunks = _get_chunks()

    max_candidates = max(candidate_counts)

    # 최대 후보 수로 1회 검색 → 이후 슬라이싱으로 각 candidate_count 시뮬레이션
    raw_results: list[dict[str, Any]] = []
    for qi, query in enumerate(expanded_queries):
        dense_query = query["retrieval_payload"]["dense_query"]
        query_vec   = dense_retrieval.embed_query(dense_query)
        for rows, source_type in [
            (dense_retrieval.search_similar(query_vec, law_chunks,  top_k=max_candidates, min_similarity=threshold), "law"),
            (dense_retrieval.search_similar(query_vec, prec_chunks, top_k=max_candidates, min_similarity=threshold), "precedent"),
        ]:
            for _, row in rows.iterrows():
                rd = row.to_dict()
                raw_results.append({
                    "source_type":  source_type,
                    "result_id":    str(rd.get("clause_key") or rd.get("case_id", "")),
                    "clause_key":   rd.get("clause_key"),
                    "law_name":     rd.get("law_name"),
                    "article_key":  rd.get("article_key"),
                    "case_name":    rd.get("case_name"),
                    "clause_index": qi,
                    "similarity":   float(rd.get("similarity", 0.0)),
                })

    # 동일 문서가 여러 쿼리에서 중복 등장하면 최고 유사도만 보존
    seen: dict[str, int] = {}
    for i, r in enumerate(raw_results):
        key = r["source_type"] + "|" + r["result_id"]
        if key not in seen or raw_results[seen[key]]["similarity"] < r["similarity"]:
            seen[key] = i
    raw_results = [raw_results[i] for i in seen.values()]

    # 유사도 내림차순 정렬
    raw_results = sorted(raw_results, key=lambda x: x["similarity"], reverse=True)

    law_refs   = case["law_references"]
    prec_refs  = case["precedent_references"]
    law_total  = len(law_refs)
    prec_total = len(prec_refs)

    candidate_metrics: dict[str, Any] = {}
    for n in candidate_counts:
        top_n = raw_results[:n]

        # 천장 recall: 상위 N개 전부를 정답 후보로 사용
        ceiling_lh = count_law_hits(law_refs, top_n)
        ceiling_ph = count_precedent_hits(prec_refs, top_n)

        # 고정 eval_k 별 recall (eval_k <= n 인 경우만 의미 있음)
        by_k: dict[str, Any] = {}
        for k in eval_k_values:
            top_k = raw_results[:k]
            lh = count_law_hits(law_refs, top_k)
            ph = count_precedent_hits(prec_refs, top_k)
            by_k[str(k)] = {
                "law_hits":          lh,
                "law_total":         law_total,
                "law_recall":        ratio(lh, law_total),
                "prec_hits":         ph,
                "prec_total":        prec_total,
                "prec_recall":       ratio(ph, prec_total),
                "integrated_hits":   lh + ph,
                "integrated_total":  law_total + prec_total,
                "integrated_recall": ratio(lh + ph, law_total + prec_total),
            }

        candidate_metrics[str(n)] = {
            "actual_count":              len(top_n),
            "ceiling_law_hits":          ceiling_lh,
            "ceiling_prec_hits":         ceiling_ph,
            "ceiling_law_recall":        ratio(ceiling_lh, law_total),
            "ceiling_prec_recall":       ratio(ceiling_ph, prec_total),
            "ceiling_integrated_recall": ratio(ceiling_lh + ceiling_ph, law_total + prec_total),
            "by_k":                      by_k,
        }

    return {
        "case_id":           case["case_id"],
        "status":            "completed",
        "expanded_queries":  expanded_queries,
        "candidate_metrics": candidate_metrics,
    }


# ── 집계 ─────────────────────────────────────────────────────────────────────

def aggregate(
    case_results: list[dict[str, Any]],
    candidate_counts: list[int],
    eval_k_values: list[int],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for n in candidate_counts:
        nn = str(n)
        # 천장 recall 집계
        ceiling_lh = sum(
            cr["candidate_metrics"].get(nn, {}).get("ceiling_law_hits", 0)
            for cr in case_results
        )
        ceiling_lt = sum(
            cr["candidate_metrics"].get(nn, {}).get("by_k", {}).get(str(eval_k_values[0]), {}).get("law_total", 0)
            for cr in case_results
        )
        ceiling_ph = sum(
            cr["candidate_metrics"].get(nn, {}).get("ceiling_prec_hits", 0)
            for cr in case_results
        )
        ceiling_pt = sum(
            cr["candidate_metrics"].get(nn, {}).get("by_k", {}).get(str(eval_k_values[0]), {}).get("prec_total", 0)
            for cr in case_results
        )
        macro_ceiling = average([
            cr["candidate_metrics"].get(nn, {}).get("ceiling_integrated_recall", 0.0)
            for cr in case_results
        ])
        avg_actual = average([
            cr["candidate_metrics"].get(nn, {}).get("actual_count", 0)
            for cr in case_results
        ])

        by_k: dict[str, Any] = {}
        for k in eval_k_values:
            kk = str(k)
            lh = sum(cr["candidate_metrics"].get(nn, {}).get("by_k", {}).get(kk, {}).get("law_hits", 0) for cr in case_results)
            lt = sum(cr["candidate_metrics"].get(nn, {}).get("by_k", {}).get(kk, {}).get("law_total", 0) for cr in case_results)
            ph = sum(cr["candidate_metrics"].get(nn, {}).get("by_k", {}).get(kk, {}).get("prec_hits", 0) for cr in case_results)
            pt = sum(cr["candidate_metrics"].get(nn, {}).get("by_k", {}).get(kk, {}).get("prec_total", 0) for cr in case_results)
            macro_int = average([
                cr["candidate_metrics"].get(nn, {}).get("by_k", {}).get(kk, {}).get("integrated_recall", 0.0)
                for cr in case_results
            ])
            by_k[kk] = {
                "micro_law":        ratio(lh, lt),
                "micro_prec":       ratio(ph, pt),
                "micro_integrated": ratio(lh + ph, lt + pt),
                "macro_integrated": macro_int,
            }

        summary[nn] = {
            "dense_top_k":              n,
            "micro_ceiling_law":        ratio(ceiling_lh, ceiling_lt),
            "micro_ceiling_prec":       ratio(ceiling_ph, ceiling_pt),
            "micro_ceiling_integrated": ratio(ceiling_lh + ceiling_ph, ceiling_lt + ceiling_pt),
            "macro_ceiling_integrated": macro_ceiling,
            "avg_actual_count":         round(avg_actual, 1),
            "by_k":                     by_k,
        }
    return summary


def find_best(
    summary: dict[str, Any],
    primary_eval_k: int = 10,
) -> tuple[int, float]:
    """ceiling_integrated_recall 기준으로 최적 dense_top_k 반환."""
    best_n, best_score = 0, -1.0
    for nn, data in summary.items():
        score = data.get("micro_ceiling_integrated", 0.0)
        if score > best_score:
            best_score = score
            best_n = data["dense_top_k"]
    return best_n, best_score


# ── 출력 ─────────────────────────────────────────────────────────────────────

def print_table(
    summary: dict[str, Any],
    candidate_counts: list[int],
    eval_k_values: list[int],
) -> None:
    eval_k_header = "  ".join(f"@{k}(micro)" for k in eval_k_values)
    header = f"{'dense_top_k':>11}  {'ceiling(micro)':>14}  {eval_k_header}  {'avg_cnt':>7}"
    print(header)
    print("-" * len(header))
    for n in candidate_counts:
        nn = str(n)
        d = summary.get(nn, {})
        ceiling = d.get("micro_ceiling_integrated", 0.0)
        avg_cnt = d.get("avg_actual_count", 0.0)
        parts = []
        for k in eval_k_values:
            mi = d.get("by_k", {}).get(str(k), {}).get("micro_integrated", 0.0)
            parts.append(f"{mi:.4f}")
        print(f"{n:>11}  {ceiling:>14.4f}  " + "  ".join(f"{p:>7}" for p in parts) + f"  {avg_cnt:>7.1f}")


# ── 실행 ─────────────────────────────────────────────────────────────────────

def run_sweep(
    input_path: Path,
    candidate_counts: list[int],
    eval_k_values: list[int],
    primary_eval_k: int,
    threshold: float,
    case_id: str | None,
    output_path: Path | None,
    qe_cache_path: Path | None = None,
) -> Path:
    log_progress(
        f"top_k_sweep_start candidates={candidate_counts} eval_k={eval_k_values} threshold={threshold}"
    )

    dataset = load_dataset(input_path)
    cases   = select_cases(dataset, case_id)
    log_progress(f"dataset_loaded cases={len(cases)}")

    _get_chunks()  # 병렬 실행 전 사전 로드

    if qe_cache_path is not None:
        cache = load_qe_cache(qe_cache_path)
        expand_fn = make_cached_expand_fn(cache)
        log_progress(f"qe_cache_loaded path={qe_cache_path} entries={len(cache)}")
    else:
        expand_fn = expand_case_queries_with_llm

    case_results: list[dict[str, Any]] = [None] * len(cases)  # type: ignore[list-item]
    completed = 0

    def _run_one(idx_case: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        idx, case = idx_case
        log_progress(f"case_start {idx + 1}/{len(cases)} case_id={case['case_id']}")
        try:
            result = evaluate_case(
                case=case,
                candidate_counts=candidate_counts,
                eval_k_values=eval_k_values,
                threshold=threshold,
                expand_fn=expand_fn,
            )
        except Exception as exc:  # noqa: BLE001
            log_progress(f"case_failed case_id={case['case_id']} error={exc}")
            result = {
                "case_id":           case["case_id"],
                "status":            "failed",
                "error":             str(exc),
                "candidate_metrics": {},
            }
        return idx, result

    with ThreadPoolExecutor(max_workers=TOP_K_SWEEP_WORKERS) as pool:
        futures = {pool.submit(_run_one, (i, case)): i for i, case in enumerate(cases)}
        for fut in as_completed(futures):
            idx, result = fut.result()
            case_results[idx] = result  # type: ignore[index]
            completed += 1
            log_progress(
                f"case_done {completed}/{len(cases)} "
                f"case_id={result['case_id']} status={result['status']}"
            )

    summary = aggregate(case_results, candidate_counts, eval_k_values)
    best_n, best_score = find_best(summary, primary_eval_k)

    report = {
        "schema_version": "top_k_sweep_eval.v1",
        "run": {
            "input_path":      str(input_path),
            "embed_col":       EMBED_COL,
            "candidate_counts": candidate_counts,
            "eval_k_values":   eval_k_values,
            "primary_eval_k":  primary_eval_k,
            "threshold":       threshold,
            "case_count":      len(cases),
        },
        "best_dense_top_k":             best_n,
        "best_micro_ceiling_integrated": best_score,
        "summary":  summary,
        "cases":    case_results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        save_path = RESULTS_DIR / f"top_k_sweep_{ts}.json"
    else:
        save_path = RESULTS_DIR / output_path.name

    with save_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    log_progress(f"report_saved path={save_path}")
    return save_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dense 검색 후보 수(dense_top_k) 스윕 평가 — Recall Ceiling 측정"
    )
    parser.add_argument(
        "--input", default=str(PROJECT_ROOT / "evaluation" / "eval_set.json"),
    )
    parser.add_argument(
        "--top-k-candidates", type=int, nargs="+",
        default=[20, 50, 100, 150, 200, 300, 500],
        help="스윕할 dense_top_k 후보 수 목록 (default: 20 50 100 150 200 300 500)",
    )
    parser.add_argument(
        "--eval-k", type=int, nargs="+", default=[5, 10, 20],
        help="고정 평가 K 목록 (default: 5 10 20)",
    )
    parser.add_argument(
        "--primary-eval-k", type=int, default=10,
        help="최적 dense_top_k 선택 기준 K (default: 10, ceiling 기준이므로 큰 영향 없음)",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.0,
        help="유사도 필터 임계값 (default: 0.0 — recall 천장 측정용)",
    )
    parser.add_argument("--case-id", help="특정 case_id만 평가")
    parser.add_argument("--output")
    parser.add_argument(
        "--qe-cache",
        metavar="PATH",
        default=None,
        help=(
            "이전 실행 결과 JSON 경로. "
            "지정 시 QE LLM 호출을 스킵하고 캐시된 expanded_queries를 재사용합니다. "
            "캐시에 없는 case_id는 LLM을 호출합니다."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # eval_k 가 candidate_counts 최댓값보다 크면 의미 없는 값 제거
    max_candidates = max(args.top_k_candidates)
    eval_k_values  = sorted(set(args.eval_k))
    if any(k > max_candidates for k in eval_k_values):
        trimmed = [k for k in eval_k_values if k <= max_candidates]
        print(
            f"[경고] eval_k에 dense_top_k 최댓값({max_candidates})보다 큰 값이 있어 제거됨: "
            f"{[k for k in eval_k_values if k > max_candidates]}"
        )
        eval_k_values = trimmed if trimmed else [min(args.top_k_candidates)]

    try:
        report_path = run_sweep(
            input_path=Path(args.input),
            candidate_counts=sorted(args.top_k_candidates),
            eval_k_values=eval_k_values,
            primary_eval_k=args.primary_eval_k,
            threshold=args.threshold,
            case_id=args.case_id,
            output_path=Path(args.output) if args.output else None,
            qe_cache_path=Path(args.qe_cache) if args.qe_cache else None,
        )
    except (PipelineImportError, DatasetValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    candidate_counts = sorted(args.top_k_candidates)
    print(
        f"\n=== Top-K Sweep — embed_col={EMBED_COL}, threshold={args.threshold} ===\n"
        f"케이스 수: {report['run']['case_count']}\n"
        f"ceiling_recall = 해당 후보 N개를 전부 사용했을 때의 최대 도달 recall\n"
    )
    print_table(report["summary"], candidate_counts, eval_k_values)
    print(
        f"\n최적 dense_top_k={report['best_dense_top_k']}  "
        f"ceiling_micro_integrated={report['best_micro_ceiling_integrated']:.6f}"
    )
    print(f"report_path={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
