"""Helpers for legal retrieval evaluation datasets and metric matching."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.processors.validation_dataset_processor import (
    case_law_has_clause_keyword,
    coerce_export_id,
    has_clause_keyword,
    stable_scalar_sort_key,
)
PIPELINE_IMPORT_ERROR: ImportError | None = None
try:
    from pipeline.reranking import reranker as project_reranker
    from pipeline.retrieval.bm25_retrieval import build_query_tokens, tokenize
    from pipeline.retrieval import dense_retrieval
    from pipeline.retrieval.evaluation_retrieval import (
        collect_case_documents,
        expand_case_queries,
        inspect_retrieved_documents,
    )
    from rank_bm25 import BM25Okapi
except ImportError as error:
    PIPELINE_IMPORT_ERROR = error


DEFAULT_RECALL_K_VALUES = [1, 3, 5, 10, 20]
REPORT_SCHEMA_VERSION = "legal_retrieval_eval.v1"
REQUIRED_CASE_FIELDS = ("case_id", "clauses", "law_references", "precedent_references")
DEFAULT_INPUT_PATH = PROJECT_ROOT / "evaluation" / "eval_set.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
SEMANTIC_EMBED_COL = "embed_vertex"
LAW_SEMANTIC_EMBED_COL = "embed_vertex"
PRECEDENT_SEMANTIC_EMBED_COL = "embedding"
LAW_SEMANTIC_KEEP_COLS = ["clause_key", "child_text"]
PRECEDENT_SEMANTIC_KEEP_COLS = ["case_id", "case_number", "judgment_summary"]


class DatasetValidationError(ValueError):
    """Raised when an evaluation dataset cannot satisfy the CLI contract."""


class PipelineImportError(RuntimeError):
    """Raised when the real retrieval/reranking pipeline is unavailable."""


@dataclass
class CaseExecutionContext:
    """Per-case state isolated from the rest of an evaluation run."""

    case: dict[str, Any]
    case_index: int
    input_path: Path
    expanded_queries: list[dict[str, Any]] = field(default_factory=list)
    keyword_results: list[dict[str, Any]] = field(default_factory=list)
    semantic_results: list[dict[str, Any]] = field(default_factory=list)
    reranked_results: list[dict[str, Any]] = field(default_factory=list)
    inspected_documents: list[dict[str, Any]] = field(default_factory=list)
    stage_trace: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"
    error: dict[str, str] | None = None

    @property
    def case_id(self) -> str:
        return self.case["case_id"]


def assert_real_pipeline_imports_available() -> None:
    if PIPELINE_IMPORT_ERROR is None:
        return
    raise PipelineImportError(
        "real retrieval/reranking pipeline import failed: "
        f"{type(PIPELINE_IMPORT_ERROR).__name__}: {PIPELINE_IMPORT_ERROR}\n"
        "Required actions: restore the project retrieval/reranking modules and "
        "install their dependencies, then rerun evaluation/legal_retrieval_eval.py."
    )


def parse_text_array(value: Any) -> list[str]:
    """Parse Cloud SQL text-array exports such as {a,b} into Python strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if not isinstance(value, str):
        return [str(value)]

    text = value.strip()
    if text in {"", "{}"}:
        return []
    if not (text.startswith("{") and text.endswith("}")):
        return [text]

    inner = text[1:-1]
    if not inner:
        return []
    return [item for item in next(csv.reader([inner])) if item]


def append_unique(items: list[str], additions: list[str]) -> None:
    for item in additions:
        if item not in items:
            items.append(item)


def has_source_clause_keyword(row: dict[str, Any]) -> bool:
    """Apply the QA and case-law keyword filters to the correct source fields."""
    source_type = row.get("source_type")
    source_text = row.get("source_text")
    text_fields = source_text if isinstance(source_text, dict) else row

    if source_type == "qa" or "question_body" in text_fields:
        return has_clause_keyword(text_fields.get("question_body") or "")
    if source_type == "case_law" or "case_id" in row:
        return case_law_has_clause_keyword(text_fields)
    return False


def preprocess_qa_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate QA rows by question_id and union answer-level GT."""
    grouped: dict[Any, dict[str, Any]] = {}
    for row in rows:
        question_id = coerce_export_id(row["question_id"])
        if question_id not in grouped:
            grouped[question_id] = {
                "source_type": "qa",
                "source_id": question_id,
                "question_id": question_id,
                "question_title": row.get("question_title") or "",
                "question_body": row.get("question_body") or "",
                "gt_laws": [],
                "gt_cases": [],
                "answer_ids": [],
                "n_answers": 0,
            }

        group = grouped[question_id]
        question_body = row.get("question_body") or ""
        if question_body and not has_clause_keyword(group["question_body"]):
            group["question_body"] = question_body
        group["answer_ids"].append(coerce_export_id(row["answer_id"]))
        group["n_answers"] += 1
        append_unique(group["gt_laws"], parse_text_array(row.get("referenced_laws")))
        append_unique(group["gt_cases"], parse_text_array(row.get("referenced_cases")))

    candidates: list[dict[str, Any]] = []
    for group in sorted(
        grouped.values(),
        key=lambda item: stable_scalar_sort_key(item["question_id"]),
    ):
        if not has_source_clause_keyword(group):
            continue
        if not group["gt_laws"] and not group["gt_cases"]:
            continue
        group["gt_laws"] = sorted(group["gt_laws"])
        group["gt_cases"] = sorted(group["gt_cases"])
        group["answer_ids"] = sorted(group["answer_ids"], key=stable_scalar_sort_key)
        candidates.append(group)
    return candidates


def build_eval_set_from_stage_rows(
    qa_stage_rows: list[dict[str, Any]],
    case_stage_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build eval_set.json records after LLM stage outputs are attached."""
    records: list[dict[str, Any]] = []
    for row in sorted(
        qa_stage_rows,
        key=lambda item: stable_scalar_sort_key(item.get("question_id", "")),
    ):
        if not has_source_clause_keyword({**row, "source_type": "qa"}):
            continue
        record = eval_record_from_qa_stage_row(row)
        if record is not None:
            records.append(record)

    for row in sorted(
        case_stage_rows,
        key=lambda item: stable_scalar_sort_key(item.get("case_id", "")),
    ):
        # The combined 특약/조항 search over issue/summary/detail is only for case-law.
        if not has_source_clause_keyword({**row, "source_type": "case_law"}):
            continue
        record = eval_record_from_case_stage_row(row)
        if record is not None:
            records.append(record)

    return records


def eval_record_from_qa_stage_row(row: dict[str, Any]) -> dict[str, Any] | None:
    source_id = coerce_export_id(row["question_id"])
    return build_stage_eval_record(
        source_type="qa",
        source_id=source_id,
        source_text={"question_body": row.get("question_body") or ""},
        gt_laws=row.get("gt_laws") or [],
        gt_cases=row.get("gt_cases") or [],
        meta={
            "question_title": row.get("question_title") or "",
            "answer_ids": row.get("answer_ids") or [],
            "n_answers": row.get("n_answers") or 0,
        },
        stage1=row.get("stage1") or {},
        stage2=row.get("stage2") or [],
    )


def eval_record_from_case_stage_row(row: dict[str, Any]) -> dict[str, Any] | None:
    source_id = coerce_export_id(row["case_id"])
    return build_stage_eval_record(
        source_type="case_law",
        source_id=source_id,
        source_text={
            "issue": row.get("issue") or "",
            "judgment_summary": row.get("judgment_summary") or "",
            "case_detail": row.get("case_detail") or "",
        },
        gt_laws=row.get("gt_laws") or [],
        gt_cases=row.get("gt_cases") or [],
        meta={
            "case_name": row.get("case_name") or "",
            "case_number": row.get("case_number") or "",
            "judgment_date": row.get("judgment_date") or "",
            "court_name": row.get("court_name") or "",
        },
        stage1=row.get("stage1") or {},
        stage2=row.get("stage2") or [],
    )


def build_stage_eval_record(
    *,
    source_type: str,
    source_id: int | str,
    source_text: dict[str, str],
    gt_laws: list[str],
    gt_cases: list[str],
    meta: dict[str, Any],
    stage1: dict[str, Any],
    stage2: list[dict[str, Any]],
) -> dict[str, Any] | None:
    clause_type = stage1.get("clause_type")
    if clause_type == "mention_only" or not stage1.get("is_evaluable"):
        return None
    clauses = stage_clauses(clause_type, stage1.get("extracted_clauses") or [], stage2)
    if not clauses or (not gt_laws and not gt_cases):
        return None
    prefix = "case" if source_type == "case_law" else source_type
    return {
        "id": f"{prefix}_{source_id}",
        "source_type": source_type,
        "source_id": source_id,
        "source_text": source_text,
        "clauses": clauses,
        "gt_laws": sorted(gt_laws),
        "gt_cases": sorted(gt_cases),
        "meta": meta,
    }


def stage_clauses(
    clause_type: str,
    extracted_clauses: list[str],
    stage2: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if clause_type == "explicit_quote":
        return [
            {"raw": clause, "normalized": clause, "clause_type": clause_type}
            for clause in extracted_clauses
            if clause
        ]
    return [
        {
            "raw": item["raw"],
            "normalized": item["normalized"],
            "clause_type": clause_type,
        }
        for item in stage2
        if item.get("raw") and item.get("normalized")
    ]


def normalize_eval_record_for_pipeline(
    record: dict[str, Any],
    case_index: int,
) -> dict[str, Any]:
    """Convert eval_set.json shape into the older retrieval-eval case shape."""
    return {
        "case_id": record.get("id") or f"eval_{case_index}",
        "clauses": [clause["normalized"] for clause in record.get("clauses", [])],
        "law_references": [
            {"law_child": law_key} for law_key in record.get("gt_laws", [])
        ],
        "precedent_references": [
            {"case_number": case_number} for case_number in record.get("gt_cases", [])
        ],
        "source_type": record.get("source_type"),
        "source_id": record.get("source_id"),
        "source_text": record.get("source_text", {}),
        "meta": record.get("meta", {}),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run legal QA retrieval evaluation for a JSON array dataset."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_PATH),
        help="Absolute path to a JSON array evaluation dataset.",
    )
    parser.add_argument(
        "--case-id",
        help="Optional case_id to evaluate from the input JSON array.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Optional JSON report filename. Reports are always written under "
            "evaluation/results/."
        ),
    )
    return parser.parse_args()


def load_dataset(input_path: Path) -> list[dict[str, Any]]:
    if not input_path.is_absolute():
        raise DatasetValidationError("--input must be an absolute path")

    if not input_path.exists():
        raise DatasetValidationError(f"input file does not exist: {input_path}")

    try:
        with input_path.open("r", encoding="utf-8") as file:
            dataset = json.load(file)
    except json.JSONDecodeError as error:
        raise DatasetValidationError(f"malformed JSON in {input_path}: {error}") from error

    if not isinstance(dataset, list):
        raise DatasetValidationError("input JSON must be an array of case objects")

    normalized_dataset = [
        normalize_eval_record_for_pipeline(case, index)
        if is_eval_set_record(case)
        else case
        for index, case in enumerate(dataset)
    ]

    for index, case in enumerate(normalized_dataset):
        validate_case(case, index)

    return normalized_dataset


def is_eval_set_record(case: Any) -> bool:
    return isinstance(case, dict) and {
        "id",
        "source_type",
        "source_id",
        "source_text",
        "clauses",
        "gt_laws",
        "gt_cases",
        "meta",
    }.issubset(case)


def validate_case(case: Any, index: int) -> None:
    if not isinstance(case, dict):
        raise DatasetValidationError(f"case at index {index} must be an object")

    missing = [field for field in REQUIRED_CASE_FIELDS if field not in case]
    if missing:
        raise DatasetValidationError(
            f"case at index {index} is missing required fields: {', '.join(missing)}"
        )

    if not isinstance(case["case_id"], str) or not case["case_id"].strip():
        raise DatasetValidationError(f"case at index {index} must include a case_id string")

    for field in ("clauses", "law_references", "precedent_references"):
        if not isinstance(case[field], list):
            raise DatasetValidationError(
                f"case {case['case_id']} field {field} must be an array"
            )

    for clause_index, clause in enumerate(case["clauses"]):
        validate_non_empty_string(
            clause,
            f"case {case['case_id']} clauses[{clause_index}]",
        )

    validate_reference_objects(
        case_id=case["case_id"],
        field="law_references",
        references=case["law_references"],
        required_key="law_child",
    )
    validate_reference_objects(
        case_id=case["case_id"],
        field="precedent_references",
        references=case["precedent_references"],
        required_key="case_number",
    )


def validate_non_empty_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{label} must be a non-empty string")


def validate_reference_objects(
    *,
    case_id: str,
    field: str,
    references: list[Any],
    required_key: str,
) -> None:
    for reference_index, reference in enumerate(references):
        item_label = f"case {case_id} {field}[{reference_index}]"
        if not isinstance(reference, dict):
            raise DatasetValidationError(f"{item_label} must be an object")

        validate_non_empty_string(
            reference.get(required_key),
            f"{item_label}.{required_key}",
        )


def select_cases(
    dataset: list[dict[str, Any]],
    case_id: str | None,
) -> list[dict[str, Any]]:
    if case_id is None:
        return dataset

    selected = [case for case in dataset if case["case_id"] == case_id]
    if not selected:
        raise DatasetValidationError(f"case_id not found: {case_id}")
    return selected


def build_case_contexts(
    *,
    input_path: Path,
    cases: list[dict[str, Any]],
) -> list[CaseExecutionContext]:
    return [
        CaseExecutionContext(case=case, case_index=index, input_path=input_path)
        for index, case in enumerate(cases)
    ]


def run_case_pipeline(context: CaseExecutionContext) -> None:
    current_stage = "query_expansion"
    try:
        current_stage = "query_expansion"
        context.expanded_queries.extend(expand_case_queries(context.case))
        record_stage(context, current_stage, len(context.expanded_queries))

        current_stage = "hybrid_retrieval"
        keyword_results = run_bm25_retrieval(
            case=context.case,
            expanded_queries=context.expanded_queries,
        )
        semantic_results = run_semantic_retrieval(
            case=context.case,
            expanded_queries=context.expanded_queries,
        )
        context.keyword_results.extend(keyword_results)
        context.semantic_results.extend(semantic_results)
        record_stage(
            context,
            current_stage,
            len(context.keyword_results) + len(context.semantic_results),
        )

        current_stage = "reranking"
        context.reranked_results.extend(
            run_project_reranking(
                keyword_results=context.keyword_results,
                semantic_results=context.semantic_results,
            )
        )
        record_stage(context, current_stage, len(context.reranked_results))

        current_stage = "document_inspection"
        context.inspected_documents.extend(
            inspect_retrieved_documents(context.reranked_results)
        )
        record_stage(context, current_stage, len(context.inspected_documents))
        context.status = "completed"
    except Exception as error:  # noqa: BLE001 - report per-case pipeline failures.
        context.status = "failed"
        context.error = {
            "type": type(error).__name__,
            "message": str(error),
            "stage": current_stage,
        }
        record_stage(
            context,
            current_stage,
            current_stage_output_count(context, current_stage),
            status="failed",
            error=context.error,
        )


def run_bm25_retrieval(
    *,
    case: dict[str, Any],
    expanded_queries: list[dict[str, Any]],
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Run the project BM25 tokenizer/query path against case-local documents."""
    documents = collect_case_documents(case)
    if not documents:
        return []

    corpus_tokens = [tokenize(document["search_text"]) for document in documents]
    bm25 = BM25Okapi(corpus_tokens)
    results: list[dict[str, Any]] = []

    for query in expanded_queries:
        keywords = query["retrieval_payload"]["bm25_keywords"]
        query_tokens = build_query_tokens(keywords)
        scores = bm25.get_scores(query_tokens)
        top_indexes = sorted(
            range(len(scores)),
            key=lambda document_index: scores[document_index],
            reverse=True,
        )[:top_k]

        for rank, document_index in enumerate(top_indexes, 1):
            document = documents[document_index]
            score = round(float(scores[document_index]), 6)
            results.append(
                {
                    "clause_index": query["clause_index"],
                    "clause": query["clause"],
                    "result_id": document["result_id"],
                    "source_type": document["source_type"],
                    "score": score,
                    "keyword_score": score,
                    "retrieval_method": "bm25",
                    "rank": rank,
                    "document_body": document["document_body"],
                    "document_text": document["document_text"],
                    "metadata": document["metadata"],
                    "query_tokens": query_tokens,
                }
            )

    return results


@lru_cache(maxsize=1)
def load_semantic_chunks() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        dense_retrieval.load_chunks(
            dense_retrieval.LAW_TABLE,
            LAW_SEMANTIC_EMBED_COL,
            LAW_SEMANTIC_KEEP_COLS,
        ),
        dense_retrieval.load_chunks(
            dense_retrieval.PREC_TABLE,
            PRECEDENT_SEMANTIC_EMBED_COL,
            PRECEDENT_SEMANTIC_KEEP_COLS,
        ),
    )


def run_semantic_retrieval(
    *,
    expanded_queries: list[dict[str, Any]],
    case: dict[str, Any] | None = None,
    top_k: int = 20,
    embed_col: str = SEMANTIC_EMBED_COL,
) -> list[dict[str, Any]]:
    """Run semantic retrieval through the project's dense retriever module."""
    case_documents = collect_case_documents(case) if case is not None else []
    if case_documents:
        return run_case_local_semantic_retrieval(
            case=case,
            expanded_queries=expanded_queries,
            top_k=top_k,
        )
    if case is not None and not is_real_eval_case(case):
        return []

    law_chunks, precedent_chunks = load_semantic_chunks()

    results: list[dict[str, Any]] = []
    for query in expanded_queries:
        dense_query = query["retrieval_payload"]["dense_query"]
        query_vec = dense_retrieval.embed_query(dense_query, embed_col)
        results.extend(
            semantic_results_from_rows(
                query=query,
                rows=dense_retrieval.search_similar(
                    query_vec,
                    law_chunks,
                    LAW_SEMANTIC_EMBED_COL,
                    top_k,
                ),
                source_type="law",
            )
        )
        results.extend(
            semantic_results_from_rows(
                query=query,
                rows=dense_retrieval.search_similar(
                    query_vec,
                    precedent_chunks,
                    PRECEDENT_SEMANTIC_EMBED_COL,
                    top_k,
                ),
                source_type="precedent",
            )
        )
    return results


def is_real_eval_case(case: dict[str, Any]) -> bool:
    return {"source_type", "source_id", "source_text", "meta"}.issubset(case)


def run_case_local_semantic_retrieval(
    *,
    case: dict[str, Any],
    expanded_queries: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """Use project dense ranking on inline documents used by tests and examples."""
    documents = collect_case_documents(case)
    texts = [query["retrieval_payload"]["dense_query"] for query in expanded_queries]
    texts.extend(document["search_text"] for document in documents)
    vocabulary = sorted({token for text in texts for token in tokenize(text)})
    if not vocabulary:
        return []

    token_index = {token: index for index, token in enumerate(vocabulary)}
    document_frame = pd.DataFrame(
        [
            {
                **document,
                "_vec": vectorize_text(document["search_text"], token_index),
            }
            for document in documents
        ]
    )

    results: list[dict[str, Any]] = []
    dense_retrieval.MIN_SIMILARITY.setdefault("case_local", 0.0)
    for query in expanded_queries:
        query_vec = vectorize_text(query["retrieval_payload"]["dense_query"], token_index)
        results.extend(
            semantic_results_from_rows(
                query=query,
                rows=dense_retrieval.search_similar(
                    query_vec,
                    document_frame,
                    "case_local",
                    top_k,
                ),
                source_type=None,
            )
        )
    return results


def vectorize_text(text: str, token_index: dict[str, int]) -> np.ndarray:
    vector = np.zeros(len(token_index), dtype=np.float32)
    for token in tokenize(text):
        if token in token_index:
            vector[token_index[token]] += 1.0
    return vector


def semantic_results_from_rows(
    *,
    query: dict[str, Any],
    rows: Any,
    source_type: str | None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for rank, (_, row) in enumerate(rows.iterrows(), 1):
        row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)
        similarity = round(float(row_dict.get("similarity", 0.0)), 6)
        result_source_type = source_type or str(row_dict.get("source_type", "document"))
        document_text = semantic_document_text(row_dict)
        metadata = {
            key: value
            for key, value in row_dict.items()
            if key
            not in {
                "_vec",
                "similarity",
                "document_body",
                "document_text",
                "search_text",
            }
        }
        # Project precedent retrieval rows expose case_number directly.
        # Store it in the same nested shape used by the metric matcher.
        if result_source_type == "precedent" and row_dict.get("case_number"):
            metadata.setdefault("case_law", {})["case_number"] = row_dict["case_number"]
        results.append(
            {
                "clause_index": query["clause_index"],
                "clause": query["clause"],
                "result_id": semantic_result_id(row_dict, result_source_type),
                "source_type": result_source_type,
                "score": similarity,
                "semantic_score": similarity,
                "similarity": similarity,
                "retrieval_method": "semantic",
                "rank": rank,
                "document_body": row_dict.get("document_body", document_text),
                "document_text": row_dict.get("document_text", document_text),
                "metadata": metadata,
            }
        )
    return results


def semantic_result_id(row: dict[str, Any], source_type: str) -> str:
    if source_type == "law" and row.get("clause_key"):
        return f"law:{row['clause_key']}"
    if source_type == "precedent":
        case_number = row.get("case_number")
        if not case_number and isinstance(row.get("case_law"), dict):
            case_number = row["case_law"].get("case_number")
        if case_number:
            return f"precedent:{case_number}"
        if row.get("case_id"):
            return f"precedent:{row['case_id']}"
    return str(row.get("result_id") or f"{source_type}:{abs(hash(str(row)))}")


def run_project_reranking(
    *,
    keyword_results: list[dict[str, Any]],
    semantic_results: list[dict[str, Any]],
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Use the project RRF reranker with the in-memory evaluation candidates."""
    result_lookup: dict[tuple[int, str], dict[str, Any]] = {}
    bm25_map: dict[int, dict[str, Any]] = {}
    dense_map: dict[str, list[dict[str, Any]]] = {}

    for result in keyword_results:
        clause_index = int(result["clause_index"])
        result_id = str(result["result_id"])
        result_lookup.setdefault((clause_index, result_id), dict(result))
        bm25_item = bm25_map.setdefault(
            clause_index,
            {"special_terms": result["clause"], "rank_map": {}},
        )
        bm25_item["rank_map"][result_id] = int(result["rank"])

    for result in semantic_results:
        clause_index = int(result["clause_index"])
        result_id = str(result["result_id"])
        lookup_item = result_lookup.setdefault((clause_index, result_id), dict(result))
        lookup_item["semantic_score"] = result.get("semantic_score", result.get("score", 0.0))
        bm25_map.setdefault(
            clause_index,
            {"special_terms": result["clause"], "rank_map": {}},
        )
        dense_map.setdefault(result["clause"], []).append(
            {
                "doc_id": result_id,
                "score": float(result.get("score", result.get("similarity", 0.0))),
                "rank": int(result["rank"]),
                "doc_text": result.get("document_body") or result.get("document_text", ""),
                "summary": result.get("metadata", {}).get("judgment_summary", ""),
            }
        )

    reranked_groups = project_reranker.run_rrf(
        bm25_map,
        dense_map,
        project_reranker.K,
        top_k,
    )
    reranked_results: list[dict[str, Any]] = []
    for group in reranked_groups:
        clause_index = int(group["index"])
        for match in group.get("top_matches", []):
            result_id = str(match["doc_id"])
            original = result_lookup.get((clause_index, result_id), {})
            # Preserve the retrieval fields used by metric matching and reports.
            item = {
                "clause_index": clause_index,
                "clause": group["special_terms"],
                "result_id": result_id,
                "source_type": original.get("source_type", "document"),
                "document_body": original.get("document_body", match.get("doc_text", "")),
                "document_text": original.get("document_text", match.get("doc_text", "")),
                "metadata": original.get("metadata", {}),
                "keyword_rank": match.get("bm25_rank"),
                "semantic_rank": match.get("dense_rank"),
                "keyword_score": float(original.get("keyword_score", 0.0)),
                "semantic_score": float(original.get("semantic_score", 0.0)),
                "rerank_score": float(match["rrf_score"]),
                "score": float(match["rrf_score"]),
                "retrieval_method": "rerank",
                "rank": int(match["rank"]),
            }
            reranked_results.append(item)
    return reranked_results


def semantic_document_text(row: dict[str, Any]) -> str:
    for field in ("child_text", "judgment_summary", "document_text", "document_body", "text"):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return " ".join(str(value) for value in row.values() if value is not None)


def current_stage_output_count(context: CaseExecutionContext, stage: str) -> int:
    if stage == "query_expansion":
        return len(context.expanded_queries)
    if stage == "hybrid_retrieval":
        return len(context.keyword_results) + len(context.semantic_results)
    if stage == "reranking":
        return len(context.reranked_results)
    if stage == "document_inspection":
        return len(context.inspected_documents)
    return 0


def build_case_report(context: CaseExecutionContext) -> dict[str, Any]:
    run_case_pipeline(context)
    return case_report_payload(context)


def case_report_payload(context: CaseExecutionContext) -> dict[str, Any]:
    case = context.case
    clauses = list(case["clauses"])
    stage_results = {
        "bm25": context.keyword_results,
        "semantic": context.semantic_results,
        "rerank": context.reranked_results,
    }
    stage_recall_at_k = {
        stage: calculate_stage_recall_at_k(
            law_references=case["law_references"],
            precedent_references=case["precedent_references"],
            results=results,
        )
        for stage, results in stage_results.items()
    }
    candidate_counts = {
        stage: count_source_candidates(results) for stage, results in stage_results.items()
    }
    recall_by_k = calculate_recall_by_k(
        law_references=case["law_references"],
        precedent_references=case["precedent_references"],
        reranked_results=context.reranked_results,
    )
    law_recall_at_k = calculate_law_recall_at_k(
        law_references=case["law_references"],
        reranked_results=context.reranked_results,
    )
    precedent_hit_flags_by_k = calculate_precedent_hit_flags_by_k(
        precedent_references=case["precedent_references"],
        reranked_results=context.reranked_results,
    )
    query_hit_flags_by_k = calculate_query_hit_flags_by_k(
        case_id=context.case_id,
        clauses=clauses,
        expanded_queries=context.expanded_queries,
        law_references=case["law_references"],
        precedent_references=case["precedent_references"],
        reranked_results=context.reranked_results,
    )
    query_expansion = build_query_expansion_payload(
        clauses=clauses,
        expanded_queries=context.expanded_queries,
    )
    integrated_recall = calculate_integrated_recall(
        law_references=case["law_references"],
        precedent_references=case["precedent_references"],
        reranked_results=context.reranked_results,
    )
    return {
        "case_id": context.case_id,
        "status": context.status,
        "error": context.error,
        "execution_context": {
            "case_id": context.case_id,
            "case_index": context.case_index,
            "input_path": str(context.input_path),
        },
        "clauses": clauses,
        "law_references": case["law_references"],
        "precedent_references": case["precedent_references"],
        "query_expansion": query_expansion,
        "expanded_queries": context.expanded_queries,
        "keyword_results": context.keyword_results,
        "semantic_results": context.semantic_results,
        "reranked_results": context.reranked_results,
        "inspected_documents": context.inspected_documents,
        "stage_trace": context.stage_trace,
        "candidate_counts": candidate_counts,
        "stage_recall_at_k": stage_recall_at_k,
        "recall_by_k": recall_by_k,
        "law_recall_at_k": law_recall_at_k,
        "precedent_hit_flags_by_k": precedent_hit_flags_by_k,
        "query_hit_flags_by_k": query_hit_flags_by_k,
        "integrated_recall": integrated_recall,
        "recall_report": {
            "case_id": context.case_id,
            "query_expansion": query_expansion,
            "expanded_queries": context.expanded_queries,
            "candidate_counts": candidate_counts,
            "stage_recall_at_k": stage_recall_at_k,
            "recall_by_k": recall_by_k,
            "law_recall_at_k": law_recall_at_k,
            "precedent_hit_flags_by_k": precedent_hit_flags_by_k,
            "query_hit_flags_by_k": query_hit_flags_by_k,
            "integrated_recall": integrated_recall,
        },
    }


def build_query_expansion_payload(
    *,
    clauses: list[str],
    expanded_queries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "query_count": len(expanded_queries),
        "clauses": clauses,
        "expanded_queries": expanded_queries,
        "per_clause_outputs": [
            query_expansion_step_output(query) for query in expanded_queries
        ],
        "expansion_queries": [
            query["expansion_query"]
            for query in expanded_queries
            if isinstance(query.get("expansion_query"), str)
        ],
        "keywords": unique_query_keywords(expanded_queries),
    }


def query_expansion_step_output(query: dict[str, Any]) -> dict[str, Any]:
    return {
        "clause_index": query.get("clause_index"),
        "clause": query.get("clause"),
        "query": query.get("query"),
        "expansion_query": query.get("expansion_query"),
        "keywords": query.get("keywords", []),
        "expansion": query.get("expansion", {}),
        "retrieval_payload": query.get("retrieval_payload", {}),
    }


def unique_query_keywords(expanded_queries: list[dict[str, Any]]) -> list[str]:
    keywords: list[str] = []
    seen = set()
    for query in expanded_queries:
        query_keywords = query.get("keywords")
        if not isinstance(query_keywords, list):
            query_keywords = query.get("expansion", {}).get("keywords", [])
        for keyword in query_keywords:
            if not isinstance(keyword, str):
                continue
            normalized = keyword.strip()
            if not normalized or normalized in seen:
                continue
            keywords.append(normalized)
            seen.add(normalized)
    return keywords


def record_stage(
    context: CaseExecutionContext,
    stage: str,
    output_count: int,
    *,
    status: str = "completed",
    error: dict[str, str] | None = None,
) -> None:
    context.stage_trace.append(
        {
            "stage": stage,
            "case_id": context.case_id,
            "status": status,
            "output_count": output_count,
            "error": error,
        }
    )


def build_report(
    *,
    input_path: Path,
    cases: list[dict[str, Any]],
    case_id: str | None,
) -> dict[str, Any]:
    contexts = build_case_contexts(input_path=input_path, cases=cases)
    case_reports = [build_case_report(context) for context in contexts]
    return build_run_report(
        input_path=input_path,
        requested_case_id=case_id,
        case_reports=case_reports,
    )


def build_run_report(
    *,
    input_path: Path,
    requested_case_id: str | None,
    case_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = count_case_statuses(case_reports)
    aggregation = build_case_aggregation(case_reports, status_counts)
    macro_recall = calculate_macro_recall(case_reports)
    micro_recall = calculate_micro_recall(case_reports)
    law_recall_at_k = calculate_run_law_recall_at_k(micro_recall)
    query_recall_by_k = calculate_query_recall_by_k(case_reports)
    query_macro_recall_by_k = calculate_query_macro_recall_by_k(case_reports)
    stage_recall_at_k = calculate_run_stage_recall_at_k(case_reports)
    candidate_counts = calculate_run_candidate_counts(case_reports)

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run": {
            "input_path": str(input_path),
            "requested_case_id": requested_case_id,
            "recall_k_values": DEFAULT_RECALL_K_VALUES,
        },
        "case_aggregation": aggregation,
        "metrics": {
            "macro_recall": macro_recall,
            "micro_recall": micro_recall,
            "recall_at_k": micro_recall,
            "law_recall_at_k": law_recall_at_k,
            "query_recall_by_k": query_recall_by_k,
            "query_macro_recall_by_k": query_macro_recall_by_k,
            "stage_recall_at_k": stage_recall_at_k,
            "candidate_counts": candidate_counts,
        },
        "input_path": str(input_path),
        "case_id": requested_case_id,
        "case_count": len(case_reports),
        "status_counts": status_counts,
        "recall_k_values": DEFAULT_RECALL_K_VALUES,
        "cases": case_reports,
        "macro_recall": macro_recall,
        "micro_recall": micro_recall,
        "recall_at_k": micro_recall,
        "law_recall_at_k": law_recall_at_k,
        "query_recall_by_k": query_recall_by_k,
        "query_macro_recall_by_k": query_macro_recall_by_k,
        "stage_recall_at_k": stage_recall_at_k,
        "candidate_counts": candidate_counts,
    }
    return report


def build_case_aggregation(
    case_reports: list[dict[str, Any]],
    status_counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "case_count": len(case_reports),
        "completed_case_count": status_counts.get("completed", 0),
        "failed_case_count": status_counts.get("failed", 0),
        "status_counts": status_counts,
        "total_law_references": sum(
            len(case_report["law_references"]) for case_report in case_reports
        ),
        "total_precedent_references": sum(
            len(case_report["precedent_references"]) for case_report in case_reports
        ),
        "case_ids": [case_report["case_id"] for case_report in case_reports],
    }


def empty_macro_recall() -> dict[str, dict[str, float]]:
    return {
        str(k): {"law": 0.0, "precedent": 0.0, "integrated": 0.0}
        for k in DEFAULT_RECALL_K_VALUES
    }


def empty_micro_recall(
    case_reports: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    law_total = sum(len(case_report["law_references"]) for case_report in case_reports)
    precedent_total = sum(
        len(case_report["precedent_references"]) for case_report in case_reports
    )
    return {
        str(k): {
            "law": 0.0,
            "precedent": 0.0,
            "integrated": 0.0,
            "law_hits": 0,
            "law_total": law_total,
            "precedent_hits": 0,
            "precedent_total": precedent_total,
            "hits": 0,
            "total": law_total + precedent_total,
        }
        for k in DEFAULT_RECALL_K_VALUES
    }


def calculate_recall_by_k(
    *,
    law_references: list[dict[str, Any]],
    precedent_references: list[dict[str, Any]],
    reranked_results: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    law_total = len(law_references)
    precedent_total = len(precedent_references)
    metrics: dict[str, dict[str, float | int]] = {}

    for k in DEFAULT_RECALL_K_VALUES:
        top_results = top_ranked_results(reranked_results, k)
        law_hits = count_law_hits(law_references, top_results)
        precedent_hits = count_precedent_hits(precedent_references, top_results)
        metrics[str(k)] = {
            "law": ratio(law_hits, law_total),
            "precedent": ratio(precedent_hits, precedent_total),
            "law_hits": law_hits,
            "law_total": law_total,
            "precedent_hits": precedent_hits,
            "precedent_total": precedent_total,
        }

    return metrics


def calculate_law_recall_at_k(
    *,
    law_references: list[dict[str, Any]],
    reranked_results: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    law_total = len(law_references)
    metrics: dict[str, dict[str, float | int]] = {}

    for k in DEFAULT_RECALL_K_VALUES:
        law_hits = count_law_hits(
            law_references,
            top_ranked_results(reranked_results, k),
        )
        metrics[str(k)] = {
            "recall": ratio(law_hits, law_total),
            "hits": law_hits,
            "total": law_total,
        }

    return metrics


def calculate_stage_recall_at_k(
    *,
    law_references: list[dict[str, Any]],
    precedent_references: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    metrics = calculate_recall_by_k(
        law_references=law_references,
        precedent_references=precedent_references,
        reranked_results=results,
    )
    for values in metrics.values():
        hits = int(values["law_hits"]) + int(values["precedent_hits"])
        total = int(values["law_total"]) + int(values["precedent_total"])
        values["hits"] = hits
        values["total"] = total
        values["integrated"] = ratio(hits, total)
    return metrics


def count_source_candidates(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"law": 0, "precedent": 0, "total": 0}
    for result in results:
        source_type = result.get("source_type")
        if source_type not in {"law", "precedent"}:
            continue
        counts[source_type] += 1
        counts["total"] += 1
    return counts


def calculate_precedent_hit_flags_by_k(
    *,
    precedent_references: list[dict[str, Any]],
    reranked_results: list[dict[str, Any]],
) -> dict[str, list[dict[str, str | bool]]]:
    return {
        str(k): precedent_hit_flags(
            precedent_references=precedent_references,
            results=top_ranked_results(reranked_results, k),
        )
        for k in DEFAULT_RECALL_K_VALUES
    }


def calculate_query_hit_flags_by_k(
    *,
    case_id: str,
    clauses: list[str],
    expanded_queries: list[dict[str, Any]],
    law_references: list[dict[str, Any]],
    precedent_references: list[dict[str, Any]],
    reranked_results: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    query_records = query_records_for_hit_flags(clauses, expanded_queries)
    return {
        str(k): [
            query_hit_flags(
                case_id=case_id,
                query=query,
                query_count=len(query_records),
                law_references=law_references,
                precedent_references=precedent_references,
                reranked_results=reranked_results,
                k=k,
            )
            for query in query_records
        ]
        for k in DEFAULT_RECALL_K_VALUES
    }


def query_records_for_hit_flags(
    clauses: list[str],
    expanded_queries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if expanded_queries:
        return [
            {
                "clause_index": query.get("clause_index"),
                "query": query.get("query", query.get("clause", "")),
            }
            for query in expanded_queries
        ]

    return [
        {
            "clause_index": clause_index,
            "query": clause,
        }
        for clause_index, clause in enumerate(clauses)
    ]


def query_hit_flags(
    *,
    case_id: str,
    query: dict[str, Any],
    query_count: int,
    law_references: list[dict[str, Any]],
    precedent_references: list[dict[str, Any]],
    reranked_results: list[dict[str, Any]],
    k: int,
) -> dict[str, Any]:
    query_results = top_ranked_query_results(
        reranked_results=reranked_results,
        clause_index=query.get("clause_index"),
        query_count=query_count,
        k=k,
    )
    law_reference_hits = law_reference_hit_flags(law_references, query_results)
    precedent_reference_hits = precedent_hit_flags(
        precedent_references=precedent_references,
        results=query_results,
    )
    law_hits = sum(1 for item in law_reference_hits if item["hit"])
    precedent_hits = sum(1 for item in precedent_reference_hits if item["hit"])
    law_total = len(law_reference_hits)
    precedent_total = len(precedent_reference_hits)
    return {
        "case_id": case_id,
        "clause_index": query.get("clause_index"),
        "query": query.get("query", ""),
        "law_reference_hits": law_reference_hits,
        "precedent_reference_hits": precedent_reference_hits,
        "law_hits": law_hits,
        "law_total": law_total,
        "precedent_hits": precedent_hits,
        "precedent_total": precedent_total,
        "hits": law_hits + precedent_hits,
        "total": law_total + precedent_total,
    }


def top_ranked_query_results(
    *,
    reranked_results: list[dict[str, Any]],
    clause_index: Any,
    query_count: int,
    k: int,
) -> list[dict[str, Any]]:
    top_results = top_ranked_results(reranked_results, k)
    if query_count == 1 and all("clause_index" not in result for result in top_results):
        return top_results
    return [result for result in top_results if result.get("clause_index") == clause_index]


def law_reference_hit_flags(
    law_references: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, str | bool]]:
    result_keys = [
        normalize_match_value(value)
        for result in results
        for value in law_match_values(result)
        if normalize_match_value(value)
    ]
    return [
        {
            "law_child": reference["law_child"],
            "hit": reference_matches_result(reference["law_child"], result_keys),
        }
        for reference in law_references
    ]


def precedent_hit_flags(
    *,
    precedent_references: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, str | bool]]:
    result_case_numbers = [
        normalize_match_value(value)
        for result in results
        for value in precedent_match_values(result)
        if normalize_match_value(value)
    ]
    return [
        {
            "case_number": reference["case_number"],
            "hit": reference_matches_result(reference["case_number"], result_case_numbers),
        }
        for reference in precedent_references
    ]


def calculate_integrated_recall(
    *,
    law_references: list[dict[str, Any]],
    precedent_references: list[dict[str, Any]],
    reranked_results: list[dict[str, Any]],
) -> dict[str, float | int]:
    law_hits = count_law_hits(law_references, reranked_results)
    precedent_hits = count_precedent_hits(precedent_references, reranked_results)
    law_total = len(law_references)
    precedent_total = len(precedent_references)
    total = law_total + precedent_total
    hits = law_hits + precedent_hits
    return {
        "value": ratio(hits, total),
        "hits": hits,
        "total": total,
        "law_hits": law_hits,
        "law_total": law_total,
        "precedent_hits": precedent_hits,
        "precedent_total": precedent_total,
        "evaluated_result_count": len(reranked_results),
    }


def calculate_macro_recall(
    case_reports: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    if not case_reports:
        return empty_macro_recall()

    macro: dict[str, dict[str, float]] = {}
    for k in DEFAULT_RECALL_K_VALUES:
        k_key = str(k)
        law_values = [case["recall_by_k"][k_key]["law"] for case in case_reports]
        precedent_values = [
            case["recall_by_k"][k_key]["precedent"] for case in case_reports
        ]
        integrated_values = [
            ratio(
                case["recall_by_k"][k_key]["law_hits"]
                + case["recall_by_k"][k_key]["precedent_hits"],
                case["recall_by_k"][k_key]["law_total"]
                + case["recall_by_k"][k_key]["precedent_total"],
            )
            for case in case_reports
        ]
        macro[k_key] = {
            "law": average(law_values),
            "precedent": average(precedent_values),
            "integrated": average(integrated_values),
        }
    return macro


def calculate_micro_recall(
    case_reports: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    if not case_reports:
        return empty_micro_recall(case_reports)

    micro: dict[str, dict[str, float | int]] = {}
    for k in DEFAULT_RECALL_K_VALUES:
        k_key = str(k)
        law_hits = sum(case["recall_by_k"][k_key]["law_hits"] for case in case_reports)
        law_total = sum(case["recall_by_k"][k_key]["law_total"] for case in case_reports)
        precedent_hits = sum(
            case["recall_by_k"][k_key]["precedent_hits"] for case in case_reports
        )
        precedent_total = sum(
            case["recall_by_k"][k_key]["precedent_total"] for case in case_reports
        )
        hits = law_hits + precedent_hits
        total = law_total + precedent_total
        micro[k_key] = {
            "law": ratio(law_hits, law_total),
            "precedent": ratio(precedent_hits, precedent_total),
            "integrated": ratio(hits, total),
            "law_hits": law_hits,
            "law_total": law_total,
            "precedent_hits": precedent_hits,
            "precedent_total": precedent_total,
            "hits": hits,
            "total": total,
        }
    return micro


def calculate_run_law_recall_at_k(
    micro_recall: dict[str, dict[str, float | int]],
) -> dict[str, dict[str, float | int]]:
    return {
        str(k): {
            "recall": micro_recall.get(str(k), {}).get("law", 0.0),
            "hits": micro_recall.get(str(k), {}).get("law_hits", 0),
            "total": micro_recall.get(str(k), {}).get("law_total", 0),
        }
        for k in DEFAULT_RECALL_K_VALUES
    }


def calculate_run_stage_recall_at_k(
    case_reports: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, float | int]]]:
    return {
        stage: calculate_stage_micro_recall(case_reports, stage)
        for stage in ("bm25", "semantic", "rerank")
    }


def calculate_stage_micro_recall(
    case_reports: list[dict[str, Any]],
    stage: str,
) -> dict[str, dict[str, float | int]]:
    metrics: dict[str, dict[str, float | int]] = {}
    for k in DEFAULT_RECALL_K_VALUES:
        k_key = str(k)
        law_hits = sum(
            case.get("stage_recall_at_k", {})
            .get(stage, {})
            .get(k_key, {})
            .get("law_hits", 0)
            for case in case_reports
        )
        law_total = sum(
            case.get("stage_recall_at_k", {})
            .get(stage, {})
            .get(k_key, {})
            .get("law_total", 0)
            for case in case_reports
        )
        precedent_hits = sum(
            case.get("stage_recall_at_k", {})
            .get(stage, {})
            .get(k_key, {})
            .get("precedent_hits", 0)
            for case in case_reports
        )
        precedent_total = sum(
            case.get("stage_recall_at_k", {})
            .get(stage, {})
            .get(k_key, {})
            .get("precedent_total", 0)
            for case in case_reports
        )
        hits = law_hits + precedent_hits
        total = law_total + precedent_total
        metrics[k_key] = {
            "law": ratio(law_hits, law_total),
            "law_hits": law_hits,
            "law_total": law_total,
            "precedent": ratio(precedent_hits, precedent_total),
            "precedent_hits": precedent_hits,
            "precedent_total": precedent_total,
            "integrated": ratio(hits, total),
            "hits": hits,
            "total": total,
        }
    return metrics


def calculate_run_candidate_counts(
    case_reports: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    totals = {
        stage: {"law": 0, "precedent": 0, "total": 0}
        for stage in ("bm25", "semantic", "rerank")
    }
    for case in case_reports:
        for stage, counts in case.get("candidate_counts", {}).items():
            if stage not in totals:
                continue
            totals[stage]["law"] += counts.get("law", 0)
            totals[stage]["precedent"] += counts.get("precedent", 0)
            totals[stage]["total"] += counts.get("total", 0)
    return totals


def calculate_query_recall_by_k(
    case_reports: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    metrics: dict[str, dict[str, float | int]] = {}
    for k in DEFAULT_RECALL_K_VALUES:
        k_key = str(k)
        query_flags = [
            query
            for case_report in case_reports
            for query in case_report.get("query_hit_flags_by_k", {}).get(k_key, [])
        ]
        law_hits = sum(query["law_hits"] for query in query_flags)
        law_total = sum(query["law_total"] for query in query_flags)
        precedent_hits = sum(query["precedent_hits"] for query in query_flags)
        precedent_total = sum(query["precedent_total"] for query in query_flags)
        hits = law_hits + precedent_hits
        total = law_total + precedent_total
        metrics[k_key] = {
            "law": ratio(law_hits, law_total),
            "precedent": ratio(precedent_hits, precedent_total),
            "integrated": ratio(hits, total),
            "law_hits": law_hits,
            "law_total": law_total,
            "precedent_hits": precedent_hits,
            "precedent_total": precedent_total,
            "hits": hits,
            "total": total,
            "query_count": len(query_flags),
        }
    return metrics


def calculate_query_macro_recall_by_k(
    case_reports: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    metrics: dict[str, dict[str, float | int]] = {}
    for k in DEFAULT_RECALL_K_VALUES:
        k_key = str(k)
        query_flags = [
            query
            for case_report in case_reports
            for query in case_report.get("query_hit_flags_by_k", {}).get(k_key, [])
        ]
        metrics[k_key] = {
            "law": average(
                [ratio(query["law_hits"], query["law_total"]) for query in query_flags]
            ),
            "precedent": average(
                [
                    ratio(query["precedent_hits"], query["precedent_total"])
                    for query in query_flags
                ]
            ),
            "integrated": average(
                [ratio(query["hits"], query["total"]) for query in query_flags]
            ),
            "query_count": len(query_flags),
        }
    return metrics


def top_ranked_results(
    reranked_results: list[dict[str, Any]],
    k: int,
) -> list[dict[str, Any]]:
    return [
        result
        for result in sorted(reranked_results, key=lambda result: result.get("rank", 10**9))
        if isinstance(result.get("rank"), int) and result["rank"] <= k
    ]


def count_law_hits(
    law_references: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> int:
    result_keys = [
        normalize_match_value(value)
        for result in results
        for value in law_match_values(result)
        if normalize_match_value(value)
    ]
    return sum(
        1
        for reference in law_references
        if reference_matches_result(reference["law_child"], result_keys)
    )


def count_precedent_hits(
    precedent_references: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> int:
    result_case_numbers = [
        normalize_match_value(value)
        for result in results
        for value in precedent_match_values(result)
        if normalize_match_value(value)
    ]
    return sum(
        1
        for reference in precedent_references
        if reference_matches_result(reference["case_number"], result_case_numbers)
    )


def law_match_values(result: dict[str, Any]) -> list[Any]:
    if result.get("source_type") != "law":
        return []
    values = [
        result.get("clause_key"),
        result.get("law_name"),
        result.get("article_key"),
        result.get("result_id"),
    ]
    values.extend(combined_law_values(result))
    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        values.extend(
            [
                metadata.get("clause_key"),
                metadata.get("law_name"),
                metadata.get("article_key"),
            ]
        )
        values.extend(combined_law_values(metadata))
    return values


def precedent_match_values(result: dict[str, Any]) -> list[Any]:
    """Return retrieved precedent identifiers eligible for validation matching."""
    if result.get("source_type") != "precedent":
        return []
    values = [
        result.get("case_number"),
        result.get("case_name"),
        result.get("result_id"),
    ]
    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        return values
    values.extend([metadata.get("case_number"), metadata.get("case_name")])
    case_law = metadata.get("case_law")
    if isinstance(case_law, dict):
        values.extend([case_law.get("case_number"), case_law.get("case_name")])
    return values


def combined_law_values(item: dict[str, Any]) -> list[str]:
    law_name = item.get("law_name")
    article_key = item.get("article_key")
    if not law_name or not article_key:
        return []
    return [f"{law_name}_{article_key}", f"{law_name} {article_key}"]


def reference_matches_result(reference: Any, result_values: list[str]) -> bool:
    normalized_reference = normalize_match_value(reference)
    if not normalized_reference:
        return False
    return any(normalized_reference in result_value for result_value in result_values)


def normalize_match_value(value: Any) -> str:
    if value is None:
        return ""
    return "".join(str(value).strip().casefold().replace("_", " ").split())


def ratio(hits: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(hits / total, 6)


def average(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def count_case_statuses(case_reports: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"completed": 0, "failed": 0}
    for case_report in case_reports:
        status = case_report["status"]
        counts[status] = counts.get(status, 0) + 1
    return counts


def save_report(report: dict[str, Any], output_path: Path | None = None) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        report_path = RESULTS_DIR / f"legal_retrieval_eval_{timestamp}.json"
    else:
        report_path = RESULTS_DIR / output_path.expanduser().name

    report["report_path"] = str(report_path)
    report.setdefault("run", {})["report_path"] = str(report_path)
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return report_path


def run(
    input_path: Path,
    case_id: str | None = None,
    output_path: Path | None = None,
) -> Path:
    assert_real_pipeline_imports_available()
    dataset = load_dataset(input_path)
    cases = select_cases(dataset, case_id)
    report = build_report(input_path=input_path, cases=cases, case_id=case_id)
    return save_report(report, output_path=output_path)


def format_core_summary_console_line(report: dict[str, Any]) -> str:
    status_counts = report.get("status_counts", {})
    return (
        f"summary input_path={report.get('input_path', '')} "
        f"cases={report.get('case_count', 0)} "
        f"completed={status_counts.get('completed', 0)} "
        f"failed={status_counts.get('failed', 0)}"
    )


def format_law_recall_console_lines(report: dict[str, Any]) -> list[str]:
    micro_recall = report.get("metrics", {}).get("micro_recall", {})
    lines: list[str] = []
    for k in report.get("recall_k_values", DEFAULT_RECALL_K_VALUES):
        k_key = str(k)
        recall_at_k = micro_recall.get(k_key, {})
        lines.append(
            (
                f"law_recall@{k}={recall_at_k.get('law', 0.0):.6f} "
                f"hits={recall_at_k.get('law_hits', 0)} "
                f"total={recall_at_k.get('law_total', 0)}"
            )
        )
    return lines


def format_recall_at_k_console_lines(report: dict[str, Any]) -> list[str]:
    recall_at_k = report.get("metrics", {}).get("recall_at_k")
    if not isinstance(recall_at_k, dict):
        recall_at_k = report.get("metrics", {}).get("micro_recall", {})

    lines: list[str] = []
    for k in report.get("recall_k_values", DEFAULT_RECALL_K_VALUES):
        k_key = str(k)
        metrics = recall_at_k.get(k_key, {})
        lines.append(
            (
                f"recall@{k} "
                f"law={metrics.get('law', 0.0):.6f} "
                f"law_hits={metrics.get('law_hits', 0)} "
                f"law_total={metrics.get('law_total', 0)} "
                f"precedent={metrics.get('precedent', 0.0):.6f} "
                f"precedent_hits={metrics.get('precedent_hits', 0)} "
                f"precedent_total={metrics.get('precedent_total', 0)} "
                f"integrated={metrics.get('integrated', 0.0):.6f} "
                f"hits={metrics.get('hits', 0)} "
                f"total={metrics.get('total', 0)}"
            )
        )
    return lines


def format_dataset_recall_summary_console_lines(report: dict[str, Any]) -> list[str]:
    metrics = report.get("metrics", {})
    macro_recall = metrics.get("macro_recall", {})
    micro_recall = metrics.get("micro_recall", {})

    lines: list[str] = []
    for k in report.get("recall_k_values", DEFAULT_RECALL_K_VALUES):
        k_key = str(k)
        macro = macro_recall.get(k_key, {})
        micro = micro_recall.get(k_key, {})
        lines.append(
            (
                f"dataset_macro_recall@{k} "
                f"law={macro.get('law', 0.0):.6f} "
                f"precedent={macro.get('precedent', 0.0):.6f} "
                f"integrated={macro.get('integrated', 0.0):.6f}"
            )
        )
        lines.append(
            (
                f"dataset_micro_recall@{k} "
                f"law={micro.get('law', 0.0):.6f} "
                f"law_hits={micro.get('law_hits', 0)} "
                f"law_total={micro.get('law_total', 0)} "
                f"precedent={micro.get('precedent', 0.0):.6f} "
                f"precedent_hits={micro.get('precedent_hits', 0)} "
                f"precedent_total={micro.get('precedent_total', 0)} "
                f"integrated={micro.get('integrated', 0.0):.6f} "
                f"hits={micro.get('hits', 0)} "
                f"total={micro.get('total', 0)}"
            )
        )
    return lines


def format_stage_recall_console_lines(report: dict[str, Any]) -> list[str]:
    metrics = report.get("metrics", {})
    stage_recall = metrics.get("stage_recall_at_k", {})
    candidate_counts = metrics.get("candidate_counts", {})
    lines: list[str] = []
    for stage in ("bm25", "semantic", "rerank"):
        counts = candidate_counts.get(stage, {})
        for k in (3, 5, 10):
            values = stage_recall.get(stage, {}).get(str(k), {})
            lines.append(
                (
                    f"stage_recall stage={stage} recall@{k} "
                    f"law={values.get('law', 0.0):.6f} "
                    f"precedent={values.get('precedent', 0.0):.6f} "
                    f"integrated={values.get('integrated', 0.0):.6f} "
                    f"candidates={counts.get('total', 0)} "
                    f"law_candidates={counts.get('law', 0)} "
                    f"precedent_candidates={counts.get('precedent', 0)}"
                )
            )
            if stage == "semantic":
                lines.append(
                    (
                        f"semantic_retrieval_recall@{k} "
                        f"law={values.get('law', 0.0):.6f} "
                        f"precedent={values.get('precedent', 0.0):.6f} "
                        f"integrated={values.get('integrated', 0.0):.6f} "
                        f"hits={values.get('hits', 0)} "
                        f"total={values.get('total', 0)}"
                    )
                )
            if stage == "rerank":
                lines.append(
                    (
                        f"rerank_recall@{k} "
                        f"law={values.get('law', 0.0):.6f} "
                        f"precedent={values.get('precedent', 0.0):.6f} "
                        f"integrated={values.get('integrated', 0.0):.6f} "
                        f"hits={values.get('hits', 0)} "
                        f"total={values.get('total', 0)}"
                    )
                )
    return lines


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else None

    try:
        report_path = run(
            input_path=input_path,
            case_id=args.case_id,
            output_path=output_path,
        )
    except PipelineImportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except DatasetValidationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    report = json.loads(report_path.read_text(encoding="utf-8"))
    print(format_core_summary_console_line(report))
    print(f"cases={report['case_count']}")
    if report["case_id"] is not None:
        print(f"case_id={report['case_id']}")
    for line in format_dataset_recall_summary_console_lines(report):
        print(line)
    for line in format_stage_recall_console_lines(report):
        print(line)
    for line in format_recall_at_k_console_lines(report):
        print(line)
    for line in format_law_recall_console_lines(report):
        print(line)
    print(f"report_path={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
