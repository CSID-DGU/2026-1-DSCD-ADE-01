import json

from data.processors.lawtalk_qa_processor import (
    extract_law_references,
    extract_precedent_numbers,
    extract_special_clauses,
    process_record,
    run,
)


def test_extract_special_clauses_only_special_sentences():
    text = (
        "안녕하세요. 임대차 문의입니다.\n"
        "계약서 특약사항에 월세 5% 인상 조항이 있습니다. "
        "이 내용이 유효한가요?"
    )

    result = extract_special_clauses(text)

    assert result == ["계약서 특약사항에 월세 5% 인상 조항이 있습니다."]


def test_extract_law_references_with_article():
    text = "주택임대차보호법 제6조의3에 따르면 임차인은 보호됩니다."

    result = extract_law_references(text)

    assert result == ["주택임대차보호법 제6조의3"]


def test_extract_law_references_normalizes_missing_je_and_space():
    text = "주택임대차보호법 6조의 3에 따른 권리입니다."

    result = extract_law_references(text)

    assert result == ["주택임대차보호법 제6조의3"]


def test_extract_law_references_same_law():
    text = "주택임대차보호법 제10조를 먼저 봅니다. 동법 제6조의3도 참고합니다."

    result = extract_law_references(text)

    assert result == ["주택임대차보호법 제10조", "주택임대차보호법 제6조의3"]


def test_extract_law_references_ignores_same_law_without_context():
    text = "동법 제15조에 따르면 효력이 없습니다."

    result = extract_law_references(text)

    assert result == []


def test_extract_law_references_excludes_commercial_law():
    text = "상가건물 임대차보호법 제11조에 따르면 제한됩니다."

    result = extract_law_references(text)

    assert result == []


def test_extract_precedent_numbers_broad_korean_case_numbers():
    text = "대법원 2012다28486, 서울중앙지방법원 2001가합12345, 헌재 2018헌바123"

    result = extract_precedent_numbers(text)

    assert result == ["2012다28486", "2001가합12345", "2018헌바123"]


def test_process_record_both_law_and_precedent():
    record = {
        "index": 1,
        "question_body": "계약서 특약사항에 월세 인상 조항이 있습니다.",
        "all_answers": [
            {
                "answer": "주택임대차보호법 제6조의3에 따릅니다. 대법원 2012다28486 판결 참고."
            }
        ],
    }

    result = process_record(record)

    assert result == {
        "index": 1,
        "special_clauses": ["계약서 특약사항에 월세 인상 조항이 있습니다."],
        "law_references": ["주택임대차보호법 제6조의3"],
        "precedent_numbers": ["2012다28486"],
    }


def test_process_record_without_special_clause_is_excluded():
    record = {
        "index": 1,
        "question_body": "월세 인상 문의입니다.",
        "all_answers": [{"answer": "민법 제623조에 따릅니다."}],
    }

    result = process_record(record)

    assert result is None


def test_run_writes_three_output_files(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    records = [
        {
            "index": 1,
            "question_body": "특약사항에 월세 인상 조항이 있습니다.",
            "all_answers": [
                {"answer": "민법 제623조에 따릅니다. 대법원 2012다28486 판결 참고."}
            ],
        },
        {
            "index": 2,
            "question_body": "특약 조항 해석이 궁금합니다.",
            "all_answers": [{"answer": "주택임대차보호법 제10조에 따릅니다."}],
        },
        {
            "index": 3,
            "question_body": "특약에 관한 판례가 있나요?",
            "all_answers": [{"answer": "서울고등법원 2023나201654 판결을 참고하세요."}],
        },
        {
            "index": 4,
            "question_body": "특약 관련 문의입니다.",
            "all_answers": [{"answer": "상담 예약을 권합니다."}],
        },
    ]

    with open(input_dir / "sample.json", "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False)

    stats = run(input_dir, output_dir)

    with open(output_dir / "qa_both.json", "r", encoding="utf-8") as file:
        both = json.load(file)

    with open(output_dir / "qa_law_only.json", "r", encoding="utf-8") as file:
        law_only = json.load(file)

    with open(output_dir / "qa_precedent_only.json", "r", encoding="utf-8") as file:
        precedent_only = json.load(file)

    assert stats["total_records"] == 4
    assert stats["both_count"] == 1
    assert stats["law_only_count"] == 1
    assert stats["precedent_only_count"] == 1
    assert both[0]["index"] == 1
    assert law_only[0]["index"] == 2
    assert precedent_only[0]["index"] == 3
