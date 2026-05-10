import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

load_dotenv()

# ── Vertex AI 초기화 ──────────────────────────────────────────────
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("GCP_LOCATION")
vertexai.init(project=PROJECT_ID, location=LOCATION)

MODEL_NAME = "gemini-2.5-pro"

# ── 공통 특약 (special_terms 인덱스 0~5) ─────────────────────────
COMMON_TERMS_COUNT = 6

# ── 출력 JSON 스키마 ──────────────────────────────────────────────
OUTPUT_SCHEMA = {
    "contract_checklist": [
        {
            "item": None,
            "description": None
        }
    ],
    "clause_results": [
        {
            "clause_id": None,
            "clause_text": None,
            "related_clauses": [
                {
                    "clause_id": None,
                    "clause_text": None,
                    "relation": None
                }
            ],
            "clause_revision": {
                "target": None,
                "reason": None,
                "direction": None
            }
        }
    ]
}

# ── 프롬프트 (수정 금지) ──────────────────────────────────────────
SYSTEM_PROMPT = """[역할 및 지시]
당신은 주택임대차 계약 검토를 도와줄 법률 전문가입니다.
아래 정보를 바탕으로 임차인이 계약 전 스스로 확인해야 할 사항을 도출하세요.

- 특약 문구의 해석 가능성, 법령과의 관계, 분쟁으로 이어질 수 있는 사실관계를 객관적으로 서술하세요.
- 명백히 법령에 위반되는 경우에는 해당 법령 조문을 근거로 위반 사실을 서술합니다.
- "위험", "유리", "불리" 등의 평가적 표현은 사용하지 마세요.
- contract_checklist는 입력된 모든 특약을 종합 검토한 후, 임차인이 계약 전 확인해야 할 항목을 통합하여 단 한 번 작성하고 확인 항목이 없는 경우 빈 배열로 반환하세요.
- clause_results는 입력된 특약 각각에 대해 작성하고, 입력에 없는 특약은 임의로 생성하지 마세요.
- related_clauses는 다른 특약과 동시에 적용될 때 확인이 필요한 사항이 실제로 존재하는 경우에만 작성하고, 없으면 빈 배열로 반환하세요.
- clause_id는 입력된 특약의 ID를 그대로 사용하세요.


[출력 형식 예시]
아래는 특약 4개가 하나의 계약서에 함께 존재하는 경우의 출력 예시입니다.
contract_checklist는 4개 특약 전체를 종합하여 단 한 번만 작성하고, clause_results는 특약 각각에 대해 작성합니다.
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
    clause_revision:
      target: '"모든", "전액"의 범위 불명확'
      reason: "통상적 사용에 따른 마모(자연 손모)와 임차인 귀책 손상이 구분되지 않아
               해석 분쟁 가능"
      direction: "임차인 귀책 손상에 한정하고, 통상 마모 및 대규모 수선은 제외됨을 명시"

  - clause_id: "특약B 해당 ID"
    clause_text: "임차 기간 중 발생하는 모든 수리 및 수선은 임차인이 부담한다."
    related_clauses:
      - clause_id: "특약A 해당 ID"
        clause_text: "임차인 퇴거 시 모든 원상복구 비용은 임차인이 전액 부담한다."
        relation: "원상복구 비용 부담 특약이 함께 존재하는 경우, 임차 기간 중
                   임차인이 수선한 부분을 퇴거 시 원상복구 대상으로 볼 것인지에 대해
                   두 조항의 적용 범위가 중첩될 수 있습니다. 수선 이후 목적물의
                   상태 변화가 원상복구 의무의 기준이 되는지를 함께 확인합니다."
    clause_revision:
      target: '"모든 수리 및 수선"의 범위가 대규모 수선까지 포함하는지 불명확'
      reason: "건물 주요 구성부분의 대수선·기본 설비 교체 등 대규모 수선과
               소규모 파손 수선이 구분되지 않아, 임대인 수선의무 면제 범위가
               불명확한 상태로 해석 분쟁 가능"
      direction: '임차인 부담 수선의 범위를 "통상 생길 수 있는 소규모 파손"으로
                 한정하고, 건물 주요 구성부분 대수선·기본 설비 교체 등 대규모
                 수선은 임대인 부담임을 별도 명시'

  - clause_id: "특약C 해당 ID"
    clause_text: "계약 갱신 시 임대료 인상률은 당사자 간 협의로 정하며 별도 제한을 두지 않는다."
    related_clauses:
      - clause_id: "특약D 해당 ID"
        clause_text: "임차인은 계약 만료 시 계약갱신을 요구하지 않기로 한다."
        relation: "계약갱신요구권 포기 특약이 함께 존재하는 경우, 임차인이
                   합의갱신 방식으로만 계약을 연장하게 되어 임대료 인상 제한(5%)
                   규정이 적용되지 않을 수 있습니다. 갱신 방식에 따라 임대료
                   결정 방식이 달라지는지를 두 조항을 함께 확인합니다."
    clause_revision:
      target: '"별도 제한을 두지 않는다"는 문구가 법정 증액 상한(5%)을 초과하는
               인상도 유효하다는 의미로 해석될 여지 존재'
      reason: "계약갱신요구권 행사 시에는 주택임대차보호법 제7조 제2항에 따라
               증액 상한이 적용되며, 이를 초과하는 약정 부분은 효력이 없음에도
               현재 문구는 이를 명시하지 않아 당사자 간 해석 충돌 가능"
      direction: '"단, 계약갱신요구권 행사에 따른 갱신의 경우 차임 증액은
                 주택임대차보호법 제7조 제2항에 따른 범위를 초과하지 않는다"는
                 내용을 병기하여 법정 상한 적용 여부를 명확히 구분'

  - clause_id: "특약D 해당 ID"
    clause_text: "임차인은 계약 만료 시 계약갱신을 요구하지 않기로 한다."
    related_clauses:
      - clause_id: "특약C 해당 ID"
        clause_text: "계약 갱신 시 임대료 인상률은 당사자 간 협의로 정하며 별도 제한을 두지 않는다."
        relation: "임대료 인상 관련 특약이 함께 존재하는 경우, 계약갱신요구권을
                   행사하지 못하게 되면 합의갱신 방식으로만 계약이 연장되어
                   임대료 인상 상한(5%) 규정이 적용되지 않을 수 있습니다.
                   갱신 방식에 따라 임대료 결정 구조가 달라지는지를 두 조항을
                   함께 확인합니다."
    clause_revision:
      target: "임차인의 계약갱신요구권을 사전에 포기하는 내용으로,
               법이 임차인에게 보장하는 권리를 배제하는 약정에 해당"
      reason: "주택임대차보호법 제10조(강행규정)에 따라 임차인에게 불리한 약정은
               효력이 없으므로, 현재 문구는 법적으로 유효하지 않은 내용을
               계약서에 포함하는 형태로 당사자 간 혼란 초래 가능"
      direction: '해당 문구를 삭제하거나, "임차인은 임대차기간 만료 6개월 전부터
                 2개월 전까지의 기간에 법이 정한 바에 따라 계약갱신 여부를
                 결정한다"는 내용으로 대체하여 법정 절차에 따르도록 명시' """


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
            "related_clauses": [{"clause_id": None, "clause_text": None, "relation": None}],
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


def call_llm(prompt: str) -> dict | None:
    model = GenerativeModel(
        MODEL_NAME,
        system_instruction=SYSTEM_PROMPT,
    )
    config = GenerationConfig(
        temperature=0.0,
        response_mime_type="application/json",
    )
    response = model.generate_content(prompt, generation_config=config)
    text = response.text.strip()

    # JSON 파싱 (코드블록 제거 후)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def main():
    # ── 파일 로드 ──────────────────────────────────────────────────
    base_dir = Path(__file__).resolve().parent
    project_root = base_dir.parent.parent

    contract = load_json(project_root / "output" / "contract.json")
    law_results = load_json(project_root / "output" / "reranking" / "reranking_law.json")
    prec_results = load_json(project_root / "output" / "reranking" / "reranking_lawcase.json")

    # ── 데이터 분리 ────────────────────────────────────────────────
    property_info = contract["property_info"]
    special_terms = contract["special_terms"]

    common_terms = special_terms[:COMMON_TERMS_COUNT]   # 인덱스 0~5
    target_terms = special_terms[COMMON_TERMS_COUNT:]   # 인덱스 6~

    # ── rrf 결과 인덱싱 ────────────────────────────────────────────
    rrf_index = build_rrf_index(law_results, prec_results)

    # ── 타겟 특약별 LLM 호출 ───────────────────────────────────────
    clause_results = []

    for i, term in enumerate(target_terms):
        rrf_idx = i + 1  # rrf index는 1부터 시작
        clause_label = f"특약{i+1}"

        laws = rrf_index.get(rrf_idx, {}).get("laws", [])
        precs = rrf_index.get(rrf_idx, {}).get("precs", [])

        print(f"[{clause_label}] LLM 호출 중...")

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

        result = call_llm(prompt)
        if result:
            clause_results.append(result)
            print(f"[{clause_label}] 완료")
        else:
            print(f"[{clause_label}] 실패 - null 반환")

    # ── 전체 계약서 체크리스트 생성 ───────────────────────────────
    print("[전체 체크리스트] LLM 호출 중...")
    checklist_prompt = build_checklist_prompt(
        target_terms=target_terms,
        clause_results=clause_results,
        property_info=property_info,
        common_terms=common_terms,
    )
    checklist_result = call_llm(checklist_prompt)
    contract_checklist = checklist_result.get("contract_checklist", []) if checklist_result else []
    print("[전체 체크리스트] 완료")

    # ── 최종 출력 ──────────────────────────────────────────────────
    final_output = {
        "contract_checklist": contract_checklist,
        "clause_results": clause_results,
    }

    output_path = project_root / "output" / "report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)

    print(f"\n완료. 결과 저장: {output_path}")


if __name__ == "__main__":
    main()