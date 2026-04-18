from __future__ import annotations

import json
from pathlib import Path

from retrieval.query_expansion import expand_clause
from retrieval.retrieval_adapter import build_retrieval_payload


CLAUSES = [
    "임차인은 계약기간 중 전입신고 및 확정일자를 받지 않는다.",
    "계약기간 만료 전 퇴실 시 또는 묵시적 갱신으로 인한 퇴실 시, 중개보수료, 월세, 관리비는 임차인이 부담한다.",
    "임대인이 실거주 목적으로 계약을 해지하는 경우, 계약 만기 4개월 전까지 이를 통지한다.",
    "대출이 불승인되더라도 계약금은 반환하지 않는다.",
    "임차목적물에 발생하는 모든 수리비는 원인과 관계없이 임차인이 부담한다.",
]


def main() -> None:
    output_dir = Path("outputs/query_expansion_samples")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for idx, clause in enumerate(CLAUSES, start=1):
        expansion = expand_clause(clause, max_retries=1)
        payload = build_retrieval_payload(expansion)

        result = {
            "index": idx,
            "clause": clause,
            "expansion": expansion.model_dump(mode="json"),
            "retrieval_payload": payload,
        }
        results.append(result)

        with open(output_dir / f"sample_{idx}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    with open(output_dir / "all_samples.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"saved to {output_dir}")


if __name__ == "__main__":
    main()