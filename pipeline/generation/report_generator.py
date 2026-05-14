import json
import os
import re
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
class RelatedLaw(BaseModel):
    type: str | None = None
    ref: str | None = None
    summary: str | None = None

class ClauseRevision(BaseModel):
    target: str | None = None
    reason: str | None = None
    direction: str | None = None

class ClauseResult(BaseModel):
    clause_id: str | None = None
    clause_text: str | None = None
    related_laws: list[RelatedLaw] | None = None
    clause_revision: ClauseRevision | None = None

class RelatedClause(BaseModel):
    clause_id: str | None = None
    clause_text: str | None = None
    relation: str | None = None

class ChecklistItem(BaseModel):
    item: str | None = None
    description: str | None = None
    basis: str | None = None

class ReportOutput(BaseModel):
    contract_checklist: list[ChecklistItem] | None = None
    related_clauses: list[RelatedClause] | None = None
    clause_results: list[ClauseResult] | None = None
    
class RelatedClausesOutput(BaseModel):
    related_clauses: list[RelatedClause] | None = None

class ChecklistOutput(BaseModel):
    contract_checklist: list[ChecklistItem] | None = None

# ── 프롬프트 ──────────────────────────────────────────
SYSTEM_PROMPT = """[역할 및 지시]
당신은 주택임대차 계약 검토를 도와줄 법률 전문가입니다.
아래 정보를 바탕으로 임차인이 계약 전 스스로 확인해야 할 사항을 도출하세요.

- 특약 문구의 해석 가능성, 법령과의 관계, 분쟁으로 이어질 수 있는 사실관계를 객관적으로 서술하세요.
- 명백히 법령에 위반되는 경우에는 해당 법령 조문을 근거로 위반 사실을 서술합니다.
- basis는 반드시 입력된 법령·판례에 실재하는 것만 인용하세요. 
- 입력에 없는 법령·판례는 임의로 생성하지 마세요.
- "위험", "유리", "불리" 등의 평가적 표현은 사용하지 마세요.
- checklist 항목이 없는 경우 빈 배열로 반환하고, no_checklist_reason 필드에 사유를 기재하세요.
- related_clauses는 다른 특약과 동시에 적용될 때 확인이 필요한 사항이 실제로 존재하는 경우에만 작성하고, 없으면 빈 배열로 반환하세요.


[출력 형식 예시]
아래는 올바르게 작성된 출력 예시입니다.
이 예시의 방향성과 서술 방식을 참고하여 분석 대상 특약을 작성하세요.
판단 표현(유리/불리/위험)은 사용하지 마세요.

예시 1)
원문: "임차인 퇴거 시 모든 원상복구 비용은 임차인이 전액 부담한다."

clause_revision:
  target: "모든", "전액"의 범위 불명확
  reason: 통상적 사용에 따른 마모(자연 손모)와 임차인 귀책 손상이 구분되지 않아
          해석 분쟁 가능
  direction: 임차인 귀책 손상에 한정하고, 통상 마모 및 대규모 수선은 제외됨을 명시

checklist:
  - item: "원상복구 범위 및 귀책 기준 확인"
    description: "원상복구 의무의 범위는 임대 당시 목적물의 상태, 계약 체결 경위,
                  임차인이 수리하거나 변경한 내용 등을 개별적으로 고려하여 정해집니다.
                  계약 체결 전 또는 입주 시 임차 목적물의 현재 상태를 사진이나
                  영상으로 기록하고, 하자 부위를 계약서에 명기해 두면 퇴거 시
                  귀책 여부를 확인하는 근거로 활용할 수 있습니다."
    basis: []

  - item: "입주 시 기존 하자 기록 여부 확인"
    description: "입주 전부터 존재하는 파손·노후화 부분이 퇴거 시 임차인 귀책으로
                  간주될 수 있는지를 확인하기 위해, 입주 당일 임대인과 함께
                  목적물 상태를 점검하고 그 내용을 계약서 또는 별도 확인서에
                  기재하는 방법을 확인합니다."
    basis: []

related_clauses:
  - clause_id: "수선의무 특약 해당 ID"
    clause_text: "연관 특약 원문"
    relation: "수선의무 부담 특약이 함께 존재하는 경우, 임차인이 임차 기간 중
               자비로 수선한 부분이 퇴거 시 원상복구 대상에 해당하는지 여부가
               불명확해집니다. 임차인이 수선 비용을 이미 부담한 부분에 대해
               추가로 원상복구 비용까지 청구될 수 있는지를 두 조항을 함께
               확인합니다."


예시 2)
원문: "임차 기간 중 발생하는 모든 수리 및 수선은 임차인이 부담한다."

clause_revision:
  target: "모든 수리 및 수선"의 범위가 대규모 수선까지 포함하는지 불명확
  reason: 건물 주요 구성부분의 대수선·기본 설비 교체 등 대규모 수선과
          소규모 파손 수선이 구분되지 않아, 임대인 수선의무 면제 범위가
          불명확한 상태로 해석 분쟁 가능
  direction: 임차인 부담 수선의 범위를 "통상 생길 수 있는 소규모 파손"으로
             한정하고, 건물 주요 구성부분 대수선·기본 설비 교체 등 대규모
             수선은 임대인 부담임을 별도 명시

checklist:
  - item: "수선의무 면제 범위 명시 여부 확인"
    description: "특약으로 임대인의 수선의무를 면제하더라도 면제 범위가
                  명시되지 않은 경우, 임차인의 수선 부담은 통상 생길 수 있는
                  소규모 파손에 한하는 것으로 해석될 수 있습니다.
                  계약서에 임차인 부담 수선의 구체적 범위(예: 문손잡이 교체,
                  형광등 교체 등 소모품 수준)가 기재되어 있는지 확인합니다."
    basis: []

  - item: "난방·배관·전기 등 핵심 설비 수선 주체 확인"
    description: "난방시설, 배관, 전기설비 등은 임차인이 별 비용 없이 손쉽게
                  고칠 수 있는 소규모 파손으로 보기 어렵습니다.
                  이러한 설비에 결함이 발생할 경우 수선 주체가 누구인지를
                  계약서 또는 임대인과의 서면 확인을 통해 명확히 합니다."
    basis: []

related_clauses:
  - clause_id: "원상복구 특약 해당 ID"
    clause_text: "연관 특약 원문"
    relation: "원상복구 비용 부담 특약이 함께 존재하는 경우, 임차 기간 중
               임차인이 수선한 부분을 퇴거 시 원상복구 대상으로 볼 것인지에 대해
               두 조항의 적용 범위가 중첩될 수 있습니다. 수선 이후 목적물의
               상태 변화가 원상복구 의무의 기준이 되는지를 함께 확인합니다."

  - clause_id: "차임 감액 불가 특약 해당 ID"
    clause_text: "연관 특약 원문"
    relation: "차임 감액 불가 특약이 함께 존재하는 경우, 임차 목적물의 일부가
               수선되지 않아 정상적으로 사용·수익할 수 없는 상태가 되더라도
               차임 감액을 요구할 수 있는지 여부가 불명확해집니다. 수선이
               지연되는 경우 차임 지급 의무와의 관계를 두 조항을 함께
               확인합니다."


예시 3)
원문: "계약 갱신 시 임대료 인상률은 당사자 간 협의로 정하며 별도 제한을 두지 않는다."

clause_revision:
  target: "별도 제한을 두지 않는다"는 문구가 법정 증액 상한(5%)을 초과하는
          인상도 유효하다는 의미로 해석될 여지 존재
  reason: 계약갱신요구권 행사 시에는 주택임대차보호법 제7조 제2항에 따라
          증액 상한이 적용되며, 이를 초과하는 약정 부분은 효력이 없음에도
          현재 문구는 이를 명시하지 않아 당사자 간 해석 충돌 가능
  direction: "단, 계약갱신요구권 행사에 따른 갱신의 경우 차임 증액은
             주택임대차보호법 제7조 제2항에 따른 범위를 초과하지 않는다"는
             내용을 병기하여 법정 상한 적용 여부를 명확히 구분

checklist:
  - item: "계약갱신 방식(합의갱신·요구권 행사) 구분 확인"
    description: "임대료 인상 상한 5% 규정은 임차인이 계약갱신요구권을 행사하는
                  경우에 적용됩니다. 임차인이 갱신요구권을 행사하지 않고 임대인과
                  합의하여 새로운 계약을 체결하는 경우에는 5%를 초과하는 인상이
                  가능합니다. 이번 갱신이 어떤 방식으로 이루어지는지를 계약서
                  문언과 당사자 의사를 통해 확인합니다."
    basis: []

  - item: "증액 청구 가능 시점 확인"
    description: "증액 청구는 임대차계약 또는 약정한 차임·보증금의 증액이 있은 후
                  1년 이내에는 할 수 없습니다. 직전 증액 시점으로부터 1년이
                  경과하였는지를 계약서 상의 날짜를 통해 확인합니다."
    basis: []

related_clauses:
  - clause_id: "갱신요구권 포기 특약 해당 ID"
    clause_text: "연관 특약 원문"
    relation: "계약갱신요구권 포기 특약이 함께 존재하는 경우, 임차인이
               합의갱신 방식으로만 계약을 연장하게 되어 임대료 인상 제한(5%)
               규정이 적용되지 않을 수 있습니다. 갱신 방식에 따라 임대료
               결정 방식이 달라지는지를 두 조항을 함께 확인합니다."


예시 4)
원문: "임차인은 계약 만료 시 계약갱신을 요구하지 않기로 한다."

clause_revision:
  target: 임차인의 계약갱신요구권을 사전에 포기하는 내용으로,
          법이 임차인에게 보장하는 권리를 배제하는 약정에 해당
  reason: 주택임대차보호법 제10조(강행규정)에 따라 임차인에게 불리한 약정은
          효력이 없으므로, 현재 문구는 법적으로 유효하지 않은 내용을
          계약서에 포함하는 형태로 당사자 간 혼란 초래 가능
  direction: 해당 문구를 삭제하거나, "임차인은 임대차기간 만료 6개월 전부터
             2개월 전까지의 기간에 법이 정한 바에 따라 계약갱신 여부를
             결정한다"는 내용으로 대체하여 법정 절차에 따르도록 명시

checklist:
  - item: "계약갱신요구권 행사 가능 기간 확인"
    description: "계약갱신요구권은 임대차기간이 끝나기 6개월 전부터 2개월 전까지의
                  기간에 행사할 수 있습니다. 이 기간을 놓치면 해당 계약에서는
                  갱신요구권을 행사할 수 없게 됩니다. 계약 만료일을 기준으로
                  행사 가능 기간의 시작일과 종료일을 계산하여 확인합니다."
    basis: []

  - item: "갱신요구권 행사 방식 확인"
    description: "계약갱신요구권은 구두, 문자메시지, 이메일 등 방식에 제한이 없으나,
                  추후 분쟁 발생 시 행사 사실을 입증하기 위해 내용증명 우편 등
                  증거를 남길 수 있는 방법으로 행사하는 방법을 확인합니다."
    basis: []

related_clauses:
  - clause_id: "임대차 기간 특약 해당 ID"
    clause_text: "연관 특약 원문"
    relation: "임대차 기간을 2년 미만으로 정한 특약이 함께 존재하는 경우,
               법에 따라 임대차 기간은 2년으로 간주되므로 계약갱신요구권
               행사 가능 기간의 기산점이 계약서상 만료일이 아닌 법정 2년
               기준으로 달라질 수 있습니다. 갱신요구권 포기 특약의 효력
               발생 시점과 실제 행사 가능 기간을 두 조항을 함께 확인합니다."

  - clause_id: "임대료 인상 특약 해당 ID"
    clause_text: "연관 특약 원문"
    relation: "임대료 인상 관련 특약이 함께 존재하는 경우, 계약갱신요구권을
               행사하지 못하게 되면 합의갱신 방식으로만 계약이 연장되어
               임대료 인상 상한(5%) 규정이 적용되지 않을 수 있습니다.
               갱신 방식에 따라 임대료 결정 구조가 달라지는지를 두 조항을
               함께 확인합니다."""


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
    lines = []
    for m in matches:
        if not m.get("doc_text") and not m.get("summary"):
            continue
        ref = m.get("doc_id", "")
        text = m.get("doc_text") or m.get("summary") or ""
        lines.append(f"[{ref}]\n{text}")
    return "\n\n".join(lines) if lines else "해당 없음"


def format_precs(matches: list) -> str:
    lines = []
    for m in matches:
        summary = m.get("summary", "")
        if not summary or summary == "nan":
            continue
        doc_id = m.get("doc_id", "")
        lines.append(f"[판례 {doc_id}]\n{summary}")
    return "\n\n".join(lines) if lines else "해당 없음"


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
    output_format = json.dumps(
        {
            "clause_id": clause_label,
            "clause_text": None,
            "related_laws": [{"type": None, "ref": None, "summary": None}],
            "clause_revision": {"target": None, "reason": None, "direction": None},
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
모든 필드는 해당 내용이 없으면 null을 반환하세요.
JSON 외 텍스트, 마크다운 코드블록은 포함하지 마세요.

{output_format}
"""

def build_related_clauses_prompt(
    target_terms: list,
    clause_results: list,
) -> str:
    target_terms_text = "\n".join(
        [f"특약{i+1}: {t}" for i, t in enumerate(target_terms)]
    )
    results_summary = json.dumps(clause_results, ensure_ascii=False, indent=2)

    output_format = json.dumps(
        {
            "related_clauses": [
                {
                    "clause_id": None,
                    "clause_text": None,
                    "relation": None,
                }
            ]
        },
        ensure_ascii=False,
        indent=2,
    )

    return f"""
[타겟 특약 전체]
{target_terms_text}

[특약별 분석 결과]
{results_summary}

[출력 지시]
위 특약들 중 동시에 적용될 때 확인이 필요한 연관 관계가 실제로 존재하는 쌍만 작성하세요.
연관 관계가 없으면 빈 배열로 반환하세요.
각 특약 쌍은 한 번만 작성하세요 (A-B가 있으면 B-A는 작성하지 마세요).
아래 JSON 형식으로만 응답하세요. JSON 외 텍스트, 마크다운 코드블록은 포함하지 마세요.

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
각 특약을 개별적으로 나열하는 것이 아니라, 계약서 전체 맥락에서 중요한 확인 사항을 도출하세요.
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

def main():
    # ── 파일 로드 ──────────────────────────────────────────────────
    base_dir = Path(__file__).resolve().parent
    project_root = base_dir.parent.parent
    reranking_dir = project_root / "output" / "reranking"

    # prefix 기준으로 law/caselaw 파일 페어링
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

        # ── 데이터 분리 ────────────────────────────────────────────────
        property_info = contract["property_info"]
        special_terms = contract["special_terms"]
        common_terms = special_terms[:COMMON_TERMS_COUNT]
        target_terms = special_terms[COMMON_TERMS_COUNT:]

        # ── rrf 결과 인덱싱 ────────────────────────────────────────────
        rrf_index = build_rrf_index(law_results, prec_results)

        # ── 타겟 특약별 LLM 호출 ───────────────────────────────────────
        clause_results = []

        for i, term in enumerate(target_terms):
            rrf_idx = i + 1
            clause_label = f"특약{i+1}"
            laws = rrf_index.get(rrf_idx, {}).get("laws", [])
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

        # ── 전체 계약서 체크리스트 생성 ───────────────────────────────
        print(f"  [전체 체크리스트] LLM 호출 중...")
        checklist_result = call_llm(
            build_checklist_prompt(target_terms, clause_results, property_info, common_terms),
            schema=ChecklistOutput,
        )
        contract_checklist = checklist_result.get("contract_checklist", []) if checklist_result else []
        print(f"  [전체 체크리스트] 완료")

        # ── 연관 특약 생성 ────────────────────────────────────────────
        print(f"  [연관 특약] LLM 호출 중...")
        related_clauses_result = call_llm(
            build_related_clauses_prompt(target_terms, clause_results),
            schema=RelatedClausesOutput,
        )
        related_clauses = related_clauses_result.get("related_clauses", []) if related_clauses_result else []
        print(f"  [연관 특약] 완료")

        # ── 최종 출력 ──────────────────────────────────────────────────
        final_output = ReportOutput(
            contract_checklist=contract_checklist,
            related_clauses=related_clauses,
            clause_results=clause_results,
        )
        output_path = project_root / "output" / f"{prefix}_report.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_output.model_dump_json(indent=2, exclude_none=False))

        print(f"  [{prefix}] 완료. 결과 저장: {output_path}")

if __name__ == "__main__":
    main()