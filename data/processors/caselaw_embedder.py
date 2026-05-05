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
BATCH_SIZE   = 16          # KURE 배치 크기
VERTEX_DIM   = 3072        # gemini-embedding-001 출력 차원
SLEEP_SEC    = 0.1         # Vertex AI 호출 간격 (초)
MAX_RETRIES  = 5
RETRY_DELAY  = 10          # 재시도 기본 대기 (초)


# ── 인자 파싱 ──────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="판례 issue 컬럼 임베딩 (Vertex AI + KURE-v1)"
    )
    parser.add_argument(
        "--model",
        choices=["vertex", "kure", "all"],
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

    targets = [
        (idx, str(r["issue"]))
        for idx, r in df.iterrows()
        if pd.notna(r["issue"]) and str(r["issue"]).strip()
        and pd.isna(r["embed_vertex"])  # 미완료 행만
    ]

    print(f"\n[Vertex AI] 임베딩 대상: {len(targets)}건 (모델: {VERTEX_MODEL})")
    if not targets:
        print("[Vertex AI] 모두 완료됨, 스킵")
        return df

    errors, start = [], time.time()

    for i, (idx, text) in enumerate(targets):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = client.models.embed_content(
                    model=VERTEX_MODEL,
                    contents=text,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=VERTEX_DIM,
                    ),
                )
                df.at[idx, "embed_vertex"] = json.dumps(resp.embeddings[0].values)
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
    print(f"[Vertex AI] 완료 — 성공: {df['embed_vertex'].notna().sum()}건 | "
          f"실패: {len(errors)}건 | 소요: {total:.1f}s ({total/60:.1f}분)")
    return df


# ── KURE-v1 임베딩 ─────────────────────────────────────────────────────────────
def run_kure_embedding(df: pd.DataFrame, output_path: str) -> pd.DataFrame:
    from sentence_transformers import SentenceTransformer

    targets_idx = [
        idx for idx, r in df.iterrows()
        if pd.notna(r["issue"]) and str(r["issue"]).strip()
        and pd.isna(r["embed_kure"])  # 미완료 행만
    ]
    texts = [str(df.at[idx, "issue"]) for idx in targets_idx]

    print(f"\n[KURE-v1] 임베딩 대상: {len(texts)}건 (모델: {KURE_MODEL})")
    if not texts:
        print("[KURE-v1] 모두 완료됨, 스킵")
        return df

    print(f"모델 로딩 중...")
    load_start = time.time()
    model = SentenceTransformer(KURE_MODEL)
    print(f"모델 로딩 완료: {time.time()-load_start:.1f}s")

    start = time.time()
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    total = time.time() - start

    for i, idx in enumerate(targets_idx):
        df.at[idx, "embed_kure"] = json.dumps(embeddings[i].tolist())

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"[KURE-v1] 완료 — 성공: {df['embed_kure'].notna().sum()}건 | "
          f"실패: {df['embed_kure'].isna().sum()}건 | "
          f"소요: {total:.1f}s ({total/60:.1f}분) | "
          f"차원: {embeddings.shape[1]}")
    return df


# ── 진입점 ─────────────────────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()
    df = load_data(args.input, args.output)

    total_rows = len(df)
    target_rows = df["issue"].notna().sum()
    print(f"전체: {total_rows}건 | issue 비어있지 않은 행: {target_rows}건")

    if args.model in ("vertex", "all"):
        df = run_vertex_embedding(df, args.output)

    if args.model in ("kure", "all"):
        df = run_kure_embedding(df, args.output)

    print(f"\n=== 완료 ===")
    print(f"embed_vertex 완료: {df['embed_vertex'].notna().sum()}건")
    print(f"embed_kure   완료: {df['embed_kure'].notna().sum()}건")
    print(f"저장 경로: {args.output}")


if __name__ == "__main__":
    main()
