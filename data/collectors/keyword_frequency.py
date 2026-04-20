import json
import re
import math
from collections import Counter
from pathlib import Path

import pandas as pd


# =========================================================
# 1. 파일 경로 설정
# =========================================================
_BASE = Path(__file__).resolve().parent.parent.parent
CASE_DETAILS_PATH = str(_BASE / "output" / "case_details.json")
OUTPUT_DIR = _BASE / "keyword_analysis_output"
OUTPUT_DIR.mkdir(exist_ok=True)

TF_OUTPUT_PATH = OUTPUT_DIR / "keyword_frequency_tf.csv"
DF_OUTPUT_PATH = OUTPUT_DIR / "keyword_frequency_df.csv"
RECOMMEND_OUTPUT_PATH = OUTPUT_DIR / "recommended_keywords.csv"


# =========================================================
# 2. 분석 설정
# =========================================================
USE_KIWI = True   # 설치되어 있으면 사용, 없으면 자동 fallback
MIN_TOKEN_LEN = 2

# 추천 키워드 조건
RECOMMEND_MIN_TF = 10
RECOMMEND_MIN_DF_RATIO = 2.0
RECOMMEND_MAX_DF_RATIO = 45.0
RECOMMEND_MIN_LEN = 2
RECOMMEND_TOP_N = 80

# 너무 일반적이거나 소송 절차상 반복되는 단어 제거
STOPWORDS = {
    "원고", "피고", "상고인", "피상고인", "항소인", "피항소인",
    "신청인", "피신청인", "법원", "대법원", "지방법원", "고등법원",
    "판결", "결정", "사건", "청구", "이유", "주문", "판단", "인정",
    "관련", "경우", "부분", "내용", "사실", "의미", "대한", "해당",
    "규정", "법률", "조문", "효력", "위반", "주장", "여부",
    "각", "그", "이", "저", "등", "및", "수", "것", "때", "바"
}

# 추천 키워드에서는 제외할 일반어
GENERIC_EXCLUDE = {
    "주택", "건물", "계약", "관계", "절차", "방법", "사례",
    "권리", "의무", "적용", "존재", "기준", "사정", "표시",
    "민법", "민사", "취지", "목적", "소정", "적극", "소극",
    "이전", "지위", "공시", "요건", "내용", "경우", "법률",
    "법원", "판결", "원고", "피고", "당사자", "이유", "주문"
}

# 프로젝트상 남기고 싶은 복합명사 사전
COMPOUND_TERMS = [
    "주택임대차", "주택임대차보호법", "계약갱신요구권", "묵시적갱신",
    "임차권등기명령", "우선변제권", "최우선변제권", "대항력", "확정일자",
    "전입신고", "주민등록", "임대인", "임차인", "임대차", "보증금",
    "임차보증금", "보증금반환", "차임", "차임연체", "전대차", "전대",
    "원상회복", "수선의무", "필요비", "유익비", "사용수익", "명도",
    "인도", "경매", "배당", "우선변제", "갱신거절", "임대차기간",
    "차임증액", "전월세전환", "계약해지", "계약해제"
]

# 정리 시 제거할 패턴
REMOVE_PATTERNS = [
    r"제\d+조",
    r"제\d+항",
    r"제\d+호",
    r"\d+년",
    r"\d+월",
    r"\d+일",
]


# =========================================================
# 3. 형태소 분석기 준비 (선택)
# =========================================================
kiwi = None

if USE_KIWI:
    try:
        from kiwipiepy import Kiwi
        kiwi = Kiwi()
        print("[INFO] Kiwi 형태소 분석기를 사용합니다.")
    except Exception:
        kiwi = None
        print("[INFO] Kiwi를 사용할 수 없어 정규식 기반 분석으로 진행합니다.")
else:
    print("[INFO] 정규식 기반 분석으로 진행합니다.")


# =========================================================
# 4. JSON 로드
# =========================================================
def load_json(path: str):
    """
    JSON 파일을 로드한다.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# =========================================================
# 5. 텍스트 전처리
# =========================================================
def clean_text(text: str) -> str:
    """
    HTML/특수문자 제거 및 공백 정리
    """
    if not text:
        return ""

    text = str(text)

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)

    for pattern in REMOVE_PATTERNS:
        text = re.sub(pattern, " ", text)

    text = re.sub(r"[^가-힣a-zA-Z0-9\s_]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


# =========================================================
# 6. 복합명사 보호
# =========================================================
def protect_compound_terms(text: str):
    """
    복합명사를 한 덩어리로 유지하기 위해 치환한다.
    예: '계약갱신요구권' -> '__TERM0__'
    """
    protected_map = {}
    protected_text = text

    # 긴 단어부터 먼저 치환해야 부분 매칭 충돌이 줄어듦
    sorted_terms = sorted(COMPOUND_TERMS, key=len, reverse=True)

    for idx, term in enumerate(sorted_terms):
        placeholder = f"__TERM{idx}__"
        if term in protected_text:
            protected_text = protected_text.replace(term, placeholder)
            protected_map[placeholder] = term

    return protected_text, protected_map


def restore_protected_tokens(tokens, protected_map):
    """
    placeholder를 원래 복합명사로 복원
    """
    restored = []
    for token in tokens:
        restored.append(protected_map.get(token, token))
    return restored


# =========================================================
# 7. 키워드 추출
# =========================================================
def extract_keywords_with_kiwi(text: str):
    """
    Kiwi 기반 키워드 추출
    - 일반명사(NNG), 고유명사(NNP) 중심
    - 복합명사 사전 보호 병행
    """
    text = clean_text(text)
    text, protected_map = protect_compound_terms(text)

    result = kiwi.tokenize(text)
    tokens = []

    for token in result:
        form = token.form
        tag = token.tag

        # placeholder 복원
        form = protected_map.get(form, form)

        if form in STOPWORDS:
            continue

        if form in COMPOUND_TERMS:
            tokens.append(form)
            continue

        if tag in {"NNG", "NNP"} and len(form) >= MIN_TOKEN_LEN:
            if re.fullmatch(r"[가-힣]{2,}", form):
                tokens.append(form)

    return tokens


def extract_keywords_with_regex(text: str):
    """
    형태소 분석기 없이 정규식으로 키워드 추출
    """
    text = clean_text(text)
    text, protected_map = protect_compound_terms(text)

    # placeholder 또는 한글 2자 이상 토큰 추출
    tokens = re.findall(r"__TERM\d+__|[가-힣]{2,}", text)
    tokens = restore_protected_tokens(tokens, protected_map)

    results = []
    for token in tokens:
        if len(token) < MIN_TOKEN_LEN:
            continue
        if token in STOPWORDS:
            continue
        results.append(token)

    return results


def extract_keywords(text: str):
    """
    Kiwi 가능하면 Kiwi, 아니면 regex fallback
    """
    if not text:
        return []

    if kiwi is not None:
        return extract_keywords_with_kiwi(text)
    return extract_keywords_with_regex(text)


# =========================================================
# 8. 상세 JSON 구조 대응
# =========================================================
def normalize_details(raw_data):
    """
    case_details.json 구조가 list 또는 dict일 수 있으므로
    분석 가능한 list[dict] 형태로 정규화한다.
    """
    if isinstance(raw_data, list):
        return raw_data

    if isinstance(raw_data, dict):
        # 흔한 패턴들 대응
        if "data" in raw_data and isinstance(raw_data["data"], list):
            return raw_data["data"]
        if "results" in raw_data and isinstance(raw_data["results"], list):
            return raw_data["results"]
        if "items" in raw_data and isinstance(raw_data["items"], list):
            return raw_data["items"]

        # dict 한 개만 들어있는 경우
        return [raw_data]

    return []


# =========================================================
# 9. 분석 대상 텍스트 조합
# =========================================================
def build_analysis_text(row: dict) -> str:
    """
    판례에서 키워드 추출 대상으로 사용할 텍스트를 합친다.
    우선순위:
    - 판시사항
    - 판결요지
    - 참조조문
    - 사건명
    """
    fields = [
        row.get("판시사항", ""),
        row.get("판결요지", ""),
        row.get("참조조문", ""),
        row.get("사건명", ""),
    ]

    return " ".join([str(x) for x in fields if x])


# =========================================================
# 10. 빈도 분석
# =========================================================
def analyze_keyword_frequency(details):
    """
    TF(전체 빈도), DF(문서 빈도), TF-IDF 참고값 계산
    """
    tf_counter = Counter()
    df_counter = Counter()

    total_docs = len(details)

    for idx, row in enumerate(details, start=1):
        if idx % 100 == 0:
            print(f"[INFO] 분석 진행: {idx}/{total_docs}")

        text = build_analysis_text(row)
        tokens = extract_keywords(text)

        tf_counter.update(tokens)
        df_counter.update(set(tokens))

    rows = []
    for token, tf in tf_counter.most_common():
        df = df_counter[token]
        df_ratio = round((df / total_docs) * 100, 2) if total_docs else 0.0
        idf = math.log((total_docs + 1) / (df + 1)) + 1
        tfidf = round(tf * idf, 4)

        rows.append({
            "키워드": token,
            "TF_전체빈도": tf,
            "DF_문서빈도": df,
            "DF비율(%)": df_ratio,
            "TFIDF_참고값": tfidf
        })

    result_df = pd.DataFrame(rows)
    return result_df


# =========================================================
# 11. 추천 키워드 추출
# =========================================================
def make_recommended_keywords(result_df: pd.DataFrame):
    """
    TF / DF / TF-IDF 결과를 기반으로 추천 키워드를 추출한다.
    가중치 없이, 조건 필터 후 TF-IDF 기준으로 정렬한다.
    """
    if result_df.empty:
        return pd.DataFrame()

    recommend_df = result_df.copy()

    # 조건 필터
    recommend_df = recommend_df[
        (recommend_df["키워드"].str.len() >= RECOMMEND_MIN_LEN) &
        (recommend_df["TF_전체빈도"] >= RECOMMEND_MIN_TF) &
        (recommend_df["DF비율(%)"] >= RECOMMEND_MIN_DF_RATIO) &
        (recommend_df["DF비율(%)"] <= RECOMMEND_MAX_DF_RATIO) &
        (~recommend_df["키워드"].isin(GENERIC_EXCLUDE))
    ].copy()

    # 정렬: TF-IDF 우선, 같으면 DF / TF 기준
    recommend_df = recommend_df.sort_values(
        by=["TFIDF_참고값", "DF_문서빈도", "TF_전체빈도"],
        ascending=[False, False, False]
    ).reset_index(drop=True)

    # 상위 N개만 사용
    recommend_df = recommend_df.head(RECOMMEND_TOP_N).copy()

    return recommend_df


def print_recommended_keywords(recommend_df: pd.DataFrame, top_n=50):
    """
    추천 키워드를 콘솔에 출력한다.
    """
    if recommend_df.empty:
        print("\n[추천 키워드] 조건에 맞는 키워드가 없습니다.")
        return

    print(f"\n[추천 키워드 상위 {min(top_n, len(recommend_df))}개]")
    print(recommend_df.head(top_n).to_string(index=False))

    recommended_list = recommend_df["키워드"].head(top_n).tolist()
    print("\n[Python 리스트용 추천 키워드]")
    print("FILTER_KEYWORDS =", recommended_list)


# =========================================================
# 12. 실행
# =========================================================
def main():
    raw_details = load_json(CASE_DETAILS_PATH)
    details = normalize_details(raw_details)

    print(f"[INFO] 상세 판례 수: {len(details)}")

    if not details:
        print("[ERROR] 분석할 상세 데이터가 없습니다.")
        return

    result_df = analyze_keyword_frequency(details)

    if result_df.empty:
        print("[ERROR] 키워드가 추출되지 않았습니다.")
        return

    # TF 기준 저장
    result_df.to_csv(TF_OUTPUT_PATH, index=False, encoding="utf-8-sig")

    # DF 기준 정렬 저장
    df_sorted = result_df.sort_values(
        by=["DF_문서빈도", "TF_전체빈도"],
        ascending=[False, False]
    ).reset_index(drop=True)
    df_sorted.to_csv(DF_OUTPUT_PATH, index=False, encoding="utf-8-sig")

    # 추천 키워드 저장
    recommend_df = make_recommended_keywords(result_df)
    recommend_df.to_csv(RECOMMEND_OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"[INFO] 저장 완료: {TF_OUTPUT_PATH}")
    print(f"[INFO] 저장 완료: {DF_OUTPUT_PATH}")
    print(f"[INFO] 저장 완료: {RECOMMEND_OUTPUT_PATH}")

    print("\n[TF 상위 50개]")
    print(result_df.head(50).to_string(index=False))

    print("\n[DF 상위 50개]")
    print(df_sorted.head(50).to_string(index=False))

    print_recommended_keywords(recommend_df, top_n=50)


if __name__ == "__main__":
    main()