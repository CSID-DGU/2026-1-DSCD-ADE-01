# Contributing Guide

> 본 문서는 팀원 모두가 일관된 방식으로 협업하기 위한 GitHub 컨벤션 가이드입니다.
> 작업 전 반드시 숙지해주세요.

---

## 📌 목차

1. [브랜치 전략](#1-브랜치-전략)
2. [커밋 메시지 컨벤션](#2-커밋-메시지-컨벤션)
3. [Issue 작성 가이드](#3-issue-작성-가이드)
4. [Pull Request 가이드](#4-pull-request-가이드)
5. [코드 리뷰 규칙](#5-코드-리뷰-규칙)
6. [라벨 체계](#6-라벨-체계)

---

## 1. 브랜치 전략

**Git Flow 변형**으로 운영합니다.

- `main`: 릴리즈/배포 시점에만 갱신되는 안정 브랜치. 항상 배포 가능한 상태 유지.
- `develop`: **기본(default) 브랜치**. 모든 일상 개발이 통합되는 브랜치.
- `feature/*`, `bugfix/*` 등 모든 이슈 브랜치는 **`develop`에서 분기**하여 작업 후 다시 `develop`으로 PR.
- `main`은 `develop`에서만 머지 (릴리즈 시점).

### 브랜치 네이밍 규칙

```
<type>/<issue번호>-<간단한-설명>
```

| 접두사 | 용도 | 예시 |
|--------|------|------|
| `feature/` | 새로운 기능 개발 | `feature/12-social-login` |
| `bugfix/` | 버그 수정 | `bugfix/27-fix-null-pointer` |
| `hotfix/` | 긴급 수정 | `hotfix/critical-db-error` |
| `docs/` | 문서 작업 | `docs/update-api-spec` |
| `refactor/` | 코드 리팩토링 | `refactor/15-clean-auth-module` |
| `test/` | 테스트 추가/수정 | `test/18-add-login-test` |

### 규칙

- **소문자**와 **하이픈(`-`)**만 사용합니다.
- 영어로 작성합니다.
- Issue 번호를 반드시 포함합니다 (Issue 없이 작업하는 경우 `no-ref` 사용).
- `main`, `develop` 브랜치에 **직접 push 금지**. 반드시 PR을 통해 머지합니다.
- 머지 완료 후 해당 브랜치는 삭제합니다.

### 작업 흐름

```
1. Issue 생성
2. develop 최신화: git checkout develop && git pull
3. 브랜치 생성: git checkout -b feature/12-social-login
4. 작업 및 커밋
5. 원격 push: git push origin feature/12-social-login
6. PR 생성 (base: develop) → 코드 리뷰 → 승인
7. develop에 머지 → 브랜치 삭제
8. (릴리즈 시) develop → main PR로 배포
```

---

## 2. 커밋 메시지 컨벤션

[Conventional Commits](https://www.conventionalcommits.org/) 규약을 따릅니다.

### 형식

```
<type>(<scope>): <description>

[선택] 본문 - 무엇을 왜 변경했는지 설명

[선택] 꼬리말 - 관련 이슈 번호 등
```

### Type 종류

| Type | 설명 | 예시 |
|------|------|------|
| `feat` | 새로운 기능 추가 | `feat(auth): 소셜 로그인 기능 추가` |
| `fix` | 버그 수정 | `fix(api): 사용자 조회 시 null 에러 수정` |
| `docs` | 문서 변경 | `docs(readme): 설치 방법 업데이트` |
| `style` | 코드 포맷팅 (기능 변경 X) | `style(ui): 들여쓰기 통일` |
| `refactor` | 리팩토링 (기능 변경 X) | `refactor(auth): 토큰 검증 로직 분리` |
| `test` | 테스트 추가/수정 | `test(login): 로그인 실패 케이스 추가` |
| `chore` | 빌드, 패키지 등 기타 | `chore: eslint 설정 변경` |
| `ci` | CI/CD 설정 변경 | `ci: GitHub Actions 워크플로우 추가` |

### Scope (선택)

변경이 영향을 미치는 모듈명을 괄호 안에 적습니다.

예: `auth`, `api`, `ui`, `db`, `config`

### 작성 규칙

- **제목은 50자 이내**로 작성합니다 (최대 72자).
- 제목 끝에 마침표(`.`)를 붙이지 않습니다.
- **명령형/명사형**으로 작성합니다: "추가", "수정", "변경" (O) / "추가했음", "수정함" (X)
- 본문은 **무엇을**, **왜** 변경했는지를 설명합니다. 어떻게는 코드가 보여줍니다.
- 관련 이슈가 있으면 꼬리말에 `Refs: #이슈번호`를 추가합니다.

### 좋은 예시 vs 나쁜 예시

```
# ✅ 좋은 예시
feat(auth): 카카오 소셜 로그인 추가

OAuth2 인증 흐름을 구현하여 카카오 계정으로
로그인할 수 있도록 함

Refs: #12

# ❌ 나쁜 예시
수정함
로그인 관련 작업
fix bug
update
```

---

## 3. Issue 작성 가이드

모든 작업은 Issue로 시작합니다. 작업 유형에 맞는 템플릿을 선택해 작성해주세요.

### Issue 템플릿 종류

| 템플릿 | 용도 | 기본 라벨 |
|--------|------|----------|
| ✨ **Feature** | 새로 추가할 기능을 정의하고 상세 설계를 기술 | `type:feature`, `priority:medium` |
| 🐛 **Bug Report** | 버그 재현 단계와 기대 동작을 기록 | `type:bug`, `priority:medium` |
| ♻️ **Refactor** | 기능 변경 없이 코드 구조/가독성/성능 개선 | `type:refactor`, `priority:medium` |
| 🧹 **Chore** | 빌드, 의존성, 설정 등 비기능적 잡무 작업 | `type:chore`, `priority:low` |
| 📝 **Docs** | 문서 추가/수정 작업 | `type:docs`, `priority:low` |

템플릿 파일 위치: `.github/ISSUE_TEMPLATE/`

### Issue 제목 형식

```
[카테고리] 간결한 설명
```

예시:
- `[Feature] 카카오 소셜 로그인 기능 구현`
- `[Bug] 로그인 페이지 비밀번호 입력 시 크래시`
- `[Refactor] 인증 모듈 토큰 검증 로직 분리`
- `[Chore] GitHub Actions Python 버전 업그레이드`
- `[Docs] API 명세서 업데이트`

### 작성 시 유의사항

- 하나의 Issue에는 **하나의 작업**만 담습니다.
- 담당자(Assignee)를 반드시 지정합니다.
- 적절한 라벨을 부착합니다.
- 마일스톤이 있다면 연결합니다.
- Feature 이슈는 **수용 기준(Acceptance Criteria)**을 명확히 기술합니다.
- Refactor 이슈는 **기능 동작이 변경되지 않음**을 전제로 합니다.

---

## 4. Pull Request 가이드

### PR 제목 형식

```
[Type] 간결한 설명 (#이슈번호)
```

예시:
- `[Feature] 카카오 소셜 로그인 구현 (#12)`
- `[Fix] 사용자 조회 null 에러 수정 (#27)`
- `[Refactor] 인증 모듈 구조 개선 (#15)`

### PR 작성 규칙

- PR 템플릿의 모든 항목을 작성합니다.
- `closes #이슈번호`를 본문에 포함하여 자동 이슈 종료를 활용합니다.
- 리뷰어를 최소 **1명** 지정합니다.
- 체크리스트를 모두 확인한 후 리뷰를 요청합니다.
- PR당 변경 파일은 가능하면 **10개 이하**로 유지합니다 (리뷰 효율).

---

## 5. 코드 리뷰 규칙

- 리뷰 요청을 받으면 **24시간 이내**에 리뷰합니다.
- 최소 **1명의 Approve**를 받아야 머지할 수 있습니다.
- 리뷰 시 아래 사항을 확인합니다:
  - 코드가 정상 동작하는가?
  - 컨벤션을 준수했는가?
  - 불필요한 코드나 주석은 없는가?
  - 테스트가 충분한가?
- 리뷰 코멘트는 건설적으로 작성합니다.

---

## 6. 라벨 체계

### Type (유형)

| 라벨 | 설명 | 색상 |
|------|------|------|
| `type:feature` | 새로운 기능 | 🔵 `#1D76DB` |
| `type:bug` | 버그 | 🔴 `#D73A4A` |
| `type:docs` | 문서 | 🟢 `#0E8A16` |
| `type:refactor` | 리팩토링 | 🟡 `#FBCA04` |
| `type:test` | 테스트 | 🟠 `#E99695` |
| `type:chore` | 기타 잡일 | ⚪ `#EDEDED` |

### Priority (우선순위)

| 라벨 | 설명 | 색상 |
|------|------|------|
| `priority:high` | 긴급 | 🔴 `#B60205` |
| `priority:medium` | 보통 | 🟡 `#FBCA04` |
| `priority:low` | 낮음 | 🟢 `#0E8A16` |

### Status (상태)

| 라벨 | 설명 | 색상 |
|------|------|------|
| `status:ready` | 작업 시작 가능 | `#C2E0C6` |
| `status:in-progress` | 작업 중 | `#0052CC` |
| `status:review` | 리뷰 대기 | `#5319E7` |
| `status:done` | 완료 | `#006B75` |

---

## 🔗 참고 자료

- [Conventional Commits](https://www.conventionalcommits.org/ko/v1.0.0/)
- [A successful Git branching model (Git Flow)](https://nvie.com/posts/a-successful-git-branching-model/)
- [How to Write a Git Commit Message](https://cbea.ms/git-commit/)
