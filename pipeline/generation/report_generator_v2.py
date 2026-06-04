import json
import os
import re
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, field_validator
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("GCP_LOCATION")
vertexai.init(project=PROJECT_ID, location=LOCATION)

MODEL_NAME_FLASH = "gemini-2.5-flash"
MODEL_NAME_FLASH_LITE = "gemini-2.5-flash-lite"
COMMON_TERMS_COUNT = 6

# ── Pydantic 스키마 ──────────────────────────────────────────────

class LawType(str, Enum):
    law  = "법령"
    case = "판례"

class SelectedLaw(BaseModel):
    ref: str | None = None
    summary: str | None = None

class ClauseSummaryOutput(BaseModel):
    selected_laws: list[SelectedLaw] = []

    @field_validator("selected_laws", mode="before")
    @classmethod
    def coerce_list(cls, v):
        if v is None:
            return []
        return v

class RelatedClause(BaseModel):
    clause_id: str | None = None
    clause_text: str | None = None
    relation: str | None = None

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

class FinalReportOutput(BaseModel):
    contract_checklist: list[ChecklistItem] = []
    related_clauses_map: dict[str, list[RelatedClause]] = {} # clause_id -> list of relations

class LLMRelatedClauseResult(BaseModel):
    clause_id: str
    related_clauses: list[RelatedClause] = []

    @field_validator("related_clauses", mode="after")
    @classmethod
    def split_combined_clause_ids(cls, v):
        result = []
        for item in v:
            c_id = item.clause_id or ""
            ids = [x.strip() for x in c_id.split(",") if x.strip()]
            if len(ids) > 1:
                for cid in ids:
                    result.append(RelatedClause(
                        clause_id=cid,
                        clause_text=None,
                        relation=item.relation,
                    ))
            else:
                result.append(item)
        return result

class FinalReportLLMOutput(BaseModel):
    contract_checklist: list[ChecklistItem] = []
    clause_relations: list[LLMRelatedClauseResult] = []

# ── 프롬프트 ──────────────────────────────────────────

SYSTEM_PROMPT = """[역할 및 지시]
당신은 주택임대차 계약 검토를 도와줄 법률 전문가입니다.
아래 정보를 바탕으로 임차인이 계약 전 스스로 확인해야 할 사항을 도출하세요.

- 특약 문구의 해석 가능성, 법령과의 관계, 분쟁으로 이어질 수 있는 사실관계를 객관적으로 서술하세요.
- 명백히 법령에 위반되는 경우에는 해당 법령 조문을 근거로 위반 사실을 서술합니다.
- "위험", "유리", "불리" 등의 평가적 표현은 절대 사용하지 마세요."""

def format_laws(matches: list) -> str:
    lines = []
    for m in matches:
        text = m.get("content") or m.get("doc_text") or m.get("summary") or ""
        if not text:
            continue
        doc_id = m.get("doc_id", "")
        lines.append(f"[{doc_id}]\n{text}")
    return "\n\n".join(lines) if lines else "해당 없음"

def format_precs(matches: list) -> str:
    lines = []
    for m in matches:
        text = m.get("content") or m.get("summary") or ""
        if not text or text == "nan":
            continue
        doc_id = m.get("doc_id", "")
        lines.append(f"[{doc_id}]\n{text}")
    return "\n\n".join(lines) if lines else "해당 없음"

def format_property_info(property_info: dict) -> str:
    return json.dumps(property_info, ensure_ascii=False, indent=2)

def build_clause_summary_prompt(
    target_clause: str,
    laws: list,
    precs: list,
) -> str:
    all_doc_ids = [m.get("doc_id", "") for m in laws + precs if m.get("doc_id")]
    output_format = json.dumps(
        {
            "selected_laws": [{"ref": "<위 목록의 doc_id 그대로>", "summary": "<일반인이 이해할 수 있는 설명>"}]
        },
        ensure_ascii=False,
        indent=2,
    )

    return f"""
[분석 대상 특약]
{target_clause}

[관련 법령]
{format_laws(laws)}

[관련 판례]
{format_precs(precs)}

[출력 지시]
위 분석 대상 특약을 검토하여 아래 JSON 형식으로만 응답하세요.

- selected_laws: [관련 법령]과 [관련 판례] 중 반드시 이 특약과 **직접적으로 관련 있는 상위 3개 이내의 항목**만 골라 연관도 높은 순서로 작성하세요.
  *   **주의**: 제공된 리스트에 없는 법령 번호나 판례를 외부 지식으로 생성하여 포함하지 마세요. 반드시 대괄호 안의 식별자({', '.join(all_doc_ids)})만 사용해야 합니다.
  *   **주의**: 연관성이 낮거나 단순히 용어가 겹치는 정도의 항목은 과감하게 제외하세요. 정말로 관련 있는 항목이 없으면 빈 배열([])을 반환하세요.
  summary는 법률 전문 지식이 없는 일반인도 이해할 수 있도록 작성하세요.
    · 이 법령/판례가 무슨 내용인지 쉬운 말로 설명하고,
    · 이 특약 내용을 반복하지 않고, 이 법령/판례가 특약에 미치는 영향이나 특약과의 구체적인 연관성을 서술하세요.
    · 전문 용어는 괄호 안에 풀어쓰세요. 예) "대항력(집을 팔아도 계속 살 수 있는 권리)"
  summary 외에 다른 필드는 생성하지 마세요.
- JSON 외 텍스트, 마크다운 코드블록은 포함하지 마세요.

{output_format}
"""

def build_final_report_prompt(
    property_info: dict,
    common_terms: list,
    target_terms_with_summaries: list[dict],
) -> str:
    common_text = "\n".join([f"공통특약 {i+1}: {t}" for i, t in enumerate(common_terms)])
    
    target_text_parts = []
    for item in target_terms_with_summaries:
        idx = item['index'] - COMMON_TERMS_COUNT
        clause_id = f"특약{idx}"
        target_text_parts.append(f"[{clause_id}]\n원문: {item['clause']}")
        if item.get('summaries'):
            target_text_parts.append("법적 해석 요약:")
            for s in item['summaries']:
                target_text_parts.append(f"- {s['ref']}: {s['summary']}")
        target_text_parts.append("")
    
    target_text = "\n".join(target_text_parts)

    output_format = json.dumps(
        {
            "contract_checklist": [
                {"item": None, "description": None, "basis": None}
            ],
            "clause_relations": [
                {
                    "clause_id": "<특약1 등>",
                    "related_clauses": [
                        {"clause_id": "<특약2 또는 공통특약 1>", "clause_text": None, "relation": "<관계 설명>"}
                    ]
                }
            ]
        },
        ensure_ascii=False,
        indent=2,
    )

    return f"""
[계약서 정보]
{format_property_info(property_info)}

[공통 특약]
{common_text}

[타겟 특약 전체 및 법적 해석]
{target_text}

[출력 지시]
위 계약서 전체와 개별 특약의 법적 해석을 바탕으로 다음 두 가지를 도출하여 JSON 형식으로만 응답하세요.

1. contract_checklist: 임차인이 계약 전 확인해야 할 통합 체크리스트
- 입력된 모든 특약을 종합 검토한 후, 확인 항목을 통합하여 작성하세요.
- 계약서 전체 맥락에서 중요한 확인 사항을 도출하세요.
- basis: 이 체크리스트 항목의 근거가 되는 특약 ID(예: "특약1", "공통특약 1")와 법령/판례 ref를 배열로 나열하세요. 위 내용에 등장한 식별자만 사용해야 합니다.

2. clause_relations: 특약 간의 연관성 분석
- [타겟 특약 전체]와 [공통 특약] 중 서로 동시에 적용될 때 확인이 필요하거나 충돌할 가능성이 있는 특약들의 관계를 분석하세요.
- clause_id들은 반드시 "특약1", "공통특약 1" 형태의 ID를 사용하세요.
- relation은 두 조항이 어떻게 연관되어 있으며 왜 주의해야 하는지 일반인 눈높이에서 설명하세요.
- 연관성이 있는 특약에 대해서만 배열에 추가하세요.
- clause_text는 null로 두세요.

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

[출력 예시 JSON 내부 구조]
"contract_checklist": [
  {{
    "item": "원상복구 범위 및 귀책 기준 확인",
    "description": "원상복구 의무의 범위는 임대 당시 목적물의 상태, 계약 체결 경위, 임차인이 수리하거나 변경한 내용 등을 개별적으로 고려하여 정해집니다. 계약 체결 전 또는 입주 시 임차 목적물의 현재 상태를 사진이나 영상으로 기록하고, 하자 부위를 계약서에 명기해 두면 퇴거 시 귀책 여부를 확인하는 근거로 활용할 수 있습니다.",
    "basis": ["특약A"]
  }}
],
"clause_relations": [
  {{
    "clause_id": "특약A",
    "related_clauses": [
      {{
        "clause_id": "특약B",
        "clause_text": null,
        "relation": "수선의무 부담 특약이 함께 존재하는 경우, 임차인이 임차 기간 중 자비로 수선한 부분이 퇴거 시 원상복구 대상에 해당하는지 여부가 불명확해집니다. 임차인이 수선 비용을 이미 부담한 부분에 대해 추가로 원상복구 비용까지 청구될 수 있는지를 두 조항을 함께 확인합니다."
      }}
    ]
  }}
]
---

JSON 외 텍스트, 마크다운 코드블록은 포함하지 마세요.

{output_format}
"""


def call_llm(
    prompt: str,
    schema: type[BaseModel] | None = None,
    max_retries: int = 2,
    model_override: str | None = None,
) -> dict | None:
    import time
    from json import JSONDecodeError
    from pydantic import ValidationError

    model_to_use = model_override if model_override else MODEL_NAME_FLASH
    model = GenerativeModel(model_to_use, system_instruction=SYSTEM_PROMPT)
    config = GenerationConfig(temperature=0.0, response_mime_type="application/json")

    for attempt in range(1, max_retries + 2):
        try:
            response = model.generate_content(prompt, generation_config=config)
            text = response.text.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)
            if schema:
                validated = schema.model_validate(parsed)
                return validated.model_dump()
            return parsed
        except JSONDecodeError as e:
            print(f"  [call_llm] JSON 파싱 실패 (시도 {attempt}/{max_retries + 1}): {e}")
        except ValidationError as e:
            print(f"  [call_llm] Pydantic 검증 실패 (시도 {attempt}/{max_retries + 1}): {e}")
        except Exception as e:
            print(f"  [call_llm] LLM 호출 오류 (시도 {attempt}/{max_retries + 1}): {e}")

        if attempt <= max_retries:
            time.sleep(2 ** attempt)

    return None

from functools import lru_cache

# ... (imports)

# ... (rest of the file)

@lru_cache(maxsize=1024)
def generate_clause_summary(target_clause: str, laws_json: str, precs_json: str) -> list[dict]:
    """1단계: 개별 특약의 법령/판례 요약만 생성 (독립적, 비동기 호출용)"""
    laws = json.loads(laws_json)
    precs = json.loads(precs_json)
    
    prompt = build_clause_summary_prompt(target_clause, laws, precs)
    result = call_llm(prompt, schema=ClauseSummaryOutput, model_override=MODEL_NAME_FLASH_LITE)
    
    rag_map: dict[str, dict] = {}
    for m in laws:
        did = m.get("doc_id", "")
        if did: rag_map[did] = {"type": LawType.law.value, "ref": did, "content": m.get("content") or m.get("doc_text") or ""}
    for m in precs:
        did = m.get("doc_id", "")
        if did: rag_map[did] = {"type": LawType.case.value, "ref": did, "content": m.get("content") or m.get("summary") or ""}

    related_laws = []
    if result:
        covered = set()
        for sel in result.get("selected_laws", []):
            ref = (sel.get("ref") or "").strip()
            if ref in rag_map and ref not in covered:
                related_laws.append({**rag_map[ref], "summary": sel.get("summary")})
                covered.add(ref)

    return related_laws


def generate_final_report(property_info: dict, common_terms: list, clauses_with_hits_and_summaries: list[dict]) -> FinalReportOutput:
    """2단계: 전체가 모인 후 통합 체크리스트와 연관성 분석 수행"""
    prompt = build_final_report_prompt(property_info, common_terms, clauses_with_hits_and_summaries)
    result = call_llm(prompt, schema=FinalReportLLMOutput, model_override=MODEL_NAME_FLASH)
    
    if not result:
        return FinalReportOutput()

    clause_text_map: dict[str, str] = {}
    for item in clauses_with_hits_and_summaries:
        label = f"특약{item['index'] - COMMON_TERMS_COUNT}"
        clause_text_map[label] = item["clause"]
    for i, term in enumerate(common_terms):
        clause_text_map[f"공통특약 {i + 1}"] = term

    relations_map = {}
    
    # 중복 제거 로직 포함 (A->B, B->A)
    seen_pairs = set()

    for cr in result.get("clause_relations", []):
        cid = cr.get("clause_id")
        if not cid: continue
        
        valid_rels = []
        for rel in cr.get("related_clauses", []):
            other_id = rel.get("clause_id")
            if not other_id: continue
            
            pair = frozenset([cid, other_id])
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                rel["clause_text"] = clause_text_map.get(other_id)
                valid_rels.append(rel)
        
        if valid_rels:
            relations_map[cid] = valid_rels

    return FinalReportOutput(
        contract_checklist=result.get("contract_checklist", []),
        related_clauses_map=relations_map
    )
