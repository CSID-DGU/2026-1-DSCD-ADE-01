"""법령 child CSV에 임베딩 벡터를 추가한다.

사용 모델:
- Vertex AI: gemini-embedding-001 (3072차원)
- KURE-v1: nlpai-lab/KURE-v1 (1024차원)
"""

import json
import os
import time
from pathlib import Path
import csv
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# ── 경로 설정 ─────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent.parent
INPUT_PATH = DATA_DIR / "law_chunks" / "law_child.csv"
OUTPUT_PATH = DATA_DIR / "law_chunks" / "law_child.csv"

# ── 상수 ──────────────────────────────────────────────────────────────

VERTEX_MODEL = "gemini-embedding-001"
KURE_MODEL = "nlpai-lab/KURE-v1"

# Vertex AI 배치 크기 (API 제한: 최대 250)
VERTEX_BATCH_SIZE = 100
# KURE 배치 크기 (메모리 상황에 따라 조정)
KURE_BATCH_SIZE = 64


# ── Vertex AI 임베딩 ──────────────────────────────────────────────────

def init_vertex():
    """Vertex AI를 초기화한다."""
    import vertexai

    project_id = os.getenv("GCP_PROJECT_ID")
    region = os.getenv("GCP_REGION", "us-central1")

    if not project_id:
        raise ValueError("GCP_PROJECT_ID 환경변수가 설정되지 않았습니다.")

    vertexai.init(project=project_id, location=region)
    print(f"  Vertex AI 초기화 완료 (project={project_id}, region={region})")


def embed_vertex_batch(texts: list[str]) -> list[list[float]]:
    """Vertex AI로 텍스트 배치를 임베딩한다."""
    from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

    model = TextEmbeddingModel.from_pretrained(VERTEX_MODEL)
    inputs = [
        TextEmbeddingInput(text, task_type="RETRIEVAL_DOCUMENT")
        for text in texts
    ]
    embeddings = model.get_embeddings(inputs)
    return [e.values for e in embeddings]


def embed_vertex(texts: list[str]) -> list[list[float]]:
    """전체 텍스트 목록을 Vertex AI로 배치 임베딩한다."""
    results = []
    total = len(texts)

    for i in range(0, total, VERTEX_BATCH_SIZE):
        batch = texts[i: i + VERTEX_BATCH_SIZE]
        print(f"    Vertex 배치 {i // VERTEX_BATCH_SIZE + 1} / {(total - 1) // VERTEX_BATCH_SIZE + 1} ({len(batch)}건)")
        vectors = embed_vertex_batch(batch)
        results.extend(vectors)
        # API 레이트 리밋 방지
        time.sleep(0.5)

    return results


# ── KURE 임베딩 ───────────────────────────────────────────────────────

def init_kure():
    """KURE 모델을 로딩한다."""
    from sentence_transformers import SentenceTransformer

    print(f"  KURE 모델 로딩 중: {KURE_MODEL}")
    model = SentenceTransformer(KURE_MODEL)
    print("  KURE 모델 로딩 완료")
    return model


def embed_kure(texts: list[str], model) -> list[list[float]]:
    """전체 텍스트 목록을 KURE로 배치 임베딩한다."""
    results = []
    total = len(texts)

    for i in range(0, total, KURE_BATCH_SIZE):
        batch = texts[i: i + KURE_BATCH_SIZE]
        print(f"    KURE 배치 {i // KURE_BATCH_SIZE + 1} / {(total - 1) // KURE_BATCH_SIZE + 1} ({len(batch)}건)")
        vectors = model.encode(batch, show_progress_bar=False)
        results.extend(vectors.tolist())

    return results


# ── 실행부 ────────────────────────────────────────────────────────────

def run(
    input_path: str | Path = INPUT_PATH,
    output_path: str | Path = OUTPUT_PATH,
    use_vertex: bool = True,
    use_kure: bool = True,
) -> None:
    """child CSV에 임베딩 컬럼을 추가한다."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    print(f"[법령 embedder] 입력: {input_path}")
    print(f"[법령 embedder] 출력: {output_path}")

    # CSV 로딩
    df = pd.read_csv(input_path, dtype={"paragraph_no": str})
    texts = df["child_text"].fillna("").tolist()
    print(f"  총 {len(texts)}건 임베딩 대상")

    # Vertex AI 임베딩
    if use_vertex:
        print(f"\n[1/2] Vertex AI 임베딩 시작 (모델: {VERTEX_MODEL})")
        init_vertex()
        vertex_vectors = embed_vertex(texts)
        df["embed_vertex"] = [json.dumps(v) for v in vertex_vectors]
        print(f"  완료: {len(vertex_vectors)}건, 차원: {len(vertex_vectors[0])}")

    # KURE 임베딩
    if use_kure:
        print(f"\n[2/2] KURE 임베딩 시작 (모델: {KURE_MODEL})")
        kure_model = init_kure()
        kure_vectors = embed_kure(texts, kure_model)
        df["embed_kure"] = [json.dumps(v) for v in kure_vectors]
        print(f"  완료: {len(kure_vectors)}건, 차원: {len(kure_vectors[0])}")

    # 저장
    df.to_csv(output_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
    print(f"\n저장 완료: {output_path}")


if __name__ == "__main__":
    run()
