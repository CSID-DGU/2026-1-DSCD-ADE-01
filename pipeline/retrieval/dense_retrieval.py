"""
특약 문장 vs 법령/판례 청크 시멘틱 검색
- DB에서 임베딩 컬럼을 로드하여 코사인 유사도 기반 검색 수행
"""

# ============================================
# 표준 라이브러리 및 서드파티 import
# ============================================
import sys
import os
import time
from pathlib import Path
import json

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
# 상수 설정
# ============================================
TOP_K = 20

MIN_SIMILARITY = {
    "embed_vertex":      0.2
}

MODEL_COLS = {
    "embed_vertex":      "gemini-embedding-001",
}

LAW_TABLE  = "law_child"
PREC_TABLE = "case_law"

LAW_KEEP_COLS  = ["clause_key", "child_text"]
PREC_KEEP_COLS = ["case_id", "issue", "judgment_summary",]

# ============================================
# Vertex AI 초기화
# ============================================
vertexai.init(project=PROJECT_ID, location=LOCATION)

import threading

_vertex_model_cache = {}
_vertex_model_lock = threading.Lock()

# df id → 사전 계산된 chunk matrix (쿼리마다 vstack 반복 방지)
_chunk_matrix_cache: dict[int, np.ndarray] = {}
_chunk_matrix_lock = threading.Lock()

def get_vertex_model(model_name: str) -> TextEmbeddingModel:
    if model_name not in _vertex_model_cache:
        with _vertex_model_lock:
            if model_name not in _vertex_model_cache:
                _vertex_model_cache[model_name] = TextEmbeddingModel.from_pretrained(model_name)
    return _vertex_model_cache[model_name]

# ============================================
# 임베딩 함수
# ============================================
@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda r: print(
        f"  API 오류, {r.next_action.sleep}초 후 재시도 "
        f"({r.attempt_number}/5)..."
    )
)
def embed_query(query_text: str, embed_col: str) -> np.ndarray:
    model_name = MODEL_COLS[embed_col]

    # Vertex
    if embed_col == "embed_vertex":
        model = get_vertex_model(model_name)

        input_obj = TextEmbeddingInput(
            text=query_text,
            task_type="RETRIEVAL_QUERY",
        )

        embeddings = model.get_embeddings([input_obj])

        return np.array(
            embeddings[0].values,
            dtype=np.float32,
        )

    else:
        raise ValueError(
            f"알 수 없는 임베딩 컬럼: {embed_col}"
        )


# ============================================
# DB 로드 + 임베딩 파싱
# ============================================

def parse_embedding(value) -> np.ndarray:
    """pgvector '[0.1,0.2,...]' 또는 list 형식을 ndarray로 변환."""
    if isinstance(value, list):
        return np.array(value, dtype=np.float32)
    if isinstance(value, str):
        cleaned = value.strip()[1:-1]  # 앞뒤 [] 제거
        return np.array([float(x) for x in cleaned.split(",")], dtype=np.float32)
    return np.array(value, dtype=np.float32)


def load_chunks(table_name: str, embed_col: str, keep_cols: list[str], extra_filter: str = "") -> pd.DataFrame:
    t0 = time.time()
    print(f"  로딩: {table_name} [{embed_col}] ...", end=" ", flush=True)

    db = get_db_client()
    select_cols = ", ".join(keep_cols + [embed_col])
    where = f"{embed_col} IS NOT NULL"
    if extra_filter:
        where += f" AND {extra_filter}"
    rows = db.fetch_all(
        text(f"SELECT {select_cols} FROM {table_name} WHERE {where}"),
    )

    if not rows:
        raise ValueError(f"테이블 '{table_name}'에서 데이터 없음")

    df = pd.DataFrame(rows)
    df["_vec"] = df[embed_col].apply(parse_embedding)
    df = df[keep_cols + ["_vec"]]

    print(f"완료 ({len(df)}행, {time.time()-t0:.1f}초)")
    return df

# def parse_embedding(value) -> np.ndarray:
#     """
#     CSV에 저장된 임베딩 문자열(JSON) 또는 list를 ndarray로 변환.
#     """

#     # 이미 list인 경우
#     if isinstance(value, list):
#         return np.array(value, dtype=np.float32)

#     # 문자열인 경우
#     if isinstance(value, str):
#         value = value.strip()
#         # 빈 문자열 처리
#         if not value:
#             raise ValueError("빈 임베딩 문자열")
#         try:
#             # JSON 문자열 파싱
#             parsed = json.loads(value)
#             return np.array(parsed, dtype=np.float32)
#         except Exception as e:
#             raise ValueError(f"임베딩 파싱 실패: {value[:100]}") from e

#     # NaN 처리
#     if pd.isna(value):
#         raise ValueError("NaN 임베딩")

#     # 그 외 ndarray 변환
#     return np.array(value, dtype=np.float32)


# def load_chunks(
#     table_name: str,
#     embed_col: str,
#     keep_cols: list[str],
#     extra_filter: str = "",
# ) -> pd.DataFrame:

#     t0 = time.time()
#     print(f"  로딩: {table_name} [{embed_col}] ...", end=" ", flush=True,)
#     base_dir = Path(__file__).resolve().parents[2]
#     if table_name == LAW_TABLE:
#         csv_path = (base_dir/"data"/"raw"/"law_child.csv")

#     elif table_name == PREC_TABLE:

#         csv_path = (base_dir/"output"/"case_law_with_embeddings.csv")

#     else:
#         raise ValueError(f"알 수 없는 테이블: {table_name}")

#     print(f"\n    CSV 경로: {csv_path}")

#     df = pd.read_csv(csv_path, encoding="utf-8-sig")

#     # 임베딩 컬럼 존재 여부 확인
#     if embed_col not in df.columns:
#         raise ValueError(f"{embed_col} 컬럼이 CSV에 없음")

#     # 임베딩 존재 row만 유지
#     df = df[df[embed_col].notna()].reset_index(drop=True)

#     if df.empty:
#         raise ValueError(f"{embed_col} 데이터 없음")

#     # 임베딩 파싱
#     df["_vec"] = df[embed_col].apply(parse_embedding)

#     # 필요한 컬럼만 유지
#     df = df[keep_cols + ["_vec"]]
#     print(
#         f"완료 ({len(df)}행, "
#         f"{time.time()-t0:.1f}초)"
#     )

#     return df


# ============================================
# 유사도 검색
# ============================================
def search_similar(
    query_vec: np.ndarray,
    df: pd.DataFrame,
    embed_col: str,
    top_k: int = TOP_K,
) -> pd.DataFrame:
    df_id = id(df)
    if df_id not in _chunk_matrix_cache:
        with _chunk_matrix_lock:
            if df_id not in _chunk_matrix_cache:
                _chunk_matrix_cache[df_id] = np.vstack(df["_vec"].values)
    chunk_matrix = _chunk_matrix_cache[df_id]
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
