"""Legal retrieval evaluation CLI.

Runs the first evaluation contract step: load a validation dataset from an
absolute JSON path, validate case shape, and write an inspectable report.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.reranking.evaluation_reranker import rerank_hybrid_results
from pipeline.retrieval.evaluation_retrieval import (
    expand_case_queries,
    inspect_retrieved_documents,
    run_hybrid_retrieval,
)


DEFAULT_RECALL_K_VALUES = [1, 3, 5, 10, 20]
REPORT_SCHEMA_VERSION = "legal_retrieval_eval.v1"
REQUIRED_CASE_FIELDS = ("case_id", "clauses", "law_references", "precedent_references")
RESULTS_DIR = Path(__file__).resolve().parent / "results"


class DatasetValidationError(ValueError):
    """Raised when an evaluation dataset cannot satisfy the CLI contract."""


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run legal QA retrieval evaluation for a JSON array dataset."
    )
    parser.add_argument(
        "--input",
        required=True,
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

    for index, case in enumerate(dataset):
        validate_case(case, index)

    return dataset


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
        keyword_results, semantic_results = run_hybrid_retrieval(
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
            rerank_hybrid_results(
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
        "recall_by_k": recall_by_k,
        "law_recall_at_k": law_recall_at_k,
        "precedent_hit_flags_by_k": precedent_hit_flags_by_k,
        "query_hit_flags_by_k": query_hit_flags_by_k,
        "integrated_recall": integrated_recall,
        "recall_report": {
            "case_id": context.case_id,
            "query_expansion": query_expansion,
            "expanded_queries": context.expanded_queries,
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
    result_keys = {
        normalize_match_value(value)
        for result in results
        for value in law_match_values(result)
        if normalize_match_value(value)
    }
    return [
        {
            "law_child": reference["law_child"],
            "hit": normalize_match_value(reference["law_child"]) in result_keys,
        }
        for reference in law_references
    ]


def precedent_hit_flags(
    *,
    precedent_references: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, str | bool]]:
    result_case_numbers = {
        normalize_match_value(value)
        for result in results
        for value in precedent_match_values(result)
        if normalize_match_value(value)
    }
    return [
        {
            "case_number": reference["case_number"],
            "hit": normalize_match_value(reference["case_number"]) in result_case_numbers,
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
    result_keys = {
        normalize_match_value(value)
        for result in results
        for value in law_match_values(result)
        if normalize_match_value(value)
    }
    return sum(
        1
        for reference in law_references
        if normalize_match_value(reference["law_child"]) in result_keys
    )


def count_precedent_hits(
    precedent_references: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> int:
    result_case_numbers = {
        normalize_match_value(value)
        for result in results
        for value in precedent_match_values(result)
        if normalize_match_value(value)
    }
    return sum(
        1
        for reference in precedent_references
        if normalize_match_value(reference["case_number"]) in result_case_numbers
    )


def law_match_values(result: dict[str, Any]) -> list[Any]:
    values = [
        result.get("clause_key"),
        result.get("article_key"),
        result.get("law_name"),
    ]
    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        values.extend(
            [
                metadata.get("clause_key"),
                metadata.get("article_key"),
                metadata.get("law_name"),
            ]
        )
    return values


def precedent_match_values(result: dict[str, Any]) -> list[Any]:
    """Return retrieved precedent identifiers eligible for validation matching."""
    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        return []
    case_law = metadata.get("case_law")
    if isinstance(case_law, dict):
        return [case_law.get("case_number")]
    return []


def normalize_match_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()


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
    for line in format_recall_at_k_console_lines(report):
        print(line)
    for line in format_law_recall_console_lines(report):
        print(line)
    print(f"report_path={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
