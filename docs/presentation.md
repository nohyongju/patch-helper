---
marp: true
theme: default
paginate: true
header: 'Patch Helper'
footer: 'spectrakr / 2026-04'
style: |
  section { font-size: 24px; }
  h1 { color: #2563eb; }
  h2 { color: #1e40af; }
  code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; }
  pre { font-size: 18px; }
  table { font-size: 20px; }
---

<!--
Marp 슬라이드. 미리보기: VS Code "Marp for VS Code" 확장 또는
  npx @marp-team/marp-cli docs/presentation.md -o docs/presentation.html
  npx @marp-team/marp-cli docs/presentation.md -o docs/presentation.pdf
-->


# Patch Helper

**Slack 멘션 한 번**으로
서비스 변경사항을 분석하고
**패치가이드 PR**을 자동 생성하는 봇

`spectrakr / 2026-04`

---

## 왜 만들었나

**기존 방식**
- 매 릴리스마다 사람이 직접 작성:
  - 변경된 JPA Entity → DDL을 손으로 작성
  - 변경된 yml → 변경분 발췌
  - 초기 데이터 변경 → curl 스크립트 작성
  - README에 모든 내용 정리

**문제**
- 누락 위험 (특히 `*Jpo.java`의 PK 컬럼 빠뜨리기 쉬움)
- 작성자별 양식이 다름
- 서비스 N개 패치 = N번 반복 노동

---

## 솔루션 한 줄 요약

> **"Slack에서 서비스 골라서 from/to 입력 → 단일 PR 자동 생성"**

```
@patch-helper 생성
  ↓
서비스 다중 선택 (cstalk, bizasset, ...)
  ↓
태그 또는 날짜 구간 입력 (모두에 일괄 적용)
  ↓
출력 방식 선택 (Slack 미리보기 / GitHub PR)
  ↓
🤖 AI 분석 → 템플릿 → 단일 PR 생성
```

---

## Slack 데모 흐름 (1/2)

```
You: @patch-helper 생성해줘

Bot: 패치가이드를 생성할 서비스를 선택해주세요. (다중 선택 가능)
     ☑ dworks-cstalk
     ☑ dworks-insight
     ☐ dworks-bizasset
     [ 다음 ▶ ]

Bot: 선택된 서비스 (2개): cstalk, insight
     비교 방식을 선택해주세요.
     [ 🏷️ 태그 비교 ]  [ 📅 날짜 구간 ]

You: develop 2026-04-01 2026-04-25

Bot: 결과를 어떻게 받으시겠어요?
     [ 💬 여기서 바로 보기 ]  [ 📂 repo에 PR 생성 ]
```

---

## Slack 데모 흐름 (2/2)

```
Bot: ⏳ 2개 서비스 패치가이드 생성 중...
     ▶️ [1/2] dworks-cstalk 시작
     ✅ ... 가이드 완료
     ▶️ [2/2] dworks-insight 시작
     ✅ ... 가이드 완료
     🏁 전체 완료 — 성공 2 / 총 2

     ✅ 단일 PR 생성 완료 (2개 서비스 통합)
     📎 https://github.com/spectrakr/attic-btalk-release-guide/pull/123
```

- 한 서비스가 실패해도 다음 서비스는 계속 진행
- 마지막에 성공/실패/건너뜀 합계 보고

---

## 산출물 — 단일 PR 구조

브랜치: `patch-guide/release_develop_20260401_20260425`

```
attic-btalk-release-guide/
├─ cstalk_develop_20260401_20260425/
│  ├─ README.md                # 표준 양식 패치가이드
│  ├─ script/
│  │  ├─ DB/patch-mysql.sql    # DDL+DML 합본
│  │  ├─ DB/patch-oracle.sql
│  │  └─ API/cstalk.http.sh    # 컨테이너별 분리
│  └─ config/talk/cstalk.yml   # 변경분 발췌 (`...` 생략 표기)
└─ insight_develop_20260401_20260425/
   └─ ...
```

→ `attic-btalk-release-guide` repo의 표준 양식을 그대로 따름

---

## DB 변경사항
> ./script/DB/patch-mysql.sql, patch-oracle.sql 참고

(AI가 분석한 변경 내용)
```

---

## 산출물 예시 — patch-mysql.sql

```sql
CREATE TABLE insight_group_talk_event_log (
  c_event_log_id VARCHAR(36)  NOT NULL COMMENT '이벤트 로그 아이디',
  c_tenant_id    VARCHAR(255) NOT NULL COMMENT '테넌트 ID',
  ...
) COMMENT='그룹톡 이벤트 로그';

ALTER TABLE insight_group_talk_event_log
  ADD PRIMARY KEY (c_event_log_id, c_tenant_id);
```

---

## DB 분석의 정확성 보장

- **테이블·필드명 컨벤션 기반**
  `*Jpo` → `{service}_*`, 컬럼은 `c_` 접두사
- **JpoId 클래스 동시 fetch**
  복합 PK 컬럼을 빠뜨리지 않음
- **신규 테이블 COMMENT 필수 포함**
  MySQL: 컬럼 COMMENT, Oracle: `COMMENT ON COLUMN ...`
- **인덱스 필수 포함**
  `@Index` / `@Table(indexes=...)` 어노테이션 해석

→ AI에게 자연어 규칙으로 강제 (`prompts/db_analysis.py`)

---

## 산출물 예시 — yml 변경분 발췌

`config/talk/cstalk.yml`:

```yaml
...
spring:
  ...
  datasource:
    url: "jdbc:mysql://..."   # 변경됨
attic:
  ...
  monitoring:
    enabled: true             # 신규 추가
```

- 변경 없는 형제 노드는 `...` 으로 생략
- 변경 포인트만 한눈에

---

## 처리 과정

```
1️⃣  변경 파일 수집
    GitHub에서 from → to 사이 변경된 파일 목록을 가져옴

2️⃣  카테고리 분류
    파일명 패턴으로 자동 분류
    *Jpo.java → DB | *Doc.java → ES | *.yml → 설정 | ...

3️⃣  카테고리별 AI 분석
    각 카테고리에 맞는 프롬프트로 OpenAI 호출
    DB → DDL | ES → mapping | yml → 변경분 발췌 | ...

4️⃣  산출물 조립
    분석 결과를 표준 양식 파일로 변환
    (README.md, patch-*.sql, *.http.sh, *.yml)

5️⃣  단일 PR 생성
    여러 서비스 결과를 한 브랜치에 모아 PR 1개로 push
```

- 서비스 N개 입력 → 1~4 반복 후 5에서 통합
- 한 서비스가 실패해도 나머지는 계속 진행

---

## 분석 카테고리

| 카테고리 | 입력 패턴 | AI 산출물 |
|---|---|---|
| 🗄️ DB 변경 | `*Jpo.java` (+ `*JpoId.java`) | MySQL/Oracle DDL |
| 🔍 ES 변경 | `*Doc.java` | ES `_mapping` API call |
| ⚙️ 설정 변경 | `*.yml` | 변경분 발췌 yml 스니펫 |
| 📦 Init Data | `*init*`, `*seed*`, `*data.sql` | DML SQL |
| 📦 초기 데이터 | `setup/*/json-data/...` | 컨테이너별 curl 스크립트 |

각 카테고리별 전용 프롬프트 — `prompts/{category}_analysis.py`

---

## 확장점 — 새 분석 카테고리

지금 다루는 카테고리: 🗄️ DB / 🔍 ES / ⚙️ 설정 / 📦 Init data

새로운 종류의 변경사항(예: Redis 스키마, Kafka 토픽)도 추가 가능

**개념적으로 필요한 3가지**:
- 📂 **어떤 파일을 보는가** → 파일명 패턴 (예: `*Stream.java`)
- 🤖 **무엇을 뽑아내는가** → AI에게 줄 프롬프트
- 📄 **어디에 저장하는가** → 산출물 파일 위치

→ 카테고리 단위로 모듈화되어 있어 점진적 확장이 쉬움

---

## 확장점 — 새 서비스 추가

`.env`의 `SERVICE_REPOS` 콤마 목록에 한 줄 추가:

```bash
SERVICE_REPOS=dworks-cstalk,dworks-bizasset,...,dworks-newservice
```

---

## 한계 & 운영 주의사항

- **AI 출력은 검증 필수**: PR 머지 전 사람이 한 번 더 검토
- **"패치 대상 컨테이너" 표는 자동 생성 X**: 운영자가 PR에서 직접 채움
- **token 비용**: 서비스당 (변경 Jpo 수 + 변경 Doc 수 + 설정/Init/초기데이터 각 1회 + 요약 1회)
- **GitHub compare API 300 파일 제한**: 
- **Jpo의 JpoId**: 변경 목록에 없어도 PK 추출 위해 head 시점 파일 자동 fetch

---

## Stack & 진입점

| 영역 | 사용 |
|---|---|
| Slack 봇 | `slack-bolt` (Socket Mode) |
| GitHub | `PyGithub` |
| AI | `openai` SDK, `gpt-4o` |
| 템플릿 | `jinja2` |
| 설정 | `pydantic-settings` |
| Python | 3.11 |

**진입점**: `python -m patch_helper`
**설정**: `.env` (Slack/GitHub/OpenAI 토큰 + repo 목록)
**대상 repo**: `spectrakr/attic-btalk-release-guide`

---

## 정리

- **Slack 멘션** 한 번으로 패치가이드 자동 생성
- AI가 DDL/yml/curl/README까지 카테고리별로 추출
- 사용자는 PR에서 컨테이너 표만 채워 머지

**🚫 제외 범위**
- 신규 인덱스 (added Doc.java) 분석 제외
- V.O 내 JSON 형태 데이터 마이그레이션 제외
- 복잡한 Elasticsearch 쿼리 제외 — 필드 생성만 다룸

**🔧 해야 하는 작업**
- DB 쿼리 정확도 향상
- yml / init data 검증
