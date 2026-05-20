"""
RRF (Reciprocal Rank Fusion)
BM25 결과 (법령 + 판례) + Dense 결과 → RRF 합산 → TOP_N 반환

[사용 필드]
BM25 결과 JSON:
  - index                        : 특약 번호 (매칭 키)
  - special_terms                : 원본 특약 문장
  - top_matches[].rank           : BM25 순위
  - top_matches[].score          : BM25 점수 (RRF에서는 미사용, 참고용)
  - top_matches[].clause_key     : 법령 식별자
  - top_matches[].case_id        : 판례 식별자

Dense 결과 JSON:
  - special_terms                : 원본 특약 문장
  - results[].clause_key         : 법령 식별자
  - results[].case_id            : 판례 식별자
  - results[].similarity         : cosine similarity 점수
  - results[].child_text         : 법령 원문
  - results[].judgment_summary   : 판결 요지
"""

import json
from pathlib import Path

# ─── 설정 ─────────────────────────────────────────────────────────────────
# 경로 설정
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent

# 입력 경로
RETRIEVAL_DIR = BASE_DIR.parent.parent / "output" / "retrieval"

# 식별자 필드명
LAW_ID_FIELD  = "clause_key"
PREC_ID_FIELD = "case_id"

# RRF 파라미터
K      = 60  # RRF 상수 (Cormack et al. 2009 기본값)
TOP_N  = 5   # 최종 반환 수

# Dense 결과에서 특약당 몇 개까지 사용할지 (두 모델 합산 기준)
DENSE_TOP_K = 20

# 출력 파일
OUTPUT_DIR = BASE_DIR.parent.parent / "output" / "reranking"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── 하이브리드 스코어 설정 ───────────────────────────────────────────────
ALPHA = 0.5  # BM25 가중치 (1-ALPHA = Dense 가중치)

# ──────────────────────────────────────────────────────────────────────────

def collect_file_groups(retrieval_dir: Path) -> dict:
    """
    파일 prefix 기준 그룹핑

    예:
    contract1_dense_law.json
    → prefix = contract1
    """

    groups = {}

    for path in retrieval_dir.glob("*.json"):
        name = path.name

        if name.endswith("_dense_law.json"):
            prefix = name.replace("_dense_law.json", "")
            groups.setdefault(prefix, {})["dense_law"] = path

        elif name.endswith("_dense_caselaw.json"):
            prefix = name.replace("_dense_caselaw.json", "")
            groups.setdefault(prefix, {})["dense_case"] = path

        elif name.endswith("_bm25_law.json"):
            prefix = name.replace("_bm25_law.json", "")
            groups.setdefault(prefix, {})["bm25_law"] = path

        elif name.endswith("_bm25_caselaw.json"):
            prefix = name.replace("_bm25_caselaw.json", "")
            groups.setdefault(prefix, {})["bm25_case"] = path

    return groups


def load_bm25(path: Path, id_field: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # 단일 객체인 경우 리스트로 감싸서 통일
    if isinstance(data, dict):
        data = [data]

    bm25_map = {}
    for item in data:
        idx = item["index"]
        rank_map = {}
        for m in item["top_matches"]:
            doc_id = str(m[id_field])
            rank_map[doc_id] = m["rank"]
        bm25_map[idx] = {
            "special_terms" : item.get("special_terms") or item.get("clause", ""),
            "rank_map"      : rank_map,
        }
    return bm25_map


def load_dense(dense_path: Path, id_field: str, top_k: int) -> dict:
    """
    Dense JSON → {clause_text: [{doc_id, score, rank, doc_text, summary}]} 반환

    - 리스트 형태로 특약 여러 개 포함
    - 두 모델 결과를 similarity 기준으로 재정렬 후 단일 rank 부여
    - 같은 doc_id가 두 모델에서 중복 시 최고 score만 유지
    - top_k개까지만 사용
    """
    with open(dense_path, encoding="utf-8") as f:
        data = json.load(f)

    # 단일 객체인 경우 리스트로 감싸서 통일
    if isinstance(data, dict):
        data = [data]

    dense_map: dict[str, list] = {}

    for item in data:
        # 키명 통일: clause → special_terms
        clause_text = item.get("special_terms") or item.get("clause", "")
        records = []

        for r in item["results"]:
            doc_id = str(r.get(id_field, ""))
            records.append({
                "doc_id"   : doc_id,
                "score"    : float(r["similarity"]),
                "doc_text" : str(r.get("child_text", "")),
                "summary"  : str(r.get("judgment_summary", "")),
                "model"    : r.get("model", ""),
            })

        # doc_id별 최고 score만 유지
        best: dict[str, dict] = {}
        for rec in records:
            did = rec["doc_id"]
            if did not in best or rec["score"] > best[did]["score"]:
                best[did] = rec

        deduped = sorted(best.values(), key=lambda x: x["score"], reverse=True)
        deduped = deduped[:top_k]
        for rank, rec in enumerate(deduped, 1):
            rec["rank"] = rank

        dense_map[clause_text] = deduped

    return dense_map


def rrf_score(bm25_rank: int, dense_rank: int, k: int) -> float:
    return 1 / (k + bm25_rank) + 1 / (k + dense_rank)


def run_rrf(bm25_map: dict, dense_map: dict, k: int, top_n: int) -> list:
    results = []

    for idx, bm25_item in bm25_map.items():
        special_terms = bm25_item["special_terms"]
        bm25_ranks    = bm25_item["rank_map"]

        dense_records = dense_map.get(special_terms, [])
        dense_ranks   = {r["doc_id"]: r for r in dense_records}

        all_ids = set(bm25_ranks.keys()) | set(dense_ranks.keys())

        scored = []
        for doc_id in all_ids:
            b_rank = bm25_ranks.get(doc_id, 1000)
            d_rank = dense_ranks[doc_id]["rank"] if doc_id in dense_ranks else 1000

            score = rrf_score(b_rank, d_rank, k)

            doc_text = dense_ranks[doc_id]["doc_text"] if doc_id in dense_ranks else ""
            summary  = dense_ranks[doc_id]["summary"]  if doc_id in dense_ranks else ""

            scored.append({
                "doc_id"     : doc_id,
                "rrf_score"  : round(score, 6),
                "bm25_rank"  : b_rank if b_rank != 1000 else None,
                "dense_rank" : d_rank if d_rank != 1000 else None,
                "doc_text"   : doc_text,
                "summary"    : summary,
            })

        scored.sort(key=lambda x: x["rrf_score"], reverse=True)
        top = scored[:top_n]

        for rank, item in enumerate(top, 1):
            item["rank"] = rank

        results.append({
            "index"         : idx,
            "special_terms" : special_terms,
            "top_matches"   : top,
        })

    return results

def min_max_normalize(scores: list[float]) -> list[float]:
    """min-max 정규화."""
    if not scores:
        return scores
    min_s = min(scores)
    max_s = max(scores)
    if max_s == min_s:
        return [1.0] * len(scores)
    return [(s - min_s) / (max_s - min_s) for s in scores]


def run_hybrid(bm25_map: dict, dense_map: dict, alpha: float, top_n: int) -> list:
    """α * norm(BM25) + (1-α) * norm(Dense) 하이브리드 스코어 계산."""
    results = []

    for idx, bm25_item in bm25_map.items():
        special_terms = bm25_item["special_terms"]
        bm25_ranks    = bm25_item["rank_map"]

        dense_records = dense_map.get(special_terms, [])
        dense_scores  = {r["doc_id"]: r for r in dense_records}

        all_ids = list(set(bm25_ranks.keys()) | set(dense_scores.keys()))

        # BM25 rank → score 변환 (rank가 낮을수록 score 높게)
        max_bm25_rank = max(bm25_ranks.values()) if bm25_ranks else 1
        raw_bm25  = [1 - (bm25_ranks.get(did, max_bm25_rank + 1) - 1) / (max_bm25_rank) for did in all_ids]
        raw_dense = [dense_scores[did]["score"] if did in dense_scores else 0.0 for did in all_ids]

        norm_bm25  = min_max_normalize(raw_bm25)
        norm_dense = min_max_normalize(raw_dense)

        scored = []
        for i, doc_id in enumerate(all_ids):
            hybrid = alpha * norm_bm25[i] + (1 - alpha) * norm_dense[i]
            dense_rec = dense_scores.get(doc_id, {})
            scored.append({
                "doc_id"       : doc_id,
                "hybrid_score" : round(hybrid, 6),
                "norm_bm25"    : round(norm_bm25[i], 6),
                "norm_dense"   : round(norm_dense[i], 6),
                "bm25_rank"    : bm25_ranks.get(doc_id, None),
                "dense_rank"   : dense_rec.get("rank", None),
                "doc_text"     : dense_rec.get("doc_text", ""),
                "summary"      : dense_rec.get("summary", ""),
            })

        scored.sort(key=lambda x: x["hybrid_score"], reverse=True)
        top = scored[:top_n]
        for rank, item in enumerate(top, 1):
            item["rank"] = rank

        results.append({
            "index"        : idx,
            "special_terms": special_terms,
            "top_matches"  : top,
        })

    return results


def run_a(
    bm25_path: Path,
    dense_path: Path,
    id_field: str,
    out_path: Path,
    label: str,
) -> None:
    """하이브리드 스코어 기반 리랭킹 (α 공식)."""
    print(f"\n{'='*70}")
    print(f"{label} 하이브리드 리랭킹 시작 (α={ALPHA})")
    print(f"{'='*70}")

    print(f"  BM25 로드: {bm25_path.name}")
    bm25_map = load_bm25(bm25_path, id_field)

    print(f"  Dense 로드: {dense_path.name}")
    dense_map = load_dense(dense_path, id_field, DENSE_TOP_K)

    print("  하이브리드 스코어 계산 중...")
    results = run_hybrid(bm25_map, dense_map, ALPHA, TOP_N)

    for r in results:
        print(f"\n[{r['index']}] {r['special_terms']}")
        for m in r["top_matches"]:
            print(f"  #{m['rank']} hybrid={m['hybrid_score']:.6f}  norm_bm25={m['norm_bm25']:.4f}  norm_dense={m['norm_dense']:.4f}")
            print(f"         id={m['doc_id']}")
            if m['doc_text']:
                print(f"         {m['doc_text'][:80]}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  저장 완료: {out_path}")
    
    

def run(
    bm25_path: Path,
    dense_path: Path,
    id_field: str,
    out_path: Path,
    label: str,
) -> None:
    print(f"\n{'='*70}")
    print(f"{label} RRF 시작")
    print(f"{'='*70}")

    print(f"  BM25 로드: {bm25_path.name}")
    bm25_map = load_bm25(bm25_path, id_field)
    print(f"  특약 수: {len(bm25_map)}개")

    print(f"  Dense 로드: {dense_path.name}")
    dense_map = load_dense(dense_path, id_field, DENSE_TOP_K)
    print(f"  특약 수: {len(dense_map)}개")

    # 특약 매칭 확인
    bm25_clauses  = set(v["special_terms"] for v in bm25_map.values())
    dense_clauses = set(dense_map.keys())
    unmatched = bm25_clauses - dense_clauses
    if unmatched:
        print(f"  BM25에는 있으나 Dense에 없는 특약 {len(unmatched)}개:")
        for c in unmatched:
            print(f"    - {c[:50]}")

    print("  RRF 계산 중...")
    results = run_rrf(bm25_map, dense_map, K, TOP_N)

    # 결과 출력
    for r in results:
        print(f"\n[{r['index']}] {r['special_terms']}")
        for m in r["top_matches"]:
            b = m['bm25_rank'] if m['bm25_rank'] else 'N/A'
            d = m['dense_rank'] if m['dense_rank'] else 'N/A'
            print(f"  #{m['rank']} rrf={m['rrf_score']:.6f}  bm25_rank={b}  dense_rank={d}")
            print(f"         id={m['doc_id']}")
            if m['doc_text']:
                print(f"         {m['doc_text'][:80]}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  저장 완료: {out_path}")


def main():

    groups = collect_file_groups(RETRIEVAL_DIR)

    print(f"파일 그룹 {len(groups)}개 발견")

    for prefix, files in groups.items():

        print(f"\n{'='*70}")
        print(f"처리 중: {prefix}")
        print(f"{'='*70}")

        # 필수 파일 체크
        required = [
            "bm25_law",
            "dense_law",
            "bm25_case",
            "dense_case",
        ]

        missing = [k for k in required if k not in files]

        if missing:
            print(f"  누락 파일: {missing}")
            continue

        # 법령
        run(
            bm25_path = files["bm25_law"],
            dense_path = files["dense_law"],
            id_field = LAW_ID_FIELD,
            out_path = OUTPUT_DIR / f"{prefix}_reranking_law.json",
            label = f"{prefix} 법령",
        )

        # 판례
        run(
            bm25_path = files["bm25_case"],
            dense_path = files["dense_case"],
            id_field = PREC_ID_FIELD,
            out_path = OUTPUT_DIR / f"{prefix}_reranking_caselaw.json",
            label = f"{prefix} 판례",
        )

        # 법령 하이브리드
        run_a(
            bm25_path  = files["bm25_law"],
            dense_path = files["dense_law"],
            id_field   = LAW_ID_FIELD,
            out_path   = OUTPUT_DIR / f"{prefix}_reranking_law_a.json",
            label      = f"{prefix} 법령",
        )

        # 판례 하이브리드
        run_a(
            bm25_path  = files["bm25_case"],
            dense_path = files["dense_case"],
            id_field   = PREC_ID_FIELD,
            out_path   = OUTPUT_DIR / f"{prefix}_reranking_caselaw_a.json",
            label      = f"{prefix} 판례",
        )

if __name__ == "__main__":
    main()