"""데이터 전처리 실행 스크립트."""

import os
import sys


# 프로젝트 루트를 import 경로에 추가한다.
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, PROJECT_ROOT)


def run_lawtalk_qa(args):
    """로톡 QA 전처리를 실행한다."""
    from data.processors.lawtalk_qa_processor import run

    input_dir = "data/lawtalk_qa"
    output_dir = "data/lawtalk_qa_filtered"

    if len(args) >= 1:
        input_dir = args[0]

    if len(args) >= 2:
        output_dir = args[1]

    print(f"[lawtalk_qa] 입력: {input_dir}")
    print(f"[lawtalk_qa] 출력: {output_dir}")

    stats = run(input_dir, output_dir)

    print("\n=== 결과 요약 ===")
    print(f"전체 레코드: {stats['total_records']}건")
    print(f"법령 + 판례: {stats['both_count']}건")
    print(f"법령만:      {stats['law_only_count']}건")
    print(f"판례만:      {stats['precedent_only_count']}건")


PROCESSORS = {
    "lawtalk_qa": run_lawtalk_qa,
}


def main():
    """명령줄 인자를 읽어서 알맞은 전처리를 실행한다."""
    if len(sys.argv) < 2:
        print("사용법: python scripts/run_processor.py <processor_name> [args...]")
        print("사용 가능한 전처리: " + ", ".join(PROCESSORS.keys()))
        sys.exit(1)

    processor_name = sys.argv[1]

    if processor_name not in PROCESSORS:
        print(f"오류: '{processor_name}'은 지원하지 않는 전처리입니다.")
        print("사용 가능한 전처리: " + ", ".join(PROCESSORS.keys()))
        sys.exit(1)

    PROCESSORS[processor_name](sys.argv[2:])


if __name__ == "__main__":
    main()
