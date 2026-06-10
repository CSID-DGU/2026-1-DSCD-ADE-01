"""지능형 PII 마스킹 (Microsoft Presidio 기반).

기존 정규식 방식의 한계를 보완하기 위해 NLP 엔진을 활용하여
계좌번호, 전화번호, 이메일 등을 더 정확하게 탐지하고 마스킹한다.
"""
from __future__ import annotations

import re
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# 1. 커스텀 패턴 정의 (정규식 보강)
# 한국형 계좌번호 패턴: 하이픈이 2개 이상 포함된 가변 길이 숫자 조합
BANK_ACCOUNT_PATTERN = Pattern(
    name="bank_account_pattern",
    regex=r"(?<!\d)\d{1,8}(?:-\d{1,10}){2,}(?!\d)",
    score=0.8
)

# 한국형 주민등록번호 패턴
RRN_PATTERN = Pattern(
    name="rrn_pattern",
    regex=r"\b\d{6}\s*-\s*\d{7}\b",
    score=0.95
)

# 2. 커스텀 Recognizer 등록
bank_account_recognizer = PatternRecognizer(
    supported_entity="BANK_ACCOUNT",
    patterns=[BANK_ACCOUNT_PATTERN],
    context=["계좌", "입금", "송금", "은행", "account", "bank"]
)

rrn_recognizer = PatternRecognizer(
    supported_entity="RRN",
    patterns=[RRN_PATTERN],
    context=["주민", "번호", "등록", "rrn"]
)

# 3. 엔진 초기화
# Presidio 기본 엔진에 커스텀 Recognizer 추가
analyzer = AnalyzerEngine(default_score_threshold=0.4)
analyzer.registry.add_recognizer(bank_account_recognizer)
analyzer.registry.add_recognizer(rrn_recognizer)

anonymizer = AnonymizerEngine()

# 마스킹 규칙 설정
OPERATORS = {
    "BANK_ACCOUNT": OperatorConfig("replace", {"new_value": "[MASKED_BANK_ACCOUNT]"}),
    "RRN": OperatorConfig("replace", {"new_value": "[MASKED_RRN]"}),
    "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[MASKED_EMAIL]"}),
    "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[MASKED_PHONE]"}),
    "LOCATION": OperatorConfig("replace", {"new_value": "[MASKED_ADDRESS]"}), # 주소 등
}

# 기존 정규식 유지 (Presidio가 놓칠 수 있는 특정 포맷용)
FALLBACK_PATTERNS = [
    ("LEASED_PART", re.compile(r"(?m)^.*임차할\s*부분.*$")),
    ("ADDRESS_LINE", re.compile(r"(?m)^\s*주\s*소\s+.+$")),
]

def mask_pii(text: str) -> str:
    """Presidio를 활용하여 지능형 마스킹을 수행한다."""
    if not text:
        return ""

    # 1. Presidio 분석 및 익명화
    results = analyzer.analyze(
        text=text, 
        entities=["BANK_ACCOUNT", "RRN", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION"],
        language="en" # NLP 엔진 기본 언어 (한국어 Recognizer는 별도 등록됨)
    )
    
    anonymized_result = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=OPERATORS
    )
    
    processed_text = anonymized_result.text

    # 2. 정규식 기반 Fallback 마스킹 (문장 단위 등 특수 케이스)
    for label, pattern in FALLBACK_PATTERNS:
        processed_text = pattern.sub(f"[MASKED_{label}]", processed_text)
        
    return processed_text

if __name__ == "__main__":
    # 테스트 코드
    test_text = """
    위 부동산의 보증금은 금 일천만원정(₩10,000,000)으로 한다.
    차임은 매월 4일에 지불한다(입금계좌:1111-123-456 ).
    임차인 연락처: 010-1234-5678, 이메일: test@gmail.com
    주소: 서울시 강남구 테헤란로 123
    """
    print(mask_pii(test_text))
