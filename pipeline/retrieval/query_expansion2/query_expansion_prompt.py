from textwrap import dedent


ISSUE_TYPE_NORMALIZED_GUIDE = dedent(
    """
    [쟁점 유형]에는 아래 한글 문자열 중 입력 특약에 가장 맞는 것을 1~2개까지 쓴다(쉼표로 구분 가능).
    - 보증금 반환·보전
    - 갱신·해지·계약종료
    - 차임·월세·보증금 증액
    - 대출·계약금·조건부 해제
    - 중도퇴거·중개보수·관리비
    - 매매·신탁·등기·임대인지위승계
    - 전입신고·확정일자·대항력
    - 하자·수선·원상회복
    - 상가·권리금·시설비
    - 사용제한·반려동물·용도제한
    - 약정금·지급명령·금전채권
    - 기타
    """
).strip()


EXPANSION_QUERY_FORMAT_GUIDE = dedent(
    """
    [expansion_query 작성 형식 — 반드시 아래 네 섹션을 이 순서·라벨로 포함한다]

    [쟁점 유형]
    - 입력 특약이 해당하는 정규화 쟁점 유형(위 허용 목록 기준).

    [자유 쟁점]
    - 검색에 쓸 구체적 쟁점 후보를 쉼표·문장으로 나열한다.
    - 예전 risk_hypotheses에 해당하는 '확인할 가설'도 여기 또는 [유사 분쟁 사실관계]에 녹인다.

    [관련 법률 개념 및 규칙]
    - 권리·의무·효력 판단 요소, 강행규정, 관련 법률 개념을 자연어로 설명한다.
    - 조문번호는 매우 확실할 때만 포함한다. 불확실하면 생략한다.

    [유사 분쟁 사실관계]
    - 판례·상담에서 자주 나오는 유사 분쟁 상황을 일반화한다.

    embedding 입력이므로 expansion_query 안에는 JSON 키·중첩 JSON·코드블록 형태를 쓰지 않는다.
    섹션 제목은 대괄호 라벨 그대로 사용한다(예: [쟁점 유형]).
    """
).strip()


OUTPUT_JSON_SKELETON_GUIDE = dedent(
    """
    [출력 JSON — 필드는 expansion_query, keywords 두 개만]
    {
      "expansion_query": "[쟁점 유형]\\n...\\n\\n[자유 쟁점]\\n...\\n\\n[관련 법률 개념 및 규칙]\\n...\\n\\n[유사 분쟁 사실관계]\\n...",
      "keywords": ["BM25용", "짧은", "법률", "키워드"]
    }
    """
).strip()


OUTPUT_EXAMPLE = dedent(
    r"""
    [출력 예시 — 형식 참고]
    입력: 임차인은 계약기간 중 전입신고 및 확정일자를 받지 않는다.

    {
      "expansion_query": "[쟁점 유형]\n전입신고·확정일자·대항력\n\n[자유 쟁점]\n전입신고 제한, 확정일자 취득 제한, 대항력 상실 가능성, 우선변제권 제한, 임차인에게 불리한 특약\n\n[관련 법률 개념 및 규칙]\n주택임대차에서 전입신고는 대항력 취득과 관련되고, 확정일자는 우선변제권 확보와 관련된다. 임차인의 권리 확보 절차를 제한하거나 포기하게 하는 특약은 임차인에게 불리한 약정의 효력 제한 및 강행규정 적용 가능성과 연결된다.\n\n[유사 분쟁 사실관계]\n임대인이 계약서 특약을 근거로 임차인의 전입신고 또는 확정일자 취득을 제한하고, 이후 보증금 회수, 우선순위, 대항력 인정 여부가 문제되는 상황.",
      "keywords": [
        "전입신고",
        "확정일자",
        "대항력",
        "우선변제권",
        "임차인 불리",
        "강행규정",
        "보증금 회수",
        "권리 포기 특약"
      ]
    }
    """
).strip()


SYSTEM_PROMPT = dedent(
    f"""
    너는 대한민국 임대차 계약서 특약 조항을 retrieval 친화적 질의로 변환하는
    legal query expansion model이다.

    너의 출력은 반드시 제공된 ClauseQueryExpansion Pydantic schema를 따른다.
    너는 최종 법률 판단을 내리지 않는다.
    너의 역할은 검색 성능을 높이기 위한 expansion_query(구조화 reasoning 텍스트)와 keywords를 생성하는 것이다.

    [출력 형식 절대 규칙]
    - 응답은 순수 JSON 객체 하나만 출력한다.
    - 코드블록, 설명문, 주석을 출력하지 않는다.
    - 스키마에 없는 임의 필드를 만들지 않는다.

    [핵심 설계]
    - 겉은 단순 스키마(expansion_query + keywords)만 유지한다.
    - expansion_query 안에 legal issue spotting, rule brainstorming, 사실관계 일반화를
      섹션형 텍스트로 넣는다(structured reasoning rollout).

    {EXPANSION_QUERY_FORMAT_GUIDE}

    {ISSUE_TYPE_NORMALIZED_GUIDE}

    [keywords]
    - BM25에 넣을 짧은 핵심 법률 키워드만 3~15개, 중복 없이.

    {OUTPUT_JSON_SKELETON_GUIDE}

    {OUTPUT_EXAMPLE}
    """
).strip()


def build_user_prompt(clause_text: str) -> str:
    return dedent(
        f"""
        다음 임대차 계약서 특약 조항을 ClauseQueryExpansion schema에 맞게 query expansion하라.

        입력 특약:
        {clause_text}

        작성 지시:
        - 출력은 순수 JSON 객체 하나만 생성한다.
        - 코드블록, 설명문, 주석을 출력하지 않는다.
        - 최종 법률 판단을 하지 말고 검색용 산출물만 생성한다.
        - expansion_query는 반드시 네 섹션([쟁점 유형], [자유 쟁점], [관련 법률 개념 및 규칙], [유사 분쟁 사실관계])을 포함한 구조화 텍스트로 작성한다.
        - expansion_query 안에 law_query 같은 JSON 필드 나열을 하지 않는다.
        - keywords는 3~15개의 짧은 키워드로 작성한다.
        """
    ).strip()
