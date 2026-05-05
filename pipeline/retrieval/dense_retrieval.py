"""
특약 문장 vs 법령/판례 청크 시멘틱 검색 MVP
- 입력: 특약 CSV (특약 컬럼)
- 출력: 특약별 유사 법령/판례 Top-K → CSV 저장
"""

from dotenv import load_dotenv
import os
import ast
import time
import json

import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Vertex AI
import vertexai
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# KURE (로컬)
from sentence_transformers import SentenceTransformer

# ============================================
# 설정 및 환경 변수 로드
# ============================================
load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("GCP_LOCATION")

# ============================================
# 경로 설정
# ============================================
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent

# 데이터 입력 경로
SPECIAL_TERMS_PATH = "특약_전체.csv" # 1. 추후 쿼리 익스펜션으로 수정 필요
SPECIAL_TERMS_COL = "특약"

LAW_PATH = BASE_DIR.parent.parent / "data" / "law_chunks" / "law_child.csv"
PREC_PATH = BASE_DIR.parent.parent / "output" / "case_law_with_embeddings.csv" # 2. 임베딩된 법령, 판례 데이터 저장 경로 통일 필요

# 출력 디렉토리
OUTPUT_DIR = BASE_DIR.parent.parent / "data" / "retrieval"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_K = 30
MIN_SIMILARITY = {
    "embed_vertex": 0.4,
    "embed_kure": 0.3,
}

MODEL_COLS = {
    "embed_vertex": "gemini-embedding-001",
    "embed_kure": "nlpai-lab/KURE-v1",
}

# 법령 출력 컬럼: 식별자, 원본 텍스트
LAW_KEEP_COLS = ["clause_key", "child_text"]
# 판례 출력 컬럼: 식별자, 판결 요지
PREC_KEEP_COLS = ["case_id", "judgment_summary"]

# ============================================
# Vertex AI 초기화
# ============================================
vertexai.init(project=PROJECT_ID, location=LOCATION)

_vertex_model_cache = {}
_kure_model = None


def get_vertex_model(model_name: str) -> TextEmbeddingModel:
    if model_name not in _vertex_model_cache:
        _vertex_model_cache[model_name] = TextEmbeddingModel.from_pretrained(model_name)
    return _vertex_model_cache[model_name]


def get_kure_model() -> SentenceTransformer:
    global _kure_model
    if _kure_model is None:
        _kure_model = SentenceTransformer("nlpai-lab/KURE-v1")
    return _kure_model


# ============================================
# 임베딩 함수
# ============================================
@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda r: print(f"  API 오류, {r.next_action.sleep}초 후 재시도 ({r.attempt_number}/5)...")
)
def embed_query(text: str, embed_col: str) -> np.ndarray:
    model_name = MODEL_COLS[embed_col]

    if embed_col == "embed_vertex":
        model = get_vertex_model(model_name)
        input_obj = TextEmbeddingInput(text=text, task_type="RETRIEVAL_QUERY")
        embeddings = model.get_embeddings([input_obj])
        return np.array(embeddings[0].values, dtype=np.float32)

    elif embed_col == "embed_kure":
        model = get_kure_model()
        vec = model.encode(text, normalize_embeddings=True)
        return np.array(vec, dtype=np.float32)

    else:
        raise ValueError(f"알 수 없는 임베딩 컬럼: {embed_col}")


# ============================================
# 청크 CSV 로드 + 임베딩 파싱
# ============================================
def parse_embedding(value):
    if isinstance(value, str):
        return np.array(ast.literal_eval(value), dtype=np.float32)
    return np.array(value, dtype=np.float32)


def load_chunks(path: str, embed_col: str, keep_cols: list[str]) -> pd.DataFrame:
    """
    청크 CSV 로드 후 필요한 컬럼만 유지.
    임베딩 벡터는 유사도 계산 후 출력에서 제외.
    """
    t0 = time.time()
    print(f"  로딩: {os.path.basename(path)} [{embed_col}] ...", end=" ", flush=True)

    df = pd.read_csv(path)

    # 필수 컬럼 존재 여부 확인
    required = [embed_col] + keep_cols
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"컬럼 누락: {missing}\n"
            f"사용 가능한 컬럼: {list(df.columns)}"
        )

    # 임베딩이 있는 행만 유지
    df = df[df[embed_col].notna()].copy()

    # 임베딩 파싱 (계산용, 출력 제외)
    df["_vec"] = df[embed_col].apply(parse_embedding)

    # 출력에 필요한 컬럼만 유지 (임베딩 원본 컬럼 제외)
    df = df[keep_cols + ["_vec"]]

    print(f"완료 ({len(df)}행, {time.time()-t0:.1f}초)")
    return df


# ============================================
# 특약 CSV 로드
# ============================================
def load_special_terms(path: str, col: str) -> list[str]:
    print(f"  로딩: {os.path.basename(path)} [{col}] ...", end=" ", flush=True)
    df = pd.read_csv(path)
    if col not in df.columns:
        raise ValueError(f"'{col}' 컬럼이 없습니다. 사용 가능: {list(df.columns)}")
    terms = df[col].dropna().astype(str).str.strip().tolist()
    terms = [t for t in terms if t]
    print(f"완료 ({len(terms)}개)")
    return terms


# ============================================
# 유사도 검색 (부스트 없음, 유사도 기준 정렬)
# ============================================
def search_similar(
    query_vec: np.ndarray,
    df: pd.DataFrame,
    embed_col: str,
    top_k: int = TOP_K,
) -> pd.DataFrame:
    chunk_matrix = np.vstack(df["_vec"].values)
    query_matrix = query_vec.reshape(1, -1)

    if chunk_matrix.shape[1] != query_matrix.shape[1]:
        raise ValueError(
            f"차원 불일치: 쿼리={query_matrix.shape[1]}, "
            f"청크={chunk_matrix.shape[1]} ({embed_col})"
        )

    sims = cosine_similarity(query_matrix, chunk_matrix)[0]

    # _vec 제외한 출력 컬럼만 유지
    result = df.drop(columns=["_vec"]).copy()
    result["similarity"] = sims

    # 유사도 하한선 필터
    min_sim = MIN_SIMILARITY.get(embed_col, 0.3)
    result = result[result["similarity"] >= min_sim]

    return result.sort_values("similarity", ascending=False).head(top_k).reset_index(drop=True)
 
    
# ============================================
# 메인
# ============================================
def main():
    total_start = time.time()

    print("=" * 60)
    print("특약 / 법령 / 판례 로드 중...")
    print("=" * 60)

    special_terms = load_special_terms(SPECIAL_TERMS_PATH, SPECIAL_TERMS_COL)
    special_terms = special_terms[133:134]  # 테스트용 1개

    # 모델별로 필요한 컬럼만 로드
    law_chunks = {col: load_chunks(LAW_PATH, col, LAW_KEEP_COLS) for col in MODEL_COLS}
    prec_chunks = {col: load_chunks(PREC_PATH, col, PREC_KEEP_COLS) for col in MODEL_COLS}
    print()

    law_rows = []
    prec_rows = []

    total = len(special_terms)
    for si, term_text in enumerate(special_terms):
        print(f"\n--- 특약 {si+1}/{total} ---")
        print(f"원문: {term_text[:100]}{'...' if len(term_text) > 100 else ''}")

        for embed_col in MODEL_COLS:
            # 쿼리 임베딩
            t0 = time.time()
            print(f"  {embed_col} 임베딩 중...", end=" ", flush=True)
            query_vec = embed_query(term_text, embed_col)
            print(f"완료 ({time.time()-t0:.2f}초)")
            time.sleep(0.5)

            # 법령 검색
            t0 = time.time()
            print(f"  {embed_col} 법령 검색 중...", end=" ", flush=True)
            law_results = search_similar(query_vec, law_chunks[embed_col], embed_col)
            print(f"완료 ({time.time()-t0:.2f}초) -> {len(law_results)}건")

            for rank, row in law_results.iterrows():
                law_rows.append({
                    "special_terms": term_text,
                    "model": embed_col,
                    "rank": rank + 1,
                    "similarity": row["similarity"],
                    "clause_key": row["clause_key"],
                    "child_text": row["child_text"],
                })

            # 판례 검색
            t0 = time.time()
            print(f"  {embed_col} 판례 검색 중...", end=" ", flush=True)
            prec_results = search_similar(query_vec, prec_chunks[embed_col], embed_col)
            print(f"완료 ({time.time()-t0:.2f}초) -> {len(prec_results)}건")

            for rank, row in prec_results.iterrows():
                prec_rows.append({
                    "special_terms": term_text,
                    "model": embed_col,
                    "rank": rank + 1,
                    "similarity": row["similarity"],
                    "case_id": row["case_id"],
                    "judgment_summary": row["judgment_summary"],
                })

    # 특약 인덱스별로 JSON 저장
    law_df = pd.DataFrame(law_rows)
    law_df["similarity"] = law_df["similarity"].astype(float)

    prec_df = pd.DataFrame(prec_rows)
    prec_df["similarity"] = prec_df["similarity"].astype(float)

    for si, term_text in enumerate(special_terms):
        # 법령 저장
        law_subset = law_df[law_df["special_terms"] == term_text]
        law_output = {
            "index": si,
            "special_terms": term_text,
            "results": law_subset.to_dict(orient="records")
        }
        law_path = OUTPUT_DIR / "dense_law.json"
        with open(law_path, "w", encoding="utf-8") as f:
            json.dump(law_output, f, ensure_ascii=False, indent=2)

        # 판례 저장
        prec_subset = prec_df[prec_df["special_terms"] == term_text]
        prec_output = {
            "index": si,
            "special_terms": term_text,
            "results": prec_subset.to_dict(orient="records")
        }
        prec_path = OUTPUT_DIR / "dense_prec.json"
        with open(prec_path, "w", encoding="utf-8") as f:
            json.dump(prec_output, f, ensure_ascii=False, indent=2)

    print(f"  법령 결과: {OUTPUT_DIR / 'dense_law.json'}")
    print(f"  판례 결과: {OUTPUT_DIR / 'dense_prec.json'}")
    
    print(f"\n{'=' * 60}")
    print(f"전체 소요 시간: {time.time()-total_start:.1f}초")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()