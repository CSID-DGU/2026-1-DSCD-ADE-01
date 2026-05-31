"""
특약 문장 vs 법령/판례 청크 시멘틱 검색
- DB에서 임베딩 컬럼을 로드하여 코사인 유사도 기반 검색 수행
"""

# ============================================
# 표준 라이브러리 및 서드파티 import
# ============================================
import sys
import time
import threading
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import vertexai
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput
from sentence_transformers import SentenceTransformer

# ============================================
# 프로젝트 루트를 sys.path에 추가 (shared 모듈 접근용)
# ============================================
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.db.connection import get_db_client
from shared.config import settings

# ============================================
# Vertex AI 초기화
# ============================================
vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)

# ============================================
# 상수 설정
# ============================================
TOP_K = 20

MIN_SIMILARITY = {
    # 법령
    "embed_vertex":      0.2,
    "embed_kure":        0.2,
    "embed_e5":          0.2,
    "embed_kolegal":     0.2,

    # 판례(js)
    "embed_vertex_js":   0.2,
    "embed_kure_js":     0.2,
    "embed_e5_js":       0.2,
    "embed_kolegal_js":  0.2,
}

MODEL_COLS = {
    # 법령
    "embed_vertex":      "gemini-embedding-001",
    "embed_kure":        "nlpai-lab/KURE-v1",
    "embed_e5":          "intfloat/multilingual-e5-large",
    "embed_kolegal":     "woong0322/ko-legal-sbert-finetuned",

    # 판례(js)
    "embed_vertex_js":   "gemini-embedding-001",
    "embed_kure_js":     "nlpai-lab/KURE-v1",
    "embed_e5_js":       "intfloat/multilingual-e5-large",
    "embed_kolegal_js":  "woong0322/ko-legal-sbert-finetuned",
}

LAW_TABLE  = "law_child"
PREC_TABLE = "case_law"

LAW_KEEP_COLS  = ["clause_key", "child_text"]
PREC_KEEP_COLS = ["case_id", "issue", "judgment_summary"]

# ============================================
# 모델 캐시 (스레드 안전)
# ============================================
_vertex_model_cache: dict[str, TextEmbeddingModel] = {}
_vertex_model_lock  = threading.Lock()
_kure_model    = None
_kure_lock     = threading.Lock()
_e5_model      = None
_e5_lock       = threading.Lock()
_kolegal_model = None
_kolegal_lock  = threading.Lock()

# df id → 사전 계산된 chunk matrix (쿼리마다 vstack 반복 방지)
_chunk_matrix_cache: dict[int, np.ndarray] = {}
_chunk_matrix_lock = threading.Lock()


def get_vertex_model(model_name: str) -> TextEmbeddingModel:
    if model_name not in _vertex_model_cache:
        with _vertex_model_lock:
            if model_name not in _vertex_model_cache:
                _vertex_model_cache[model_name] = TextEmbeddingModel.from_pretrained(model_name)
    return _vertex_model_cache[model_name]


def get_kure_model() -> SentenceTransformer:
    global _kure_model
    if _kure_model is None:
        with _kure_lock:
            if _kure_model is None:
                _kure_model = SentenceTransformer("nlpai-lab/KURE-v1")
    return _kure_model


def get_e5_model() -> SentenceTransformer:
    global _e5_model
    if _e5_model is None:
        with _e5_lock:
            if _e5_model is None:
                _e5_model = SentenceTransformer("intfloat/multilingual-e5-large")
    return _e5_model


def get_kolegal_model() -> SentenceTransformer:
    global _kolegal_model
    if _kolegal_model is None:
        with _kolegal_lock:
            if _kolegal_model is None:
                _kolegal_model = SentenceTransformer("woong0322/ko-legal-sbert-finetuned")
    return _kolegal_model


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

    if embed_col in ["embed_vertex", "embed_vertex_js"]:
        model = get_vertex_model(model_name)
        input_obj = TextEmbeddingInput(text=query_text, task_type="RETRIEVAL_QUERY")
        embeddings = model.get_embeddings([input_obj])
        return np.array(embeddings[0].values, dtype=np.float32)

    elif embed_col in ["embed_kure", "embed_kure_js"]:
        model = get_kure_model()
        vec = model.encode(query_text, normalize_embeddings=True)
        return np.array(vec, dtype=np.float32)

    elif embed_col in ["embed_e5", "embed_e5_js"]:
        model = get_e5_model()
        vec = model.encode("query: " + query_text, normalize_embeddings=True)
        return np.array(vec, dtype=np.float32)

    elif embed_col in ["embed_kolegal", "embed_kolegal_js"]:
        model = get_kolegal_model()
        vec = model.encode(query_text, normalize_embeddings=True)
        return np.array(vec, dtype=np.float32)

    else:
        raise ValueError(f"알 수 없는 임베딩 컬럼: {embed_col}")


# ============================================
# DB 로드 + 임베딩 파싱 (DB 우선, CSV 폴백)
# ============================================
_CSV_PATHS = {
    LAW_TABLE:  Path(__file__).resolve().parents[2] / "data" / "raw" / "law_child_vertex.csv",
    PREC_TABLE: Path(__file__).resolve().parents[2] / "data" / "raw" / "case_law_with_embeddings_vertex.csv",
}


def parse_embedding(value) -> np.ndarray:
    """pgvector '[0.1,0.2,...]' / CSV JSON 문자열 / list 형식을 ndarray로 변환."""
    if isinstance(value, list):
        return np.array(value, dtype=np.float32)
    if isinstance(value, str):
        cleaned = value.strip()[1:-1]  # 앞뒤 [] 제거
        return np.array([float(x) for x in cleaned.split(",")], dtype=np.float32)
    return np.array(value, dtype=np.float32)


def load_chunks(
    table_name: str,
    embed_col: str,
    keep_cols: list[str],
    extra_filter: str = "",
) -> pd.DataFrame:
    t0 = time.time()
    print(f"  로딩: {table_name} [{embed_col}] ...", end=" ", flush=True)

    # ── DB 우선 ──────────────────────────────────────────────────────
    try:
        db = get_db_client()
        select_cols = ", ".join(keep_cols + [embed_col])
        where = f"{embed_col} IS NOT NULL"
        if extra_filter:
            where += f" AND {extra_filter}"
        rows = db.fetch_all(text(f"SELECT {select_cols} FROM {table_name} WHERE {where}"))
        if not rows:
            raise ValueError(f"테이블 '{table_name}'에서 데이터 없음")
        df = pd.DataFrame(rows)
        print(f"(DB) ", end="", flush=True)

    # ── CSV 폴백 ─────────────────────────────────────────────────────
    except Exception as e:
        csv_path = _CSV_PATHS.get(table_name)
        if csv_path is None or not csv_path.exists():
            raise ValueError(f"DB 연결 실패 + CSV 없음: {table_name}") from e
        print(f"\n  [경고] DB 연결 실패 ({e.__class__.__name__}), CSV 폴백: {csv_path.name}", flush=True)
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        df = df[df[embed_col].notna()].reset_index(drop=True)
        if df.empty:
            raise ValueError(f"{embed_col} 데이터 없음 (CSV)") from e

    df["_vec"] = df[embed_col].apply(parse_embedding)
    df = df[keep_cols + ["_vec"]]
    print(f"완료 ({len(df)}행, {time.time()-t0:.1f}초)")
    return df


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
