"""Alpha 하이퍼파라미터 스윕 평가

--mode 1d : 단일 alpha (법령+판례 동일 적용)
--mode 2d : 법령/판례 별도 alpha (alpha_law × alpha_prec 2D 그리드)

사용 예:
    # 1D sweep (step 0.1)
    python evaluation/alpha_sweep_eval.py --embed-col embed_kure --mode 1d --alpha-step 0.1 --top-k 10

    # 2D sweep (step 0.2)
    python evaluation/alpha_sweep_eval.py --embed-col embed_kure --mode 2d --alpha-step 0.2 --top-k 10
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

SWEEP_CASE_WORKERS = 3  # 케이스 단위 병렬 처리 스레드 수

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.legal_retrieval_eval_multi import (
    DEFAULT_RECALL_K_VALUES,
    RESULTS_DIR,
    SEMANTIC_EMBED_CONFIGS,
    DatasetValidationError,
    PipelineImportError,
    average,
    calculate_recall_by_k,
    load_dataset,
    load_bm25_corpus,
    load_semantic_chunks,
    log_progress,
    minmax_normalize,
    ratio,
    run_bm25_retrieval,
    run_semantic_retrieval_for_embed_col,
    select_cases,
    semantic_embed_config,
)
from pipeline.retrieval.evaluation_retrieval import expand_case_queries_with_llm


# ── 공통 리랭킹 ───────────────────────────────────────────────────────────

def run_alpha_hybrid(
    keyword_results: list[dict[str, Any]],
    semantic_results: list[dict[str, Any]],
    alpha_law: float,
    alpha_prec: float,
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """법령/판례별 alpha를 적용한 hybrid 리랭킹.
    1D 모드: alpha_law == alpha_prec 로 호출
    2D 모드: alpha_law != alpha_prec 가능
    """
    clause_indices: set[int] = set()
    for r in keyword_results + semantic_results:
        clause_indices.add(int(r["clause_index"]))

    all_results: list[dict[str, Any]] = []

    for clause_idx in sorted(clause_indices):
        bm25_clause = [r for r in keyword_results if int(r["clause_index"]) == clause_idx]
        dense_clause = [r for r in semantic_results if int(r["clause_index"]) == clause_idx]

        result_map: dict[str, dict[str, Any]] = {}

        for r in bm25_clause:
            rid = str(r["result_id"])
            if rid not in result_map:
                result_map[rid] = dict(r)
                result_map[rid]["dense_score_raw"] = 0.0
            result_map[rid]["bm25_score_raw"] = float(
                r.get("keyword_score", r.get("score", 0.0))
            )

        for r in dense_clause:
            rid = str(r["result_id"])
            if rid not in result_map:
                result_map[rid] = dict(r)
                result_map[rid]["bm25_score_raw"] = 0.0
            result_map[rid]["dense_score_raw"] = float(
                r.get("semantic_score", r.get("similarity", r.get("score", 0.0)))
            )

        if not result_map:
            continue

        # dict 기반 min-max 정규화 (legal_retrieval_eval_multi.minmax_normalize 공유)
        norm_bm25 = minmax_normalize({rid: e["bm25_score_raw"] for rid, e in result_map.items()})
        norm_dense = minmax_normalize({rid: e["dense_score_raw"] for rid, e in result_map.items()})

        scored: list[tuple[float, str, dict[str, Any]]] = []
        for rid, entry in result_map.items():
            stype = entry.get("source_type", "")
            alpha = alpha_prec if stype == "precedent" else alpha_law
            combined = alpha * norm_bm25.get(rid, 0.0) + (1.0 - alpha) * norm_dense.get(rid, 0.0)
            scored.append((combined, rid, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        for rank, (score, _rid, entry) in enumerate(scored[:top_k], 1):
            result = dict(entry)
            result["rank"] = rank
            result["score"] = round(score, 8)
            result["clause_index"] = clause_idx
            all_results.append(result)

    return all_results


# ── 케이스 단위 평가 ──────────────────────────────────────────────────────

def _pair_key(al: float, ap: float) -> str:
    return f"{al:.4f}_{ap:.4f}"


def evaluate_case(
    case: dict[str, Any],
    embed_col: str,
    alpha_pairs: list[tuple[float, float]],
    top_k: int,
    bm25_top_k: int = 40,
    dense_top_k: int = 80,
) -> dict[str, Any]:
    """BM25+Dense를 1회 수행 후 모든 (alpha_law, alpha_prec) 조합을 평가."""
    expanded_queries = expand_case_queries_with_llm(case)

    keyword_results = run_bm25_retrieval(
        case=case, expanded_queries=expanded_queries, top_k=bm25_top_k,
    )
    semantic_results = run_semantic_retrieval_for_embed_col(
        expanded_queries=expanded_queries, top_k=dense_top_k, semantic_embed_col=embed_col,
    )

    law_refs  = case["law_references"]
    prec_refs = case["precedent_references"]

    alpha_metrics: dict[str, dict[str, Any]] = {}
    for al, ap in alpha_pairs:
        key = _pair_key(al, ap)
        reranked = run_alpha_hybrid(
            keyword_results=keyword_results,
            semantic_results=semantic_results,
            alpha_law=al, alpha_prec=ap, top_k=top_k,
        )
        recall_by_k = calculate_recall_by_k(
            law_references=law_refs, precedent_references=prec_refs,
            reranked_results=reranked,
        )
        alpha_metrics[key] = {"recall_by_k": recall_by_k}

    return {
        "case_id": case["case_id"],
        "status": "completed",
        "law_references": law_refs,
        "precedent_references": prec_refs,
        "alpha_metrics": alpha_metrics,
    }


# ── 집계 ─────────────────────────────────────────────────────────────────

def aggregate(
    case_results: list[dict[str, Any]],
    alpha_pairs: list[tuple[float, float]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for al, ap in alpha_pairs:
        pk = _pair_key(al, ap)
        micro: dict[str, Any] = {}
        macro_law   = {str(k): [] for k in DEFAULT_RECALL_K_VALUES}
        macro_prec  = {str(k): [] for k in DEFAULT_RECALL_K_VALUES}
        macro_integ = {str(k): [] for k in DEFAULT_RECALL_K_VALUES}

        for k in DEFAULT_RECALL_K_VALUES:
            kk = str(k)
            lh = sum(cr["alpha_metrics"].get(pk, {}).get("recall_by_k", {}).get(kk, {}).get("law_hits", 0) for cr in case_results)
            lt = sum(cr["alpha_metrics"].get(pk, {}).get("recall_by_k", {}).get(kk, {}).get("law_total", 0) for cr in case_results)
            ph = sum(cr["alpha_metrics"].get(pk, {}).get("recall_by_k", {}).get(kk, {}).get("precedent_hits", 0) for cr in case_results)
            pt = sum(cr["alpha_metrics"].get(pk, {}).get("recall_by_k", {}).get(kk, {}).get("precedent_total", 0) for cr in case_results)
            micro[kk] = {
                "law": ratio(lh, lt), "law_hits": lh, "law_total": lt,
                "precedent": ratio(ph, pt), "precedent_hits": ph, "precedent_total": pt,
                "integrated": ratio(lh + ph, lt + pt),
            }
            for cr in case_results:
                rb = cr["alpha_metrics"].get(pk, {}).get("recall_by_k", {}).get(kk, {})
                macro_law[kk].append(float(rb.get("law", 0.0)))
                macro_prec[kk].append(float(rb.get("precedent", 0.0)))
                macro_integ[kk].append(ratio(
                    int(rb.get("law_hits", 0)) + int(rb.get("precedent_hits", 0)),
                    int(rb.get("law_total", 0)) + int(rb.get("precedent_total", 0)),
                ))

        summary[pk] = {
            "alpha_law": al, "alpha_prec": ap,
            "micro_recall": micro,
            "macro_recall": {
                kk: {"law": average(macro_law[kk]), "precedent": average(macro_prec[kk]),
                     "integrated": average(macro_integ[kk])}
                for kk in macro_law
            },
        }
    return summary


def find_best(
    summary: dict[str, Any], primary_k: int = 10,
) -> tuple[float, float, float]:
    best_al, best_ap, best = 0.0, 0.0, -1.0
    for data in summary.values():
        score = data["micro_recall"].get(str(primary_k), {}).get("integrated", 0.0)
        if score > best:
            best = score
            best_al, best_ap = data["alpha_law"], data["alpha_prec"]
    return best_al, best_ap, best


# ── 출력: 1D ────────────────────────────────────────────────────────────

def print_1d_table(
    summary: dict[str, Any],
    alphas: list[float],
    k_values: list[int] | None = None,
) -> None:
    if k_values is None:
        k_values = [3, 5, 10, 20]
    header = f"{'alpha':>7}  " + "  ".join(
        f"micro@{k}(int)  macro@{k}(int)" for k in k_values
    )
    print(header)
    print("-" * len(header))
    for a in alphas:
        pk = _pair_key(a, a)
        parts = []
        for k in k_values:
            kk = str(k)
            mi = summary.get(pk, {}).get("micro_recall", {}).get(kk, {}).get("integrated", 0.0)
            ma = summary.get(pk, {}).get("macro_recall", {}).get(kk, {}).get("integrated", 0.0)
            parts.append(f"{mi:.4f}         {ma:.4f}")
        print(f"{a:>7.4f}  " + "  ".join(parts))


# ── 출력: 2D ────────────────────────────────────────────────────────────

def print_2d_table(
    summary: dict[str, Any],
    alpha_pairs: list[tuple[float, float]],
    primary_k: int = 10,
) -> None:
    law_vals  = sorted(set(al for al, _ in alpha_pairs))
    prec_vals = sorted(set(ap for _, ap in alpha_pairs))

    def _grid(metric: str) -> None:
        header = f"{'α_law\\α_prec':>14}" + "".join(f"   {ap:.2f}" for ap in prec_vals)
        print(header)
        print("-" * len(header))
        for al in law_vals:
            row = f"{al:>14.2f}"
            for ap in prec_vals:
                val = summary.get(_pair_key(al, ap), {}).get("micro_recall", {}).get(str(primary_k), {}).get(metric, 0.0)
                row += f"  {val:.4f}"
            print(row)

    print(f"\n=== micro integrated@{primary_k} (행=alpha_law / 열=alpha_prec) ===")
    _grid("integrated")
    print(f"\n=== micro law recall@{primary_k} ===")
    _grid("law")
    print(f"\n=== micro precedent recall@{primary_k} ===")
    _grid("precedent")


# ── 리포트 저장 ───────────────────────────────────────────────────────────

def save_report(report: dict[str, Any], mode: str, output_path: Path | None) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = RESULTS_DIR / f"alpha_sweep_{mode}_{ts}.json"
    else:
        path = RESULTS_DIR / output_path.expanduser().name
    report["report_path"] = str(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


# ── 메인 ─────────────────────────────────────────────────────────────────

def run_sweep(
    input_path: Path,
    embed_col: str,
    alpha_pairs: list[tuple[float, float]],
    top_k: int,
    primary_k: int,
    mode: str,
    case_id: str | None,
    output_path: Path | None,
    bm25_top_k: int = 40,
    dense_top_k: int = 80,
) -> Path:
    log_progress(
        f"alpha_sweep_{mode}_start embed_col={embed_col} pairs={len(alpha_pairs)} "
        f"top_k={top_k} bm25_top_k={bm25_top_k} dense_top_k={dense_top_k}"
    )

    dataset = load_dataset(input_path)
    cases = select_cases(dataset, case_id)
    log_progress(f"dataset_loaded cases={len(cases)}")

    load_bm25_corpus()
    load_semantic_chunks(embed_col)

    case_results: list[dict[str, Any]] = [None] * len(cases)  # 순서 보존용
    completed = 0

    def _run_one(idx_case: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        idx, case = idx_case
        log_progress(f"case_start {idx + 1}/{len(cases)} case_id={case['case_id']}")
        try:
            result = evaluate_case(
                case=case, embed_col=embed_col,
                alpha_pairs=alpha_pairs, top_k=top_k,
                bm25_top_k=bm25_top_k, dense_top_k=dense_top_k,
            )
        except Exception as exc:  # noqa: BLE001
            log_progress(f"case_failed case_id={case['case_id']} error={exc}")
            result = {
                "case_id": case["case_id"], "status": "failed",
                "error": str(exc),
                "law_references": case.get("law_references", []),
                "precedent_references": case.get("precedent_references", []),
                "alpha_metrics": {},
            }
        return idx, result

    with ThreadPoolExecutor(max_workers=SWEEP_CASE_WORKERS) as pool:
        futures = {pool.submit(_run_one, (i, case)): i for i, case in enumerate(cases)}
        for fut in as_completed(futures):
            idx, result = fut.result()
            case_results[idx] = result  # type: ignore[index]
            completed += 1
            log_progress(
                f"case_done {completed}/{len(cases)} "
                f"case_id={result['case_id']} status={result['status']}"
            )

    summary = aggregate(case_results, alpha_pairs)
    best_al, best_ap, best_score = find_best(summary, primary_k=primary_k)

    report = {
        "schema_version": f"alpha_sweep_eval.v2_{mode}",
        "run": {
            "mode": mode,
            "input_path": str(input_path),
            "embed_col": embed_col,
            "embed_config": semantic_embed_config(embed_col),
            "alpha_pairs": alpha_pairs,
            "top_k": top_k,
            "bm25_top_k": bm25_top_k,
            "dense_top_k": dense_top_k,
            "primary_k": primary_k,
            "case_count": len(cases),
        },
        "best_alpha_law": best_al,
        "best_alpha_prec": best_ap,
        "best_micro_integrated": best_score,
        "summary": summary,
        "cases": case_results,
    }

    path = save_report(report, mode, output_path)
    log_progress(f"report_saved path={path}")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Alpha sweep: 1D (단일) 또는 2D (법령/판례 분리)"
    )
    parser.add_argument("--input", default=str(PROJECT_ROOT / "evaluation" / "eval_set.json"))
    parser.add_argument(
        "--embed-col",
        nargs="+",
        choices=list(SEMANTIC_EMBED_CONFIGS),
        default=["embed_kure"],
        help="Dense 임베딩 모델 (여러 개 가능, 예: embed_kure embed_e5 embed_vertex)",
    )
    parser.add_argument("--mode", choices=["1d", "2d"], default="1d",
                        help="1d=단일 alpha / 2d=법령·판례 분리 alpha (default: 1d)")
    parser.add_argument("--alpha-start", type=float, default=0.0)
    parser.add_argument("--alpha-end",   type=float, default=1.0)
    parser.add_argument("--alpha-step",  type=float, default=0.1,
                        help="alpha 간격 (1d: 11단계, 2d: step=0.2 추천 → 6×6=36 조합)")
    parser.add_argument("--top-k",     type=int, default=20,
                        help="최종 리랭킹 후 반환할 문서 수 (default: 20)")
    parser.add_argument("--primary-k", type=int, default=10,
                        help="최적 alpha 선택 기준 K (default: 10)")
    parser.add_argument("--bm25-top-k", type=int, default=40,
                        help="BM25 1차 검색 후보 수 (default: 40). 클수록 후보 풀이 넓어집니다.")
    parser.add_argument("--dense-top-k", type=int, default=80,
                        help="Dense 1차 검색 후보 수 (default: 80). 클수록 후보 풀이 넓어집니다.")
    parser.add_argument("--case-id", help="특정 case_id만 평가")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    n = round((args.alpha_end - args.alpha_start) / args.alpha_step)
    alphas = [round(args.alpha_start + i * args.alpha_step, 8) for i in range(n + 1)]
    alphas = [a for a in alphas if args.alpha_start - 1e-9 <= a <= args.alpha_end + 1e-9]

    if args.mode == "1d":
        alpha_pairs = [(a, a) for a in alphas]
    else:
        alpha_pairs = [(al, ap) for al in alphas for ap in alphas]

    embed_cols: list[str] = args.embed_col  # nargs="+" → list

    for embed_col in embed_cols:
        print(f"\n{'='*60}")
        print(f"embed_col={embed_col}")
        print('='*60)
        try:
            report_path = run_sweep(
                input_path=Path(args.input),
                embed_col=embed_col,
                alpha_pairs=alpha_pairs,
                top_k=args.top_k,
                primary_k=args.primary_k,
                mode=args.mode,
                case_id=args.case_id,
                output_path=Path(args.output) if args.output else None,
                bm25_top_k=args.bm25_top_k,
                dense_top_k=args.dense_top_k,
            )
        except (PipelineImportError, DatasetValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)

        print(f"\n=== Alpha Sweep ({args.mode.upper()}) — embed_col={embed_col}, top_k={args.top_k} ===")
        print(f"케이스 수: {report['run']['case_count']}\n")

        if args.mode == "1d":
            print_1d_table(report["summary"], alphas)
            best = report["best_alpha_law"]
            print(f"\n최적 alpha={best:.4f}  micro_integrated@{args.primary_k}={report['best_micro_integrated']:.6f}")
        else:
            print_2d_table(report["summary"], alpha_pairs, primary_k=args.primary_k)
            print(
                f"\n최적 조합: alpha_law={report['best_alpha_law']:.4f}  "
                f"alpha_prec={report['best_alpha_prec']:.4f}  "
                f"micro_integrated@{args.primary_k}={report['best_micro_integrated']:.6f}"
            )

        print(f"report_path={report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
