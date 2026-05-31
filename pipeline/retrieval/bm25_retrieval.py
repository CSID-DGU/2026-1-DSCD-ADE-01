"""
BM25 통합 검색 파이프라인
- 판례 매칭: bm25_keywords → case_law (DB: issue + judgment_summary) → bm25_caselaw/{stem}.json
- 법령 매칭: bm25_keywords → law_child (DB: child_text)              → bm25_law/{stem}.json

[입력]
  폴더 경로: query_expansion_full/ 내 *.json 파일 자동 수집
  단일 파일: 기존처럼 동작

[출력]
  입력 JSON 파일 1개 → 결과 JSON 파일 1개 (파일명 동일, 출력 디렉토리 하위에 저장)
  하나의 JSON에 특약이 여러 개 담겨 있어도 해당 파일 기준으로 한 파일로 출력됨

[쿼리 토크나이징]
  corpus(법령·판례)는 kiwipiepy 형태소 분석으로 토크나이징
  query는 쿼리 익스펜션 결과 bm25_keywords를 공백 제거 후 그대로 사용
  (형태소 재분리 시 복합명사 손실 문제 방지)

[데이터 소스]
  shared.db.connection.get_db_client 사용 (Cloud SQL)
"""
import sys
import argparse
import json
import time
import pandas as pd
from rank_bm25 import BM25Okapi
from pathlib import Path

# ─── 프로젝트 루트를 sys.path에 추가 ──────────────────────────────
_BASE         = Path(__file__).resolve().parent
_PROJECT_ROOT = _BASE.parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import text
from shared.db.connection import get_db_client

# ─── 경로 설정 ──────────────────────────────────────────────────────
_DATA   = _BASE / "data"
_OUTPUT = _BASE / "output"

TOP_K_CASE = 20
TOP_K_LAW  = 20
POS_FILTER = {"NNG", "NNP", "VV", "VA", "XR"}

# ─── DB 테이블 및 컬럼 상수 ─────────────────────────────────────────
CASE_TABLE = "case_law"
CASE_COLS  = "case_id, case_name, case_number, judgment_date, court_name, issue, judgment_summary"

LAW_TABLE = "law_child"
LAW_COLS  = "clause_key, law_name, article_no, paragraph_no, child_text"
# ────────────────────────────────────────────────────────────────────


# ── 인자 파싱 ────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BM25 통합 검색 (판례 + 법령)")
    parser.add_argument(
        "--target", choices=["case", "law", "all"], default="all",
        help="실행할 검색 대상 (default: all)",
    )
    parser.add_argument(
        "--samples",
        default=str(_DATA / "query_expansion_full"),
        help="샘플 JSON 경로 또는 폴더 경로 "
             "(폴더 지정 시 *.json 전체 수집, default: query_expansion_full/)",
    )
    parser.add_argument(
        "--out-case", default=str(_OUTPUT / "retrieval" / "bm25_caselaw"),
        help="판례 결과 저장 디렉토리 (default: retrieval/bm25_caselaw/)",
    )
    parser.add_argument(
        "--out-law", default=str(_OUTPUT / "retrieval" / "bm25_law"),
        help="법령 결과 저장 디렉토리 (default: retrieval/bm25_law/)",
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


# ── Kiwi 초기화 (corpus 토크나이징 전용) ────────────────────────────
# 주의: Python 설치 경로에 한글이 포함된 경우(예: Windows 한글 사용자 계정) kiwipiepy가
#       네이티브 크래시(힙 오염, 0xC0000374)를 일으키므로, ASCII 경로인지 먼저 확인한다.
try:
    sys.prefix.encode("ascii")          # 한글 경로면 UnicodeEncodeError → 폴백
    from kiwipiepy import Kiwi
    kiwi = Kiwi()
    _KIWI_OK = True
except (UnicodeEncodeError, Exception) as e:
    print(f"[경고] Kiwi 초기화 건너뜀: {type(e).__name__}: {e} → 공백 분리 토크나이저로 대체")
    kiwi = None
    _KIWI_OK = False


def tokenize(text_val: str) -> list[str]:
    """corpus(법령·판례 문서) 토크나이징 전용 — 형태소 분석 or 공백 분리"""
    if not text_val or not text_val.strip():
        return []
    if _KIWI_OK and kiwi is not None:
        tokens = [
            token.form
            for token in kiwi.tokenize(text_val)
            if token.tag in POS_FILTER
        ]
        return tokens if tokens else text_val.split()
    return text_val.split()


def build_query_tokens(keywords: list[str]) -> list[str]:
    """쿼리 토큰 생성: 형태소 분석 토큰 + raw 키워드(공백 제거) 보너스"""
    tokens = []
    for kw in keywords:
        tokens.extend(tokenize(kw))        # corpus와 같은 토큰 공간
        tokens.append(kw.replace(" ", "")) # raw 보너스
    return list(dict.fromkeys(tokens))     # 순서 유지 중복 제거


# ── CSV 경로 (DB 폴백용) ─────────────────────────────────────────────
_CSV_CASE_LAW = _PROJECT_ROOT / "data" / "raw" / "case_law_with_embeddings_vertex.csv"
_CSV_LAW      = _PROJECT_ROOT / "data" / "raw" / "law_child_vertex.csv"

_CASE_CSV_COLS = {"case_id", "case_name", "case_number", "judgment_date", "court_name", "issue", "judgment_summary"}
_LAW_CSV_COLS  = {"clause_key", "law_name", "article_no", "paragraph_no", "child_text"}


# ── 데이터 로드 (DB 우선, CSV 폴백) ─────────────────────────────────
def load_case_law_from_db() -> pd.DataFrame:
    """판례 로드: Cloud SQL 우선, 접근 불가 시 CSV 폴백."""
    t0 = time.time()
    print(f"▶ [판례] DB 로드 중... ({CASE_TABLE})", end=" ", flush=True)
    try:
        db = get_db_client()
        rows = db.fetch_all(text(f"SELECT {CASE_COLS} FROM {CASE_TABLE}"))
        if not rows:
            raise ValueError(f"테이블 '{CASE_TABLE}'에서 데이터 없음")
        df = pd.DataFrame(rows)
        print(f"(DB) ", end="", flush=True)
    except Exception as e:
        print(f"\n  [경고] DB 연결 실패 ({e.__class__.__name__}), CSV 폴백: {_CSV_CASE_LAW.name}", flush=True)
        df = pd.read_csv(_CSV_CASE_LAW, encoding="utf-8-sig",
                         usecols=lambda c: c in _CASE_CSV_COLS)

    df["bm25_target"] = (
        df["issue"].fillna("") + " " + df["judgment_summary"].fillna("")
    ).str.strip()
    df_valid = df[df["bm25_target"].str.len() > 0].reset_index(drop=True)
    print(f"완료 ({len(df_valid)}행 유효 / 전체 {len(df)}행, {time.time()-t0:.1f}초)")
    return df_valid


def load_law_child_from_db() -> pd.DataFrame:
    """법령 로드: Cloud SQL 우선, 접근 불가 시 CSV 폴백."""
    t0 = time.time()
    print(f"▶ [법령] DB 로드 중... ({LAW_TABLE})", end=" ", flush=True)
    try:
        db = get_db_client()
        rows = db.fetch_all(text(f"SELECT {LAW_COLS} FROM {LAW_TABLE}"))
        if not rows:
            raise ValueError(f"테이블 '{LAW_TABLE}'에서 데이터 없음")
        df = pd.DataFrame(rows)
        print(f"(DB) ", end="", flush=True)
    except Exception as e:
        print(f"\n  [경고] DB 연결 실패 ({e.__class__.__name__}), CSV 폴백: {_CSV_LAW.name}", flush=True)
        df = pd.read_csv(_CSV_LAW, encoding="utf-8-sig",
                         usecols=lambda c: c in _LAW_CSV_COLS)

    df["child_text"] = df["child_text"].fillna("").astype(str)
    print(f"완료 ({len(df)}행, {time.time()-t0:.1f}초)")
    return df


# ── 샘플 로드 ────────────────────────────────────────────────────────
def load_samples_by_file(path: str) -> list[tuple[str, list]]:
    """
    입력 경로별로 (파일 stem, 샘플 리스트) 튜플 반환.
    - 폴더: 하위 *.json 파일 각각을 독립 단위로 읽음
    - 단일 파일: [(stem, samples)] 형태로 반환
    파일 하나에 특약이 여러 개(리스트) 또는 하나(객체)이어도 모두 허용.
    """
    p = Path(path)

    if p.is_dir():
        files = sorted(p.glob("*.json"))
        if not files:
            raise FileNotFoundError(f"[ERROR] 폴더에 JSON 파일이 없습니다: {p}")
        file_samples = []
        for f in files:
            with open(f, encoding="utf-8") as fh:
                obj = json.load(fh)
            samples = obj if isinstance(obj, list) else [obj]
            file_samples.append((f.stem, samples))
        total = sum(len(s) for _, s in file_samples)
        print(f"  샘플 로드: {len(files)}개 파일, 총 {total}개 특약")
        return file_samples

    else:
        with open(p, encoding="utf-8") as f:
            obj = json.load(f)
        samples = obj if isinstance(obj, list) else [obj]
        print(f"  샘플 로드: 1개 파일, {len(samples)}개 특약")
        return [(p.stem, samples)]


def save_json(data: list, out_dir: str, stem: str) -> None:
    """out_dir / stem.json 으로 저장"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    out_path = out / f"{stem}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 저장: {out_path}")


# ── 판례 BM25 매칭 ───────────────────────────────────────────────────
def run_case_matching(args) -> None:
    print("\n" + "="*70)

    df_valid = load_case_law_from_db()

    print("▶ [판례] corpus 토크나이징 중...")
    corpus_tokens = []
    for i, text_val in enumerate(df_valid["bm25_target"]):
        corpus_tokens.append(tokenize(text_val))
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(df_valid)} 완료")

    bm25 = BM25Okapi(corpus_tokens)
    print("  BM25 인덱스 완료")

    file_samples = load_samples_by_file(args.samples)

    for stem, samples in file_samples:
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

        print(f"\n[{stem}] {len(results)}개 특약 검색 완료")
        for r in results:
            print(f"  [{r['index']}] {r['clause'][:50]}")
            for m in r["top_matches"][:3]:
                print(f"    #{m['rank']} score={m['score']:6.3f}  {m['case_name']} "
                      f"({m['court_name']}, {str(m['judgment_date'])[:8]})")

        save_json(results, args.out_case, stem)


# ── 법령 BM25 매칭 ───────────────────────────────────────────────────
def run_law_matching(args) -> None:
    print("\n" + "="*70)

    df = load_law_child_from_db()

    print("▶ [법령] corpus 토크나이징 중... (약 1~2분 소요)")
    corpus_tokens = [tokenize(t) for t in df["child_text"]]
    bm25 = BM25Okapi(corpus_tokens)
    print("  BM25 인덱스 완료")

    file_samples = load_samples_by_file(args.samples)

    for stem, samples in file_samples:
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

        print(f"\n[{stem}] {len(results)}개 특약 검색 완료")
        for r in results:
            print(f"  [{r['index']}] {r['clause'][:50]}")
            for m in r["top_matches"][:3]:
                print(f"    #{m['rank']} score={m['score']:6.3f}  "
                      f"{m['law_name']} 제{m['article_no']}조 제{m['paragraph_no']}항")

        save_json(results, args.out_law, stem)


# ── 진입점 ──────────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()

    if args.target in ("case", "all"):
        run_case_matching(args)

    if args.target in ("law", "all"):
        run_law_matching(args)


if __name__ == "__main__":
    main()
