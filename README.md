# CLARA: RAG 기반 임대차 계약서 분석 시스템

## 2026-1 데이터사이언스캡스톤디자인 팀 ADE

<!-- 로고 이미지 -->
<!-- <img src="이미지경로" width="200"/> -->

> 🌐 **[서비스 바로가기 →](https://dscd-ade-fe.web.app/)**　　🎬 **[시연 영상 보기 →](https://www.youtube.com/watch?v=ZcvXUgnevZw&feature=youtu.be)**

## 💡 프로젝트 개요

**CLARA(Contract Lease Analysis and Review Assistant)** 는 RAG(Retrieval-Augmented Generation) 기술을 활용하여 주택 임대차 계약서의 특약 조항을 자동 분석하는 AI 기반 법률 보조 서비스입니다.

법률 지식이 부족한 임차인이 특약 속 위험을 쉽게 파악하고, 계약 전 분쟁을 스스로 예방할 수 있도록 돕는 것을 목표로 합니다.
범용 LLM의 근거 없는 답변 대신, **법령·판례에 근거한 신뢰 가능한 분석**을 제공하며, 기존 법률 전문가 의뢰 시 평균 24시간 이상 걸리던 검토를 **1분 내로** 완료할 수 있도록 합니다.

---

## 목차

- [팀원 소개](#-팀원-소개)
- [개발 배경](#-개발-배경)
- [주요 기능](#-주요-기능)
- [서비스 화면](#-서비스-화면)
- [시스템 아키텍처](#-시스템-아키텍처)
- [기술 스택](#-기술-스택)
- [폴더 구조](#-폴더-구조)
- [설치 및 실행](#-설치-및-실행)
- [성능 평가](#-성능-평가)
- [기대 효과](#-기대-효과)

---

## 👥 팀원 소개

| 역할 | 이름 |
|:---:|:---:|
| 팀장 / 개발 | 윤서현 |
| 개발 | 배범서 |
| 개발 | 윤예정 |
| 개발 | 박민영 |

---

## 🚨 개발 배경

주택임대차 분쟁 조정 신청 건수는 2021년 대비 2025년 **3배 이상** 증가했습니다.
분쟁의 상당수는 계약서 속 특약 조항에 대한 해석 차이에서 비롯되지만, 대부분의 임차인은 특약의 법적 의미를 정확히 파악하기 어렵습니다.

**예시)**
- `"입주 당시 상태로 원상복구하여 반환한다"` → 원상복구 범위 불명확 → 보증금 반환 분쟁
- `"반려동물로 인한 손해는 임차인이 책임진다"` → 손해 산정 기준 없음 → 과도한 수리비 청구 분쟁

---

## 🌟 주요 기능

### 1. 특약 분석
계약서를 업로드하면 각 특약을 세 가지 관점에서 분석합니다.
- 복잡한 조항을 **쉬운 말로 한 줄 요약**
- 발생 가능한 **분쟁 소지 및 위법 가능성** 안내
- 분석 근거가 되는 **관련 법령 및 판례** 제공

### 2. 특약 수정
위법 소지가 있는 특약을 자동으로 수정해주는 기능
- 모호한 표현을 명확하게 수정
- 관련 법령을 반영하여 더 안전한 조항으로 개선

### 3. 특약 간 관계 분석
여러 특약을 함께 해석했을 때 발생할 수 있는 파생 효과 분석
- 개별 특약으로는 확인하기 어려운 불이익 사전 안내
- 계약서 전체 맥락에서의 위험 파악

### 4. 체크리스트
계약 전 확인해야 할 사항을 근거와 함께 자동 생성
- 언제까지 퇴실 의사를 알려야 하는지 등 실질적 안내
- 관련 특약 및 근거 법령 함께 제공

### 5. 챗봇 질의응답
보고서 및 계약서 내용 기반 질의응답
- 어려운 법률 용어를 쉬운 말로 설명
- 해당 용어가 계약서의 어떤 조항과 관련 있는지 함께 안내

---

## 📸 서비스 화면

<!-- 스크린샷 이미지를 아래에 삽입하세요 -->

| 메인 화면 (업로드) | 특약 분석 결과 |
|:---:|:---:|
| <img width="1280" height="705" alt="화면 캡처 2026-06-10 0214381" src="https://github.com/user-attachments/assets/8ed04030-a7a5-412a-b601-2b8d448845ff" /> | <img width="1280" height="705" alt="화면 캡처 2026-06-10 0216321" src="https://github.com/user-attachments/assets/283d908e-3838-4a2e-9ae4-b805017a73e5" /> |


| 특약 수정 | 체크리스트 |
|:---:|:---:|
| <img width="1280" height="706" alt="화면 캡처 2026-06-10 021738" src="https://github.com/user-attachments/assets/cc63c692-4f2c-4b50-832f-55d023781bf7" /> | <img width="1280" height="703" alt="화면 캡처 2026-06-10 021801" src="https://github.com/user-attachments/assets/1ad1eecc-e159-4e73-8a46-aeef53f5205e" /> |

| 챗봇 |
|:---:|
| <img width="1280" height="705" alt="화면 캡처 2026-06-10 0218132" src="https://github.com/user-attachments/assets/2e807ff2-12fb-4d37-bffe-f4449fa6d775" /> |

> 🎬 **시연 영상**: [YouTube 링크](https://www.youtube.com/watch?v=ZcvXUgnevZw&feature=youtu.be)
> 
> 🌐 **서비스 바로가기**: [https://dscd-ade-fe.web.app/](https://dscd-ade-fe.web.app/)

---

## 🏗 시스템 아키텍처

### 전체 파이프라인

```
[계약서 PDF 업로드]
       ↓
[텍스트 파싱 + 개인정보 마스킹]
       ↓
[특약 추출 + 쿼리 확장 (LLM)]
       ↓
  ┌────┴────┐
[BM25    Dense
 법률용어  의미적
 매칭]    유사도]
  └────┬────┘
       ↓
[하이브리드 검색 → Reranking]
       ↓
[법령 · 판례 DB]
       ↓
[보고서 생성 (Gemini LLM)]
       ↓
[분석 결과 제공: 특약 분석 / 수정 / 관계 분석 / 체크리스트 / 챗봇]
```

### 인프라 구조

```
[사용자 브라우저 (Next.js)]
         ↓ HTTPS
[Google Cloud Run (FastAPI 백엔드)]
         ↓
  ┌──────┴──────┐
[Cloud SQL]  [Cloud Storage]
(법령·판례 DB)  (계약서 파일)
```

---

## 🔧 기술 스택

| 분야 | 기술 스택 |
|:---:|---|
| **Frontend** | ![Next.js](https://img.shields.io/badge/Next.js-000000?style=flat-square&logo=next.js&logoColor=white) ![React](https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=React&logoColor=white) ![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white) ![TailwindCSS](https://img.shields.io/badge/TailwindCSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white) |
| **Backend** | ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white) ![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white) |
| **AI / RAG** | ![Gemini](https://img.shields.io/badge/Gemini_API-8E75B2?style=flat-square&logo=google&logoColor=white) ![sentence-transformers](https://img.shields.io/badge/sentence--transformers-FF6B6B?style=flat-square) ![BM25](https://img.shields.io/badge/BM25-555555?style=flat-square) |
| **DB / Storage** | ![Cloud SQL](https://img.shields.io/badge/Cloud_SQL-4285F4?style=flat-square&logo=googlecloud&logoColor=white) ![Cloud Storage](https://img.shields.io/badge/Cloud_Storage-4285F4?style=flat-square&logo=googlecloud&logoColor=white) |
| **Infra** | ![Google Cloud Run](https://img.shields.io/badge/Cloud_Run-4285F4?style=flat-square&logo=googlecloud&logoColor=white) ![Firebase](https://img.shields.io/badge/Firebase-FFCA28?style=flat-square&logo=firebase&logoColor=black) |

---

## 📂 폴더 구조

```
2026-1-DSCD-ADE-01/
├── README.md
│
├── frontend/                        # Next.js 프론트엔드
│   ├── app/
│   │   ├── page.tsx                 # 메인 페이지 (계약서 업로드)
│   │   └── analysis/page.tsx        # 분석 결과 페이지
│   └── components/
│       ├── UploadDropzone.tsx        # 계약서 업로드 컴포넌트
│       ├── TopNavBar.tsx             # 상단 네비게이션
│       ├── RecentDocumentPanel.tsx   # 최근 분석 히스토리 패널
│       └── analysis/
│           ├── DocumentPanel.tsx     # 특약 목록 패널
│           ├── ChatBot.tsx           # 챗봇 컴포넌트
│           ├── LawSection.tsx        # 법령 섹션
│           └── PrecedentSection.tsx  # 판례 섹션
│
├── app/                             # FastAPI 백엔드 서버
│   ├── main.py                      # API 엔트리포인트
│   └── schemas.py                   # 요청/응답 스키마
│
├── pipeline/                        # RAG 파이프라인 핵심 모듈
│   ├── preprocessing/               # 계약서 파싱 및 전처리
│   │   ├── pipeline.py              # 전처리 파이프라인
│   │   ├── layout.py                # 레이아웃 파싱
│   │   ├── masking.py               # 개인정보 마스킹
│   │   └── rule_parser.py           # 특약 추출 규칙
│   ├── retrieval/                   # 검색 모듈
│   │   ├── bm25_retrieval.py        # BM25 키워드 검색
│   │   ├── dense_retrieval.py       # Dense 의미 검색
│   │   ├── retrieval_service.py     # 하이브리드 검색 서비스
│   │   └── query_expansion/         # 쿼리 확장
│   │       └── query_expansion.py   # LLM 기반 쿼리 확장
│   ├── reranking/
│   │   └── reranker.py              # 검색 결과 재랭킹
│   └── generation/
│       └── report_generator_v2.py   # 보고서 생성
│
├── shared/                          # 공통 유틸리티
│   ├── config.py                    # 환경 설정
│   ├── llm/gemini_client.py         # Gemini API 클라이언트
│   ├── db/connection.py             # Cloud SQL 연결
│   └── storage/gcs_client.py        # GCS 클라이언트
│
├── data/                            # 데이터 수집 및 처리
│   ├── collectors/
│   │   ├── law_collector.py         # 법령 데이터 수집
│   │   └── case_collector.py        # 판례 데이터 수집
│   └── processors/
│       ├── law_embedder.py          # 법령 임베딩
│       └── caselaw_embedder.py      # 판례 임베딩
│
├── evaluation/                      # 성능 평가
│   ├── legal_retrieval_eval.py      # 검색 성능 평가 (Recall)
│   └── judge_eval.py                # 보고서 생성 평가 (LLM-as-a-Judge)
│
├── infra/
│   └── cloud_sql/init_schema.sql    # DB 스키마
│
├── scripts/                         # 유틸리티 스크립트
│   ├── deploy_cloud_run.sh          # Cloud Run 배포 스크립트
│   └── load_data_cloud_sql.py       # DB 데이터 로드
│
└── requirements.txt                 # Python 의존성
```

---

## 🚀 설치 및 실행

### 사전 요구사항

- Python 3.10+
- Node.js 18+
- Google Cloud 계정 (Cloud SQL, Cloud Storage, Cloud Run)
- Gemini API Key

### 백엔드 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env
# .env 파일에 API KEY 및 DB 정보 입력

# 서버 실행
cd app
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

### 프론트엔드 실행

```bash
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행
npm run dev
# http://localhost:3000
```

### 환경 변수 설정

`.env.example` 참고:

```env
# Gemini API
GEMINI_API_KEY=your-gemini-api-key

# Google Cloud
GOOGLE_CLOUD_PROJECT=your-project-id
GCS_BUCKET_NAME=your-bucket-name

# Cloud SQL
DB_HOST=your-db-host
DB_NAME=your-db-name
DB_USER=your-db-user
DB_PASSWORD=your-db-password
```

---

## 📊 성능 평가

### 검색 성능 평가 (RAGAS Recall@10)

| 항목 | 수치 |
|:---:|:---:|
| 법령 recall@10 | **0.7034** |
| 판례 recall@10 | **0.8095** |

### 보고서 생성 성능 평가 (LLM-as-a-Judge)

| 항목 | 설명 | 성능 |
|:---:|---|:---:|
| **Coherence** | 생성된 문장들이 자연스럽고 논리적으로 연결되는지 측정 | **4.2 / 5.0** |
| **Consistency** | 생성된 문장들이 원문·법령 근거와 일치하는지 측정 | **4.0 / 5.0** |

> 실제 변호사의 답변과 비교 시 주요 법적 쟁점과 판단에서 유사한 결과 확인

---

## 💼 기대 효과

- **검토 시간 단축**: 24시간 이상 → 1분 이내
- **접근성 향상**: 법률 전문 지식 없이도 계약서 위험 파악 가능
- **검토 비용 절감**: 법률 전문가 의뢰 비용 절감
- **분쟁 예방**: 계약 전 위험 요소 사전 인지로 분쟁 감소

---

## 📄 라이선스

본 프로젝트는 동국대학교 데이터사이언스캡스톤디자인 수업의 졸업 프로젝트로 개발되었습니다.

---

## 📬 문의

프로젝트 관련 문의는 이슈를 통해 등록해주세요.

