"""법령 child CSV에 임베딩 벡터를 추가한다.

사용 모델:
- Vertex AI: gemini-embedding-001 (3072차원)

임베딩 텍스트: parent_text + child_text (prefix 방식)
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
INPUT_CHILD_PATH = DATA_DIR / "raw" / "law_child.csv"
INPUT_PARENT_PATH = DATA_DIR / "raw" / "law_parent.csv"
OUTPUT_PATH = DATA_DIR / "raw" / "law_child_vertex.csv"

# ── 상수 ──────────────────────────────────────────────────────────────

VERTEX_MODEL = "gemini-embedding-001"

# Vertex AI 배치 크기 (API 제한: 최대 250)
VERTEX_BATCH_SIZE = 100


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


# ── 실행부 ────────────────────────────────────────────────────────────

def run(
    input_child_path: str | Path = INPUT_CHILD_PATH,
    input_parent_path: str | Path = INPUT_PARENT_PATH,
    output_path: str | Path = OUTPUT_PATH,
) -> None:
    """child CSV에 parent_text 컬럼 및 임베딩 컬럼을 추가한다.

    - law_child와 law_parent를 article_key로 JOIN
    - 임베딩 텍스트: parent_text + child_text (prefix 방식)
    - embed_vertex 컬럼이 이미 존재하면 임베딩을 건너뜀
    """
    input_child_path = Path(input_child_path)
    input_parent_path = Path(input_parent_path)
    output_path = Path(output_path)

    print(f"[법령 embedder] child 입력: {input_child_path}")
    print(f"[법령 embedder] parent 입력: {input_parent_path}")
    print(f"[법령 embedder] 출력: {output_path}")

    # child, parent 로드
    df_child = pd.read_csv(input_child_path, dtype={"paragraph_no": str})
    df_parent = pd.read_csv(input_parent_path)[["article_key", "parent_text"]]
    print(f"  child {len(df_child)}건, parent {len(df_parent)}건 로드 완료")

    # article_key로 JOIN하여 parent_text 추가
    df = df_child.merge(df_parent, on="article_key", how="left")

    # JOIN 결과 확인
    missing = df["parent_text"].isna().sum()
    if missing > 0:
        print(f"  경고: parent_text 매핑 실패 {missing}건 (article_key 불일치)")

    print(f"\n[1] Vertex AI 임베딩 시작 (모델: {VERTEX_MODEL})")

    if "embed_vertex" in df.columns:
        print("  embed_vertex 컬럼 존재 → 건너뜀")
    else:
        init_vertex()

        # 임베딩 텍스트: parent_text를 prefix로 붙인 뒤 child_text 결합
        def build_embed_text(row) -> str:
            parent = row["parent_text"] if pd.notna(row["parent_text"]) else ""
            child = row["child_text"] if pd.notna(row["child_text"]) else ""
            if parent:
                return f"{parent}\n\n{child}"
            return child

        embed_texts = df.apply(build_embed_text, axis=1).tolist()

        vectors = embed_vertex(embed_texts)
        df["embed_vertex"] = [json.dumps(v) for v in vectors]
        print(f"  완료: {len(vectors)}건, 차원: {len(vectors[0])}")

    # 저장할 컬럼 순서 정의
    keep_cols = [
        "clause_key",
        "article_key",
        "law_name",
        "article_no",
        "paragraph_no",
        "child_text",
        "parent_text",
        "embed_vertex",
    ]

    existing_cols = [c for c in keep_cols if c in df.columns]
    df = df[existing_cols]

    df.to_csv(output_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
    print(f"\n저장 완료: {output_path}")
    
if __name__ == "__main__":
    run()