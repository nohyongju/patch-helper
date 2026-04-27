# Patch Helper - 설계 문서

MSA 백엔드 서비스의 패치가이드를 AI 활용해서 자동 생성하는 Slack Bot 도구.

---

## 1. 개요

### 배경
- MSA 서비스 약 20개 운영 중 (개별 GitHub repo)
- 패치가이드를 수동으로 작성하고 있음
- MySQL, Oracle, Elasticsearch 구조변경, 설정 변경(yml), Init Data 등의 내용을 가이드로 작성
- DB 마이그레이션 도구(Flyway, Liquibase 등) 미사용, 수동 SQL 관리
- JPA 사용, `@Entity`, `@Table`, `@Column`, `@Index` 등 어노테이션 기반

### 목표
- AI(OpenAI API)를 활용하여 패치가이드 자동 생성
- Slack Bot으로 편리하게 트리거
- 결과를 Slack에서 바로 확인하거나, 특정 repo에 PR로 생성

---

## 2. 분석 대상

### 핵심: Java 소스코드가 분석 대상

SQL 파일이나 별도 마이그레이션 파일이 아니라, **Java 소스코드의 변경사항**을 분석하여 패치가이드를 생성한다.

### 2.1 서비스 repo (예: dworks-cstalk, bizasset, aibiz)

| 파일 패턴 | 감지 내용 | AI가 분석할 것 |
|----------|----------|---------------|
| `*Jpo.java` 변경 | DB 스키마 변경 | JPA 어노테이션 분석 → 컬럼 추가/삭제/변경, 테이블명 변경, 인덱스 변경 → MySQL/Oracle DDL 생성 |
| `*Doc.java` 변경 | ES 구조 변경 | Spring Data ES 어노테이션 분석 → 필드 추가/삭제/변경, 매핑 타입 → ES 변경 가이드 생성 |
| Init/seed 파일 | Init Data | MySQL/Oracle INSERT 생성 |

### 2.2 설정 repo (dworks-common-resource)

| 파일 패턴 | 감지 내용 | AI가 분석할 것 |
|----------|----------|---------------|
| `registry-config/**/*.yml` | 설정 변경 | 추가/삭제/변경된 설정 항목 정리 |

설정은 각 서비스 repo의 application.yml이 아니라, **별도 repo**(`dworks-common-resource/registry-config/`)에서 관리한다.
- 공통 설정 yml 존재
- 서비스별 `{서비스명}.yml` 존재

### 2.3 초기 데이터 repo (dworks-common-initial)

| 파일 패턴 | 감지 내용 | AI가 분석할 것 |
|----------|----------|---------------|
| `setup/**/json-data/**/*.json` | 초기 데이터 변경 | JSON 데이터 변경사항 분석 → curl 스크립트 / sh 스크립트 / 변경사항 요약 |

초기 데이터는 **API 호출 기반**으로 관리된다:
- `setup/{서비스}/json-data/` 하위에 JSON 데이터 파일 존재
- 설정 JSON (예: `1_cstalk-setting.json`)에 API 매핑 정의:
  - `ActionURI`: API 엔드포인트 (예: `/applications/settings`)
  - `ActionType`: HTTP 메서드 (POST, PUT 등)
  - `DataFile`: 실제 데이터 JSON 파일 경로
  - `Header`: 필요한 헤더 (예: `X-Attic-Authority`)
- 데이터 JSON 파일에 실제 요청 body 정의

#### 초기 데이터 출력 형태 (3가지 지원)

**1. curl 스크립트 생성 (권장)**
```bash
#!/bin/bash
# 패치가이드: dworks-common-initial v1.0 → v1.1

# 설정 변경 (2_setting.json 변경됨)
curl -X PUT http://localhost:8040/cstalk/applications/settings \
  -H "Content-Type: application/json" \
  -d '[{"manualMaskingEnabled": true}]'
```
→ 변경된 JSON 파일에 대응하는 API 호출을 curl 명령어로 자동 생성

**2. sh 실행 스크립트 생성**
→ 기존 `data-initialize.js` 방식과 호환되는 형태로, 변경된 파일만 실행하는 스크립트

**3. 변경사항 요약 문서**
→ 변경된 JSON 파일 목록, 변경 내용 diff, 실행 대상 API 정리

### 2.4 사용 방식

서비스 repo, 설정 repo, 초기 데이터 repo는 **별도로 요청**한다:

```
# 서비스 코드 변경 분석
@patch-helper 생성해줘 → dworks-cstalk, tag, v1.0, v1.1

# 설정 변경 분석 (별도 요청)
@patch-helper 생성해줘 → dworks-common-resource, tag, v1.0, v1.1

# 초기 데이터 변경 분석 (별도 요청)
@patch-helper 생성해줘 → dworks-common-initial, tag, v1.0, v1.1
```

같은 도구, 같은 흐름. repo만 다르게 지정하면 됨.

### 2.4 테이블 네이밍 규칙

| repo | 테이블명 패턴 | 예시 |
|------|-------------|------|
| dworks-cstalk | `cstalk_{도메인명}` | PartnerJpo.java → `cstalk_partner` |
| bizasset | `cstalk_{도메인명}` | |
| aibiz | `cstalk_{도메인명}` | |

실제 테이블명은 `@Table(name = "...")` 어노테이션에서 확인.

---

## 3. 사용자 경험 (Slack)

### 3.1 대화형 버튼 UI

```
🧑 김개발:
@patch-helper 생성해줘

🤖 patch-helper:
서비스를 선택해주세요.

[dworks-cstalk] [bizasset] [aibiz]
[dworks-common-resource] [dworks-common-initial] [더 보기...]

                ↓ dworks-cstalk 클릭

🤖 patch-helper:
비교 방식을 선택해주세요.

[태그 비교]  [날짜 구간]

                ↓ 태그 비교 클릭

🤖 patch-helper:
시작 태그와 종료 태그를 입력해주세요.
예: v1.0 v1.1

🧑 김개발:
v1.0 v1.1

                ↓

🤖 patch-helper:
결과를 어떻게 받으시겠어요?

[여기서 바로 보기]  [repo에 PR 생성]

                ↓ 여기서 바로 보기 클릭

🤖 patch-helper:
⏳ dworks-cstalk (v1.0 → v1.1) 생성 중...

🤖 patch-helper:
┌────────────────────────────────────────────────┐
│ ✅ dworks-cstalk 패치가이드 (v1.0 → v1.1)       │
│                                                │
│ 🗄️ DB 변경: 3건 (MySQL + Oracle)                │
│ ⚙️ 설정 변경: 2건                               │
│ 📦 Init Data: 1건                              │
│ 🔍 ES 변경: 없음                                │
│                                                │
│ [상세 보기]  [repo에 저장]                        │
└────────────────────────────────────────────────┘
```

### 3.2 입력 파라미터

| 파라미터 | 설명 | 예시 |
|---------|------|------|
| 서비스 | 대상 repo | dworks-cstalk, dworks-common-resource, dworks-common-initial |
| 비교 방식 | 태그 비교 또는 날짜 구간 | tag / date |
| 시작/종료 (태그) | from tag ~ to tag | v1.0 ~ v1.1 |
| 브랜치 (날짜) | 대상 브랜치 | develop |
| 시작/종료 (날짜) | from date ~ to date | 2026-04-01 ~ 2026-04-25 |
| 결과 처리 | Slack 표시 또는 repo PR 생성 | 바로 보기 / PR 생성 |

### 3.3 결과 확인

**A. Slack에서 바로 보기**
- 요약 메시지 + 버튼
- "상세 보기" 클릭 시 스레드에 전체 내용 펼침
- 나중에 "repo에 저장" 버튼으로 PR 생성 가능

**B. repo에 PR 생성**
- patch-guides repo에 파일 push
- PR 자동 생성
- Slack에 PR 링크 전달

---

## 4. 내부 처리 흐름

```
Step 1. 변경사항 수집 (코드, GitHub API)
    ↓
Step 2. 파일 분류 (코드, 파일명 패턴 매칭)
    ↓
Step 3. AI 분석 (⭐ OpenAI API)
    ↓
Step 4. 문서 생성 (코드 + ⭐ OpenAI API)
    ↓
Step 5. 결과 전달 (코드, Slack API / GitHub API)
```

### Step 1. 변경사항 수집

GitHub API로 원격 diff 조회. 로컬에 코드를 clone/pull 할 필요 없음.

**태그 모드:**
```
GET /repos/{owner}/{repo}/compare/{fromTag}...{toTag}
```

**날짜 모드:**
```
GET /repos/{owner}/{repo}/commits?sha={branch}&since={fromDate}&until={toDate}
→ 해당 구간 커밋들의 diff 수집
```

결과: 변경된 파일 목록 + 각 파일의 diff 내용

### Step 2. 파일 분류

**파일명 패턴 매칭**으로 카테고리 분류:

#### 서비스 repo 분류 규칙

| 패턴 | 카테고리 | 설명 |
|-----|---------|------|
| `*Jpo.java` | DB 변경 | JPA Entity → DB 스키마 변경 감지 |
| `*Doc.java` | ES 변경 | ES Document → ES 구조 변경 감지 |
| `*init*`, `*seed*`, `data.sql` | Init Data | 초기 데이터 변경 |
| 그 외 (`*.java`, `*.gradle` 등) | **무시** | 패치가이드 대상 아님 |

#### 설정 repo (dworks-common-resource) 분류 규칙

| 패턴 | 카테고리 | 설명 |
|-----|---------|------|
| `registry-config/**/*.yml` | 설정 변경 | 서비스 설정 변경 |

#### 초기 데이터 repo (dworks-common-initial) 분류 규칙

| 패턴 | 카테고리 | 설명 |
|-----|---------|------|
| `setup/**/json-data/**/*.json` | 초기 데이터 변경 | API 호출 기반 데이터 변경 |
| `setup/**/*-setting.json` | 초기 데이터 매핑 | API 매핑 정의 변경 (URI, Method 등) |
| `setup/**/*.sh` | 실행 스크립트 변경 | 초기화 스크립트 변경 |

결과: 카테고리별로 분류된 diff 묶음

### Step 3. AI 분석 (⭐ OpenAI API)

카테고리별로 프롬프트를 나눠서 OpenAI API 호출.
**핵심: Java 소스코드의 diff를 읽고, JPA/ES 어노테이션을 해석하여 DDL/쿼리를 생성한다.**

**3-1. DB 변경 분석 (`*Jpo.java` diff)**
- 입력: Jpo.java의 diff (JPA 어노테이션 포함)
- AI가 해석할 것:
  - `@Table(name=...)` → 테이블명
  - `@Column(name=..., length=..., nullable=...)` → 컬럼 정의
  - `@Index(name=..., columnList=...)` → 인덱스 정의
  - 필드 추가/삭제 → 컬럼 추가/삭제
  - 어노테이션 변경 → 컬럼 타입/제약조건 변경
  - 테이블명 변경, 인덱스 추가/삭제
- 출력:
  - MySQL DDL + 한글 코멘트
  - Oracle DDL + 한글 코멘트 (변환)
  - 실행 순서, 주의사항
  - 롤백 쿼리

**3-2. ES 변경 분석 (`*Doc.java` diff)**
- 입력: Doc.java의 diff (Spring Data ES 어노테이션 포함)
- AI가 해석할 것:
  - `@Document(indexName=...)` → 인덱스명
  - `@Field(type=FieldType.Keyword)` → 필드 매핑 타입
  - 필드 추가/삭제/변경
- 출력:
  - 인덱스 변경사항
  - reindex 필요 여부
  - ES API 호출 가이드

**3-3. 설정 변경 분석 (`*.yml` diff)**
- 입력: yml diff
- 출력:
  - 추가/삭제/변경된 설정 항목 정리
  - 설정 목적 설명
  - 환경별(dev/stg/prod) 주의사항

**3-4. Init Data 분석 (서비스 repo 내 init/seed 파일)**
- 입력: data diff
- 출력:
  - MySQL INSERT + 한글 코멘트
  - Oracle INSERT + 한글 코멘트
  - 실행 시점 (배포 전/후)

**3-5. 초기 데이터 분석 (`dworks-common-initial` repo)**
- 입력: JSON 데이터 파일 diff + API 매핑 정의 (ActionURI, ActionType, Header)
- AI가 해석할 것:
  - 변경된 JSON 데이터 파일 식별
  - 해당 파일에 매핑된 API 엔드포인트 확인 (설정 JSON에서 조회)
  - 변경 내용 해석 (필드 추가/삭제/값 변경)
- 출력 (3가지 형태):
  - **curl 스크립트**: 변경된 데이터에 대응하는 curl 명령어 자동 생성
    - 설정 JSON의 ActionURI, ActionType, Header 정보 활용
    - 변경된 JSON 파일의 내용을 -d 파라미터로 포함
  - **sh 실행 스크립트**: 기존 data-initialize.js 방식과 호환되는 형태
  - **변경사항 요약**: 변경 파일 목록, diff 내용, 실행 대상 API 정리

**3-6. 전체 종합**
- 입력: 위 3-1 ~ 3-4 결과 전부
- 출력:
  - 전체 배포 순서
  - 서비스 간 의존성 주의사항
  - 최종 검증 체크리스트

### Step 4. 문서 생성

Jinja2 템플릿 기반으로 문서 조립. AI가 자연어 설명, 순서 정리, 코멘트 작성.

출력물 (repo 유형에 따라 다름):

**서비스 repo 분석 시:**
- `patch-guide.md` - 전체 가이드
- `mysql-ddl.sql` - MySQL DDL 쿼리 + 코멘트
- `oracle-ddl.sql` - Oracle DDL 쿼리 + 코멘트
- `mysql-init-data.sql` - MySQL 초기 데이터 + 코멘트
- `oracle-init-data.sql` - Oracle 초기 데이터 + 코멘트
- `es-migration.json` - ES 변경사항 (있을 경우)

**설정 repo (dworks-common-resource) 분석 시:**
- `patch-guide.md` - 설정 변경 가이드

**초기 데이터 repo (dworks-common-initial) 분석 시:**
- `patch-guide.md` - 초기 데이터 변경 가이드
- `init-data.sh` - curl 스크립트 (변경된 데이터 API 호출용)
- `init-data-summary.md` - 변경사항 요약 (변경 파일, API 목록, diff)

### Step 5. 결과 전달

**A. Slack에서 바로 보기**
- Slack Block Kit으로 요약 메시지 전송
- "상세 보기" 버튼 → 스레드에 전체 내용

**B. repo에 PR 생성**
- GitHub API로 patch-guides repo에 파일 push
- PR 자동 생성
- Slack에 PR 링크 전달

---

## 5. AI 분석 상세 예시

### 5.1 Jpo.java diff → DB DDL 생성

**입력 (GitHub API diff):**
```diff
// OrderJpo.java
 @Entity
 @Table(name = "cstalk_order", indexes = {
-    @Index(name = "idx_status", columnList = "status")
+    @Index(name = "idx_status", columnList = "status"),
+    @Index(name = "idx_cancel", columnList = "cancel_reason")
 })
 public class OrderJpo {
     @Id
     private Long id;

     @Column(name = "status", length = 20)
     private String status;

+    @Column(name = "cancel_reason", length = 200)
+    private String cancelReason;
 }
```

**AI 분석 결과:**

MySQL:
```sql
-- 주문 취소사유 컬럼 추가
ALTER TABLE cstalk_order
  ADD COLUMN cancel_reason VARCHAR(200) COMMENT '취소사유';

-- 취소사유 인덱스 추가
CREATE INDEX idx_cancel ON cstalk_order(cancel_reason);
```

Oracle:
```sql
-- 주문 취소사유 컬럼 추가
ALTER TABLE CSTALK_ORDER
  ADD (CANCEL_REASON VARCHAR2(200));
COMMENT ON COLUMN CSTALK_ORDER.CANCEL_REASON IS '취소사유';

-- 취소사유 인덱스 추가
CREATE INDEX IDX_CANCEL ON CSTALK_ORDER(CANCEL_REASON);
```

### 5.2 Doc.java diff → ES 변경 가이드

**입력 (GitHub API diff):**
```diff
// OrderDoc.java
 @Document(indexName = "cstalk-order")
 public class OrderDoc {
     private String id;
     private String status;

+    @Field(type = FieldType.Keyword)
+    private String cancelReason;
 }
```

**AI 분석 결과:**
```
인덱스: cstalk-order
변경: cancelReason 필드 추가 (Keyword 타입)
reindex 필요 여부: 아니오 (필드 추가는 매핑 업데이트로 가능)

PUT cstalk-order/_mapping
{
  "properties": {
    "cancelReason": {
      "type": "keyword"
    }
  }
}
```

### 5.3 초기 데이터 JSON diff → curl 스크립트

**입력 (GitHub API diff):**

설정 JSON (`1_cstalk-setting.json`)에서 API 매핑 확인:
```json
{
  "ActionURI": "/applications/settings",
  "ActionType": "PUT",
  "DataFile": "2_setting.json"
}
```

데이터 JSON diff (`2_setting.json`):
```diff
 [
   {
-    "manualMaskingEnabled": false
+    "manualMaskingEnabled": true
   }
 ]
```

**AI 분석 결과:**

curl 스크립트 (`init-data.sh`):
```bash
#!/bin/bash
# ===========================================
# 패치가이드: dworks-common-initial v1.0 → v1.1
# 생성일: 2026-04-27
# ===========================================

# 마스킹 설정 변경 (manualMaskingEnabled: false → true)
curl -X PUT http://localhost:8040/cstalk/applications/settings \
  -H "Content-Type: application/json" \
  -d '[{"manualMaskingEnabled": true}]'
```

변경사항 요약 (`init-data-summary.md`):
```markdown
## 초기 데이터 변경사항

### 변경된 파일
| 파일 | 변경 유형 | API | Method |
|------|----------|-----|--------|
| cstalk/2_setting.json | 수정 | /applications/settings | PUT |

### 상세 변경 내용
- **2_setting.json**: manualMaskingEnabled 값 변경 (false → true)
```

---

## 6. 아키텍처

```
┌──────────┐           ┌──────────────────────┐
│  Slack   │◄────────►│  내 PC (WSL)          │
│          │  Socket   │                      │
│ 대화형   │  Mode     │  patch_helper Bot    │
│ 버튼UI   │           │                      │
│ 결과표시  │           │  ┌─ core/ ─────────┐ │
└──────────┘           │  │ collector      │ │──► GitHub API (diff 조회)
                       │  │ classifier     │ │
                       │  │ analyzer       │ │──► OpenAI API (AI 분석)
                       │  │ generator      │ │
                       │  └────────────────┘ │
                       │                      │
                       │  publisher/          │
                       │  ├─ slack            │──► Slack API (결과 전송)
                       │  └─ github           │──► GitHub API (PR 생성)
                       └──────────────────────┘
```

### 핵심 포인트
- **서버 불필요**: 내 PC에서 실행 (Socket Mode, URL 필요 없음)
- **코드 clone 불필요**: GitHub API로 원격 diff 조회
- **비용**: OpenAI API만 (나머지 전부 무료)
- **이동 가능**: 나중에 사내 서버로 코드 그대로 옮기면 됨

---

## 7. 기술 스택

| 구성 | 선택 | 비고 |
|-----|------|------|
| 언어 | Python 3.11+ | |
| Slack 연동 | Slack Bolt (Socket Mode) | URL 불필요, 서버 불필요 |
| GitHub 연동 | PyGithub | diff 조회, PR 생성 |
| AI | OpenAI API (GPT-4o) | JPA/ES 어노테이션 분석, 쿼리 변환, 가이드 작성 |
| 템플릿 | Jinja2 | md/sql 파일 생성 |
| 설정 관리 | pydantic-settings | 환경변수, .env 파일 |
| 패키징 | Poetry | 의존성 관리 |

---

## 8. 프로젝트 구조

```
patch_helper/
├── pyproject.toml
├── .env.example
├── design.md                       # 이 문서
│
├── src/
│   └── patch_helper/
│       ├── __init__.py
│       ├── config.py               # 설정 (API 키, repo 정보 등)
│       │
│       ├── core/                   # 핵심 엔진
│       │   ├── __init__.py
│       │   ├── collector.py        # GitHub API diff 수집
│       │   ├── classifier.py       # 파일 분류 (패턴 매칭)
│       │   ├── analyzer.py         # OpenAI 분석 (JPA/ES 어노테이션 해석)
│       │   ├── generator.py        # 문서 생성 (Jinja2)
│       │   └── models.py           # 데이터 모델
│       │
│       ├── prompts/                # OpenAI 프롬프트 템플릿
│       │   ├── db_analysis.py      # Jpo.java diff → MySQL/Oracle DDL
│       │   ├── config_analysis.py  # yml diff → 설정 변경 정리
│       │   ├── es_analysis.py      # Doc.java diff → ES 변경 가이드
│       │   ├── data_analysis.py    # init data → MySQL/Oracle INSERT
│       │   ├── initial_data_analysis.py  # 초기 데이터 JSON diff → curl/sh/요약
│       │   └── summary.py          # 전체 종합 (배포순서, 체크리스트)
│       │
│       ├── templates/              # Jinja2 출력 템플릿
│       │   ├── patch-guide.md.j2
│       │   ├── mysql-ddl.sql.j2
│       │   ├── oracle-ddl.sql.j2
│       │   ├── mysql-init-data.sql.j2
│       │   └── oracle-init-data.sql.j2
│       │
│       ├── publisher/              # 결과 전달
│       │   ├── __init__.py
│       │   ├── slack_publisher.py  # Slack Block Kit 메시지 전송
│       │   └── github_publisher.py # repo push + PR 생성
│       │
│       ├── bot/                    # Slack Bot
│       │   ├── __init__.py
│       │   ├── app.py              # Slack Bolt 앱 (Socket Mode 진입점)
│       │   ├── commands.py         # 메시지/명령어 핸들러
│       │   └── views.py            # 버튼/인터랙션 핸들러
│       │
│       └── cli.py                  # 로컬 테스트용 CLI
│
└── tests/
    ├── test_collector.py
    ├── test_classifier.py
    ├── test_analyzer.py
    └── test_generator.py
```

---

## 9. 환경 변수

```env
# Slack
SLACK_BOT_TOKEN=xoxb-xxxxxxxxxxxx
SLACK_APP_TOKEN=xapp-xxxxxxxxxxxx

# GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
GITHUB_ORG=org-name

# OpenAI
OPENAI_API_KEY=sk-xxxxxxxxxxxx
OPENAI_MODEL=gpt-4o

# 결과 저장 repo
PATCH_GUIDES_REPO=org-name/patch-guides
```

---

## 10. 출력물 예시

### patch-guide.md

```markdown
# 패치가이드 - dworks-cstalk v1.0 → v1.1
> 생성일: 2026-04-26

## 1. DB 변경 (배포 전 실행)

### MySQL
- cstalk_order 테이블에 cancel_reason 컬럼 추가
- cstalk_order 테이블에 idx_cancel 인덱스 추가

### Oracle
- CSTALK_ORDER 테이블에 CANCEL_REASON 컬럼 추가
- CSTALK_ORDER 테이블에 IDX_CANCEL 인덱스 추가

⚠️ 주의: 데이터량이 많은 경우 점검시간에 실행 권장

## 2. ES 변경
- cstalk-order 인덱스에 cancelReason 필드 추가 (Keyword)
- reindex 불필요

## 3. Init Data (배포 후 실행)
- 취소사유 코드 마스터 데이터 3건 추가
- ⚠️ 이 데이터가 없으면 취소 API에서 코드 조회 실패

## 4. 배포 순서
1. DDL 실행
2. ES 매핑 업데이트
3. 서비스 배포
4. Init Data 실행
5. API 정상 동작 확인
```

### mysql-ddl.sql

```sql
-- ===========================================
-- 패치가이드: dworks-cstalk v1.0 → v1.1
-- 생성일: 2026-04-26
-- 실행 시점: 배포 전
-- ===========================================

-- 주문 취소사유 컬럼 추가
-- 주문 취소 기능 신규 추가에 따른 컬럼 추가
ALTER TABLE cstalk_order
  ADD COLUMN cancel_reason VARCHAR(200) COMMENT '취소사유';

-- 취소사유 조회를 위한 인덱스 추가
CREATE INDEX idx_cancel ON cstalk_order(cancel_reason);
```

### oracle-ddl.sql

```sql
-- ===========================================
-- 패치가이드: dworks-cstalk v1.0 → v1.1
-- 생성일: 2026-04-26
-- 실행 시점: 배포 전
-- ===========================================

-- 주문 취소사유 컬럼 추가
-- 주문 취소 기능 신규 추가에 따른 컬럼 추가
ALTER TABLE CSTALK_ORDER
  ADD (CANCEL_REASON VARCHAR2(200));
COMMENT ON COLUMN CSTALK_ORDER.CANCEL_REASON IS '취소사유';

-- 취소사유 조회를 위한 인덱스 추가
CREATE INDEX IDX_CANCEL ON CSTALK_ORDER(CANCEL_REASON);
```

---

## 11. 구현 순서

### Phase 0: 핵심 엔진
- collector: GitHub API diff 수집
- classifier: 파일 분류 (`*Jpo.java`, `*Doc.java`, `*.yml` 패턴 매칭)
- analyzer: OpenAI 분석 (JPA/ES 어노테이션 해석 → MySQL/Oracle DDL 생성)
- generator: 문서 생성 (Jinja2 템플릿)
- cli.py로 로컬 테스트

### Phase 1: Slack Bot 연동
- Slack App 생성 (Socket Mode)
- 대화형 버튼 UI 구현
- 결과 Slack 전송 (Block Kit)

### Phase 2: GitHub PR 생성
- patch-guides repo에 파일 push
- PR 자동 생성
- Slack에 PR 링크 전달

### Phase 3: 고도화
- 프롬프트 튜닝 (실제 서비스 repo 기반)
- 서비스별 커스텀 분류 규칙
- 에러 핸들링
- 생성 이력 관리

---

## 12. 실행 방법

### 개발/테스트 (내 PC)

```bash
# 환경 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 의존성 설치
poetry install

# CLI로 테스트 (Phase 0)
poetry run python -m patch_helper.cli \
  --repo org/dworks-cstalk \
  --mode tag \
  --from v1.0 --to v1.1

# Slack Bot 실행 (Phase 1~)
poetry run python -m patch_helper.bot.app
```

### 사내 서버 이동 시

```bash
git clone https://github.com/org/patch-helper.git
cp .env.example .env   # API 키 설정
pip install .
python -m patch_helper.bot.app

# 백그라운드 실행
nohup python -m patch_helper.bot.app &
# 또는 systemd 서비스 등록
# 또는 docker compose up -d
```

---

## 13. 필요한 사전 준비

| 항목 | 설명 | 비용 |
|-----|------|------|
| Slack App | Bot Token + App Token (Socket Mode) | 무료 |
| GitHub Token | Personal Access Token (repo 읽기/쓰기) | 무료 |
| OpenAI API Key | GPT-4o 사용 | 유료 (건당 $0.01~0.05) |
| Python 3.11+ | 실행 환경 | 무료 |
