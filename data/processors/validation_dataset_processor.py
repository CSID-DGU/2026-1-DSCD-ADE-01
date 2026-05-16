"""Load Cloud SQL validation exports for the legal retrieval eval dataset."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CASE_EXPORT_NAME = "val_data_from_cloudsql_case.json"
QA_EXPORT_NAME = "val_data_from_cloudsql_qa.json"


class ExportFormat(str, Enum):
    CASE_LAW = "case_law"
    QA = "qa"


CASE_EXPORT_FIELDS = {
    "case_id",
    "case_number",
    "issue",
    "judgment_summary",
    "case_detail",
    "gt_laws",
    "gt_cases",
}
QA_EXPORT_FIELDS = {
    "answer_id",
    "question_id",
    "question_body",
    "answer_body",
    "referenced_laws",
    "referenced_cases",
}
EXPORT_REQUIRED_FIELDS = {
    ExportFormat.CASE_LAW: CASE_EXPORT_FIELDS,
    ExportFormat.QA: QA_EXPORT_FIELDS,
}
EXPORT_REQUIRED_VALUE_FIELDS = {
    ExportFormat.CASE_LAW: {"case_id"},
    ExportFormat.QA: {"answer_id", "question_id"},
}
EXPORT_TEXT_FIELDS = {
    ExportFormat.CASE_LAW: {
        "case_number",
        "issue",
        "judgment_summary",
        "case_detail",
        "case_name",
        "judgment_date",
        "court_name",
    },
    ExportFormat.QA: {
        "question_title",
        "question_body",
        "answer_body",
    },
}
EXPORT_ARRAY_FIELDS = {
    ExportFormat.CASE_LAW: {"gt_laws", "gt_cases"},
    ExportFormat.QA: {"referenced_laws", "referenced_cases"},
}
EVAL_SET_FIELDS = {
    "id",
    "source_type",
    "source_id",
    "source_text",
    "clauses",
    "gt_laws",
    "gt_cases",
    "meta",
}
CLAUSE_FIELDS = {"raw", "normalized", "clause_type"}
STAGE1_MODEL = "gemini-2.5-pro"
STAGE1_TEMPERATURE = 0.0
STAGE2_MODEL = "gemini-2.5-pro"
STAGE2_TEMPERATURE = 0.0
SAMPLE_REVIEW_SIZE = 5
MIN_LLM_WORKERS = 5
MAX_LLM_WORKERS = 8
DEFAULT_LLM_WORKERS = 6
MAX_LLM_RETRIES = 3
CHECKPOINT_BATCH_SIZE = 10


class Stage1ClauseExtraction(BaseModel):
    """Structured JSON output expected from the stage 1 clause extractor."""

    clause_type: Literal["explicit_quote", "paraphrased", "mention_only"]
    is_evaluable: bool
    extracted_clauses: list[str] = Field(default_factory=list)
    source_field: str | None = None
    reasoning: str


class Stage2ClauseNormalization(BaseModel):
    """Structured JSON output expected from the stage 2 clause normalizer."""

    normalized: str
    info_preserved: bool
    notes: str


@dataclass(frozen=True)
class CloudSQLExports:
    case_rows: list[dict[str, Any]]
    qa_rows: list[dict[str, Any]]
    case_path: Path
    qa_path: Path


@dataclass(frozen=True)
class IntermediateEvalRecord:
    source_type: str
    source_id: int | str
    source_text: dict[str, str]
    gt_laws: list[str]
    gt_cases: list[str]
    meta: dict[str, Any]


class SampleReviewRequired(RuntimeError):
    """Raised when full processing must wait for human review of stage 1 samples."""

    def __init__(self, samples: list[dict[str, Any]]) -> None:
        self.samples = samples
        super().__init__(
            "Human approval required after reviewing 5 QA and 5 case_law "
            "stage 1 samples. Re-run with --sample-review-approved after approval."
        )


def parse_cloudsql_text_array(value: Any) -> list[str]:
    """Parse Postgres text[] values exported as strings such as {a,b}."""
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


def coerce_export_id(value: Any) -> int | str:
    """Keep numeric export IDs easy to compare while preserving non-numeric IDs."""
    text = str(value)
    return int(text) if text.isdecimal() else text


def append_unique(items: list[str], additions: list[str]) -> None:
    for item in additions:
        if item not in items:
            items.append(item)


def stable_scalar_sort_key(value: Any) -> tuple[int, int | str]:
    """Sort numeric IDs by value and other IDs by text for repeatable output."""
    text = str(value)
    return (0, int(text)) if text.isdecimal() else (1, text)


def has_clause_keyword(text: str) -> bool:
    return "특약" in text or "조항" in text


def normalize_case_gt_law_key(law_key: str) -> str:
    """Case-law exports include a display suffix that retrieval keys do not use."""
    return law_key.removesuffix("_조문")


def case_law_has_clause_keyword(row: dict[str, Any]) -> bool:
    """Case-law candidates are filtered only by legal text fields from SQL."""
    return any(
        has_clause_keyword(row.get(field) or "")
        for field in ("issue", "judgment_summary", "case_detail")
    )


def build_stage1_extraction_prompt(source_type: str, source_text: dict[str, str]) -> str:
    """Build the stage 1 prompt without importing any Vertex AI client."""
    text_lines = "\n".join(f"[{key}]\n{value}" for key, value in source_text.items())
    return f"""
다음 {source_type} 자료에서 평가 가능한 계약 특약/조항을 추출하세요.

분류 기준:
- explicit_quote: 원문에 계약 조항 문장이 그대로 인용되어 있음
- paraphrased: 조항 내용이 판결문 또는 상담문 안에서 의미상 재서술됨
- mention_only: 특약/조항이라는 말만 있고 평가할 구체 내용이 없음

규칙:
- is_evaluable은 검색 평가 쿼리로 쓸 구체 조항 내용이 있을 때만 true입니다.
- mention_only이면 is_evaluable=false이고 extracted_clauses는 빈 배열입니다.
- 출력은 지정된 JSON schema만 따르세요.

자료:
{text_lines}
""".strip()


def build_stage2_normalization_prompt(raw_clause: str) -> str:
    """Build the stage 2 prompt without importing any Vertex AI client."""
    return f"""
다음 계약 특약/조항 표현을 검색 평가에 적합한 한 문장으로 정규화하세요.

규칙:
- 원문의 법적 의미와 핵심 조건을 보존하세요.
- 생략된 주어가 명확하면 자연스럽게 보충하세요.
- 새로운 조건, 금액, 기간, 법률 효과를 만들지 마세요.
- 출력은 지정된 JSON schema만 따르세요.

원문:
{raw_clause}
""".strip()


def retryable_api_exception_types() -> tuple[type[Exception], ...]:
    try:
        from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
    except ImportError:  # pragma: no cover - local tests install google-api-core
        return ()
    return (ResourceExhausted, ServiceUnavailable)


def is_retryable_llm_error(error: Exception) -> bool:
    """Retry only quota/service API failures and JSON decoding failures."""
    retryable_api_errors = retryable_api_exception_types()
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, json.JSONDecodeError):
            return True
        if retryable_api_errors and isinstance(current, retryable_api_errors):
            return True
        current = current.__cause__ or current.__context__
    return False


def run_llm_call_with_retries(call: Callable[[], Any]) -> Any:
    for attempt in range(MAX_LLM_RETRIES + 1):
        try:
            return call()
        except Exception as error:
            if attempt == MAX_LLM_RETRIES or not is_retryable_llm_error(error):
                raise
    raise RuntimeError("unreachable LLM retry state")


def extract_stage1_clauses(
    source_type: str,
    source_text: dict[str, str],
    *,
    client: Any | None = None,
) -> Stage1ClauseExtraction:
    """Run stage 1 extraction with the required deterministic Gemini config."""
    if client is None:
        from shared.llm.gemini_client import gemini_client

        client = gemini_client

    result = run_llm_call_with_retries(
        lambda: client.generate(
            build_stage1_extraction_prompt(source_type, source_text),
            model=STAGE1_MODEL,
            temperature=STAGE1_TEMPERATURE,
            response_schema=Stage1ClauseExtraction,
        )
    )
    if isinstance(result, Stage1ClauseExtraction):
        return result
    if isinstance(result, dict):
        return Stage1ClauseExtraction.model_validate(result)
    if isinstance(result, str):
        return Stage1ClauseExtraction.model_validate_json(result)
    raise TypeError(f"Unsupported stage 1 response type: {type(result).__name__}")


def normalize_stage2_clause(
    raw_clause: str,
    *,
    client: Any | None = None,
) -> Stage2ClauseNormalization:
    """Run stage 2 normalization with the required deterministic Gemini config."""
    if client is None:
        from shared.llm.gemini_client import gemini_client

        client = gemini_client

    result = run_llm_call_with_retries(
        lambda: client.generate(
            build_stage2_normalization_prompt(raw_clause),
            model=STAGE2_MODEL,
            temperature=STAGE2_TEMPERATURE,
            response_schema=Stage2ClauseNormalization,
        )
    )
    if isinstance(result, Stage2ClauseNormalization):
        return result
    if isinstance(result, dict):
        return Stage2ClauseNormalization.model_validate(result)
    if isinstance(result, str):
        return Stage2ClauseNormalization.model_validate_json(result)
    raise TypeError(f"Unsupported stage 2 response type: {type(result).__name__}")


def build_final_clauses_from_stage1(
    stage1: Stage1ClauseExtraction,
    *,
    normalize_stage2: Callable[[str], Stage2ClauseNormalization] = normalize_stage2_clause,
) -> list[dict[str, str]]:
    """Convert stage 1 extraction output into final eval_set clause objects."""
    if not stage1.is_evaluable or stage1.clause_type == "mention_only":
        return []

    clauses: list[dict[str, str]] = []
    for raw_clause in stage1.extracted_clauses:
        raw = raw_clause.strip()
        if not raw:
            continue
        if stage1.clause_type == "explicit_quote":
            normalized = raw
        else:
            # Paraphrased clauses need a second LLM pass before retrieval evaluation.
            normalized = normalize_stage2(raw).normalized

        clauses.append(
            {
                "raw": raw,
                "normalized": normalized,
                "clause_type": stage1.clause_type,
            }
        )

    return clauses


def load_checkpoint_records(checkpoint: Path) -> dict[str, dict[str, Any]]:
    """Load completed checkpoint rows by eval record id."""
    if not checkpoint.exists():
        return {}

    checkpoint_records = load_json_array(checkpoint)
    validate_eval_set_records(checkpoint_records)

    records_by_id: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(checkpoint_records):
        record_id = str(record["id"])
        if record_id in records_by_id:
            raise ValueError(f"{checkpoint} row {index} duplicates id {record_id}")
        records_by_id[record_id] = record
    return records_by_id


def write_checkpoint_records(
    checkpoint: Path,
    results: list[dict[str, Any] | None],
) -> None:
    """Write completed records in eval_set order so resume stays deterministic."""
    completed = [record for record in results if record is not None]
    validate_eval_set_records(completed)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(
        json.dumps(completed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def process_eval_records_with_llm(
    records: list[dict[str, Any]],
    *,
    max_workers: int = DEFAULT_LLM_WORKERS,
    extract_stage1: Callable[[str, dict[str, str]], Stage1ClauseExtraction] = extract_stage1_clauses,
    normalize_stage2: Callable[[str], Stage2ClauseNormalization] = normalize_stage2_clause,
    checkpoint_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Apply stage 1 and needed stage 2 LLM work with bounded item concurrency."""
    validate_eval_set_records(records)
    if not MIN_LLM_WORKERS <= max_workers <= MAX_LLM_WORKERS:
        raise ValueError(
            f"max_workers must be between {MIN_LLM_WORKERS} and {MAX_LLM_WORKERS}"
        )
    checkpoint = Path(checkpoint_path) if checkpoint_path is not None else None
    checkpoint_records = load_checkpoint_records(checkpoint) if checkpoint is not None else {}
    results: list[dict[str, Any] | None] = [None] * len(records)
    pending: list[tuple[int, dict[str, Any]]] = []

    for index, record in enumerate(records):
        record_id = str(record.get("id", ""))
        checkpoint_record = checkpoint_records.get(record_id)
        checkpoint_error = (
            (checkpoint_record.get("meta") or {}).get("processing_error")
            if checkpoint_record is not None
            else None
        )
        if checkpoint_record is not None and checkpoint_error is None:
            results[index] = checkpoint_records[record_id]
        else:
            pending.append((index, record))

    def process_one(record: dict[str, Any]) -> dict[str, Any]:
        item = dict(record)
        item["meta"] = dict(record.get("meta", {}))
        try:
            stage1 = extract_stage1(item["source_type"], item["source_text"])
            item["clauses"] = build_final_clauses_from_stage1(
                stage1,
                normalize_stage2=normalize_stage2,
            )
            item["meta"]["stage1"] = stage1.model_dump()
        except Exception as error:
            item["clauses"] = []
            item["meta"]["processing_error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        return item

    completed_count = sum(1 for record in results if record is not None)
    pending_index = 0
    while pending_index < len(pending):
        to_next_checkpoint = CHECKPOINT_BATCH_SIZE - (
            completed_count % CHECKPOINT_BATCH_SIZE
        )
        batch_size = min(to_next_checkpoint or CHECKPOINT_BATCH_SIZE, len(pending) - pending_index)
        batch = pending[pending_index : pending_index + batch_size]
        batch_results: list[tuple[int, dict[str, Any]] | None] = [None] * len(batch)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(process_one, record): batch_position
                for batch_position, (_record_index, record) in enumerate(batch)
            }
            for future in as_completed(futures):
                record_index, _record = batch[futures[future]]
                batch_results[futures[future]] = (record_index, future.result())

        for batch_result in batch_results:
            if batch_result is None:
                continue
            record_index, processed_record = batch_result
            results[record_index] = processed_record
            completed_count += 1

        pending_index += batch_size
        if checkpoint is not None and completed_count % CHECKPOINT_BATCH_SIZE == 0:
            write_checkpoint_records(checkpoint, results)

    processed = [record for record in results if record is not None]
    validate_eval_set_records(processed)
    return processed


def missing_fields(row: dict[str, Any], required_fields: set[str]) -> list[str]:
    return sorted(field for field in required_fields if field not in row)


def require_fields(
    row: dict[str, Any],
    required_fields: set[str],
    label: str,
) -> None:
    """Raise one consistent error for records that cannot be processed."""
    missing = missing_fields(row, required_fields)
    if missing:
        raise ValueError(f"{label} missing required fields: {', '.join(missing)}")


def require_values(
    row: dict[str, Any],
    required_fields: set[str],
    label: str,
) -> None:
    """Raise a clear error when source identifiers are blank or null."""
    missing = sorted(
        field
        for field in required_fields
        if row.get(field) is None or str(row.get(field)).strip() == ""
    )
    if missing:
        raise ValueError(f"{label} missing required values: {', '.join(missing)}")


def validate_export_field_values(
    row: dict[str, Any],
    export_format: ExportFormat,
    label: str,
) -> None:
    """Reject malformed values before parsing so outcomes do not depend on Python coercion."""
    for field in sorted(EXPORT_REQUIRED_VALUE_FIELDS[export_format]):
        if isinstance(row.get(field), (dict, list)):
            raise ValueError(f"{label} {field} must be a scalar value")

    for field in sorted(EXPORT_TEXT_FIELDS[export_format] & set(row)):
        if row[field] is not None and not isinstance(row[field], str):
            raise ValueError(f"{label} {field} must be str or null")

    for field in sorted(EXPORT_ARRAY_FIELDS[export_format]):
        value = row.get(field)
        if value is None or isinstance(value, str):
            continue
        if not isinstance(value, list):
            raise ValueError(
                f"{label} {field} must be a Postgres text array string, list, or null"
            )
        for item_index, item in enumerate(value):
            if item is not None and not isinstance(item, (str, int, float, bool)):
                raise ValueError(f"{label} {field}[{item_index}] must be scalar or null")


def resolve_export_path(project_root: Path, file_name: str) -> Path:
    """Find an export in supported repo locations."""
    candidates = [
        project_root / "data" / file_name,
        project_root / "data" / "eval" / file_name,
    ]

    for path in candidates:
        if path.exists():
            return path

    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Could not find {file_name}. Searched: {searched}")


def load_json_array(path: Path) -> list[dict[str, Any]]:
    """Load a JSON file that must contain a list of objects."""
    with path.open(encoding="utf-8") as input_file:
        rows = json.load(input_file)

    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON array")

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{path} row {index} must be a JSON object")

    return rows


def identify_export_format(rows: list[dict[str, Any]]) -> ExportFormat:
    """Identify the Cloud SQL export shape from its row fields."""
    if not rows:
        raise ValueError("Cannot identify export format from an empty JSON array")

    row_fields = set(rows[0])
    if CASE_EXPORT_FIELDS <= row_fields:
        return ExportFormat.CASE_LAW
    if QA_EXPORT_FIELDS <= row_fields:
        return ExportFormat.QA

    known_fields = sorted(CASE_EXPORT_FIELDS | QA_EXPORT_FIELDS)
    actual_fields = sorted(row_fields)
    raise ValueError(
        "Unknown validation export format. "
        f"Expected fields for case_law or qa export; got {actual_fields}. "
        f"Known fields include {known_fields}"
    )


def validate_export_rows(
    rows: list[dict[str, Any]],
    export_format: ExportFormat,
    label: str,
) -> None:
    """Validate every row, not just the first row used to identify the export."""
    required_fields = EXPORT_REQUIRED_FIELDS[export_format]
    required_value_fields = EXPORT_REQUIRED_VALUE_FIELDS[export_format]
    for index, row in enumerate(rows):
        row_label = f"{label} row {index}"
        require_fields(row, required_fields, row_label)
        require_values(row, required_value_fields, row_label)
        validate_export_field_values(row, export_format, row_label)


def load_export(path: Path, expected_format: ExportFormat) -> list[dict[str, Any]]:
    """Load an export and verify it matches the expected validation format."""
    rows = load_json_array(path)
    actual_format = identify_export_format(rows)
    if actual_format != expected_format:
        raise ValueError(
            f"{path} expected {expected_format.value} export, "
            f"but found {actual_format.value} export"
        )
    validate_export_rows(rows, expected_format, path.name)
    return rows


def load_cloudsql_exports(project_root: Path | str | None = None) -> CloudSQLExports:
    """Locate and load the QA and case-law Cloud SQL export files."""
    root = (
        Path(project_root)
        if project_root is not None
        else Path(__file__).resolve().parents[2]
    )
    case_path = resolve_export_path(root, CASE_EXPORT_NAME)
    qa_path = resolve_export_path(root, QA_EXPORT_NAME)

    return CloudSQLExports(
        case_rows=load_export(case_path, ExportFormat.CASE_LAW),
        qa_rows=load_export(qa_path, ExportFormat.QA),
        case_path=case_path,
        qa_path=qa_path,
    )


def parse_qa_records(rows: list[dict[str, Any]]) -> list[IntermediateEvalRecord]:
    """Group QA answer exports by question_id and union answer-level GT."""
    grouped: dict[Any, dict[str, Any]] = {}

    for index, row in enumerate(rows):
        row_label = f"qa row {index}"
        require_fields(row, QA_EXPORT_FIELDS, row_label)
        require_values(row, EXPORT_REQUIRED_VALUE_FIELDS[ExportFormat.QA], row_label)
        validate_export_field_values(row, ExportFormat.QA, row_label)
        question_id = coerce_export_id(row["question_id"])
        if question_id not in grouped:
            grouped[question_id] = {
                "question_id": question_id,
                "question_title": row.get("question_title") or "",
                "question_body": row.get("question_body") or "",
                "answer_ids": [],
                "gt_laws": [],
                "gt_cases": [],
            }

        group = grouped[question_id]
        question_body = row.get("question_body") or ""
        if question_body and not has_clause_keyword(group["question_body"]):
            # Duplicate answer rows can carry a stale body; keep the body that can be evaluated.
            group["question_body"] = question_body
        group["answer_ids"].append(coerce_export_id(row["answer_id"]))
        append_unique(group["gt_laws"], parse_cloudsql_text_array(row.get("referenced_laws")))
        append_unique(group["gt_cases"], parse_cloudsql_text_array(row.get("referenced_cases")))

    records: list[IntermediateEvalRecord] = []
    groups = sorted(
        grouped.values(),
        key=lambda group: stable_scalar_sort_key(group["question_id"]),
    )
    for group in groups:
        gt_laws = sorted(group["gt_laws"])
        gt_cases = sorted(group["gt_cases"])
        question_body = group["question_body"]
        if not has_clause_keyword(question_body) or (not gt_laws and not gt_cases):
            continue

        records.append(
            IntermediateEvalRecord(
                source_type="qa",
                source_id=group["question_id"],
                source_text={"question_body": question_body},
                gt_laws=gt_laws,
                gt_cases=gt_cases,
                meta={
                    "question_title": group["question_title"],
                    "answer_ids": sorted(group["answer_ids"], key=stable_scalar_sort_key),
                    "n_answers": len(group["answer_ids"]),
                },
            )
        )

    return records


def parse_case_law_records(rows: list[dict[str, Any]]) -> list[IntermediateEvalRecord]:
    """Map case-law exports to the shared intermediate evaluation shape."""
    records: list[IntermediateEvalRecord] = []

    sorted_rows = sorted(
        rows,
        key=lambda row: stable_scalar_sort_key(row.get("case_id", "")),
    )
    for index, row in enumerate(sorted_rows):
        row_label = f"case_law row {index}"
        require_fields(row, CASE_EXPORT_FIELDS, row_label)
        require_values(
            row,
            EXPORT_REQUIRED_VALUE_FIELDS[ExportFormat.CASE_LAW],
            row_label,
        )
        validate_export_field_values(row, ExportFormat.CASE_LAW, row_label)
        gt_laws = sorted(
            normalize_case_gt_law_key(law_key)
            for law_key in parse_cloudsql_text_array(row.get("gt_laws"))
        )
        gt_cases = sorted(parse_cloudsql_text_array(row.get("gt_cases")))
        if (not gt_laws and not gt_cases) or not case_law_has_clause_keyword(row):
            continue

        records.append(
            IntermediateEvalRecord(
                source_type="case_law",
                source_id=coerce_export_id(row["case_id"]),
                source_text={
                    "issue": row.get("issue") or "",
                    "judgment_summary": row.get("judgment_summary") or "",
                    "case_detail": row.get("case_detail") or "",
                },
                gt_laws=gt_laws,
                gt_cases=gt_cases,
                meta={
                    "case_name": row.get("case_name") or "",
                    "case_number": row.get("case_number") or "",
                    "judgment_date": row.get("judgment_date") or "",
                    "court_name": row.get("court_name") or "",
                },
            )
        )

    return records


def build_eval_record_id(source_type: str, source_id: int | str) -> str:
    """Use stable IDs that show the source family at a glance."""
    prefix = "case" if source_type == "case_law" else source_type
    return f"{prefix}_{source_id}"


def build_stage1_review_samples(
    records: list[IntermediateEvalRecord],
    *,
    extract_stage1: Callable[
        [str, dict[str, str]],
        Stage1ClauseExtraction,
    ] = extract_stage1_clauses,
) -> list[dict[str, Any]]:
    """Run stage 1 on the required human-review samples before full processing."""
    records_by_type: dict[str, list[IntermediateEvalRecord]] = {}
    for source_type in ("qa", "case_law"):
        source_records = [record for record in records if record.source_type == source_type]
        if len(source_records) < SAMPLE_REVIEW_SIZE:
            raise ValueError(
                "stage 1 review gate needs at least "
                f"{SAMPLE_REVIEW_SIZE} {source_type} records"
            )
        records_by_type[source_type] = source_records

    samples: list[dict[str, Any]] = []
    for source_type in ("qa", "case_law"):
        for record in records_by_type[source_type][:SAMPLE_REVIEW_SIZE]:
            stage1 = extract_stage1(record.source_type, record.source_text)
            samples.append(
                {
                    "id": build_eval_record_id(record.source_type, record.source_id),
                    "source_type": record.source_type,
                    "source_id": record.source_id,
                    "source_text": dict(record.source_text),
                    "gt_laws": list(record.gt_laws),
                    "gt_cases": list(record.gt_cases),
                    "meta": dict(record.meta),
                    "stage1": stage1.model_dump(),
                }
            )

    return samples


def validate_eval_set_records(records: list[dict[str, Any]]) -> None:
    """Validate the shared eval_set.json schema before writing or evaluating."""
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"eval_set row {index} must be a JSON object")

        label = f"eval_set row {index}"
        require_fields(record, EVAL_SET_FIELDS, label)
        if not isinstance(record["id"], str) or not record["id"].strip():
            raise ValueError(f"{label} id must be a non-empty string")
        if isinstance(record["source_id"], (dict, list)) or not str(record["source_id"]).strip():
            raise ValueError(f"{label} source_id must be a non-empty scalar")
        if not record["gt_laws"] and not record["gt_cases"]:
            raise ValueError(f"{label} must have gt_laws or gt_cases")

        if record["source_type"] not in {"qa", "case_law"}:
            raise ValueError(f"{label} source_type must be qa or case_law")

        typed_fields = {
            "source_text": dict,
            "clauses": list,
            "gt_laws": list,
            "gt_cases": list,
            "meta": dict,
        }
        for field, expected_type in typed_fields.items():
            if not isinstance(record[field], expected_type):
                raise ValueError(f"{label} {field} must be {expected_type.__name__}")

        if record["source_type"] == "qa":
            question_body = record["source_text"].get("question_body")
            if not isinstance(question_body, str) or not has_clause_keyword(question_body):
                raise ValueError(
                    f"{label} qa source_text.question_body must contain 특약 or 조항"
                )
        if record["source_type"] == "case_law" and not case_law_has_clause_keyword(
            record["source_text"]
        ):
            raise ValueError(
                f"{label} case_law source_text.issue, judgment_summary, "
                "or case_detail must contain 특약 or 조항"
            )

        for clause_index, clause in enumerate(record["clauses"]):
            if not isinstance(clause, dict):
                raise ValueError(f"{label} clause {clause_index} must be a JSON object")
            clause_label = f"{label} clause {clause_index}"
            require_fields(
                clause,
                CLAUSE_FIELDS,
                clause_label,
            )
            if clause.get("clause_type") == "mention_only":
                raise ValueError(f"{clause_label} mention_only must be excluded")
            if clause.get("is_evaluable") is False:
                raise ValueError(f"{clause_label} is_evaluable=false must be excluded")


def normalize_eval_records(records: list[IntermediateEvalRecord]) -> list[dict[str, Any]]:
    """Convert parsed records into the shared eval_set item schema."""
    items: list[dict[str, Any]] = []
    source_order = {"case_law": 0, "qa": 1}

    ordered_records = sorted(
        records,
        key=lambda record: (
            source_order.get(record.source_type, 99),
            stable_scalar_sort_key(record.source_id),
        ),
    )
    for record in ordered_records:
        if not record.gt_laws and not record.gt_cases:
            raise ValueError(
                f"{record.source_type} {record.source_id} must have gt_laws or gt_cases"
            )

        items.append(
            {
                "id": build_eval_record_id(record.source_type, record.source_id),
                "source_type": record.source_type,
                "source_id": record.source_id,
                "source_text": dict(record.source_text),
                "clauses": [],
                "gt_laws": list(record.gt_laws),
                "gt_cases": list(record.gt_cases),
                "meta": dict(record.meta),
            }
        )

    validate_eval_set_records(items)
    return items


def build_eval_set(
    case_rows: list[dict[str, Any]],
    qa_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build one eval_set.json array from both Cloud SQL validation exports."""
    validate_export_rows(case_rows, ExportFormat.CASE_LAW, "case_law input")
    validate_export_rows(qa_rows, ExportFormat.QA, "qa input")
    records = parse_case_law_records(case_rows) + parse_qa_records(qa_rows)
    return normalize_eval_records(records)


def build_eval_set_with_review_gate(
    case_rows: list[dict[str, Any]],
    qa_rows: list[dict[str, Any]],
    *,
    sample_review_approved: bool = False,
    max_workers: int = DEFAULT_LLM_WORKERS,
    checkpoint_path: Path | str | None = None,
    extract_stage1: Callable[
        [str, dict[str, str]],
        Stage1ClauseExtraction,
    ] = extract_stage1_clauses,
    normalize_stage2: Callable[[str], Stage2ClauseNormalization] = normalize_stage2_clause,
) -> list[dict[str, Any]]:
    """Build the eval set only after required stage 1 sample review is approved."""
    validate_export_rows(case_rows, ExportFormat.CASE_LAW, "case_law input")
    validate_export_rows(qa_rows, ExportFormat.QA, "qa input")
    records = parse_qa_records(qa_rows) + parse_case_law_records(case_rows)
    if not sample_review_approved:
        raise SampleReviewRequired(
            build_stage1_review_samples(records, extract_stage1=extract_stage1)
        )

    processed = process_eval_records_with_llm(
        normalize_eval_records(records),
        max_workers=max_workers,
        extract_stage1=extract_stage1,
        normalize_stage2=normalize_stage2,
        checkpoint_path=checkpoint_path,
    )
    final_records = [record for record in processed if record["clauses"]]
    if not final_records:
        raise ValueError("No evaluable records remained after LLM clause extraction")
    validate_eval_set_records(final_records)
    return final_records


def write_eval_set(records: list[dict[str, Any]], project_root: Path | str) -> Path:
    """Write records to evaluation/eval_set.json after schema validation."""
    validate_eval_set_records(records)
    output_path = Path(project_root) / "evaluation" / "eval_set.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def write_stage1_review_samples(
    samples: list[dict[str, Any]],
    project_root: Path | str,
) -> Path:
    """Persist stage 1 review samples so a human can approve or reject them."""
    output_path = Path(project_root) / "evaluation" / "stage1_review_samples.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(samples, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def format_eval_set_statistics(
    records: list[dict[str, Any]],
    *,
    review_samples: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return the required eval_set summary lines for console reporting."""
    validate_eval_set_records(records)
    review_samples = review_samples or []

    source_counts = Counter(str(record["source_type"]) for record in records)
    gt_availability = Counter(
        "both"
        if record["gt_laws"] and record["gt_cases"]
        else "laws_only"
        if record["gt_laws"]
        else "cases_only"
        for record in records
    )
    clause_types = Counter(
        str(clause.get("clause_type"))
        for record in records
        for clause in record["clauses"]
    )
    clause_counts = Counter(len(record["clauses"]) for record in records)
    gt_counts = [len(record["gt_laws"]) + len(record["gt_cases"]) for record in records]
    review_counts = Counter(str(sample.get("source_type", "")) for sample in review_samples)
    review_ids = ",".join(str(sample.get("id", "")) for sample in review_samples[:10])

    return [
        "Dataset statistics:",
        "source_count "
        f"case_law={source_counts.get('case_law', 0)} "
        f"qa={source_counts.get('qa', 0)} total={len(records)}",
        "gt_availability "
        f"both={gt_availability.get('both', 0)} "
        f"cases_only={gt_availability.get('cases_only', 0)} "
        f"laws_only={gt_availability.get('laws_only', 0)}",
        "clause_type "
        f"explicit_quote={clause_types.get('explicit_quote', 0)} "
        f"paraphrased={clause_types.get('paraphrased', 0)} "
        f"mention_only={clause_types.get('mention_only', 0)}",
        "clause_count_distribution "
        + " ".join(
            f"{count}={clause_counts[count]}" for count in sorted(clause_counts)
        ),
        "gt_count "
        f"average={sum(gt_counts) / len(gt_counts):.6f} max={max(gt_counts)}",
        "review_samples "
        f"total={len(review_samples)} "
        f"qa={review_counts.get('qa', 0)} "
        f"case_law={review_counts.get('case_law', 0)} "
        f"ids={review_ids}",
    ]


def load_stage1_review_samples(project_root: Path | str) -> list[dict[str, Any]]:
    """Load saved review samples when present so final stats include the review gate."""
    sample_path = Path(project_root) / "evaluation" / "stage1_review_samples.json"
    if not sample_path.exists():
        return []
    return load_json_array(sample_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load legal retrieval validation exports.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument(
        "--sample-review-approved",
        action="store_true",
        help="Proceed only after a human approves the 5 QA and 5 case_law stage 1 samples.",
    )
    args = parser.parse_args()

    try:
        exports = load_cloudsql_exports(args.project_root)
        eval_set = build_eval_set_with_review_gate(
            exports.case_rows,
            exports.qa_rows,
            sample_review_approved=args.sample_review_approved,
            checkpoint_path=Path(args.project_root)
            / "evaluation"
            / "eval_set_checkpoint.json",
        )
        output_path = write_eval_set(eval_set, args.project_root)
        review_samples = load_stage1_review_samples(args.project_root)
    except SampleReviewRequired as review:
        output_path = write_stage1_review_samples(review.samples, args.project_root)
        print(f"Sample review required: {review}", file=sys.stderr)
        print(f"Wrote stage 1 review samples to {output_path}", file=sys.stderr)
        return 2
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    print(f"Loaded {len(exports.case_rows)} case-law rows from {exports.case_path}")
    print(f"Loaded {len(exports.qa_rows)} QA rows from {exports.qa_path}")
    print(
        "Parsed "
        f"{sum(1 for record in eval_set if record['source_type'] == 'case_law')} "
        "case-law records"
    )
    print(
        f"Parsed {sum(1 for record in eval_set if record['source_type'] == 'qa')} "
        "QA records"
    )
    print(f"Wrote {len(eval_set)} eval records to {output_path}")
    for line in format_eval_set_statistics(eval_set, review_samples=review_samples):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
