# 2026-1-DSCD-ADE-01 GitHub 폴더 구조

> 본 문서는 `2026-1-DSCD-ADE-01` 리포지토리의 폴더 구조와 설계 근거 기록이다.
> 팀 내부 참고용으로 유지하며, 구조 변경 시 함께 갱신한다.
>
> **참고**: 본 문서에 포함된 코드 스니펫은 구조와 역할을 설명하기 위한 **예시**이며, 실제 구현과 다를 수 있다. 클래스명, 메서드 시그니처, SQL 스키마 등은 개발 과정에서 변경될 수 있다.

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 리포지토리 | `2026-1-DSCD-ADE-01` |
| 팀 규모 | 4명 |
| 핵심 기술 | FastAPI + Cloud Run, Firebase Hosting, Vertex AI Gemini, Document AI, pgvector |
| 데이터 소스 | 법령(법제처 API), 판례, 상담사례(크롤링), 분쟁사례(PDF) — 총 4개 |
| 데이터 저장소 | Cloud SQL (pgvector) |
| GCP 프로젝트 | `dcsd-ade` |
| 기본 브랜치 | `develop` |
| 브랜치 전략 | 모든 issue 브랜치는 `develop`에서 분기 |

---

## 2. 디렉토리 구조

```
2026-1-DSCD-ADE-01/
├── README.md
├── .env.example
├── .gitignore
│
├── .github/                             # GitHub 설정
│   ├── workflows/                           # GitHub Actions CI/CD
│   ├── ISSUE_TEMPLATE/                      # 이슈 템플릿
│   └── PULL_REQUEST_TEMPLATE.md             # PR 템플릿
│
├── data/                                # 1회성 배치: 데이터 수집 → 전처리 → 인덱싱
│   ├── __init__.py
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── law_collector.py                 # 법제처 Open API → 법령 원문 수집
│   │   ├── case_collector.py                # 판례 수집 (TF-IDF 키워드 필터링)
│   │   ├── counsel_crawler.py               # 상담사례 웹 크롤링
│   │   └── dispute_pdf_parser.py            # 분쟁사례 PDF 파싱 (Document AI)
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── law_processor.py                 # 법령 XML → 조문 단위 구조화
│   │   ├── case_processor.py                # 판례 구조화 (사실관계/판결요지 분리)
│   │   ├── counsel_extractor.py             # LLM 기반 상담사례 Q&A 구조화
│   │   └── dispute_processor.py             # 분쟁사례 구조화 (쟁점/결과 분리)
│   ├── indexer.py                           # Vertex AI Embeddings → pgvector 적재
│   └── raw/                                 # 원시 데이터 저장 (git 미추적)
│
├── pipeline/                            # 핵심: RAG 파이프라인 (서빙 전용)
│   ├── __init__.py
│   │
│   ├── preprocessing/                   # 사용자 업로드 계약서 전처리
│   │   ├── __init__.py
│   │   ├── ocr.py                           # Document AI OCR
│   │   ├── masking.py                       # PII 마스킹 (Gemini 활용)
│   │   └── clause_splitter.py               # 조항 단위 분리
│   │
│   ├── retrieval/                       # 검색
│   │   ├── __init__.py
│   │   ├── query_expansion.py               # Gemini 기반 쿼리 재작성
│   │   ├── bm25_retriever.py                # BM25 키워드 검색 (pgvector ts_rank)
│   │   ├── dense_retriever.py               # Vertex AI Embeddings 유사도 검색
│   │   └── hybrid.py                        # Hybrid Retrieval 통합 + 가중치 조정
│   │
│   ├── reranking/                       # 재순위화
│   │   ├── __init__.py
│   │   └── reranker.py                      # Cross-encoder 기반 재순위화
│   │
│   ├── generation/                      # 응답 생성
│   │   ├── __init__.py
│   │   ├── report_generator.py              # 계약서 분석 보고서 생성 (Gemini)
│   │   └── chat_generator.py                # 챗봇 응답 생성 (Gemini)
│   │
│   └── quality/                         # 품질 제어 루프
│       ├── __init__.py
│       ├── faithfulness.py                  # RAGAS Faithfulness 검증
│       └── rubric_judge.py                  # LRAGE 커스텀 루브릭 평가
│
├── api/                                 # FastAPI 서버 (Cloud Run 배포)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                          # FastAPI 엔트리포인트, CORS, 미들웨어
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── upload.py                    # POST /upload — 계약서 업로드 → GCS 저장
│   │   │   ├── analysis.py                  # POST /analyze — 전처리 → 검색 → 보고서 생성
│   │   │   └── chat.py                      # POST /chat — 챗봇 질의응답
│   │   ├── schemas/                         # Pydantic 요청/응답 모델
│   │   │   ├── __init__.py
│   │   │   ├── upload.py
│   │   │   ├── analysis.py
│   │   │   └── chat.py
│   │   └── dependencies.py                 # DB 세션, GCS 클라이언트 등 공통 의존성
│   ├── Dockerfile
│   └── requirements.txt
│
├── web/                                 # Firebase Hosting 프론트엔드
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── pages/
│   │   │   ├── UploadPage.jsx               # 계약서 업로드 UI
│   │   │   ├── ReportPage.jsx               # 분석 보고서 뷰어
│   │   │   └── ChatPage.jsx                 # 챗봇 UI
│   │   ├── components/                      # 공통 UI 컴포넌트
│   │   ├── services/                        # API 호출 래퍼
│   │   │   └── api.js
│   │   └── App.jsx
│   ├── package.json
│   └── firebase.json
│
├── shared/                              # 공통 인프라 모듈
│   ├── __init__.py
│   ├── config.py                            # 환경변수 로딩 (.env), 공통 설정값
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py                    # Cloud SQL 연결 풀 관리
│   │   └── vector_store.py                  # pgvector CRUD (insert, search, delete)
│   ├── llm/
│   │   ├── __init__.py
│   │   └── gemini_client.py                 # Vertex AI Gemini 공통 래퍼
│   └── storage/
│       ├── __init__.py
│       └── gcs_client.py                    # Cloud Storage 업로드/다운로드
│
├── evaluation/                          # 오프라인 평가
│   ├── datasets/                            # 평가용 데이터셋
│   │   ├── synthetic_contracts/             # 합성 계약서
│   │   └── qa_pairs/                        # 질의-정답 쌍
│   ├── eval_retrieval.py                    # Recall@k, MRR, NDCG 측정
│   ├── eval_lrage.py                        # LRAGE 프레임워크 평가
│   ├── eval_ragas.py                        # RAGAS 평가
│   └── results/                             # 평가 결과 저장 (git 미추적)
│
├── scripts/                             # 배치 실행 스크립트
│   ├── run_ingestion.sh                     # 전체 데이터 수집 파이프라인 실행
│   ├── run_indexing.sh                      # 임베딩 생성 + pgvector 인덱싱
│   └── run_evaluation.sh                    # 오프라인 평가 실행
│
├── tests/                               # 테스트
│   ├── conftest.py                          # pytest 공통 fixture
│   ├── pipeline/
│   │   ├── test_query_expansion.py
│   │   ├── test_retrieval.py
│   │   ├── test_reranker.py
│   │   └── test_preprocessing.py
│   └── api/
│       └── test_routers.py
│
├── infra/                               # GCP 인프라 설정
│   ├── cloudbuild.yaml                      # Cloud Build CI/CD 파이프라인
│   ├── cloud_run/
│   │   └── service.yaml                     # Cloud Run 서비스 정의
│   └── cloud_sql/
│       └── init.sql                         # pgvector 확장 활성화 + 테이블 DDL
│
├── docs/                                # 프로젝트 문서
│   ├── VERTEX_AI_GUIDE.md                   # Vertex AI 사용 가이드
│   ├── ARCHITECTURE.md                      # 시스템 아키텍처 문서
│   ├── API_SPEC.md                          # API 명세
│   ├── DATA_SCHEMA.md                       # 데이터 스키마 정의
│   └── SETUP.md                             # 로컬 개발 환경 구축 가이드
│
└── notebooks/                           # 실험/분석용 노트북
    ├── parser_test.ipynb
    └── rag_experiment.ipynb
```

---

## 3. 각 디렉토리 역할

### 3.1 `.github/` — GitHub 설정

리포지토리 운영에 필요한 GitHub 메타 설정 디렉토리.

| 하위 항목 | 역할 |
|----------|------|
| `workflows/` | GitHub Actions 기반 CI/CD 워크플로우 정의 |
| `ISSUE_TEMPLATE/` | 이슈 템플릿 (버그 리포트, 기능 요청 등) |
| `PULL_REQUEST_TEMPLATE.md` | PR 생성 시 기본 템플릿 |

**브랜치 운영 원칙:**
- `develop`이 default 브랜치.
- 모든 issue 브랜치는 `develop`에서 분기하여 작업 후 `develop`으로 PR.
- `main`은 릴리즈/배포 시점에만 `develop`에서 머지.

### 3.2 `data/` — 1회성 데이터 수집

외부 소스에서 법률 데이터를 수집·전처리하여 Cloud SQL(pgvector)에 적재하는 **배치 작업** 코드.

| 하위 디렉토리 | 역할 |
|--------------|------|
| `collectors/` | 4개 소스(법령, 판례, 상담사례, 분쟁사례 PDF)에서 원시 데이터 수집 |
| `processors/` | 수집된 원시 데이터를 구조화 (예: 법령 XML → 조문 단위, 판례 → 사실관계/판결요지 분리) |
| `indexer.py` | 구조화된 데이터를 Vertex AI Embeddings로 벡터화 후 pgvector에 적재 |
| `raw/` | 원시 데이터 임시 저장 (`.gitignore` 대상) |

**특징:**
- 프로젝트 초반 1회 실행. 데이터 보강이 필요할 때만 재실행.
- 수집 완료 후 코드 동결. 서빙 시 미사용.
- Cloud Run 배포 이미지에 불포함.

### 3.3 `pipeline/` — RAG 파이프라인 (서빙 전용)

사용자 요청이 들어올 때마다 실시간으로 실행되는 RAG 파이프라인.

| 하위 디렉토리 | 역할 | 실행 흐름 순서 |
|--------------|------|--------------|
| `preprocessing/` | 업로드된 계약서 OCR → PII 마스킹 → 조항 분리 | 1단계 |
| `retrieval/` | 쿼리 재작성 → BM25 + Dense 하이브리드 검색 | 2단계 |
| `reranking/` | 검색 결과 재순위화 | 3단계 |
| `generation/` | 분석 보고서 또는 챗봇 응답 생성 | 4단계 |
| `quality/` | Faithfulness/LRAGE 기반 품질 검증. 미달 시 재생성 | 5단계 |

**특징:**
- Cloud Run에 배포되어 API 요청마다 호출.
- 각 단계는 독립 모듈로, 개별 교체·실험 가능.
- `data/`를 import하지 않음. 모든 데이터는 pgvector에서 조회.

### 3.4 `api/` — FastAPI 서버

`pipeline/`을 HTTP API로 노출하는 서버.

| 라우터 | 엔드포인트 | 호출하는 pipeline 모듈 |
|--------|-----------|---------------------|
| `upload.py` | `POST /upload` | 없음 (GCS 저장만) |
| `analysis.py` | `POST /analyze` | preprocessing → retrieval → reranking → generation → quality |
| `chat.py` | `POST /chat` | retrieval → reranking → generation |

### 3.5 `web/` — 프론트엔드

Firebase Hosting 기반의 웹 인터페이스.

| 페이지 | 역할 |
|--------|------|
| `UploadPage` | 계약서 PDF 업로드 |
| `ReportPage` | 분석 보고서 뷰어 |
| `ChatPage` | 챗봇 질의응답 UI |

### 3.6 `shared/` — 공통 인프라 모듈

`data/`, `pipeline/`, `api/`, `evaluation/`에서 공통으로 사용하는 **인프라 래퍼**.

| 모듈 | 역할 |
|------|------|
| `config.py` | 환경변수 로딩, 공통 설정값 |
| `db/connection.py` | Cloud SQL 연결 풀 관리 |
| `db/vector_store.py` | pgvector CRUD (insert, search, delete) |
| `llm/gemini_client.py` | Vertex AI Gemini API 호출 래퍼 |
| `storage/gcs_client.py` | Cloud Storage 업로드/다운로드 |

**원칙: `shared/`에는 비즈니스 로직 금지.**

| 허용 | 금지 |
|---------------|-----------------|
| DB 연결 관리 | RAG 검색 로직 |
| pgvector insert/search 함수 | 보고서 생성 로직 |
| Gemini API 호출 래퍼 | 쿼리 재작성 로직 |
| GCS 업로드/다운로드 | 조항 분리 로직 |
| 환경변수 로딩 | 도메인별 데이터 모델 |

### 3.7 `evaluation/` — 오프라인 평가

RAG 파이프라인의 성능을 검증하는 오프라인 평가 코드.

| 파일 | 역할 |
|------|------|
| `eval_retrieval.py` | Recall@k, MRR, NDCG 측정 |
| `eval_lrage.py` | LRAGE 프레임워크 평가 |
| `eval_ragas.py` | RAGAS 평가 |
| `datasets/` | 합성 계약서, 질의-정답 쌍 등 평가용 데이터셋 |
| `results/` | 평가 결과 저장 (`.gitignore` 대상) |

### 3.8 `docs/` — 프로젝트 문서

팀 내부 참고 및 인수인계용 문서 저장소. 아키텍처, API 명세, 환경 구축 가이드, 외부 서비스 사용법 등 다양한 프로젝트 문서를 보관한다.

| 파일 | 역할 |
|------|------|
| `ARCHITECTURE.md` | 시스템 아키텍처 및 데이터 흐름 |
| `API_SPEC.md` | REST API 엔드포인트 명세 |
| `DATA_SCHEMA.md` | pgvector 테이블 및 메타데이터 스키마 |
| `SETUP.md` | 로컬 개발 환경 구축 가이드 |
| `VERTEX_AI_GUIDE.md` | Vertex AI 사용 가이드 |

### 3.9 기타 디렉토리

| 디렉토리 | 역할 |
|----------|------|
| `scripts/` | 배치 작업 실행 스크립트 (수집, 인덱싱, 평가) |
| `tests/` | pytest 기반 단위 테스트 |
| `infra/` | GCP 인프라 설정 (Cloud Build, Cloud Run, Cloud SQL DDL) |
| `notebooks/` | 실험/분석용 Jupyter 노트북 |

---

## 4. 설계 근거

### 4.1 `data/`와 `pipeline/` 분리

| 기준 | `data/` (수집) | `pipeline/` (서빙) |
|------|---------------|-------------------|
| 실행 시점 | 프로젝트 초반 1회 | API 요청마다 |
| 실행 주체 | 로컬/배치로 수동 실행 | Cloud Run 자동 실행 |
| 의존성 | 법제처 API, 크롤링 라이브러리, Document AI | Vertex AI Embeddings, pgvector |
| 배포 | Cloud Run 불포함 | Cloud Run 포함 |
| 완료 후 | 코드 동결 가능 | 지속 개선 |

- **생명주기 차이**: 수집은 1회성, 서빙은 상시 운영.
- **상호 import 금지**: 서빙 시점에 모든 데이터는 Cloud SQL에 존재하므로 `pipeline/`이 `data/`를 참조할 필요 없음.
- **배포 이미지 경량화**: `data/`를 Cloud Run Docker 이미지에서 제외하여 이미지 크기 축소.

### 4.2 `shared/` 분리

`data/`, `pipeline/`, `api/`, `evaluation/` 모두 pgvector, Gemini, Cloud Storage를 사용. 각 모듈에서 개별 구현 시 연결 설정 불일치, 환경변수 중복 로딩, 클라이언트 초기화 불일치 위험 존재.

단, `shared/`에는 **인프라 래퍼만** 두고 비즈니스 로직 금지. 이 경계를 유지해야 4명 팀에서 관리 오버헤드가 최소화된다.

### 4.3 `scripts/` 분리

`data/` 내 코드는 **import 가능한 모듈**(라이브러리), `scripts/`는 이를 **조합하여 실행하는 진입점**.

분리 효과:
- 개별 collector의 독립 개발·테스트 가능.
- 전체 실행 순서와 옵션은 스크립트에서 관리.
- CI/CD에서 스크립트 직접 호출 가능.

---

## 5. 데이터 흐름

### 5.1 배치: 데이터 수집 → 인덱싱 (`data/` — 1회성)

```
[법제처 API] → collectors/law_collector → processors/law_processor ─────────┐
[판례 소스]  → collectors/case_collector → processors/case_processor ────────┤
[상담사례]   → collectors/counsel_crawler → processors/counsel_extractor ────┤→ indexer → pgvector
[분쟁 PDF]   → collectors/dispute_pdf_parser → processors/dispute_processor ┘

※ 수집 완료 후 data/ 코드는 동결. 이후 서빙은 pgvector만 참조.
```

### 5.2 서빙: 계약서 분석 요청 (`pipeline/` — Cloud Run)

```
[사용자] → web/ → POST /upload → GCS 저장
        → web/ → POST /analyze
                    ↓
              pipeline/preprocessing/
              ocr → masking → clause_splitter
                    ↓
              pipeline/retrieval/
              query_expansion → hybrid (bm25 + dense) → pgvector
                    ↓
              pipeline/reranking/reranker
                    ↓
              pipeline/generation/report_generator
                    ↓
              pipeline/quality/faithfulness
                    ↓ (품질 미달 시 재생성)
              ← 분석 보고서 응답
```

### 5.3 서빙: 챗봇 질의 (`pipeline/` — Cloud Run)

```
[사용자] → web/ → POST /chat
                    ↓
              pipeline/retrieval/
              query_expansion → hybrid → pgvector
                    ↓
              pipeline/reranking/reranker
                    ↓
              pipeline/generation/chat_generator
                    ↓
              ← 챗봇 응답
```

---

## 6. 주요 파일 예시

> **아래 코드는 각 파일의 역할과 인터페이스를 설명하기 위한 예시다.
> 실제 구현 시 클래스명, 메서드 시그니처, 파라미터, 반환 타입 등은 달라질 수 있다.**

### 6.1 `shared/config.py`

모든 모듈이 참조하는 환경변수와 설정값을 중앙 관리.

```python
# 예시 — 실제 구현과 다를 수 있음
import os
from dotenv import load_dotenv

load_dotenv()

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]       # dcsd-ade
GCP_LOCATION = os.environ["GCP_LOCATION"]            # us-central1
CLOUD_SQL_CONNECTION = os.environ["CLOUD_SQL_CONNECTION"]
GCS_BUCKET = os.environ["GCS_BUCKET"]
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
```

### 6.2 `shared/db/vector_store.py`

pgvector 접근을 추상화. 수집(`data/`)과 RAG(`pipeline/`)의 공통 인터페이스.

```python
# 예시 — 실제 구현과 다를 수 있음
class VectorStore:
    def insert(self, doc_id: str, text: str, embedding: list[float], metadata: dict): ...
    def search_dense(self, query_embedding: list[float], top_k: int) -> list[dict]: ...
    def search_bm25(self, query: str, top_k: int) -> list[dict]: ...
    def search_hybrid(self, query: str, query_embedding: list[float], top_k: int, alpha: float) -> list[dict]: ...
```

### 6.3 `infra/cloud_sql/init.sql`

pgvector 확장과 테이블 스키마 정의.

```sql
-- 예시 — 실제 스키마는 개발 과정에서 변경될 수 있음
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id          TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,          -- 'law' | 'case' | 'counsel' | 'dispute'
    title       TEXT,
    content     TEXT NOT NULL,
    metadata    JSONB,
    embedding   vector(768),            -- Vertex AI text-embedding 차원
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_documents_embedding ON documents
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

---

## 7. 환경 설정

### `.env.example`

```env
# GCP
GCP_PROJECT_ID=dcsd-ade
GCP_LOCATION=us-central1

# Cloud SQL (pgvector)
CLOUD_SQL_CONNECTION=dcsd-ade:us-central1:ade-lease-db
DB_USER=
DB_PASSWORD=
DB_NAME=ade_lease

# Cloud Storage
GCS_BUCKET=ade-lease-contracts

# 모델
GEMINI_MODEL=gemini-2.5-flash
```

### `.gitignore` 권장 사항

```gitignore
# 환경 설정
.env
*.json
!package.json
!firebase.json

# 데이터 (용량 큼)
data/raw/
evaluation/results/

# Python
__pycache__/
*.pyc
.venv/

# Node
node_modules/
web/dist/

# IDE
.vscode/
.idea/

# GCP
google-cloud-sdk/
```
