"""로톡 QA 데이터에서 특약 질문과 법령/판례 참조를 추출한다."""

import json
import re
from pathlib import Path


TARGET_LAWS = [
    "민법",
    "부동산등기법",
    "공인중개사법",
    "주택임대차보호법",
    "화물자동차운수사업법",
    "민사소송법",
    "민사조정법",
    "민사집행법",
    "소액사건심판법",
    "공동주택관리법",
    "주민등록법",
]

SPECIAL_KEYWORDS = ["특약", "특약사항", "특약조항", "특약 조항"]


def add_unique(items, value):
    """리스트에 같은 값이 없을 때만 값을 추가한다."""
    if value not in items:
        items.append(value)


def make_law_reference(law_name, article_number, sub_article_number):
    """법령명과 조문 번호를 출력용 문자열로 만든다."""
    if article_number is None:
        return law_name

    reference = law_name + " 제" + article_number + "조"

    if sub_article_number is not None:
        reference = reference + "의" + sub_article_number

    return reference


def find_direct_law_matches(text):
    """답변에서 직접 등장한 법령명을 찾는다."""
    matches = []

    for law_name in TARGET_LAWS:
        escaped_law_name = re.escape(law_name)
        pattern = (
            escaped_law_name
            + r"\s*(?:제\s*)?(\d+)?\s*"
            + r"(?:조\s*(?:의\s*(\d+))?)?"
        )

        for match in re.finditer(pattern, text):
            article_number = match.group(1)
            sub_article_number = match.group(2)

            matches.append(
                {
                    "start": match.start(),
                    "law_name": law_name,
                    "article_number": article_number,
                    "sub_article_number": sub_article_number,
                    "is_same_law": False,
                }
            )

    return matches


def find_same_law_matches(text):
    """답변에서 '동법'으로 표현된 조문을 찾는다."""
    matches = []
    pattern = r"동법\s*(?:제\s*)?(\d+)?\s*(?:조\s*(?:의\s*(\d+))?)?"

    for match in re.finditer(pattern, text):
        matches.append(
            {
                "start": match.start(),
                "law_name": None,
                "article_number": match.group(1),
                "sub_article_number": match.group(2),
                "is_same_law": True,
            }
        )

    return matches


def extract_law_references(text):
    """답변에서 대상 법령 참조를 추출한다.

    '동법'은 같은 답변 안에서 앞서 나온 대상 법령명으로 바꾼다.
    """
    all_matches = find_direct_law_matches(text) + find_same_law_matches(text)
    all_matches.sort(key=lambda item: item["start"])

    references = []
    last_law_name = None

    for match in all_matches:
        if match["is_same_law"]:
            if last_law_name is None:
                continue

            reference = make_law_reference(
                last_law_name,
                match["article_number"],
                match["sub_article_number"],
            )
            add_unique(references, reference)
            continue

        last_law_name = match["law_name"]
        reference = make_law_reference(
            match["law_name"],
            match["article_number"],
            match["sub_article_number"],
        )
        add_unique(references, reference)

    return references


def extract_precedent_numbers(text):
    """답변에서 한국 사건번호 형식의 판례번호를 추출한다."""
    pattern = r"(?<!\d)(\d{2}|\d{4})\s*(?!년|월|일|조|항|호)([가-힣]{1,4})\s*(\d+)(?!\d)"
    numbers = []

    for match in re.finditer(pattern, text):
        precedent_number = match.group(1) + match.group(2) + match.group(3)
        add_unique(numbers, precedent_number)

    return numbers


def split_sentences(text):
    """줄바꿈과 문장 종료 기호를 기준으로 문장을 나눈다."""
    sentences = []
    lines = text.splitlines()

    for line in lines:
        line = line.strip()
        if line == "":
            continue

        line_sentences = re.findall(r"[^.!?。]+[.!?。]?", line)

        for sentence in line_sentences:
            sentence = sentence.strip()
            if sentence != "":
                sentences.append(sentence)

    return sentences


def extract_special_clauses(question_body):
    """질문 본문에서 특약이 언급된 문장만 추출한다."""
    special_clauses = []
    sentences = split_sentences(question_body)

    for sentence in sentences:
        for keyword in SPECIAL_KEYWORDS:
            if keyword in sentence:
                special_clauses.append(sentence)
                break

    return special_clauses


def process_record(record):
    """로톡 QA 레코드 하나를 필터링하고 출력 형식으로 바꾼다."""
    question_body = record.get("question_body", "")
    special_clauses = extract_special_clauses(question_body)

    if len(special_clauses) == 0:
        return None

    law_references = []
    precedent_numbers = []

    for answer_item in record.get("all_answers", []):
        answer_text = answer_item.get("answer", "")

        for law_reference in extract_law_references(answer_text):
            add_unique(law_references, law_reference)

        for precedent_number in extract_precedent_numbers(answer_text):
            add_unique(precedent_numbers, precedent_number)

    if len(law_references) == 0 and len(precedent_numbers) == 0:
        return None

    return {
        "index": record.get("index"),
        "special_clauses": special_clauses,
        "law_references": law_references,
        "precedent_numbers": precedent_numbers,
    }


def read_records_from_file(file_path):
    """JSON 파일 하나에서 레코드 목록을 읽는다."""
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def write_json(file_path, records):
    """레코드 목록을 JSON 파일로 저장한다."""
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)


def run(input_dir="data/lawtalk_qa", output_dir="data/lawtalk_qa_filtered"):
    """입력 디렉터리의 로톡 QA JSON 파일들을 처리한다."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    both = []
    law_only = []
    precedent_only = []
    total_records = 0

    for file_path in sorted(input_path.glob("*.json")):
        records = read_records_from_file(file_path)

        for record in records:
            total_records = total_records + 1
            processed_record = process_record(record)

            if processed_record is None:
                continue

            has_law = len(processed_record["law_references"]) > 0
            has_precedent = len(processed_record["precedent_numbers"]) > 0

            if has_law and has_precedent:
                both.append(processed_record)
            elif has_law:
                law_only.append(processed_record)
            else:
                precedent_only.append(processed_record)

    write_json(output_path / "qa_both.json", both)
    write_json(output_path / "qa_law_only.json", law_only)
    write_json(output_path / "qa_precedent_only.json", precedent_only)

    filtered_count = len(both) + len(law_only) + len(precedent_only)

    print(f"총 {total_records}건 중 {filtered_count}건 필터링 완료")
    print(f"  법령 + 판례 모두: {len(both)}건 → qa_both.json")
    print(f"  법령만: {len(law_only)}건 → qa_law_only.json")
    print(f"  판례만: {len(precedent_only)}건 → qa_precedent_only.json")

    return {
        "total_records": total_records,
        "both_count": len(both),
        "law_only_count": len(law_only),
        "precedent_only_count": len(precedent_only),
    }
