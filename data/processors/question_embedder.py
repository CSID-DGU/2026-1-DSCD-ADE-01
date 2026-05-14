"""Lawtalk 질문 JSON에 Vertex AI 768차원 임베딩을 채운다.

입력은 ``lawtalk_qa_db_ready_from_predictions.json`` 형태를 기대한다.
기존 ``questions[*].embedding`` 값이 있으면 건너뛰므로 중간 저장 파일로 재개할 수 있다.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "lawtalk_qa_preprocessed"
    / "lawtalk_qa_db_ready_from_predictions.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "lawtalk_qa_preprocessed"
    / "lawtalk_qa_db_ready_with_question_embeddings.json"
)

VERTEX_MODEL = "gemini-embedding-001"
VERTEX_DIMENSIONS = 3072
VERTEX_BATCH_SIZE = 100
SLEEP_SEC = 0.5
CHECKPOINT_EVERY = 5
MAX_RETRIES = 5
RETRY_DELAY_SEC = 10


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def build_question_embedding_text(question: dict[str, Any]) -> str:
    parts = []

    title = str(question.get("title") or "").strip()
    if title:
        parts.append(f"제목: {title}")

    body = str(question.get("body") or "").strip()
    if body:
        parts.append(f"본문: {body}")

    tags = question.get("tags") or []
    if isinstance(tags, list) and tags:
        tag_text = ", ".join(str(tag).strip() for tag in tags if str(tag).strip())
        if tag_text:
            parts.append(f"태그: {tag_text}")

    return "\n".join(parts)


def collect_pending_questions(questions: list[dict[str, Any]]) -> list[tuple[int, str]]:
    pending = []
    for index, question in enumerate(questions):
        embedding = question.get("embedding")
        if isinstance(embedding, list) and len(embedding) == VERTEX_DIMENSIONS:
            continue

        text = build_question_embedding_text(question)
        if text:
            pending.append((index, text))

    return pending


def apply_question_embeddings(
    questions: list[dict[str, Any]],
    updates: list[tuple[int, list[float]]],
) -> None:
    for index, embedding in updates:
        questions[index]["embedding"] = embedding


def init_vertex_client():
    load_dotenv(PROJECT_ROOT / ".env")

    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION") or os.getenv("GCP_REGION") or "us-central1"
    if not project_id:
        raise RuntimeError("GCP_PROJECT_ID 환경변수가 필요합니다.")

    from google import genai

    return genai.Client(vertexai=True, project=project_id, location=location)


def embed_batch(client: Any, texts: list[str]) -> list[list[float]]:
    from google.genai import types

    response = client.models.embed_content(
        model=VERTEX_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=VERTEX_DIMENSIONS,
        ),
    )
    return [embedding.values for embedding in response.embeddings]


def embed_batch_with_retry(client: Any, texts: list[str]) -> list[list[float]]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return embed_batch(client, texts)
        except Exception:
            if attempt == MAX_RETRIES:
                raise

            wait_seconds = RETRY_DELAY_SEC * attempt
            print(f"  [재시도 {attempt}/{MAX_RETRIES}] {wait_seconds}s 대기", flush=True)
            time.sleep(wait_seconds)

    raise RuntimeError("unreachable")


def run(
    input_path: str | Path = DEFAULT_INPUT,
    output_path: str | Path = DEFAULT_OUTPUT,
    *,
    limit: int | None = None,
) -> dict[str, int]:
    input_path = Path(input_path)
    output_path = Path(output_path)

    source_path = output_path if output_path.exists() else input_path
    data = read_json(source_path)
    questions = data.get("questions", [])
    pending = collect_pending_questions(questions)
    if limit is not None:
        pending = pending[:limit]

    print(f"[question_embedder] 입력: {source_path}", flush=True)
    print(f"[question_embedder] 출력: {output_path}", flush=True)
    print(f"[question_embedder] 전체 질문: {len(questions)}건", flush=True)
    print(f"[question_embedder] 임베딩 대상: {len(pending)}건", flush=True)

    if not pending:
        write_json(output_path, data)
        return {
            "total_questions": len(questions),
            "embedded_count": sum(q.get("embedding") is not None for q in questions),
            "processed_count": 0,
        }

    client = init_vertex_client()
    processed_count = 0
    total_batches = (len(pending) - 1) // VERTEX_BATCH_SIZE + 1

    for batch_index, start in enumerate(range(0, len(pending), VERTEX_BATCH_SIZE), 1):
        batch = pending[start : start + VERTEX_BATCH_SIZE]
        indexes = [item[0] for item in batch]
        texts = [item[1] for item in batch]

        print(
            f"  Vertex 배치 {batch_index}/{total_batches} ({len(batch)}건)",
            flush=True,
        )
        embeddings = embed_batch_with_retry(client, texts)
        apply_question_embeddings(questions, list(zip(indexes, embeddings)))
        processed_count += len(batch)

        if batch_index % CHECKPOINT_EVERY == 0:
            write_json(output_path, data)
            print(f"  체크포인트 저장: {processed_count}건", flush=True)

        time.sleep(SLEEP_SEC)

    write_json(output_path, data)

    embedded_count = sum(q.get("embedding") is not None for q in questions)
    print(f"[question_embedder] 완료: {embedded_count}/{len(questions)}건", flush=True)
    return {
        "total_questions": len(questions),
        "embedded_count": embedded_count,
        "processed_count": processed_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed Lawtalk questions with Vertex AI")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = run(args.input, args.output, limit=args.limit)
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
