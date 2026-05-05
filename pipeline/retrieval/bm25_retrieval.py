"""
BM25 통합 검색 파이프라인
- 판례 매칭: bm25_keywords → case_law.csv (issue + judgment_summary) → bm25_caselaw.json
- 법령 매칭: bm25_keywords → law_child.csv (child_text)             → bm25_law.json
"""
import argparse
import json
import pandas as pd
from rank_bm25 import BM25Okapi
from kiwipiepy import Kiwi
from pathlib import Path

# ─── 경로 설정 ──────────────────────────────────────────
_BASE   = Path(__file__).resolve().parent.parent.parent
_DATA   = _BASE / "data"
_OUTPUT = _BASE / "output"

TOP_K_CASE = 20
TOP_K_LAW  = 20
POS_FILTER = {"NNG", "NNP", "VV", "VA", "XR"}
# ────────────────────────────────────────────────────────


# ── 인자 파싱 ─────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BM25 통합 검색 (판례 + 법령)")
    parser.add_argument(
        "--target", choices=["case", "law", "all"], default="all",
        help="실행할 검색 대상 (default: all)",
    )
    parser.add_argument(
        "--caselaw", default=str(_OUTPUT / "case_law.csv"),
        help="판례 CSV 경로 (default: output/case_law.csv)",
    )
    parser.add_argument(
        "--law", default=str(_DATA / "law_chunks" / "law_child.csv"),
        help="법령 CSV 경로 (default: data/law_chunks/law_child.csv)",
    )
    parser.add_argument(
        "--samples", default=str(_DATA / "all_samples.json"),
        help="샘플 JSON 경로 (default: data/all_samples.json) — query expansion 테스트 데이터이며 교체 가능",
    )
    parser.add_argument(
        "--out-case", default=str(_OUTPUT / "bm25_caselaw.json"),
        help="판례 결과 저장 경로 (default: output/bm25_caselaw.json)",
    )
    parser.add_argument(
        "--out-law", default=str(_OUTPUT / "bm25_law.json"),
        help="법령 결과 저장 경로 (default: output/bm25_law.json)",
    )
    parser.add_argument(
        "--top-k-case", type=int, default=TOP_K_CASE,
        help=f"판례 상위 K개 (default: {TOP_K_CASE})",
    )
    parser.add_argument(
        "--top-k-law", type=int, default=TOP_K_LAW,
        help=f"법령 상위 K개 (default: {TOP_K_LAW})",
    )
    return parser.parse_args()


# ── Kiwi 초기화 ──────────────────────────────────────────
import kiwipiepy_model
kiwi = Kiwi(model_path=str(Path(kiwipiepy_model.__file__).parent))

def tokenize(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    tokens = [
        token.form
        for token in kiwi.tokenize(text)
        if token.tag in POS_FILTER
    ]
    return tokens if tokens else text.split()

def build_query_tokens(keywords: list[str]) -> list[str]:
    return list(dict.fromkeys(
        token for kw in keywords for token in tokenize(kw)
    ))


# ── 샘플 JSON 로드 ────────────────────────────────────────
def load_samples(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_json(data: list, path: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 저장 완료: {out}")


# ── 판례 BM25 매칭 ────────────────────────────────────────
def run_case_matching(args) -> None:
    print("\n" + "="*70)
    print("▶ [판례] CSV 로드 중...")
    df = pd.read_csv(args.caselaw, encoding="utf-8-sig")

    df["bm25_target"] = (
        df["issue"].fillna("") + " " + df["judgment_summary"].fillna("")
    ).str.strip()
    df_valid = df[df["bm25_target"].str.len() > 0].reset_index(drop=True)
    print(f"  유효 판례: {len(df_valid)}개 / 전체 {len(df)}개")

    print("▶ [판례] corpus 토크나이징 중...")
    corpus_tokens = []
    for i, text in enumerate(df_valid["bm25_target"]):
        corpus_tokens.append(tokenize(text))
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(df_valid)} 완료")

    bm25 = BM25Okapi(corpus_tokens)
    print("  BM25 인덱스 완료")

    samples = load_samples(args.samples)
    results = []

    for sample in samples:
        clause       = sample["clause"]
        keywords     = sample["retrieval_payload"]["bm25_keywords"]
        query_tokens = build_query_tokens(keywords)

        scores  = bm25.get_scores(query_tokens)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:args.top_k_case]

        matched = []
        for rank, idx in enumerate(top_idx, 1):
            row          = df_valid.iloc[idx]
            issue_text   = str(row["issue"])
            summary_text = str(row["judgment_summary"])
            matched.append({
                "rank":            rank,
                "score":           round(float(scores[idx]), 4),
                "case_id":         int(row["case_id"]),
                "case_name":       str(row["case_name"]),
                "case_number":     str(row["case_number"]),
                "judgment_date":   str(row["judgment_date"]),
                "court_name":      str(row["court_name"]),
                "issue_preview":   issue_text[:100] + "..." if len(issue_text) > 100 else issue_text,
                "summary_preview": summary_text[:100] + "..." if len(summary_text) > 100 else summary_text,
            })

        results.append({
            "index":        sample["index"],
            "clause":       clause,
            "query_tokens": query_tokens,
            "top_matches":  matched,
        })

    for r in results:
        print(f"\n[{r['index']}] {r['clause']}")
        print(f"  query tokens: {r['query_tokens']}")
        for m in r["top_matches"]:
            print(f"  #{m['rank']} score={m['score']:6.3f}  {m['case_name']} "
                  f"({m['court_name']}, {str(m['judgment_date'])[:8]})")
            print(f"         [판시] {m['issue_preview']}")

    save_json(results, args.out_case)


# ── 법령 BM25 매칭 ────────────────────────────────────────
def run_law_matching(args) -> None:
    print("\n" + "="*70)
    print("▶ [법령] CSV 로드 중...")
    df = pd.read_csv(args.law, encoding="utf-8-sig")
    df["child_text"] = df["child_text"].fillna("").astype(str)

    print("▶ [법령] corpus 토크나이징 중... (31k rows, 약 1~2분)")
    corpus_tokens = [tokenize(t) for t in df["child_text"]]
    bm25 = BM25Okapi(corpus_tokens)
    print("  BM25 인덱스 완료")

    samples = load_samples(args.samples)
    results = []

    for sample in samples:
        clause       = sample["clause"]
        keywords     = sample["retrieval_payload"]["bm25_keywords"]
        query_tokens = build_query_tokens(keywords)

        scores  = bm25.get_scores(query_tokens)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:args.top_k_law]

        matched = []
        for rank, idx in enumerate(top_idx, 1):
            row = df.iloc[idx]
            matched.append({
                "rank":         rank,
                "score":        round(float(scores[idx]), 4),
                "clause_key":   str(row["clause_key"]),
                "law_name":     str(row["law_name"]),
                "article_no":   str(row["article_no"]),
                "paragraph_no": str(row["paragraph_no"]),
                "child_text":   str(row["child_text"])[:120] + "...",
            })

        results.append({
            "index":        sample["index"],
            "clause":       clause,
            "query_tokens": query_tokens,
            "top_matches":  matched,
        })

    for r in results:
        print(f"\n[{r['index']}] {r['clause']}")
        print(f"  query tokens: {r['query_tokens']}")
        for m in r["top_matches"]:
            print(f"  #{m['rank']} score={m['score']:6.3f}  "
                  f"{m['law_name']} 제{m['article_no']}조 제{m['paragraph_no']}항")
            print(f"         {m['child_text'][:80]}...")

    save_json(results, args.out_law)


# ── 진입점 ────────────────────────────────────────────────
def main() -> None:
    args = parse_args()

    if args.target in ("case", "all"):
        run_case_matching(args)

    if args.target in ("law", "all"):
        run_law_matching(args)


if __name__ == "__main__":
    main()