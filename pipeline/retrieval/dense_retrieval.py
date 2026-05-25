"""
특약 문장 vs 법령/판례 청크 시멘틱 검색 (Vertex AI gemini-embedding-001)
- CSV에서 embed_vertex 컬럼을 로드하여 코사인 유사도 기반 검색 수행
"""

import json
import os
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import vertexai
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION   = os.getenv("GCP_LOCATION", "us-central1")

vertexai.init(project=PROJECT_ID, location=LOCATION)

# ── 상수 ──────────────────────────────────────────────────────────────────────
TOP_K        = 100
EMBED_COL    = "embed_vertex"
VERTEX_MODEL = "gemini-embedding-001"

# 코사인 유사도 최솟값 (threshold_sweep_eval.py 결과: 0.0~0.65 구간 동일 recall, 사실상 무효)
MIN_SIMILARITY = 0.2

LAW_TABLE  = "law_child"
PREC_TABLE = "case_law"

LAW_KEEP_COLS  = ["clause_key", "law_name", "article_key", "child_text"]
PREC_KEEP_COLS = ["case_id", "case_name", "judgment_summary"]

_BASE_DIR = Path(__file__).resolve().parents[2]
LAW_CSV_PATH  = _BASE_DIR / "data" / "raw" / "law_child_vertex.csv"
PREC_CSV_PATH = _BASE_DIR / "data" / "raw" / "case_law_with_embeddings_vertex.csv"

# ── 모델 캐시 ─────────────────────────────────────────────────────────────────
_vertex_model: TextEmbeddingModel | None = None
_vertex_lock = threading.Lock()

# df id → 사전 계산된 chunk matrix (쿼리마다 vstack 반복 방지)
_chunk_matrix_cache: dict[int, np.ndarray] = {}
_chunk_matrix_lock = threading.Lock()


def get_vertex_model() -> TextEmbeddingModel:
    global _vertex_model
    if _vertex_model is None:
        with _vertex_lock:
            if _vertex_model is None:
                _vertex_model = TextEmbeddingModel.from_pretrained(VERTEX_MODEL)
    return _vertex_model


# ── 쿼리 임베딩 ───────────────────────────────────────────────────────────────
@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda r: print(
        f"  API 오류, {r.next_action.sleep}초 후 재시도 ({r.attempt_number}/5)..."
    ),
)
def embed_query(query_text: str, embed_col: str = EMBED_COL) -> np.ndarray:
    if embed_col != EMBED_COL:
        raise ValueError(f"지원하지 않는 임베딩 컬럼: {embed_col}. 현재는 {EMBED_COL}만 사용.")
    model = get_vertex_model()
    result = model.get_embeddings([TextEmbeddingInput(text=query_text, task_type="RETRIEVAL_QUERY")])
    return np.array(result[0].values, dtype=np.float32)


# ── CSV 로드 + 임베딩 파싱 ────────────────────────────────────────────────────
def parse_embedding(value) -> np.ndarray:
    if isinstance(value, list):
        return np.array(value, dtype=np.float32)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError("빈 임베딩 문자열")
        return np.array(json.loads(value), dtype=np.float32)
    if pd.isna(value):
        raise ValueError("NaN 임베딩")
    return np.array(value, dtype=np.float32)


def load_chunks(
    table_name: str,
    embed_col: str = EMBED_COL,
    keep_cols: list[str] | None = None,
    extra_filter: str = "",
) -> pd.DataFrame:
    if embed_col != EMBED_COL:
        raise ValueError(f"지원하지 않는 임베딩 컬럼: {embed_col}")

    t0 = time.time()
    if table_name == LAW_TABLE:
        csv_path = LAW_CSV_PATH
        default_keep = LAW_KEEP_COLS
    elif table_name == PREC_TABLE:
        csv_path = PREC_CSV_PATH
        default_keep = PREC_KEEP_COLS
    else:
        raise ValueError(f"알 수 없는 테이블: {table_name}")

    cols = keep_cols if keep_cols is not None else default_keep
    print(f"  로딩: {csv_path.name} [{embed_col}] ...", end=" ", flush=True)

    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    if embed_col not in df.columns:
        raise ValueError(f"{embed_col} 컬럼이 CSV에 없음: {csv_path}")

    df = df[df[embed_col].notna()].reset_index(drop=True)
    if df.empty:
        raise ValueError(f"{embed_col} 데이터 없음: {csv_path}")

    df["_vec"] = df[embed_col].apply(parse_embedding)
    df = df[[c for c in cols if c in df.columns] + ["_vec"]]

    print(f"완료 ({len(df)}행, {time.time() - t0:.1f}초)")
    return df


# ── 유사도 검색 ───────────────────────────────────────────────────────────────
def search_similar(
    query_vec: np.ndarray,
    df: pd.DataFrame,
    embed_col: str = EMBED_COL,
    top_k: int = TOP_K,
    min_similarity: float = MIN_SIMILARITY,
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
            f"차원 불일치: 쿼리={query_matrix.shape[1]}, 청크={chunk_matrix.shape[1]}"
        )

    sims   = cosine_similarity(query_matrix, chunk_matrix)[0]
    result = df.drop(columns=["_vec"]).copy()
    result["similarity"] = sims
    result = result[result["similarity"] >= min_similarity]

    return result.sort_values("similarity", ascending=False).head(top_k).reset_index(drop=True)
