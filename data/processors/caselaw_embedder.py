"""
임베딩 통합 파이프라인: gemini-embedding-001 (Vertex AI) + KURE-v1 (로컬)
- case_law.csv 읽어서 issue 컬럼을 두 모델로 임베딩
- embed_vertex, embed_kure 컬럼을 JSON 문자열로 저장
- 체크포인트/재개 지원: 기존 출력 파일이 있으면 미완료 행만 처리
- 인증: ADC (gcloud auth application-default login)
- 설치: pip install google-genai sentence-transformers python-dotenv
"""

import argparse
import json
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
import os

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
_BASE       = Path(__file__).resolve().parent.parent.parent
INPUT_CSV   = _BASE / "output" / "case_law.csv"
OUTPUT_FILE = _BASE / "output" / "case_law_with_embeddings.csv"

VERTEX_MODEL = "gemini-embedding-001"
KURE_MODEL   = "nlpai-lab/KURE-v1"
E5_MODEL     = "intfloat/multilingual-e5-large"
KOLEGAL_MODEL = "woong0322/ko-legal-sbert-finetuned"

BATCH_SIZE   = 16          # KURE 배치 크기
VERTEX_DIM   = 3072        # gemini-embedding-001 출력 차원
SLEEP_SEC    = 0.1         # Vertex AI 호출 간격 (초)
MAX_RETRIES  = 5
RETRY_DELAY  = 10          # 재시도 기본 대기 (초)

MAX_CHARS_VERTEX = 3000   # gemini-embedding-001: 2048토큰 × 1.5
MAX_CHARS_KURE   = 768    # KURE-v1: 512토큰 × 1.5
MAX_CHARS_E5     = 768

# 임베딩 컬럼명
COL_VERTEX   = "embed_vertex"
COL_KURE     = "embed_kure"
COL_E5       = "embed_e5"
COL_KOLEGAL    = "embed_kolegal"

COL_VERTEX_JS = "embed_vertex_js"
COL_KURE_JS   = "embed_kure_js"
COL_E5_JS     = "embed_e5_js"
COL_KOLEGAL_JS = "embed_kolegal_js"


# ── 인자 파싱 ──────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="판례 issue 컬럼 임베딩 (Vertex AI + KURE-v1)"
    )
    parser.add_argument(
        "--model",
        choices=["vertex", "kure", "e5", "kolegal", "all"],
        default="all",
        help="실행할 임베딩 모델 선택 (default: all)",
    )
    parser.add_argument(
        "--input",  default=str(INPUT_CSV),
        help=f"입력 CSV 경로 (default: {INPUT_CSV})",
    )
    parser.add_argument(
        "--output", default=str(OUTPUT_FILE),
        help=f"출력 CSV 경로 (default: {OUTPUT_FILE})",
    )
    return parser.parse_args()

# ── 텍스트 선택 함수 ─────────────────────────────────────────────
def select_js_text(row: pd.Series, max_chars: int) -> str:
    """judgment_summary 우선, 없으면 issue로 fallback하고 truncate한다."""
    summary = str(row.get("judgment_summary") or "").strip()
    issue   = str(row.get("issue") or "").strip()
    text    = summary if summary else issue
    return text[:max_chars]


# ── 데이터 로드 / 체크포인트 복원 ─────────────────────────────────────────────
def load_data(input_path: str, output_path: str) -> pd.DataFrame:
    """
    출력 파일이 이미 있으면 해당 파일을 기준으로 미완료 행만 처리.
    없으면 입력 파일을 읽고 embed_vertex / embed_kure 컬럼을 추가.
    """
    output_p = Path(output_path)
    if output_p.exists():
        df = pd.read_csv(output_p, encoding="utf-8-sig")
        print(f"[체크포인트] 기존 출력 파일 로드: {output_path}")
    else:
        df = pd.read_csv(input_path, encoding="utf-8-sig")
        print(f"[신규] 입력 파일 로드: {input_path}")

    df["case_id"] = df["case_id"].astype(str)

    if "embed_vertex" not in df.columns:
        df["embed_vertex"] = None
    if "embed_kure" not in df.columns:
        df["embed_kure"] = None
        
    for col in (
    COL_E5,
    COL_VERTEX_JS,
    COL_KURE_JS,
    COL_E5_JS,
    COL_KOLEGAL,
    COL_KOLEGAL_JS,
    ):
        if col not in df.columns:
            df[col] = None

    return df


# ── Vertex AI 임베딩 ───────────────────────────────────────────────────────────
def run_vertex_embedding(df: pd.DataFrame, output_path: str) -> pd.DataFrame:
    load_dotenv(_BASE / ".env")
    project_id = os.getenv("GCP_PROJECT_ID")
    location   = os.getenv("GCP_LOCATION", "us-central1")

    if not project_id:
        raise EnvironmentError("GCP_PROJECT_ID가 .env에 설정되지 않았습니다.")

    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True, project=project_id, location=location)

    targets = []
    for idx, r in df.iterrows():
        issue_text = str(r.get("issue") or "").strip()
        js_text    = select_js_text(r, MAX_CHARS_VERTEX)
        need_issue = bool(issue_text) and pd.isna(r[COL_VERTEX])
        need_js    = bool(js_text)    and pd.isna(r[COL_VERTEX_JS])
        if need_issue or need_js:
            targets.append((idx, issue_text, js_text, need_issue, need_js))

    print(f"\n[Vertex AI] 임베딩 대상: {len(targets)}건 (모델: {VERTEX_MODEL})")
    if not targets:
        print("[Vertex AI] 모두 완료됨, 스킵")
        return df

    errors, start = [], time.time()

    for i, (idx, issue_text, js_text, need_issue, need_js) in enumerate(targets):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # issue 기반 임베딩
                if need_issue and pd.isna(df.at[idx, COL_VERTEX]):
                    resp = client.models.embed_content(
                        model=VERTEX_MODEL,
                        contents=issue_text,
                        config=types.EmbedContentConfig(
                            task_type="RETRIEVAL_DOCUMENT",
                            output_dimensionality=VERTEX_DIM,
                        ),
                    )
                    df.at[idx, COL_VERTEX] = json.dumps(resp.embeddings[0].values)
                    time.sleep(SLEEP_SEC)
 
                # judgment_summary 기반 임베딩
                if need_js and pd.isna(df.at[idx, COL_VERTEX_JS]):
                    resp = client.models.embed_content(
                        model=VERTEX_MODEL,
                        contents=js_text,
                        config=types.EmbedContentConfig(
                            task_type="RETRIEVAL_DOCUMENT",
                            output_dimensionality=VERTEX_DIM,
                        ),
                    )
                    df.at[idx, COL_VERTEX_JS] = json.dumps(resp.embeddings[0].values)
                    time.sleep(SLEEP_SEC)
 
                break
            except Exception as e:
                if attempt == MAX_RETRIES:
                    errors.append({"case_id": df.at[idx, "case_id"], "error": str(e)})
                    print(f"  [오류] case_id={df.at[idx, 'case_id']}: {e}")
                else:
                    wait = RETRY_DELAY * attempt
                    print(f"  [재시도 {attempt}/{MAX_RETRIES}] {wait}s 대기...")
                    time.sleep(wait)

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start
            print(f"  [{i+1}/{len(targets)}] {elapsed:.1f}s | 평균 {elapsed/(i+1):.2f}s/건")
            df.to_csv(output_path, index=False, encoding="utf-8-sig")  # 중간 저장

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    total = time.time() - start
    print(
        f"[Vertex AI] 완료 — "
        f"issue: {df[COL_VERTEX].notna().sum()}건 | "
        f"js: {df[COL_VERTEX_JS].notna().sum()}건 | "
        f"실패: {len(errors)}건 | "
        f"소요: {total:.1f}s ({total/60:.1f}분)"
    )
    return df

# ── KURE-v1 임베딩 ─────────────────────────────────────────────────────────────
def run_kure_embedding(df: pd.DataFrame, output_path: str) -> pd.DataFrame:
    from sentence_transformers import SentenceTransformer

    targets_issue = [
        idx for idx, r in df.iterrows()
        if str(r.get("issue") or "").strip() and pd.isna(r[COL_KURE])
    ]
    targets_js = [
        idx for idx, r in df.iterrows()
        if select_js_text(r, MAX_CHARS_KURE) and pd.isna(r[COL_KURE_JS])
    ]

    print(f"\n[KURE-v1] issue 대상: {len(targets_issue)}건 | js 대상: {len(targets_js)}건")
    if not targets_issue and not targets_js:
        print("[KURE-v1] 모두 완료됨, 스킵")
        return df

    print("모델 로딩 중...")
    model = SentenceTransformer(KURE_MODEL)

    if targets_issue:
        texts_issue = [str(df.at[idx, "issue"]) for idx in targets_issue]
        emb_issue = model.encode(texts_issue, batch_size=BATCH_SIZE,
                                 show_progress_bar=True, normalize_embeddings=True)
        for i, idx in enumerate(targets_issue):
            df.at[idx, COL_KURE] = json.dumps(emb_issue[i].tolist())
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"[KURE-v1 issue] 완료 — {len(targets_issue)}건, 차원: {emb_issue.shape[1]}")

    if targets_js:
        texts_js = [select_js_text(df.loc[idx], MAX_CHARS_KURE) for idx in targets_js]
        emb_js = model.encode(texts_js, batch_size=BATCH_SIZE,
                              show_progress_bar=True, normalize_embeddings=True)
        for i, idx in enumerate(targets_js):
            df.at[idx, COL_KURE_JS] = json.dumps(emb_js[i].tolist())
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"[KURE-v1 js] 완료 — {len(targets_js)}건, 차원: {emb_js.shape[1]}")

    return df

# ── E5 임베딩 ──────────────────────────────────────────────────────────
def run_e5_embedding(df: pd.DataFrame, output_path: str) -> pd.DataFrame:
    """E5: issue 기반(embed_e5) + judgment_summary 기반(embed_e5_js) 모두 생성."""
    from sentence_transformers import SentenceTransformer

    targets_issue = [
        idx for idx, r in df.iterrows()
        if str(r.get("issue") or "").strip() and pd.isna(r[COL_E5])
    ]
    targets_js = [
        idx for idx, r in df.iterrows()
        if select_js_text(r, MAX_CHARS_E5) and pd.isna(r[COL_E5_JS])
    ]

    print(f"\n[E5] issue 대상: {len(targets_issue)}건 | js 대상: {len(targets_js)}건")
    if not targets_issue and not targets_js:
        print("[E5] 모두 완료됨, 스킵")
        return df

    print("모델 로딩 중...")
    model = SentenceTransformer(E5_MODEL)

    # issue 기반 임베딩
    if targets_issue:
        texts_issue = ["passage: " + str(df.at[idx, "issue"]) for idx in targets_issue]
        emb_issue = model.encode(texts_issue, batch_size=BATCH_SIZE,
                                 show_progress_bar=True, normalize_embeddings=True)
        for i, idx in enumerate(targets_issue):
            df.at[idx, COL_E5] = json.dumps(emb_issue[i].tolist())
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"[E5 issue] 완료 — {len(targets_issue)}건, 차원: {emb_issue.shape[1]}")

    # judgment_summary 기반 임베딩
    if targets_js:
        texts_js = ["passage: " + select_js_text(df.loc[idx], MAX_CHARS_E5) for idx in targets_js]
        emb_js = model.encode(texts_js, batch_size=BATCH_SIZE,
                              show_progress_bar=True, normalize_embeddings=True)
        for i, idx in enumerate(targets_js):
            df.at[idx, COL_E5_JS] = json.dumps(emb_js[i].tolist())
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"[E5 js] 완료 — {len(targets_js)}건, 차원: {emb_js.shape[1]}")

    return df


# ── KoLegal 임베딩 ──────────────────────────────────────────────────────────
def run_kolegal_embedding(df: pd.DataFrame, output_path: str) -> pd.DataFrame:
    from sentence_transformers import SentenceTransformer

    targets_issue = [
        idx for idx, r in df.iterrows()
        if str(r.get("issue") or "").strip() and pd.isna(r[COL_KOLEGAL])
    ]

    targets_js = [
        idx for idx, r in df.iterrows()
        if select_js_text(r, MAX_CHARS_KURE) and pd.isna(r[COL_KOLEGAL_JS])
    ]

    print(
        f"\n[KoLegal] issue 대상: {len(targets_issue)}건 | "
        f"js 대상: {len(targets_js)}건"
    )

    if not targets_issue and not targets_js:
        print("[KoLegal] 모두 완료됨, 스킵")
        return df

    print("모델 로딩 중...")
    model = SentenceTransformer(KOLEGAL_MODEL)

    # issue 기반 임베딩
    if targets_issue:
        texts_issue = [
            str(df.at[idx, "issue"])
            for idx in targets_issue
        ]

        emb_issue = model.encode(
            texts_issue,
            batch_size=BATCH_SIZE,
            show_progress_bar=True,
            normalize_embeddings=True,
        )

        for i, idx in enumerate(targets_issue):
            df.at[idx, COL_KOLEGAL] = json.dumps(
                emb_issue[i].tolist()
            )

        df.to_csv(output_path, index=False, encoding="utf-8-sig")

        print(
            f"[KoLegal issue] 완료 — "
            f"{len(targets_issue)}건, 차원: {emb_issue.shape[1]}"
        )

    # judgment_summary 기반 임베딩
    if targets_js:
        texts_js = [
            select_js_text(df.loc[idx], MAX_CHARS_KURE)
            for idx in targets_js
        ]

        emb_js = model.encode(
            texts_js,
            batch_size=BATCH_SIZE,
            show_progress_bar=True,
            normalize_embeddings=True,
        )

        for i, idx in enumerate(targets_js):
            df.at[idx, COL_KOLEGAL_JS] = json.dumps(
                emb_js[i].tolist()
            )

        df.to_csv(output_path, index=False, encoding="utf-8-sig")

        print(
            f"[KoLegal js] 완료 — "
            f"{len(targets_js)}건, 차원: {emb_js.shape[1]}"
        )

    return df

# ── 진입점 ────────────────────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()
    df = load_data(args.input, args.output)
 
    print(f"전체: {len(df)}건")
    print(f"  issue 있음:              {df['issue'].notna().sum()}건")
    print(f"  judgment_summary 있음:   {df['judgment_summary'].notna().sum()}건")
    print(f"  js 텍스트 선택 가능:     {sum(bool(select_js_text(r, MAX_CHARS_VERTEX)) for _, r in df.iterrows())}건")
 
    if args.model in ("vertex", "all"):
        df = run_vertex_embedding(df, args.output)
 
    if args.model in ("kure", "all"):
        df = run_kure_embedding(df, args.output)
 
    if args.model in ("e5", "all"):
        df = run_e5_embedding(df, args.output)
    
    if args.model in ("kolegal", "all"):
        df = run_kolegal_embedding(df, args.output)
        
    print(f"\n=== 완료 ===")
    print(f"embed_vertex    완료: {df[COL_VERTEX].notna().sum()}건")
    print(f"embed_kure      완료: {df[COL_KURE].notna().sum()}건")
    print(f"embed_e5        완료: {df[COL_E5].notna().sum()}건")
    print(f"embed_kolegal    완료: {df[COL_KOLEGAL].notna().sum()}건")
    print(f"embed_vertex_js 완료: {df[COL_VERTEX_JS].notna().sum()}건")
    print(f"embed_kure_js   완료: {df[COL_KURE_JS].notna().sum()}건")
    print(f"embed_e5_js     완료: {df[COL_E5_JS].notna().sum()}건")
    print(f"embed_kolegal_js 완료: {df[COL_KOLEGAL_JS].notna().sum()}건")
    print(f"저장 경로: {args.output}")
 
 
if __name__ == "__main__":
    main()