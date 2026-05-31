"""
run_single_eval.py

qa_structured_1754 단건 평가 파이프라인:
  Step 1: 계약서 special_terms → eval_set 포맷 변환
  Step 2: legal_retrieval_eval_multi 검색 실행
  Step 3: report_generator_v2 보고서 생성
  Step 4: LLM-as-a-judge 평가

사용법:
  python evaluation/run_single_eval.py
  python evaluation/run_single_eval.py --skip-retrieval <retrieval_result.json>
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

load_dotenv()

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(__file__).resolve().parents[1]
EVAL_DIR       = PROJECT_ROOT / "evaluation"
RESULTS_DIR    = EVAL_DIR / "results"
CONTRACT_FILE  = Path(r"C:\Users\윤예정\Downloads\특약_통합_계약서\qa_structured_1754.json")
CONTRACT_ID    = CONTRACT_FILE.stem          # qa_structured_1754
REPORTS_DIR    = CONTRACT_FILE.parent / "reports"

COMMON_TERMS_COUNT = 6
GEN_MODEL          = "gemini-2.5-pro"

# ── Vertex AI 초기화 ──────────────────────────────────────────────────────────
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION   = os.getenv("GCP_LOCATION", "us-central1")
vertexai.init(project=PROJECT_ID, location=LOCATION)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: eval_set 포맷 변환
# ─────────────────────────────────────────────────────────────────────────────
_ENDINGS = [
    ("하여야 한다", "해야함"), ("하여야한다", "해야함"),
    ("하여야 함",   "해야함"), ("하여야함",   "해야함"),
    ("하였다", "함"), ("했다", "함"),
    ("한다",   "함"), ("됩니다", "됨"), ("된다",  "됨"),
    ("입니다", "임"), ("이다",   "임"),
    ("있다",   "있음"), ("없다", "없음"),
    ("한다고", "함"), ("하다", "함"),
]

def _normalize(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    for src, dst in _ENDINGS:
        if t.endswith(src):
            t = t[: -len(src)] + dst
            break
    return t


def step1_build_eval_input() -> Path:
    """계약서 special_terms[6:]를 eval_set.json 포맷으로 변환."""
    out_path = EVAL_DIR / f"eval_input_{CONTRACT_ID}.json"
    if out_path.exists():
        print(f"[Step 1] 이미 존재 → {out_path}")
        return out_path

    data = json.loads(CONTRACT_FILE.read_text(encoding="utf-8-sig"))
    special_terms = data.get("special_terms", [])
    target_terms  = special_terms[COMMON_TERMS_COUNT:]

    record = {
        "id": CONTRACT_ID,
        "source_type": "qa",
        "source_id": int(re.search(r"(\d+)", CONTRACT_ID).group(1)),
        "source_text": {},
        "clauses": [
            {
                "raw": t,
                "normalized": _normalize(t),
                "clause_type": "explicit_quote",
            }
            for t in target_terms
            if isinstance(t, str) and t.strip()
        ],
        "gt_laws":  [],
        "gt_cases": [],
        "meta": {"contract_file": CONTRACT_FILE.name},
    }

    out_path.write_text(
        json.dumps([record], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[Step 1] eval input 생성 완료 ({len(record['clauses'])}개 clause) → {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: 검색 실행
# ─────────────────────────────────────────────────────────────────────────────
def step2_run_retrieval(eval_input: Path) -> Path:
    """legal_retrieval_eval_multi.py 실행 후 결과 파일 반환."""
    output_name = f"retrieval_{CONTRACT_ID}.json"
    output_path = RESULTS_DIR / output_name

    if output_path.exists():
        print(f"[Step 2] 이미 존재 → {output_path}")
        return output_path

    cmd = [
        sys.executable,
        str(EVAL_DIR / "legal_retrieval_eval_multi.py"),
        "--input",       str(eval_input),
        "--output",      output_name,
        "--case-id",     CONTRACT_ID,
        "--case-workers", "1",
    ]
    print(f"[Step 2] 검색 실행: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)
    print(f"[Step 2] 검색 완료 → {output_path}")
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: 보고서 생성
# ─────────────────────────────────────────────────────────────────────────────
def step3_generate_report(retrieval_path: Path) -> Path:
    """report_generator_v2.py 실행 후 보고서 파일 반환."""
    report_path = REPORTS_DIR / f"{CONTRACT_ID}_report.json"

    if report_path.exists():
        print(f"[Step 3] 이미 존재 → {report_path}")
        return report_path

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "pipeline" / "generation" / "report_generator_v2.py"),
        "--prefix",    CONTRACT_ID,
        "--retrieval", str(retrieval_path),
        "--output",    str(REPORTS_DIR),
    ]
    print(f"[Step 3] 보고서 생성: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)
    print(f"[Step 3] 보고서 완료 → {report_path}")
    return report_path


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: LLM-as-a-judge
# ─────────────────────────────────────────────────────────────────────────────
JUDGE_COHERENCE_PROMPT = """\
[Task Introduction]
당신은 주택임대차 계약 분석 시스템이 생성한 특약 간 관계 분석을
평가하는 전문가입니다. 아래 두 특약과 생성된 관계 설명을 바탕으로
품질을 평가하세요.

[분석 대상 특약]
{clause_text}

[연관 특약]
{related_clause_text}

[생성된 관계 설명 (relation)]
{relation}

[Evaluation Criteria]
Coherence (1-5): 생성된 관계 설명이 두 특약의 원문에 있는
구체적인 표현을 근거로 논리적으로 도출되었는가.
두 특약이 동시에 적용될 때 발생하는 확인 필요 사항이
문장에서 문장으로 자연스럽게 이어지는 일관된 서술로
구성되었는가. 근거 없이 결론만 제시하거나 두 특약 내용과
무관한 설명이 포함되지 않을수록 높은 점수.

[Evaluation Steps]

JSON 형식으로만 응답:
{{
  "coherence": {{"score": int, "reason": str}}
}}"""

JUDGE_CHECKLIST_PROMPT = """\
[Task Introduction]
당신은 주택임대차 계약 분석 시스템이 생성한 계약 전 체크리스트를
평가하는 전문가입니다. 아래 입력 정보를 바탕으로 체크리스트의 품질을
평가하세요.

[입력 특약 목록]
{target_terms}

[특약별 분석 결과 (basis 근거)]
{clause_results}

[평가 대상 체크리스트]
{contract_checklist}

[Evaluation Criteria]
Correctness (1-5): 각 항목(item)이 입력된 특약 내용 또는
주택임대차보호법 핵심 사항에 실제로 근거하고 있으며, basis 필드에
명시된 법령·특약과 description 내용이 일치하는가.
특약과 무관하거나 근거 없이 생성된 항목이 없어야 높은 점수.

Actionability (1-5): 각 항목의 description이 임차인이 계약 전
직접 수행 가능한 구체적 행동으로 서술되었는가.
"전문가 상담 권장" 같은 위임형 표현이나 평가적 표현 없이
임차인이 스스로 취할 수 있는 행동이 명시될수록 높은 점수.

[Evaluation Steps]

JSON 형식으로만 응답:
{{
  "correctness": {{"score": int, "reason": str}},
  "actionability": {{"score": int, "reason": str}}
}}"""


def _call_judge(prompt: str) -> dict:
    model    = GenerativeModel(GEN_MODEL)
    config   = GenerationConfig(temperature=0.0, response_mime_type="application/json")
    response = model.generate_content(prompt, generation_config=config)
    text     = re.sub(r"^```(?:json)?\s*", "", response.text.strip())
    text     = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def step4_llm_judge(report_path: Path, contract_path: Path) -> Path:
    """보고서를 읽어 LLM-as-a-judge 평가 실행."""
    judge_path = report_path.parent / f"{CONTRACT_ID}_judge.json"

    report   = json.loads(report_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))

    special_terms = contract.get("special_terms", [])
    target_terms  = special_terms[COMMON_TERMS_COUNT:]

    clause_results    = report.get("clause_results", [])
    contract_checklist = report.get("contract_checklist", [])

    judge_output = {
        "contract_id":        CONTRACT_ID,
        "coherence_results":  [],
        "checklist_result":   None,
    }

    # ── Coherence: clause pair 단위 ─────────────────────────────────────────
    print("[Step 4] Coherence 평가 시작")
    for cr in clause_results:
        clause_text = cr.get("clause_text") or ""
        for rc in (cr.get("related_clauses") or []):
            related_text = rc.get("clause_text") or ""
            relation     = rc.get("relation") or ""
            if not (clause_text and related_text and relation):
                continue

            prompt = JUDGE_COHERENCE_PROMPT.format(
                clause_text=clause_text,
                related_clause_text=related_text,
                relation=relation,
            )
            result = _call_judge(prompt)
            score  = result.get("coherence", {}).get("score", "?")
            print(f"  [{cr.get('clause_id','?')} → {rc.get('clause_id','?')}] coherence={score}")
            judge_output["coherence_results"].append({
                "clause_id":         cr.get("clause_id"),
                "clause_text":       clause_text,
                "related_clause_id": rc.get("clause_id"),
                "related_clause_text": related_text,
                "relation":          relation,
                "judge":             result,
            })

    # ── Correctness + Actionability: 체크리스트 전체 ──────────────────────
    print("[Step 4] Checklist 평가 시작")
    if contract_checklist:
        prompt = JUDGE_CHECKLIST_PROMPT.format(
            target_terms="\n".join(f"{i+1}. {t}" for i, t in enumerate(target_terms)),
            clause_results=json.dumps(clause_results, ensure_ascii=False, indent=2),
            contract_checklist=json.dumps(contract_checklist, ensure_ascii=False, indent=2),
        )
        result = _call_judge(prompt)
        corr = result.get("correctness", {}).get("score", "?")
        actn = result.get("actionability", {}).get("score", "?")
        print(f"  correctness={corr}, actionability={actn}")
        judge_output["checklist_result"] = result
    else:
        print("  체크리스트 없음 — 건너뜀")

    judge_path.write_text(
        json.dumps(judge_output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[Step 4] 평가 완료 → {judge_path}")
    return judge_path


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="qa_structured_1754 단건 평가 파이프라인")
    parser.add_argument(
        "--skip-retrieval",
        metavar="RETRIEVAL_JSON",
        default=None,
        help="기존 retrieval 결과 파일 경로. 지정 시 Step 2 건너뜀.",
    )
    parser.add_argument(
        "--skip-report",
        metavar="REPORT_JSON",
        default=None,
        help="기존 보고서 파일 경로. 지정 시 Step 3 건너뜀.",
    )
    parser.add_argument(
        "--judge-only",
        action="store_true",
        help="Step 4(LLM judge)만 실행. --skip-report 필수.",
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  단건 평가 파이프라인: {CONTRACT_ID}")
    print(f"{'='*60}\n")

    # Step 1
    eval_input = step1_build_eval_input()

    # Step 2
    if args.skip_retrieval:
        retrieval_path = Path(args.skip_retrieval)
        print(f"[Step 2] skip → {retrieval_path}")
    elif args.judge_only:
        retrieval_path = None
        print("[Step 2] skip (judge-only)")
    else:
        retrieval_path = step2_run_retrieval(eval_input)

    # Step 3
    if args.skip_report:
        report_path = Path(args.skip_report)
        print(f"[Step 3] skip → {report_path}")
    elif args.judge_only:
        if not args.skip_report:
            parser.error("--judge-only 사용 시 --skip-report 필요")
        report_path = Path(args.skip_report)
    else:
        report_path = step3_generate_report(retrieval_path)

    # Step 4
    judge_path = step4_llm_judge(report_path, CONTRACT_FILE)

    print(f"\n{'='*60}")
    print(f"  완료")
    print(f"  보고서:  {report_path}")
    print(f"  평가:    {judge_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
