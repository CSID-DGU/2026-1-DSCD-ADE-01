import argparse
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from pydantic import BaseModel

load_dotenv()

# ── Vertex AI 초기화 ──────────────────────────────────────────────
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("GCP_LOCATION")
vertexai.init(project=PROJECT_ID, location=LOCATION)

MODEL_NAME = "gemini-2.5-pro"

# ── 공통 특약 (special_terms 인덱스 0~5) ─────────────────────────
COMMON_TERMS_COUNT = 6

# ── Pydantic 스키마 ──────────────────────────────────────────────
from enum import Enum
from pydantic import field_validator

class LawType(str, Enum):
    law  = "법령"
    case = "판례"

class RelatedLaw(BaseModel):
    """최종 출력 스키마 - RAG에서 구성, summary만 LLM 생성"""
    type: LawType | None = None
    ref: str | None = None       # RAG doc_id
    summary: str | None = None   # LLM 생성
    content: str | None = None   # RAG 원문

class RelatedClause(BaseModel):
    clause_id: str | None = None
    clause_text: str | None = None
    relation: str | None = None

# LLM이 반환하는 중간 스키마 (summary + related_clauses만 생성)
class LawSummary(BaseModel):
    ref: str | None = None      # RAG doc_id 그대로
    summary: str | None = None

class ClauseLLMOutput(BaseModel):
    law_summaries: list[LawSummary] = []
    related_clauses: list[RelatedClause] = []

    @field_validator("law_summaries", "related_clauses", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if v is None:
            return []
        return v

    @field_validator("related_clauses", mode="after")
    @classmethod
    def split_combined_clause_ids(cls, v):
        """
        1. LLM이 "공통특약 1, 2"처럼 여러 특약을 하나로 합친 경우 별도 항목으로 분리.
           clause_text는 합쳐진 텍스트라 신뢰 불가 → None 처리.
           relation은 그대로 이어받음.
        2. 공통특약은 related_clauses에서 제외 (개별 특약 간 관계만 표시).
        """
        result = []
        for item in v:
            clause_id = item.clause_id or ""
            ids = [x.strip() for x in clause_id.split(",") if x.strip()]
            if len(ids) > 1:
                for cid in ids:
                    if not cid.startswith("공통특약"):
                        result.append(RelatedClause(
                            clause_id=cid,
                            clause_text=None,
                            relation=item.relation,
                        ))
            else:
                if not clause_id.startswith("공통특약"):
                    result.append(item)
        return result

class ClauseResult(BaseModel):
    clause_id: str | None = None
    clause_text: str | None = None
    related_laws: list[RelatedLaw] = []
    related_clauses: list[RelatedClause] = []

class ChecklistItem(BaseModel):
    item: str | None = None
    description: str | None = None
    basis: list[str] = []

    @field_validator("basis", mode="before")
    @classmethod
    def coerce_basis(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

class ReportOutput(BaseModel):
    contract_checklist: list[ChecklistItem] = []
    clause_results: list[ClauseResult] = []

class ChecklistOutput(BaseModel):
    contract_checklist: list[ChecklistItem] = []

# ── 프롬프트 ──────────────────────────────────────────
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

  - item: "수선의무 면제 범위 명시 여부 확인"
    description: "특약으로 임대인의 수선의무를 면제하더라도 면제 범위가
                  명시되지 않은 경우, 임차인의 수선 부담은 통상 생길 수 있는
                  소규모 파손에 한하는 것으로 해석될 수 있습니다.
                  계약서에 임차인 부담 수선의 구체적 범위(예: 문손잡이 교체,
                  형광등 교체 등 소모품 수준)가 기재되어 있는지 확인합니다."

  - item: "난방·배관·전기 등 핵심 설비 수선 주체 확인"
    description: "난방시설, 배관, 전기설비 등은 임차인이 별 비용 없이 손쉽게
                  고칠 수 있는 소규모 파손으로 보기 어렵습니다.
                  이러한 설비에 결함이 발생할 경우 수선 주체가 누구인지를
                  계약서 또는 임대인과의 서면 확인을 통해 명확히 합니다."

  - item: "계약갱신 방식(합의갱신·요구권 행사) 구분 확인"
    description: "임대료 인상 상한 5% 규정은 임차인이 계약갱신요구권을 행사하는
                  경우에 적용됩니다. 임차인이 갱신요구권을 행사하지 않고 임대인과
                  합의하여 새로운 계약을 체결하는 경우에는 5%를 초과하는 인상이
                  가능합니다. 이번 갱신이 어떤 방식으로 이루어지는지를 계약서
                  문언과 당사자 의사를 통해 확인합니다."

  - item: "증액 청구 가능 시점 확인"
    description: "증액 청구는 임대차계약 또는 약정한 차임·보증금의 증액이 있은 후
                  1년 이내에는 할 수 없습니다. 직전 증액 시점으로부터 1년이
                  경과하였는지를 계약서 상의 날짜를 통해 확인합니다."

  - item: "계약갱신요구권 행사 가능 기간 확인"
    description: "계약갱신요구권은 임대차기간이 끝나기 6개월 전부터 2개월 전까지의
                  기간에 행사할 수 있습니다. 이 기간을 놓치면 해당 계약에서는
                  갱신요구권을 행사할 수 없게 됩니다. 계약 만료일을 기준으로
                  행사 가능 기간의 시작일과 종료일을 계산하여 확인합니다."

  - item: "갱신요구권 행사 방식 확인"
    description: "계약갱신요구권은 구두, 문자메시지, 이메일 등 방식에 제한이 없으나,
                  추후 분쟁 발생 시 행사 사실을 입증하기 위해 내용증명 우편 등
                  증거를 남길 수 있는 방법으로 행사하는 방법을 확인합니다."


clause_results:
  - clause_id: "특약A 해당 ID"
    clause_text: "임차인 퇴거 시 모든 원상복구 비용은 임차인이 전액 부담한다."
    related_clauses:
      - clause_id: "특약B 해당 ID"
        clause_text: "임차 기간 중 발생하는 모든 수리 및 수선은 임차인이 부담한다."
        relation: "수선의무 부담 특약이 함께 존재하는 경우, 임차인이 임차 기간 중
                   자비로 수선한 부분이 퇴거 시 원상복구 대상에 해당하는지 여부가
                   불명확해집니다. 임차인이 수선 비용을 이미 부담한 부분에 대해
                   추가로 원상복구 비용까지 청구될 수 있는지를 두 조항을 함께
                   확인합니다."
                   

  - clause_id: "특약B 해당 ID"
    clause_text: "임차 기간 중 발생하는 모든 수리 및 수선은 임차인이 부담한다."
    related_clauses:
      - clause_id: "특약A 해당 ID"
        clause_text: "임차인 퇴거 시 모든 원상복구 비용은 임차인이 전액 부담한다."
        relation: "원상복구 비용 부담 특약이 함께 존재하는 경우, 임차 기간 중
                   임차인이 수선한 부분을 퇴거 시 원상복구 대상으로 볼 것인지에 대해
                   두 조항의 적용 범위가 중첩될 수 있습니다. 수선 이후 목적물의
                   상태 변화가 원상복구 의무의 기준이 되는지를 함께 확인합니다."


  - clause_id: "특약C 해당 ID"
    clause_text: "계약 갱신 시 임대료 인상률은 당사자 간 협의로 정하며 별도 제한을 두지 않는다."
    related_clauses:
      - clause_id: "특약D 해당 ID"
        clause_text: "임차인은 계약 만료 시 계약갱신을 요구하지 않기로 한다."
        relation: "계약갱신요구권 포기 특약이 함께 존재하는 경우, 임차인이
                   합의갱신 방식으로만 계약을 연장하게 되어 임대료 인상 제한(5%)
                   규정이 적용되지 않을 수 있습니다. 갱신 방식에 따라 임대료
                   결정 방식이 달라지는지를 두 조항을 함께 확인합니다."


  - clause_id: "특약D 해당 ID"
    clause_text: "임차인은 계약 만료 시 계약갱신을 요구하지 않기로 한다."
    related_clauses:
      - clause_id: "특약C 해당 ID"
        clause_text: "계약 갱신 시 임대료 인상률은 당사자 간 협의로 정하며 별도 제한을 두지 않는다."
        relation: "임대료 인상 관련 특약이 함께 존재하는 경우, 계약갱신요구권을
                   행사하지 못하게 되면 합의갱신 방식으로만 계약이 연장되어
                   임대료 인상 상한(5%) 규정이 적용되지 않을 수 있습니다.
                   갱신 방식에 따라 임대료 결정 구조가 달라지는지를 두 조항을
                   함께 확인합니다." """


def load_json(path: str) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_rrf_index(law_list: list, prec_list: list) -> dict:
    """rrf 결과를 타겟 특약 index 기준으로 딕셔너리화"""
    index = {}
    for item in law_list:
        idx = item["index"]
        index.setdefault(idx, {"laws": [], "precs": []})
        index[idx]["laws"] = item.get("top_matches", [])
    for item in prec_list:
        idx = item["index"]
        index.setdefault(idx, {"laws": [], "precs": []})
        index[idx]["precs"] = item.get("top_matches", [])
    return index


def format_property_info(property_info: dict) -> str:
    return json.dumps(property_info, ensure_ascii=False, indent=2)


def format_common_terms(common_terms: list) -> str:
    lines = []
    for i, term in enumerate(common_terms):
        lines.append(f"공통특약 {i+1}: {term}")
    return "\n".join(lines)


def format_other_target_terms(target_terms: list, exclude_idx: int) -> str:
    """타겟 특약 중 현재 분석 대상을 제외한 나머지"""
    lines = []
    for i, term in enumerate(target_terms):
        if i == exclude_idx:
            continue
        lines.append(f"특약{i+1}: {term}")
    return "\n".join(lines) if lines else "없음"


def format_laws(matches: list) -> str:
    """LLM 프롬프트용 - 대괄호 안에 doc_id를 노출해 LLM이 그대로 ref로 쓰도록 함"""
    lines = []
    for m in matches:
        text = m.get("content") or m.get("doc_text") or m.get("summary") or ""
        if not text:
            continue
        doc_id = m.get("doc_id", "")
        lines.append(f"[{doc_id}]\n{text}")
    return "\n\n".join(lines) if lines else "해당 없음"


def format_precs(matches: list) -> str:
    """LLM 프롬프트용 - 대괄호 안에 doc_id를 노출해 LLM이 그대로 ref로 쓰도록 함"""
    lines = []
    for m in matches:
        text = m.get("content") or m.get("summary") or ""
        if not text or text == "nan":
            continue
        doc_id = m.get("doc_id", "")
        lines.append(f"[{doc_id}]\n{text}")
    return "\n\n".join(lines) if lines else "해당 없음"


def fill_all_laws(
    llm_laws: list[dict],
    laws: list[dict],
    precs: list[dict],
) -> list[dict]:
    """
    1. LLM이 반환한 related_laws에 RAG 원문(type, ref=doc_id, content)을 덮어씀.
    2. LLM이 빠뜨린 RAG 항목을 summary=None으로 추가해 전체 포함을 보장.

    format_laws/format_precs는 [title] 형태로 프롬프트에 노출하므로
    LLM이 ref로 title을 쓰는 경우 title→doc_id 변환 후 매칭.
    """
    all_rag = laws + precs

    # doc_id → {type, content} 인덱스
    did_index: dict[str, dict] = {}
    for m in laws:
        did = m.get("doc_id", "")
        if did:
            did_index[did] = {
                "type": LawType.law,
                "content": m.get("content") or m.get("doc_text") or "",
            }
    for m in precs:
        did = m.get("doc_id", "")
        if did:
            did_index[did] = {
                "type": LawType.case,
                "content": m.get("content") or m.get("summary") or "",
            }

    # title → doc_id 매핑 (LLM이 title을 ref로 쓸 경우 역변환용)
    title_to_did: dict[str, str] = {}
    for m in all_rag:
        title = m.get("title") or ""
        did   = m.get("doc_id", "")
        if title and did:
            title_to_did[title] = did

    def _find_did(ref: str) -> str | None:
        if ref in did_index:
            return ref
        if ref in title_to_did:
            return title_to_did[ref]
        for title, did in title_to_did.items():
            if title and (title in ref or ref in title):
                return did
        for did in did_index:
            if did in ref or ref in did:
                return did
        return None

    # LLM 결과: type/ref/content 덮어쓰기
    covered_dids: set[str] = set()
    result = []
    for law in llm_laws:
        ref = str(law.get("ref") or "").strip()
        matched_did = _find_did(ref)
        if matched_did:
            law["type"]    = did_index[matched_did]["type"]
            law["ref"]     = matched_did
            law["content"] = did_index[matched_did]["content"] or None
            covered_dids.add(matched_did)
        else:
            law.setdefault("content", None)
        result.append(law)

    # LLM이 빠뜨린 항목 추가 (summary=None)
    for m in all_rag:
        did = m.get("doc_id", "")
        if did and did not in covered_dids:
            result.append({
                "type":    did_index[did]["type"],
                "ref":     did,
                "summary": None,
                "content": did_index[did]["content"] or None,
            })

    return result


def dedup_related_clauses(clause_results: list[dict]) -> list[dict]:
    """
    A→B, B→A 중복 제거. 먼저 등장한 쌍만 유지.
    """
    seen: set[frozenset] = set()
    for cr in clause_results:
        cid = cr.get("clause_id", "")
        deduped = []
        for rel in cr.get("related_clauses") or []:
            other_id = rel.get("clause_id", "")
            pair: frozenset = frozenset([cid, other_id])
            if pair not in seen:
                seen.add(pair)
                deduped.append(rel)
        cr["related_clauses"] = deduped
    return clause_results


def load_from_rag_result(rag_path: str) -> tuple[dict, list, list, dict]:
    """
    test_rag_one_contract.py 결과 JSON을 읽어
    (property_info, common_terms, clauses_with_hits, {}) 반환.

    clauses_with_hits 각 항목:
        {
            "index":   int,          # 절대 인덱스 (COMMON_TERMS_COUNT+1 ~)
            "clause":  str,          # 특약 원문
            "laws":    list[dict],   # source_type == "law" 인 top_results
            "precs":   list[dict],   # source_type == "precedent" 인 top_results
        }
    """
    data = load_json(rag_path)
    property_info = data.get("property_info", {})
    common_terms  = data.get("common_terms", [])
    clauses_with_hits = []
    for item in data.get("clauses", []):
        laws  = [r for r in item.get("top_results", []) if r.get("source_type") == "law"]
        precs = [r for r in item.get("top_results", []) if r.get("source_type") == "precedent"]
        clauses_with_hits.append({
            "index":  item["index"],
            "clause": item["clause"],
            "laws":   laws,
            "precs":  precs,
        })
    return property_info, common_terms, clauses_with_hits


def build_clause_prompt(
    target_clause: str,
    clause_label: str,
    property_info: dict,
    common_terms: list,
    other_target_terms: list,
    exclude_idx: int,
    laws: list,
    precs: list,
) -> str:
    # 프롬프트에 노출할 doc_id 목록 (LLM이 ref로 그대로 사용)
    all_doc_ids = [m.get("doc_id", "") for m in laws + precs if m.get("doc_id")]
    output_format = json.dumps(
        {
            "law_summaries": [{"ref": "<위 목록의 doc_id 그대로>", "summary": None}],
            "related_clauses": [{"clause_id": None, "clause_text": None, "relation": None}]
        },
        ensure_ascii=False,
        indent=2,
    )

    return f"""
[계약서 정보]
{format_property_info(property_info)}

[공통 특약 (모든 계약서 동일)]
{format_common_terms(common_terms)}

[기타 특약 목록 (분석 대상 제외)]
{format_other_target_terms(other_target_terms, exclude_idx)}

[분석 대상 특약 ({clause_label})]
{target_clause}

[관련 법령]
{format_laws(laws)}

[관련 판례]
{format_precs(precs)}

[출력 지시]
위 분석 대상 특약을 검토하여 아래 JSON 형식으로만 응답하세요.

- law_summaries: [관련 법령]과 [관련 판례]의 모든 항목에 대해 이 특약에 어떻게 적용되는지 summary를 작성하세요.
  ref는 반드시 대괄호 안의 식별자({', '.join(all_doc_ids)})를 변형 없이 그대로 사용하세요.
  summary 외에 다른 필드는 생성하지 마세요.
- related_clauses: [기타 특약 목록]과 [공통 특약] 중 이 특약과 동시에 적용될 때 확인이 필요한 것만 작성하세요. 없으면 빈 배열로 반환하세요.
- JSON 외 텍스트, 마크다운 코드블록은 포함하지 마세요.

{output_format}
"""

def build_checklist_prompt(
    target_terms: list,
    clause_results: list,
    property_info: dict,
    common_terms: list,
) -> str:
    # 각 특약 분석 결과 요약 구성
    results_summary = json.dumps(clause_results, ensure_ascii=False, indent=2)

    output_format = json.dumps(
        {
            "contract_checklist": [
                {"item": None, "description": None, "basis": None}
            ]
        },
        ensure_ascii=False,
        indent=2,
    )

    target_terms_text = "\n".join(
        [f"특약{i+1}: {t}" for i, t in enumerate(target_terms)]
    )

    return f"""
[계약서 정보]
{format_property_info(property_info)}

[공통 특약]
{format_common_terms(common_terms)}

[타겟 특약 전체]
{target_terms_text}

[특약별 분석 결과]
{results_summary}

[출력 지시]
위 계약서 전체를 바탕으로 임차인이 계약 전 확인해야 할 통합 체크리스트를 작성하세요.
- 입력된 모든 특약을 종합 검토한 후, 확인 항목을 통합하여 작성하고 확인 항목이 없는 경우 빈 배열로 반환하세요.
- 각 특약을 개별적으로 나열하는 것이 아니라, 계약서 전체 맥락에서 중요한 확인 사항을 도출하세요.
아래 JSON 형식으로만 응답하세요. JSON 외 텍스트, 마크다운 코드블록은 포함하지 마세요.

{output_format}
"""


def call_llm(prompt: str, schema: type[BaseModel] | None = None) -> dict | None:
    model = GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
    config = GenerationConfig(temperature=0.0, response_mime_type="application/json")
    response = model.generate_content(prompt, generation_config=config)
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if schema:
        # Pydantic 검증 - 스키마 불일치 시 ValidationError 발생
        validated = schema.model_validate(parsed)
        return validated.model_dump()
    return parsed

def run_from_rag_result(rag_path: str, output_path: str | None = None) -> None:
    """
    test_rag_one_contract.py 결과 JSON 하나를 입력받아 보고서 생성.

    사용법:
        python pipeline/generation/report_generator.py --rag-result path/to/test_rag_104.json
        python pipeline/generation/report_generator.py --rag-result path/to/test_rag_104.json --output path/to/report.json
    """
    print(f"[rag-result 모드] 입력: {rag_path}")
    property_info, common_terms, clauses_with_hits = load_from_rag_result(rag_path)

    # 다른 특약 원문 리스트 (관계 분석용)
    all_target_terms = [c["clause"] for c in clauses_with_hits]

    def _call_one(i: int, item: dict) -> tuple[int, dict | None]:
        clause_label = f"특약{item['index'] - COMMON_TERMS_COUNT}"
        print(f"  [{clause_label}] LLM 호출 중...")
        prompt = build_clause_prompt(
            target_clause=item["clause"],
            clause_label=clause_label,
            property_info=property_info,
            common_terms=common_terms,
            other_target_terms=all_target_terms,
            exclude_idx=i,
            laws=item["laws"],
            precs=item["precs"],
        )
        # RAG 결과로 related_laws 직접 구성 (LLM 개입 없음)
        related_laws = []
        for m in item["laws"]:
            related_laws.append({
                "type":    LawType.law,
                "ref":     m.get("doc_id", ""),
                "summary": None,
                "content": m.get("content") or m.get("doc_text") or "",
            })
        for m in item["precs"]:
            related_laws.append({
                "type":    LawType.case,
                "ref":     m.get("doc_id", ""),
                "summary": None,
                "content": m.get("content") or m.get("summary") or "",
            })

        # LLM: summary + related_clauses만 생성
        llm_out = call_llm(prompt, schema=ClauseLLMOutput)
        if llm_out:
            # doc_id → summary 매핑 후 related_laws에 주입
            summary_map = {
                ls["ref"]: ls["summary"]
                for ls in (llm_out.get("law_summaries") or [])
                if ls.get("ref") and ls.get("summary")
            }
            for law in related_laws:
                if law["ref"] in summary_map:
                    law["summary"] = summary_map[law["ref"]]
            related_clauses = llm_out.get("related_clauses") or []
            print(f"  [{clause_label}] 완료")
        else:
            related_clauses = []
            print(f"  [{clause_label}] null 반환 → related_clauses 빈 배열")

        result = {
            "clause_id":      clause_label,
            "clause_text":    item["clause"],
            "related_laws":   related_laws,
            "related_clauses": related_clauses,
        }
        return i, result

    # 특약별 LLM 호출 병렬 실행 후 원래 순서로 정렬
    clause_results_map: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=len(clauses_with_hits)) as executor:
        futures = {executor.submit(_call_one, i, item): i
                   for i, item in enumerate(clauses_with_hits)}
        for future in as_completed(futures):
            i, result = future.result()
            if result:
                clause_results_map[i] = result

    clause_results = [clause_results_map[i]
                      for i in sorted(clause_results_map)]

    # A→B / B→A 중복 관계 제거
    clause_results = dedup_related_clauses(clause_results)

    # ── 체크리스트 생성 ────────────────────────────────────────────
    print("  [전체 체크리스트] LLM 호출 중...")
    checklist_result = call_llm(
        build_checklist_prompt(all_target_terms, clause_results, property_info, common_terms),
        schema=ChecklistOutput,
    )
    contract_checklist = checklist_result.get("contract_checklist", []) if checklist_result else []
    print("  [전체 체크리스트] 완료")

    # ── 저장 ──────────────────────────────────────────────────────
    final_output = ReportOutput(
        contract_checklist=contract_checklist,
        clause_results=clause_results,
    )
    if not output_path:
        stem = Path(rag_path).stem  # e.g. "test_rag_104"
        output_path = str(Path(rag_path).parent / f"{stem}_report.json")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_output.model_dump_json(indent=2, exclude_none=False))
    print(f"  완료. 결과 저장: {output_path}")


def run_legacy() -> None:
    """기존 reranking 파일 기반 처리 (하위 호환)."""
    base_dir = Path(__file__).resolve().parent
    project_root = base_dir.parent.parent
    reranking_dir = project_root / "output" / "reranking"

    law_files = list(reranking_dir.glob("*_reranking_law.json"))
    for law_file in law_files:
        prefix = law_file.name.replace("_reranking_law.json", "")
        caselaw_file = reranking_dir / f"{prefix}_reranking_caselaw.json"
        contract_file = project_root / "output" / f"{prefix}_contract.json"

        if not caselaw_file.exists():
            print(f"[{prefix}] caselaw 파일 없음, 건너뜀")
            continue
        if not contract_file.exists():
            print(f"[{prefix}] contract 파일 없음, 건너뜀")
            continue

        print(f"\n[{prefix}] 처리 시작")
        contract = load_json(contract_file)
        law_results = load_json(law_file)
        prec_results = load_json(caselaw_file)

        property_info = contract["property_info"]
        special_terms = contract["special_terms"]
        common_terms  = special_terms[:COMMON_TERMS_COUNT]
        target_terms  = special_terms[COMMON_TERMS_COUNT:]

        rrf_index = build_rrf_index(law_results, prec_results)
        clause_results = []

        for i, term in enumerate(target_terms):
            rrf_idx = i + 1
            clause_label = f"특약{i+1}"
            laws  = rrf_index.get(rrf_idx, {}).get("laws", [])
            precs = rrf_index.get(rrf_idx, {}).get("precs", [])

            print(f"  [{clause_label}] LLM 호출 중...")
            prompt = build_clause_prompt(
                target_clause=term,
                clause_label=clause_label,
                property_info=property_info,
                common_terms=common_terms,
                other_target_terms=target_terms,
                exclude_idx=i,
                laws=laws,
                precs=precs,
            )
            result = call_llm(prompt, schema=ClauseResult)
            if result:
                clause_results.append(result)
                print(f"  [{clause_label}] 완료")
            else:
                print(f"  [{clause_label}] 실패 - null 반환")

        print(f"  [전체 체크리스트] LLM 호출 중...")
        checklist_result = call_llm(
            build_checklist_prompt(target_terms, clause_results, property_info, common_terms),
            schema=ChecklistOutput,
        )
        contract_checklist = checklist_result.get("contract_checklist", []) if checklist_result else []
        print(f"  [전체 체크리스트] 완료")

        final_output = ReportOutput(
            contract_checklist=contract_checklist,
            clause_results=clause_results,
        )
        output_path = project_root / "output" / f"{prefix}_report.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_output.model_dump_json(indent=2, exclude_none=False))
        print(f"  [{prefix}] 완료. 결과 저장: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="report_generator")
    parser.add_argument(
        "--rag-result",
        type=str,
        default=None,
        help="test_rag_*.json 파일 경로 또는 해당 파일들이 들어있는 폴더 경로.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="출력 JSON 경로 또는 폴더. 파일 지정 시 단일 파일, 폴더 지정 시 해당 폴더에 저장. 미지정 시 입력 파일과 같은 폴더.",
    )
    args = parser.parse_args()

    if args.rag_result:
        rag_path = Path(args.rag_result)

        # 폴더 지정 시 → test_rag_*.json 전부 처리
        if rag_path.is_dir():
            files = sorted(rag_path.glob("test_rag_*.json"))
            if not files:
                print(f"[경고] {rag_path} 에서 test_rag_*.json 파일을 찾을 수 없습니다.")
                return
            print(f"[폴더 모드] {len(files)}개 파일 처리 시작")
            for f in files:
                out = None
                if args.output:
                    out = str(Path(args.output) / f"{f.stem}_report.json")
                run_from_rag_result(str(f), out)
        # 파일 지정 시 → 해당 파일만 처리
        else:
            run_from_rag_result(str(rag_path), args.output)
    else:
        run_legacy()


if __name__ == "__main__":
    main()