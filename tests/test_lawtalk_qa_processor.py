import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import scripts.run_processor as run_processor
from data.processors.lawtalk_qa_processor import (
    ExtractedClausesResult,
    LawtalkAnswerAnalysis,
    analyze_answer_for_db_with_llm,
    build_answer_analysis_prompt,
    build_clause_postprocess_prompt,
    extract_clauses_from_special_clauses_with_llm,
    extract_law_references,
    extract_precedent_numbers,
    extract_special_clauses,
    load_rule_based_filtered_records,
    process_record,
    prepare_db_ready_records,
    process_rule_based_filtered_clauses,
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


def test_extracted_clauses_result_schema_accepts_clause_list():
    result = ExtractedClausesResult(
        extracted_clauses=["임차인은 원상복구 비용을 부담한다."]
    )

    assert result.extracted_clauses == ["임차인은 원상복구 비용을 부담한다."]
    description = ExtractedClausesResult.model_fields["extracted_clauses"].description
    assert "실제 계약서에 존재할 만한 특약" in description


def test_build_clause_postprocess_prompt_uses_special_clauses_only():
    special_clauses = [
        "계약서 특약사항에 원상복구는 임차인이 부담한다고 적혀 있습니다.",
        "이 특약이 민법보다 우선하나요?",
    ]

    prompt = build_clause_postprocess_prompt(special_clauses)

    assert "special_clauses" in prompt
    assert "원상복구는 임차인이 부담" in prompt
    assert "질문 본문" not in prompt
    assert "실제 계약서에 존재할 만한 특약" in prompt
    assert "extracted_clauses" in prompt


def test_extract_clauses_from_special_clauses_with_llm_uses_gemini_schema():
    special_clauses = [
        "계약서 특약사항에 원상복구는 임차인이 부담한다고 적혀 있습니다.",
        "이 특약이 민법보다 우선하나요?",
    ]
    parsed = ExtractedClausesResult(
        extracted_clauses=["원상복구는 임차인이 부담한다."]
    )
    mock_gemini_client = Mock()
    mock_gemini_client.generate.return_value = parsed

    with patch.dict(
        "sys.modules",
        {
            "shared.llm.gemini_client": SimpleNamespace(
                gemini_client=mock_gemini_client
            )
        },
    ):
        result = extract_clauses_from_special_clauses_with_llm(special_clauses)

    assert result == ["원상복구는 임차인이 부담한다."]
    args, kwargs = mock_gemini_client.generate.call_args
    assert kwargs["response_schema"] is ExtractedClausesResult
    assert "special_clauses" in args[0]
    assert "원상복구는 임차인이 부담" in args[0]


def test_build_answer_analysis_prompt_uses_only_db_schema_fields():
    question_record = {
        "index": 1,
        "question_title": "임대차 분쟁",
        "question_body": "임대인이 보증금을 돌려주지 않습니다.",
    }
    answer_item = {
        "lawyer": "홍길동 변호사",
        "answer": "보증금 반환 청구를 검토해야 합니다.",
    }

    prompt = build_answer_analysis_prompt(question_record, answer_item)

    assert "dispute_background" in prompt
    assert "lawyer_conclusion" in prompt
    assert "lawyer_reasoning" in prompt
    assert "action_checklist" in prompt
    assert "questioner_questions" not in prompt
    assert "special_clauses" not in prompt
    assert "legal_references" not in prompt
    assert "임대인이 보증금을 돌려주지 않습니다." in prompt
    assert "보증금 반환 청구를 검토해야 합니다." in prompt


def test_analyze_answer_for_db_with_llm_uses_gemini_schema():
    question_record = {
        "index": 1,
        "question_title": "임대차 분쟁",
        "question_body": "임대인이 보증금을 돌려주지 않습니다.",
    }
    answer_item = {
        "lawyer": "홍길동 변호사",
        "answer": "보증금 반환 청구를 검토해야 합니다.",
    }
    parsed = LawtalkAnswerAnalysis(
        dispute_background="임차인이 보증금 반환 문제를 겪고 있습니다.",
        lawyer_conclusion="보증금 반환 청구를 검토할 수 있습니다.",
        lawyer_reasoning="- 임대차 종료 후 반환 의무가 문제됩니다.",
        action_checklist="- 계약서와 반환 요청 증거를 정리합니다.",
    )
    mock_gemini_client = Mock()
    mock_gemini_client.generate.return_value = parsed

    with patch.dict(
        "sys.modules",
        {
            "shared.llm.gemini_client": SimpleNamespace(
                gemini_client=mock_gemini_client
            )
        },
    ):
        result = analyze_answer_for_db_with_llm(question_record, answer_item)

    assert result == parsed
    args, kwargs = mock_gemini_client.generate.call_args
    assert kwargs["response_schema"] is LawtalkAnswerAnalysis
    assert "system_instruction" in kwargs
    assert "임대인이 보증금을 돌려주지 않습니다." in args[0]


def test_prepare_db_ready_records_writes_questions_and_answers_after_each_answer(
    tmp_path,
):
    input_file = tmp_path / "lawtalk_QA_Context.json"
    output_file = tmp_path / "lawtalk_qa_db_ready.json"
    records = [
        {
            "index": 7,
            "question_title": "임대차 질문",
            "question_body": "임차인입니다. 보증금 반환이 지연됩니다.",
            "tags": ["#임대차"],
            "question_written_at_raw": "2026-01-01T00:00:00.000Z",
            "all_answers": [
                {
                    "lawyer": "홍길동 변호사",
                    "answer": "내용증명을 보내고 반환 청구를 검토하세요.",
                    "written_at_raw": "2026-01-02T00:00:00.000Z",
                    "is_ad": False,
                },
                {
                    "lawyer": "김길동 변호사",
                    "answer": "임차권등기명령도 검토할 수 있습니다.",
                    "written_at_raw": "2년 전 작성됨",
                    "is_ad": False,
                },
            ],
        }
    ]
    with open(input_file, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False)

    def fake_analyzer(question_record, answer_item):
        if answer_item["lawyer"] == "김길동 변호사":
            with open(output_file, "r", encoding="utf-8") as file:
                saved = json.load(file)
            assert len(saved["answers"]) == 1
            assert saved["answers"][0]["lawyer_name"] == "홍길동 변호사"
        return LawtalkAnswerAnalysis(
            dispute_background="임차인이 보증금 반환 지연을 겪고 있습니다.",
            lawyer_conclusion="반환 청구를 검토할 수 있습니다.",
            lawyer_reasoning="- 임대차 종료 후 반환 의무가 문제됩니다.",
            action_checklist="- 증거를 정리합니다.",
        )

    stats = prepare_db_ready_records(
        input_file,
        output_file=output_file,
        answer_analyzer=fake_analyzer,
    )

    with open(output_file, "r", encoding="utf-8") as file:
        processed = json.load(file)

    assert stats == {
        "total_questions": 1,
        "total_answers": 2,
        "processed_count": 2,
        "skipped_count": 0,
        "failed_count": 0,
    }
    assert processed["questions"] == [
        {
            "id": 7,
            "title": "임대차 질문",
            "body": "임차인입니다. 보증금 반환이 지연됩니다.",
            "tags": ["#임대차"],
            "written_at": "2026-01-01T00:00:00.000Z",
            "embedding": None,
        }
    ]
    assert processed["answers"][0]["id"] == 1
    assert processed["answers"][0]["question_id"] == 7
    assert processed["answers"][0]["answer_body"] == records[0]["all_answers"][0]
    assert processed["answers"][1]["written_at"] == "2년 전 작성됨"


def test_prepare_db_ready_records_skips_existing_answers_and_respects_limit(tmp_path):
    input_file = tmp_path / "lawtalk_QA_Context.json"
    output_file = tmp_path / "lawtalk_qa_db_ready.json"
    records = [
        {
            "index": 3,
            "question_title": "질문",
            "question_body": "본문",
            "tags": [],
            "question_written_at_raw": "작성일 텍스트",
            "all_answers": [
                {"lawyer": "A", "answer": "답변 A", "written_at_raw": "A일"},
                {"lawyer": "B", "answer": "답변 B", "written_at_raw": "B일"},
                {"lawyer": "C", "answer": "답변 C", "written_at_raw": "C일"},
            ],
        }
    ]
    with open(input_file, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False)
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(
            {
                "questions": [],
                "answers": [
                    {
                        "id": 1,
                        "question_id": 3,
                        "lawyer_name": "A",
                        "answer_body": records[0]["all_answers"][0],
                        "written_at": "A일",
                        "dispute_background": "기존",
                        "lawyer_conclusion": "기존",
                        "lawyer_reasoning": "기존",
                        "action_checklist": "기존",
                    }
                ],
            },
            file,
            ensure_ascii=False,
        )

    calls = []

    def fake_analyzer(question_record, answer_item):
        calls.append(answer_item["lawyer"])
        return LawtalkAnswerAnalysis(
            dispute_background="배경",
            lawyer_conclusion="결론",
            lawyer_reasoning="근거",
            action_checklist="행동",
        )

    stats = prepare_db_ready_records(
        input_file,
        output_file=output_file,
        answer_analyzer=fake_analyzer,
        limit=1,
    )

    with open(output_file, "r", encoding="utf-8") as file:
        processed = json.load(file)

    assert calls == ["B"]
    assert stats["processed_count"] == 1
    assert stats["skipped_count"] == 1
    assert [answer["id"] for answer in processed["answers"]] == [1, 2]


def test_prepare_db_ready_records_uses_default_output_when_output_file_is_none(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    input_dir = tmp_path / "data" / "raw"
    input_dir.mkdir(parents=True)
    input_file = input_dir / "lawtalk_QA_Context.json"
    with open(input_file, "w", encoding="utf-8") as file:
        json.dump(
            [
                {
                    "index": 1,
                    "question_title": "질문",
                    "question_body": "본문",
                    "tags": [],
                    "question_written_at_raw": "작성일",
                    "all_answers": [
                        {
                            "lawyer": "A",
                            "answer": "답변",
                            "written_at_raw": "답변일",
                        }
                    ],
                }
            ],
            file,
            ensure_ascii=False,
        )

    stats = prepare_db_ready_records(
        input_file,
        output_file=None,
        answer_analyzer=lambda question_record, answer_item: LawtalkAnswerAnalysis(
            dispute_background="배경",
            lawyer_conclusion="결론",
            lawyer_reasoning="근거",
            action_checklist="행동",
        ),
    )

    output_file = tmp_path / "data" / "lawtalk_qa_preprocessed" / "lawtalk_qa_db_ready.json"
    assert stats["processed_count"] == 1
    assert output_file.exists()


def test_load_rule_based_filtered_records_merges_three_files_with_source_metadata(
    tmp_path,
):
    input_dir = tmp_path / "lawtalk_qa_filtered"
    input_dir.mkdir()

    with open(input_dir / "qa_both.json", "w", encoding="utf-8") as file:
        json.dump(
            [
                {
                    "index": 1,
                    "special_clauses": ["특약 A"],
                    "law_references": ["민법 제103조"],
                    "precedent_numbers": ["2012다28486"],
                }
            ],
            file,
            ensure_ascii=False,
        )
    with open(input_dir / "qa_law_only.json", "w", encoding="utf-8") as file:
        json.dump(
            [
                {
                    "index": 1,
                    "special_clauses": ["특약 B"],
                    "law_references": ["민법 제623조"],
                    "precedent_numbers": [],
                }
            ],
            file,
            ensure_ascii=False,
        )
    with open(input_dir / "qa_precedent_only.json", "w", encoding="utf-8") as file:
        json.dump(
            [
                {
                    "index": 1,
                    "special_clauses": ["특약 C"],
                    "law_references": [],
                    "precedent_numbers": ["2020가단123"],
                }
            ],
            file,
            ensure_ascii=False,
        )

    records = load_rule_based_filtered_records(input_dir)

    assert [record["source_file"] for record in records] == [
        "qa_both.json",
        "qa_law_only.json",
        "qa_precedent_only.json",
    ]
    assert [record["source_position"] for record in records] == [1, 1, 1]
    assert records[0]["special_clauses"] == ["특약 A"]
    assert records[1]["special_clauses"] == ["특약 B"]
    assert records[2]["special_clauses"] == ["특약 C"]


def test_process_rule_based_filtered_clauses_writes_after_each_record(tmp_path):
    input_dir = tmp_path / "lawtalk_qa_filtered"
    output_file = input_dir / "qa_clauses_processed.json"
    input_dir.mkdir()

    with open(input_dir / "qa_both.json", "w", encoding="utf-8") as file:
        json.dump(
            [
                {
                    "index": 1,
                    "special_clauses": ["특약 A"],
                    "law_references": ["민법 제103조"],
                    "precedent_numbers": [],
                },
                {
                    "index": 2,
                    "special_clauses": ["특약 B"],
                    "law_references": ["민법 제623조"],
                    "precedent_numbers": [],
                },
            ],
            file,
            ensure_ascii=False,
        )
    for name in ["qa_law_only.json", "qa_precedent_only.json"]:
        with open(input_dir / name, "w", encoding="utf-8") as file:
            json.dump([], file)

    def fake_extractor(special_clauses):
        if special_clauses == ["특약 A"]:
            return ["추출 A"]
        with open(output_file, "r", encoding="utf-8") as file:
            saved = json.load(file)
        assert saved[0]["extracted_clauses"] == ["추출 A"]
        return ["추출 B"]

    stats = process_rule_based_filtered_clauses(
        input_dir,
        output_file=output_file,
        clause_extractor=fake_extractor,
    )

    with open(output_file, "r", encoding="utf-8") as file:
        processed = json.load(file)

    assert stats == {
        "total_records": 2,
        "processed_count": 2,
        "skipped_count": 0,
        "failed_count": 0,
    }
    assert processed[0]["extracted_clauses"] == ["추출 A"]
    assert processed[1]["extracted_clauses"] == ["추출 B"]


def test_process_rule_based_filtered_clauses_skips_existing_output_records(tmp_path):
    input_dir = tmp_path / "lawtalk_qa_filtered"
    output_file = input_dir / "qa_clauses_processed.json"
    input_dir.mkdir()

    with open(input_dir / "qa_both.json", "w", encoding="utf-8") as file:
        json.dump(
            [
                {"index": 1, "special_clauses": ["특약 A"]},
                {"index": 2, "special_clauses": ["특약 B"]},
            ],
            file,
            ensure_ascii=False,
        )
    for name in ["qa_law_only.json", "qa_precedent_only.json"]:
        with open(input_dir / name, "w", encoding="utf-8") as file:
            json.dump([], file)

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(
            [
                {
                    "index": 1,
                    "special_clauses": ["특약 A"],
                    "source_file": "qa_both.json",
                    "source_position": 1,
                    "extracted_clauses": ["추출 A"],
                    "clause_processing_status": "success",
                }
            ],
            file,
            ensure_ascii=False,
        )

    calls = []

    def fake_extractor(special_clauses):
        calls.append(special_clauses)
        return ["추출 B"]

    stats = process_rule_based_filtered_clauses(
        input_dir,
        output_file=output_file,
        clause_extractor=fake_extractor,
    )

    with open(output_file, "r", encoding="utf-8") as file:
        processed = json.load(file)

    assert calls == [["특약 B"]]
    assert stats["processed_count"] == 1
    assert stats["skipped_count"] == 1
    assert processed[0]["extracted_clauses"] == ["추출 A"]
    assert processed[1]["extracted_clauses"] == ["추출 B"]


def test_process_rule_based_filtered_clauses_respects_limit(tmp_path):
    input_dir = tmp_path / "lawtalk_qa_filtered"
    output_file = input_dir / "qa_clauses_processed.json"
    input_dir.mkdir()

    with open(input_dir / "qa_both.json", "w", encoding="utf-8") as file:
        json.dump(
            [
                {"index": 1, "special_clauses": ["특약 A"]},
                {"index": 2, "special_clauses": ["특약 B"]},
            ],
            file,
            ensure_ascii=False,
        )
    for name in ["qa_law_only.json", "qa_precedent_only.json"]:
        with open(input_dir / name, "w", encoding="utf-8") as file:
            json.dump([], file)

    stats = process_rule_based_filtered_clauses(
        input_dir,
        output_file=output_file,
        clause_extractor=lambda special_clauses: special_clauses,
        limit=1,
    )

    with open(output_file, "r", encoding="utf-8") as file:
        processed = json.load(file)

    assert stats["total_records"] == 2
    assert stats["processed_count"] == 1
    assert len(processed) == 1
    assert processed[0]["extracted_clauses"] == ["특약 A"]


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


def test_run_lawtalk_qa_extract_clauses_option(monkeypatch):
    calls = []

    def fake_process(input_dir, output_file=None, debug=False, limit=None):
        calls.append((input_dir, output_file, debug, limit))
        return {
            "total_records": 3,
            "processed_count": 2,
            "skipped_count": 1,
            "failed_count": 0,
        }

    monkeypatch.setattr(
        "data.processors.lawtalk_qa_processor.process_rule_based_filtered_clauses",
        fake_process,
    )

    run_processor.run_lawtalk_qa(
        [
            "--extract-clauses",
            "data/lawtalk_qa_filtered",
            "data/lawtalk_qa_filtered/qa_clauses_processed.json",
            "--debug",
            "--limit",
            "2",
        ]
    )

    assert calls == [
        (
            "data/lawtalk_qa_filtered",
            "data/lawtalk_qa_filtered/qa_clauses_processed.json",
            True,
            2,
        )
    ]


def test_run_lawtalk_qa_prepare_db_option(monkeypatch):
    calls = []

    def fake_prepare(input_file, output_file=None, debug=False, limit=None):
        calls.append((input_file, output_file, debug, limit))
        return {
            "total_questions": 5,
            "total_answers": 10,
            "processed_count": 3,
            "skipped_count": 1,
            "failed_count": 0,
        }

    monkeypatch.setattr(
        "data.processors.lawtalk_qa_processor.prepare_db_ready_records",
        fake_prepare,
    )

    run_processor.run_lawtalk_qa(
        [
            "--prepare-db",
            "data/raw/lawtalk_QA_Context.json",
            "data/lawtalk_qa_preprocessed/lawtalk_qa_db_ready.json",
            "--debug",
            "--limit",
            "3",
        ]
    )

    assert calls == [
        (
            "data/raw/lawtalk_QA_Context.json",
            "data/lawtalk_qa_preprocessed/lawtalk_qa_db_ready.json",
            True,
            3,
        )
    ]
