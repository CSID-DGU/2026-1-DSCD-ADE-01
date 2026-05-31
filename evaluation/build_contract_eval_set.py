"""
특약_통합_계약서 폴더의 계약서 JSON에서 special_terms[6:]를 추출하여
legal_retrieval_eval_multi.py 입력 포맷(eval_set.json)으로 변환.

출력: evaluation/contract_eval_set.json
사용: python evaluation/legal_retrieval_eval_multi.py --input evaluation/contract_eval_set.json
"""

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(__file__).resolve().parents[1]
CONTRACTS_DIR  = Path(r"C:\Users\윤예정\Downloads\특약_통합_계약서")
OUTPUT_PATH    = PROJECT_ROOT / "evaluation" / "contract_eval_set.json"
COMMON_TERMS_COUNT = 6  # 앞 6개는 표준 고지사항 → 제외

# ── 정규화 함수 ───────────────────────────────────────────────────────────────
ENDINGS = [
    ("하여야 한다", "해야함"), ("하여야한다", "해야함"),
    ("하여야 함",   "해야함"), ("하여야함",   "해야함"),
    ("하였다", "함"), ("했다", "함"),
    ("한다",   "함"), ("됩니다", "됨"), ("된다",  "됨"),
    ("입니다", "임"), ("이다",   "임"),
    ("있다",   "있음"), ("없다", "없음"),
    ("한다고", "함"), ("하다", "함"),
]

def normalize_clause(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    for src, dst in ENDINGS:
        if t.endswith(src):
            t = t[: -len(src)] + dst
            break
    return t


# ── 계약서 로드 & 변환 ────────────────────────────────────────────────────────
records = []
contract_files = sorted(CONTRACTS_DIR.glob("*.json"))

print(f"계약서 파일 수: {len(contract_files)}")

skipped = 0
for path in contract_files:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"  [오류] {path.name}: {e}")
        skipped += 1
        continue

    special_terms = data.get("special_terms", [])
    target_terms  = special_terms[COMMON_TERMS_COUNT:]

    if not target_terms:
        print(f"  [스킵] {path.name}: target_terms 없음")
        skipped += 1
        continue

    # source_type 및 source_id 결정
    stem = path.stem  # e.g. "qa_structured_1027" or "caselense_structured_contract_1"
    if stem.startswith("qa_"):
        source_type = "qa"
        try:
            source_id = int(stem.rsplit("_", 1)[-1])
        except ValueError:
            source_id = stem
    elif stem.startswith("caselense_"):
        source_type = "caselense"
        try:
            source_id = int(stem.rsplit("_", 1)[-1])
        except ValueError:
            source_id = stem
    else:
        source_type = "contract"
        source_id = stem

    record = {
        "id": stem,
        "source_type": source_type,
        "source_id": source_id,
        "source_text": {},
        "clauses": [
            {
                "raw": t,
                "normalized": normalize_clause(t),
                "clause_type": "explicit_quote",
            }
            for t in target_terms
            if isinstance(t, str) and t.strip()
        ],
        "gt_laws":  [],
        "gt_cases": [],
        "meta": {
            "contract_file": path.name,
            "total_special_terms": len(special_terms),
            "target_terms_count": len(target_terms),
        },
    }

    # clauses가 비어있으면 스킵
    if not record["clauses"]:
        print(f"  [스킵] {path.name}: 유효한 clause 없음")
        skipped += 1
        continue

    records.append(record)

print(f"\n변환 완료: {len(records)}개 계약서, {skipped}개 스킵")
print(f"총 clause 수: {sum(len(r['clauses']) for r in records)}")

OUTPUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n저장 완료: {OUTPUT_PATH}")
