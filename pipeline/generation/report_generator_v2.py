"""
report_generator_v2.py

특약_통합_계약서 폴더의 계약서 JSON + retrieval eval JSON으로 리포트 생성.

검색 전략:
  clause 텍스트로 retrieval eval에서 pre-computed 결과 조회.
  eval에 없는 clause(추가특약 등)는 법령/판례 없이 LLM 분석 진행.

사용법:
    python pipeline/generation/report_generator_v2.py \\
        --contracts "C:/path/to/특약_통합_계약서" \\
        --retrieval "C:/path/to/legal_retrieval_eval_*.json" \\
        [--output "output/reports_v2"] \\
        [--top-k-law 5] [--top-k-prec 3] \\
        [--prefix qa_structured_781]
"""

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

load_dotenv()

# ── Vertex AI 초기화 ─────────────────────────────────────────────────
PROJECT_ID  = os.getenv("GCP_PROJECT_ID")
LOCATION    = os.getenv("GCP_LOCATION", "us-central1")
vertexai.init(project=PROJECT_ID, location=LOCATION)

GEN_MODEL = "gemini-2.5-pro"

COMMON_TERMS_COUNT = 6
DEFAULT_TOP_K_LAW  = 5
DEFAULT_TOP_K_PREC = 3


# ── Pydantic 스키마 ──────────────────────────────────────────────────
class RelatedLaw(BaseModel):
    type: str | None = None
    ref: str | None = None
    summary: str | None = None

class RelatedClause(BaseModel):
    clause_id: str | None = None
    clause_text: str | None = None
    relation: str | None = None

class ClauseResult(BaseModel):
    clause_id: str | None = None
    clause_text: str | None = None
    related_laws: list[RelatedLaw] | None = None
    related_clauses: list[RelatedClause] | None = None

class ChecklistItem(BaseModel):
    item: str | None = None
    description: str | None = None
    basis: list[str] | None = None

class ReportOutput(BaseModel):
    contract_checklist: list[ChecklistItem] | None = None
    clause_results: list[ClauseResult] | None = None

class ChecklistOutput(BaseModel):
    contract_checklist: list[ChecklistItem] | None = None


# ── 시스템 프롬프트 ──────────────────────────────────────────────────
SYSTEM_PROMPT = """[역할 및 지시]
당신은 주택임대차 계약 검토를 도와줄 법률 전문가입니다.
아래 정보를 바탕으로 임차인이 계약 전 스스로 확인해야 할 사항을 도출하세요.

- 특약 문구의 해석 가능성, 법령과의 관계, 분쟁으로 이어질 수 있는 사실관계를 객관적으로 서술하세요.
- 명백히 법령에 위반되는 경우에는 해당 법령 조문을 근거로 위반 사실을 서술합니다.
- "위험", "유리", "불리" 등의 평가적 표현은 사용하지 마세요.


[출력 형식 예시]
아래는 특약 4개가 하나의 계약서에 함께 존재하는 경우의 출력 예시입니다.
실제 입력의 특약 수와 내용에 맞게 작성하세요.
판단 표현(유리/불리/위험)은 사용하지 마세요.

---
[입력 예시]
특약A: "임차인 퇴거 시 모든 원상복구 비용은 임차인이 전액 부담한다."
특약B: "임차 기간 중 발생하는 모든 수리 및 수선은 임차인이 부담한다."
특약C: "계약 갱신 시 임대료 인상률은 당사자 간 협의로 정하며 별도 제한을 두지 않는다."
특약D: "임차인은 계약 만료 시 계약갱신을 요구하지 않기로 한다."

[출력 예시]

contract_checklist:
  - item: "원상복구 범위 및 귀책 기준 확인"
    description: "원상복구 의무의 범위는 임대 당시 목적물의 상태, 계약 체결 경위,
                  임차인이 수리하거나 변경한 내용 등을 개별적으로 고려하여 정해집니다.
                  계약 체결 전 또는 입주 시 임차 목적물의 현재 상태를 사진이나
                  영상으로 기록하고, 하자 부위를 계약서에 명기해 두면 퇴거 시
                  귀책 여부를 확인하는 근거로 활용할 수 있습니다."

  - item: "계약갱신 방식(합의갱신·요구권 행사) 구분 확인"
    description: "임대료 인상 상한 5% 규정은 임차인이 계약갱신요구권을 행사하는
                  경우에 적용됩니다. 임차인이 갱신요구권을 행사하지 않고 임대인과
                  합의하여 새로운 계약을 체결하는 경우에는 5%를 초과하는 인상이
                  가능합니다. 이번 갱신이 어떤 방식으로 이루어지는지를 계약서
                  문언과 당사자 의사를 통해 확인합니다."

clause_results:
  - clause_id: "특약A 해당 ID"
    clause_text: "임차인 퇴거 시 모든 원상복구 비용은 임차인이 전액 부담한다."
    related_clauses:
      - clause_id: "특약B 해당 ID"
        clause_text: "임차 기간 중 발생하는 모든 수리 및 수선은 임차인이 부담한다."
        relation: "수선의무 부담 특약이 함께 존재하는 경우, 임차인이 임차 기간 중
                   자비로 수선한 부분이 퇴거 시 원상복구 대상에 해당하는지 여부가
                   불명확해집니다."

  - clause_id: "특약C 해당 ID"
    clause_text: "계약 갱신 시 임대료 인상률은 당사자 간 협의로 정하며 별도 제한을 두지 않는다."
    related_clauses:
      - clause_id: "특약D 해당 ID"
        clause_text: "임차인은 계약 만료 시 계약갱신을 요구하지 않기로 한다."
        relation: "계약갱신요구권 포기 특약이 함께 존재하는 경우, 임차인이
                   합의갱신 방식으로만 계약을 연장하게 되어 임대료 인상 제한(5%)
                   규정이 적용되지 않을 수 있습니다." """


# ── 정규화 함수 (3단계) ──────────────────────────────────────────────
# 1단계: 공백 정규화만
def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

# 2단계: 공백·마침표·쉼표·따옴표 제거
def _norm_strip(text: str) -> str:
    return re.sub(r"[\s\.,'\"''""·、]", "", text).lower()

# 3단계: 위 + 한국어 어미 정규화 (한다→함, 이다→임 등)
_ENDINGS = [
    ("하여야 한다", "해야함"), ("하여야한다", "해야함"),
    ("하여야 함",   "해야함"), ("하여야함",   "해야함"),
    ("하였다", "함"), ("했다", "함"),
    ("한다",   "함"), ("됩니다", "됨"), ("된다",  "됨"),
    ("입니다", "임"), ("이다",   "임"),
    ("있다",   "있음"), ("없다", "없음"),
    ("한다고", "함"), ("하다", "함"),
]

def _norm_endings(text: str) -> str:
    t = _norm_strip(text)
    for src, dst in _ENDINGS:
        src_n = re.sub(r"[\s\.,'\"''""·、]", "", src).lower()
        if t.endswith(src_n):
            t = t[: -len(src_n)] + dst
            break
    return t


def _all_keys(text: str) -> tuple[str, str, str]:
    """(공백정규화, 공백+구두점 제거, 어미정규화) 세 가지 키 반환"""
    return _norm_space(text), _norm_strip(text), _norm_endings(text)


# ── retrieval eval 인덱스 구축 ───────────────────────────────────────
def _add_to_index(index: dict, key: str, laws: list, precs: list) -> None:
    """key에 대해 법령·판례 병합 (result_id 중복 제거, rerank_score 내림차순)"""
    if not key:
        return
    if key not in index:
        index[key] = {"laws": [], "precs": []}
    existing_law_ids  = {r["result_id"] for r in index[key]["laws"]}
    existing_prec_ids = {r["result_id"] for r in index[key]["precs"]}
    for r in sorted(laws,  key=lambda x: x.get("rerank_score", 0), reverse=True):
        if r["result_id"] not in existing_law_ids:
            index[key]["laws"].append(r)
            existing_law_ids.add(r["result_id"])
    for r in sorted(precs, key=lambda x: x.get("rerank_score", 0), reverse=True):
        if r["result_id"] not in existing_prec_ids:
            index[key]["precs"].append(r)
            existing_prec_ids.add(r["result_id"])


def build_eval_index(retrieval_path: Path) -> dict[str, dict]:
    """
    clause 텍스트 → {"laws": [...], "precs": [...]} 인덱스 구축.
    인덱스 키는 _norm_endings(가장 강한 정규화) 하나만 사용.
    조회 시 쿼리도 동일하게 3단계 정규화 후 순차 매칭.
    """
    data  = json.loads(retrieval_path.read_text(encoding="utf-8"))
    index: dict[str, dict] = {}

    for case in data["cases"]:
        clauses = case.get("clauses", [])
        clause_texts: list[str] = []
        for c in clauses:
            if isinstance(c, str):
                clause_texts.append(c)
            elif isinstance(c, dict):
                clause_texts.append(c.get("normalized") or c.get("raw") or "")
            else:
                clause_texts.append("")

        per_clause: dict[int, dict] = defaultdict(lambda: {"laws": [], "precs": []})
        for r in case.get("reranked_results", []):
            ci = r.get("clause_index", 0)
            if r.get("source_type") == "law":
                per_clause[ci]["laws"].append(r)
            elif r.get("source_type") == "precedent":
                per_clause[ci]["precs"].append(r)

        for ci, results in per_clause.items():
            if ci >= len(clause_texts):
                continue
            raw_text = clause_texts[ci]
            if not raw_text.strip():
                continue
            # 인덱스 키: _norm_endings 하나만 사용
            key = _norm_endings(raw_text)
            _add_to_index(index, key, results["laws"], results["precs"])

    total_clauses = len(index)
    total_laws    = sum(len(v["laws"])  for v in index.values())
    total_precs   = sum(len(v["precs"]) for v in index.values())
    print(f"[eval index] {total_clauses}개 clause → 법령 {total_laws}건 / 판례 {total_precs}건 인덱싱 완료")
    return index


def lookup_eval(
    clause_text: str,
    index: dict,
    top_k_law: int,
    top_k_prec: int,
) -> tuple[list[dict], list[dict], bool]:
    """
    쿼리를 3단계로 정규화하여 순차 조회.
    인덱스 키는 _norm_endings 기준이므로, 쿼리도 같은 방식으로 변환하면
    공백/구두점 차이나 어미 차이도 흡수됨.
    Returns: (top_laws, top_precs, hit)
    """
    for key in (_norm_space(clause_text), _norm_strip(clause_text), _norm_endings(clause_text)):
        if key in index:
            entry = index[key]
            return entry["laws"][:top_k_law], entry["precs"][:top_k_prec], True
    return [], [], False


# ── 통합 검색: eval 조회, 없으면 빈 결과 ───────────────────────────
def retrieve(
    clause_text: str,
    eval_index: dict,
    top_k_law: int,
    top_k_prec: int,
) -> tuple[list[dict], list[dict], str]:
    """
    eval 인덱스에서 pre-computed 결과 조회 (3단계 정규화 매칭).
    없는 clause는 빈 결과로 반환 (LLM이 특약 자체만으로 분석).
    Returns: (top_laws, top_precs, source: "eval" | "miss")
    """
    laws, precs, hit = lookup_eval(clause_text, eval_index, top_k_law, top_k_prec)
    if hit:
        return laws, precs, "eval"
    return [], [], "miss"


# ── 프롬프트 빌더 ────────────────────────────────────────────────────
def fmt_property(info: dict) -> str:
    return json.dumps(info, ensure_ascii=False, indent=2)

def fmt_common(terms: list) -> str:
    return "\n".join(f"공통특약 {i+1}: {t}" for i, t in enumerate(terms))

def fmt_others(terms: list, exclude: int) -> str:
    lines = [f"특약{i+1}: {t}" for i, t in enumerate(terms) if i != exclude]
    return "\n".join(lines) if lines else "없음"

def fmt_laws(docs: list[dict]) -> str:
    lines = []
    for d in docs:
        text = d.get("document_text") or d.get("document_body") or ""
        if text:
            lines.append(f"[{d.get('result_id','')}]\n{text}")
    return "\n\n".join(lines) if lines else "해당 없음"

def fmt_precs(docs: list[dict]) -> str:
    lines = []
    for d in docs:
        text = d.get("document_text") or d.get("document_body") or ""
        if text:
            lines.append(f"[{d.get('result_id','')}]\n{text[:800]}")
    return "\n\n".join(lines) if lines else "해당 없음"


def build_clause_prompt(
    term: str, label: str, property_info: dict,
    common_terms: list, target_terms: list, exclude_idx: int,
    top_laws: list[dict], top_precs: list[dict],
) -> str:
    out_fmt = json.dumps({
        "clause_id": label, "clause_text": None,
        "related_laws": [{"type": None, "ref": None, "summary": None}],
        "related_clauses": [{"clause_id": None, "clause_text": None, "relation": None}],
    }, ensure_ascii=False, indent=2)
    return f"""
[계약서 정보]
{fmt_property(property_info)}

[공통 특약 (모든 계약서 동일)]
{fmt_common(common_terms)}

[기타 특약 목록 (분석 대상 제외)]
{fmt_others(target_terms, exclude_idx)}

[분석 대상 특약 ({label})]
{term}

[관련 법령]
{fmt_laws(top_laws)}

[관련 판례]
{fmt_precs(top_precs)}

[출력 지시]
위 분석 대상 특약을 검토하여 아래 JSON 형식으로만 응답하세요.
- related_clauses는 다른 특약과 동시에 적용될 때 확인이 필요한 사항이 실제로 존재하는 경우에만 작성하고, 없으면 빈 배열로 반환하세요.
- clause_id는 입력된 특약의 ID를 그대로 사용하세요.
- 모든 필드는 해당 내용이 없으면 null을 반환하세요.
- JSON 외 텍스트, 마크다운 코드블록은 포함하지 마세요.

{out_fmt}
"""


def build_checklist_prompt(
    target_terms: list, clause_results: list,
    property_info: dict, common_terms: list,
) -> str:
    out_fmt = json.dumps(
        {"contract_checklist": [{"item": None, "description": None, "basis": None}]},
        ensure_ascii=False, indent=2,
    )
    terms_text = "\n".join(f"특약{i+1}: {t}" for i, t in enumerate(target_terms))
    return f"""
[계약서 정보]
{fmt_property(property_info)}

[공통 특약]
{fmt_common(common_terms)}

[타겟 특약 전체]
{terms_text}

[특약별 분석 결과]
{json.dumps(clause_results, ensure_ascii=False, indent=2)}

[출력 지시]
위 계약서 전체를 바탕으로 임차인이 계약 전 확인해야 할 통합 체크리스트를 작성하세요.
- 입력된 모든 특약을 종합 검토한 후, 확인 항목을 통합하여 작성하고 확인 항목이 없는 경우 빈 배열로 반환하세요.
- 각 특약을 개별적으로 나열하는 것이 아니라, 계약서 전체 맥락에서 중요한 확인 사항을 도출하세요.
아래 JSON 형식으로만 응답하세요. JSON 외 텍스트, 마크다운 코드블록은 포함하지 마세요.

{out_fmt}
"""


# ── LLM 호출 ─────────────────────────────────────────────────────────
def call_llm(prompt: str, schema: type[BaseModel] | None = None) -> dict | None:
    model    = GenerativeModel(GEN_MODEL, system_instruction=SYSTEM_PROMPT)
    config   = GenerationConfig(temperature=0.0, response_mime_type="application/json")
    response = model.generate_content(prompt, generation_config=config)
    text     = re.sub(r"^```(?:json)?\s*", "", response.text.strip())
    text     = re.sub(r"\s*```$", "", text)
    parsed   = json.loads(text)
    if schema:
        return schema.model_validate(parsed).model_dump()
    return parsed


# ── 계약서 1건 처리 ──────────────────────────────────────────────────
def process_contract(
    contract_path: Path,
    eval_index: dict,
    output_dir: Path,
    top_k_law: int,
    top_k_prec: int,
) -> None:
    prefix   = contract_path.stem
    out_path = output_dir / f"{prefix}_report.json"

    if out_path.exists():
        print(f"  [{prefix}] 이미 존재 — 건너뜀")
        return

    contract      = json.loads(contract_path.read_text(encoding="utf-8"))
    property_info = contract.get("property_info", {})
    special_terms = contract.get("special_terms", [])
    common_terms  = special_terms[:COMMON_TERMS_COUNT]
    target_terms  = special_terms[COMMON_TERMS_COUNT:]

    if not target_terms:
        print(f"  [{prefix}] 타겟 특약 없음 — 건너뜀")
        return

    print(f"\n[{prefix}] 처리 시작 (특약 {len(target_terms)}개)")

    clause_results = []
    eval_hits = hybrid_hits = 0

    for i, term in enumerate(target_terms):
        label = f"특약{i+1}"
        top_laws, top_precs, source = retrieve(
            term, eval_index, top_k_law, top_k_prec,
        )
        if source == "eval":
            eval_hits += 1
        else:
            hybrid_hits += 1

        print(f"  [{label}] [{source}] 법령 {len(top_laws)}건 / 판례 {len(top_precs)}건 → LLM", flush=True)
        prompt = build_clause_prompt(
            term, label, property_info, common_terms, target_terms, i, top_laws, top_precs
        )
        result = call_llm(prompt, schema=ClauseResult)
        if result:
            clause_results.append(result)
            print(f"  [{label}] 완료")
        else:
            print(f"  [{label}] LLM 응답 없음")

    print(f"  검색 요약: eval hit {eval_hits}건 / miss {hybrid_hits}건")

    print(f"  [체크리스트] LLM 호출")
    checklist_result = call_llm(
        build_checklist_prompt(target_terms, clause_results, property_info, common_terms),
        schema=ChecklistOutput,
    )
    contract_checklist = (checklist_result or {}).get("contract_checklist", [])

    final = ReportOutput(
        contract_checklist=contract_checklist,
        clause_results=clause_results,
    )
    out_path.write_text(final.model_dump_json(indent=2, exclude_none=False), encoding="utf-8")
    print(f"  [{prefix}] 저장 → {out_path}")


# ── 메인 ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contracts", default=r"C:\Users\윤예정\Downloads\특약_통합_계약서")
    parser.add_argument("--retrieval", default=(
        r"C:\Users\윤예정\Downloads\legal_retrieval_eval_20260531_020111_147888"
        r"\legal_retrieval_eval_20260531_020111_147888.json"
    ))
    parser.add_argument("--output",     default=None)
    parser.add_argument("--top-k-law",  type=int, default=DEFAULT_TOP_K_LAW)
    parser.add_argument("--top-k-prec", type=int, default=DEFAULT_TOP_K_PREC)
    parser.add_argument("--prefix",     default=None, help="특정 파일만 처리 (예: qa_structured_781)")
    args = parser.parse_args()

    contracts_dir  = Path(args.contracts)
    retrieval_path = Path(args.retrieval)
    output_dir     = Path(args.output) if args.output else contracts_dir / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. eval 인덱스 구축 ──────────────────────────────────────────
    eval_index = build_eval_index(retrieval_path)

    # ── 2. 처리 대상 목록 (qa + caselense 전체) ──────────────────────
    if args.prefix:
        targets = [contracts_dir / f"{args.prefix}.json"]
    else:
        targets = sorted(contracts_dir.glob("*.json"))
    print(f"\n처리 대상: {len(targets)}개 계약서\n")

    for contract_path in targets:
        if not contract_path.exists():
            print(f"[없음] {contract_path}")
            continue
        try:
            process_contract(
                contract_path, eval_index,
                output_dir, args.top_k_law, args.top_k_prec,
            )
        except Exception as e:
            print(f"  [{contract_path.stem}] 오류: {e}")


if __name__ == "__main__":
    main()
