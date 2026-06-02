"""
test_rag_*.json → report_generator → judge_eval 전체 파이프라인 실행

사용법:
    # 단일 파일
    python evaluation/run_judge_test.py --rag-result data/test_rag_104.json
    # 폴더 전체
    python evaluation/run_judge_test.py --rag-result data/
    # 출력 폴더 지정
    python evaluation/run_judge_test.py --rag-result data/ --output-dir results/
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── 1단계: report_generator 실행 ─────────────────────────────────
def run_report_generator(rag_result: str, output_dir: str | None = None) -> list[Path]:
    cmd = [
        sys.executable,
        str(ROOT / "pipeline" / "generation" / "report_generator.py"),
        "--rag-result", rag_result,
    ]
    if output_dir:
        cmd += ["--output", output_dir]

    print(f"\n[step 1] report_generator.py 실행 중... ({rag_result})")
    result = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8"
    )
    print(result.stdout)
    if result.returncode != 0:
        print("[ERROR] report_generator 실패:")
        print(result.stderr)
        sys.exit(1)

    # 생성된 *_report.json 경로 추론
    rag_path = Path(rag_result)
    base_dir = Path(output_dir) if output_dir else rag_path if rag_path.is_dir() else rag_path.parent
    return sorted(base_dir.glob("*_report.json"))


# ── 2단계: judge_eval 실행 ────────────────────────────────────────
def run_judge_eval(report_path: Path, output_dir: str | None = None) -> Path:
    judge_stem = (
        report_path.stem.replace("_report", "_judge")
        if "_report" in report_path.stem
        else f"{report_path.stem}_judge"
    )
    out_dir  = Path(output_dir) if output_dir else report_path.parent
    out_path = out_dir / f"{judge_stem}.json"

    cmd = [
        sys.executable,
        str(ROOT / "evaluation" / "judge_eval.py"),
        "--report", str(report_path),
        "--output", str(out_path),
    ]

    print(f"\n[step 2] judge_eval.py 실행 중... ({report_path.name})")
    result = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8"
    )
    print(result.stdout)
    if result.returncode != 0:
        print("[ERROR] judge_eval 실패:")
        print(result.stderr)
        sys.exit(1)

    return out_path


# ── 결과 출력 ─────────────────────────────────────────────────────
def print_results(judge_path: Path) -> None:
    with open(judge_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    coherence_score    = result.get("coherence_score")
    consistency        = result.get("consistency_result") or {}
    consistency_score  = consistency.get("score")

    print("\n" + "=" * 50)
    print(f"  {judge_path.name}")
    print(f"  Coherence  : {coherence_score if coherence_score is not None else 'N/A'} / 5")
    print(f"  Consistency: {consistency_score if consistency_score is not None else 'N/A'} / 5")
    print("=" * 50)

    if consistency.get("reason"):
        print(f"\nConsistency 이유: {consistency['reason']}")

    for rel in result.get("coherence_results", []):
        print(f"\n[{rel.get('clause_id')} ↔ {rel.get('related_clause_id')}]")
        print(f"  Coherence {rel.get('score')}: {rel.get('reason')}")


# ── 메인 ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="test_rag → report_generator → judge_eval 전체 파이프라인"
    )
    parser.add_argument(
        "--rag-result",
        required=True,
        help="test_rag_*.json 파일 경로 또는 폴더",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="report/judge 파일 저장 폴더. 미지정 시 입력 파일과 같은 폴더",
    )
    args = parser.parse_args()

    # step 1: report 생성
    report_paths = run_report_generator(args.rag_result, args.output_dir)
    if not report_paths:
        print("[경고] 생성된 report 파일을 찾을 수 없습니다.")
        sys.exit(1)

    # step 2: 각 report에 대해 judge 실행 및 결과 출력
    for report_path in report_paths:
        if not report_path.exists():
            print(f"[경고] report 파일 없음: {report_path}")
            continue
        judge_path = run_judge_eval(report_path, args.output_dir)
        print_results(judge_path)


if __name__ == "__main__":
    main()
