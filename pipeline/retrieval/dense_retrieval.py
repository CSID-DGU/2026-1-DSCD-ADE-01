"""
특약 문장 vs 법령/판례 청크 시멘틱 검색 MVP
- 입력: query_expansion.json (특약 + dense_query + bm25_keywords)
- 출력: dense_law.json, dense_caselaw.json (전체 특약 결과 통합)
"""

# ============================================
# 표준 라이브러리 및 서드파티 import
# ============================================
import sys
import os
import ast
import time
import json
from pathlib import Path

from dotenv import load_dotenv
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

import vertexai
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sentence_transformers import SentenceTransformer
from sqlalchemy import text

# ============================================
# 프로젝트 루트를 sys.path에 추가 (shared 모듈 접근용)
# ============================================
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.db.connection import get_db_client

# ============================================
# 환경 변수 로드
# ============================================
load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION   = os.getenv("GCP_LOCATION")

# ============================================
# 경로 설정
# ============================================
BASE_DIR = Path(__file__).resolve().parent

QUERY_EXPANSION_PATH = BASE_DIR.parent.parent / "output" / "query_expansion"
OUTPUT_DIR           = BASE_DIR.parent.parent / "output" / "retrieval"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================
# 상수 설정
# ============================================
TOP_K        = 20
KEYWORD_BOOST = 0.05

MIN_SIMILARITY = {
    "embed_vertex": 0.4,
    "embed_kure":   0.3,
    "embed_e5":     0.3,  # 추가 (KURE와 동일 기준으로 시작, 추후 조정)
}

MODEL_COLS = {
    "embed_vertex": "gemini-embedding-001",
    "embed_kure":   "nlpai-lab/KURE-v1",
    "embed_e5":     "intfloat/multilingual-e5-large",  # 추가
}

LAW_TABLE  = "law_child"
PREC_TABLE = "case_law"

LAW_KEEP_COLS  = ["clause_key", "child_text"]
PREC_KEEP_COLS = ["case_id", "judgment_summary"]

# ============================================
# Vertex AI 초기화
# ============================================
vertexai.init(project=PROJECT_ID, location=LOCATION)

_vertex_model_cache = {}
_kure_model = None
_e5_model = None


def get_vertex_model(model_name: str) -> TextEmbeddingModel:
    if model_name not in _vertex_model_cache:
        _vertex_model_cache[model_name] = TextEmbeddingModel.from_pretrained(model_name)
    return _vertex_model_cache[model_name]


def get_kure_model() -> SentenceTransformer:
    global _kure_model
    if _kure_model is None:
        _kure_model = SentenceTransformer("nlpai-lab/KURE-v1")
    return _kure_model


def get_e5_model() -> SentenceTransformer:
    global _e5_model
    if _e5_model is None:
        _e5_model = SentenceTransformer("intfloat/multilingual-e5-large")
    return _e5_model


# ============================================
# 임베딩 함수
# ============================================
@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda r: print(f"  API 오류, {r.next_action.sleep}초 후 재시도 ({r.attempt_number}/5)...")
)
def embed_query(query_text: str, embed_col: str) -> np.ndarray:
    model_name = MODEL_COLS[embed_col]

    if embed_col == "embed_vertex":
        model     = get_vertex_model(model_name)
        input_obj = TextEmbeddingInput(text=query_text, task_type="RETRIEVAL_QUERY")
        embeddings = model.get_embeddings([input_obj])
        return np.array(embeddings[0].values, dtype=np.float32)

    elif embed_col == "embed_kure":
        model = get_kure_model()
        vec   = model.encode(query_text, normalize_embeddings=True)
        return np.array(vec, dtype=np.float32)
    
    elif embed_col == "embed_e5":
        # E5는 쿼리 측에 "query: " 접두어 필요
        model = get_e5_model()
        vec   = model.encode("query: " + query_text, normalize_embeddings=True)
        return np.array(vec, dtype=np.float32)

    else:
        raise ValueError(f"알 수 없는 임베딩 컬럼: {embed_col}")


# ============================================
# DB 로드 + 임베딩 파싱
# ============================================
def parse_embedding(value):
    if isinstance(value, str):
        # pgvector가 반환하는 '[0.1,0.2,...]' 형식 처리
        cleaned = value.strip()[1:-1]  # 앞뒤 [] 제거
        return np.array([float(x) for x in cleaned.split(",")], dtype=np.float32)
    if isinstance(value, list):
        return np.array(value, dtype=np.float32)
    return np.array(value, dtype=np.float32)

def load_chunks(table_name: str, embed_col: str, keep_cols: list[str]) -> pd.DataFrame:
    t0 = time.time()
    print(f"  로딩: {table_name} [{embed_col}] ...", end=" ", flush=True)

    db          = get_db_client()
    select_cols = ", ".join(keep_cols + [embed_col])
    rows        = db.fetch_all(
        text(f"SELECT {select_cols} FROM {table_name} WHERE {embed_col} IS NOT NULL"),
    )

    if not rows:
        raise ValueError(f"테이블 '{table_name}'에서 데이터 없음")

    df        = pd.DataFrame(rows)
    df["_vec"] = df[embed_col].apply(parse_embedding)
    df        = df[keep_cols + ["_vec"]]

    print(f"완료 ({len(df)}행, {time.time()-t0:.1f}초)")
    
    return df


# ============================================
# 쿼리 확장 JSON 로드
# ============================================
def load_query_expansion(path: Path) -> list[dict]:
    print(f"  로딩: {path.name} ...", end=" ", flush=True)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]

    print(f"완료 ({len(data)}개 특약)")
    return data


# ============================================
# 유사도 검색
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

    sims   = cosine_similarity(query_matrix, chunk_matrix)[0]
    result = df.drop(columns=["_vec"]).copy()
    result["similarity"] = sims

    min_sim = MIN_SIMILARITY.get(embed_col, 0.3)
    result  = result[result["similarity"] >= min_sim]

    return result.sort_values("similarity", ascending=False).head(top_k).reset_index(drop=True)


# ============================================
# 메인
# ============================================
def main():
    total_start = time.time()

    query_files = sorted(QUERY_EXPANSION_PATH.glob("*.json"))
    if not query_files:
        print(f"쿼리 확장 파일 없음: {QUERY_EXPANSION_PATH}")
        return
    print(f"쿼리 확장 파일 {len(query_files)}개 발견")

    print("=" * 60)
    print("법령 / 판례 청크 로드 중...")
    print("=" * 60)

    law_chunks  = {col: load_chunks(LAW_TABLE,  col, LAW_KEEP_COLS)  for col in MODEL_COLS}
    prec_chunks = {col: load_chunks(PREC_TABLE, col, PREC_KEEP_COLS) for col in MODEL_COLS}

    print()

    for query_file in query_files:
        all_law_results  = []
        all_prec_results = []

        print("=" * 60)
        print(f"처리 중: {query_file.name}")
        print("=" * 60)

        terms = load_query_expansion(query_file)
        total = len(terms)

        for item in terms:
            idx           = item["index"]
            clause        = item["clause"]
            dense_query   = item["retrieval_payload"]["dense_query"]

            print(f"\n--- 특약 [{idx}] ({terms.index(item)+1}/{total}) ---")
            print(f"원문: {clause[:100]}{'...' if len(clause) > 100 else ''}")

            term_law_results  = []
            term_prec_results = []

            for embed_col in MODEL_COLS:
                t0 = time.time()
                print(f"  {embed_col} 임베딩 중...", end=" ", flush=True)
                query_vec = embed_query(dense_query, embed_col)
                print(f"완료 ({time.time()-t0:.2f}초)")
                time.sleep(0.5)

                # 법령 검색
                t0 = time.time()
                print(f"  {embed_col} 법령 검색 중...", end=" ", flush=True)
                law_results = search_similar(query_vec, law_chunks[embed_col], embed_col)
                print(f"완료 ({time.time()-t0:.2f}초) → {len(law_results)}건")

                for rank, row in law_results.iterrows():
                    term_law_results.append({
                        "model":      embed_col,
                        "rank":       rank + 1,
                        "similarity": float(row["similarity"]),
                        "clause_key": row["clause_key"],
                        "child_text": row["child_text"],
                    })

                # 판례 검색
                t0 = time.time()
                print(f"  {embed_col} 판례 검색 중...", end=" ", flush=True)
                prec_results = search_similar(query_vec, prec_chunks[embed_col], embed_col)
                print(f"완료 ({time.time()-t0:.2f}초) → {len(prec_results)}건")

                for rank, row in prec_results.iterrows():
                    term_prec_results.append({
                        "model":            embed_col,
                        "rank":             rank + 1,
                        "similarity":       float(row["similarity"]),
                        "case_id":          row["case_id"],
                        "judgment_summary": row["judgment_summary"],
                    })

            all_law_results.append({
                "source_file": query_file.name,
                "index":       idx,
                "clause":      clause,
                "results":     term_law_results,
            })

            all_prec_results.append({
                "source_file": query_file.name,
                "index":       idx,
                "clause":      clause,
                "results":     term_prec_results,
            })

        print(f"\n{'=' * 60}")
        print("결과 JSON 저장 중...")
        print("=" * 60)

        file_stem = query_file.stem

        law_path = OUTPUT_DIR / f"{file_stem}_dense_law.json"
        with open(law_path, "w", encoding="utf-8") as f:
            json.dump(all_law_results, f, ensure_ascii=False, indent=2)
        print(f"법령: {law_path} ({sum(len(r['results']) for r in all_law_results)}건)")

        prec_path = OUTPUT_DIR / f"{file_stem}_dense_caselaw.json"
        with open(prec_path, "w", encoding="utf-8") as f:
            json.dump(all_prec_results, f, ensure_ascii=False, indent=2)
        print(f"판례: {prec_path} ({sum(len(r['results']) for r in all_prec_results)}건)")

        print(f"\n{'=' * 60}")
        print(f"전체 소요 시간: {time.time()-total_start:.1f}초")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()