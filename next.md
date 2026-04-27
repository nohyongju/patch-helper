# 다음 단계 - Patch Helper 셋업 가이드

## 1. Slack App 생성

1. https://api.slack.com/apps 접속
2. **Create New App** → **From scratch** 선택
3. App Name: `patch-helper`, 워크스페이스 선택
4. 아래 순서대로 설정

### Socket Mode 활성화
- Settings → **Socket Mode** → Enable Socket Mode
- Token Name: `patch-helper-socket` → **Generate**
- `xapp-` 토큰 복사해두기

### Bot Token Scopes 추가
- Features → **OAuth & Permissions** → Scopes → Bot Token Scopes에 추가:
  - `app_mentions:read`
  - `chat:write`
  - `channels:history`
  - `groups:history` (private 채널도 쓸 경우)
  - `im:history` (DM도 쓸 경우)
  - `im:read`

### Event Subscriptions 활성화
- Features → **Event Subscriptions** → Enable Events
- Subscribe to bot events 추가:
  - `app_mention`
  - `message.channels`
  - `message.im` (DM도 쓸 경우)

### Interactivity 활성화
- Features → **Interactivity & Shortcuts** → ON
- (Socket Mode라 Request URL 입력 불필요)

### 워크스페이스에 설치
- Settings → **Install App** → **Install to Workspace**
- `xoxb-` 토큰 복사해두기

### 결과
```
SLACK_BOT_TOKEN=xoxb-xxxxxxxxx  (OAuth & Permissions 페이지)
SLACK_APP_TOKEN=xapp-xxxxxxxxx  (Socket Mode 설정 시 생성됨)
```

---

## 2. GitHub Personal Access Token 발급

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens**
2. **Generate new token**
3. 설정:
   - Token name: `patch-helper`
   - Expiration: 원하는 기간
   - Repository access: 서비스 repo들 + patch-guides repo 선택
   - Permissions:
     - **Contents**: Read and write
     - **Pull requests**: Read and write
4. **Generate token** → `github_pat_` 토큰 복사해두기

### 결과
```
GITHUB_TOKEN=github_pat_xxxxxxxxx
```

---

## 3. OpenAI API Key 발급

1. https://platform.openai.com/api-keys 접속
2. **Create new secret key**
3. 이름: `patch-helper`
4. `sk-` 토큰 복사해두기

### 결과
```
OPENAI_API_KEY=sk-xxxxxxxxx
```

---

## 4. patch-guides repo 생성 (선택)

PR 생성 기능을 쓸 경우, 결과를 저장할 repo가 필요합니다.

1. GitHub에서 새 repo 생성: `{org}/patch-guides`
2. README.md 하나만 넣고 생성
3. 위에서 발급한 GitHub Token이 이 repo에 접근 가능해야 함

---

## 5. 환경 설정

```bash
cd /mnt/d/_P_REPOSITORY/patch_helper

# .env 파일 생성
cp .env.example .env
```

`.env` 파일 편집:
```env
# Slack
SLACK_BOT_TOKEN=xoxb-실제토큰
SLACK_APP_TOKEN=xapp-실제토큰

# GitHub
GITHUB_TOKEN=github_pat_실제토큰
GITHUB_ORG=실제org이름

# OpenAI
OPENAI_API_KEY=sk-실제토큰
OPENAI_MODEL=gpt-4o

# 결과 저장 repo (PR 생성 기능용)
PATCH_GUIDES_REPO=org이름/patch-guides
```

---

## 6. 의존성 설치

```bash
# Poetry가 있으면
poetry install

# 없으면 pip로 직접
pip install openai PyGithub slack-bolt slack-sdk jinja2 pydantic pydantic-settings typer python-dotenv rich
```

---

## 7. 테스트

### CLI로 먼저 테스트 (Slack 없이)

```bash
# 콘솔에 출력
python -m patch_helper.cli generate \
  --repo dworks-cstalk \
  --mode tag \
  --from v1.0 --to v1.1 \
  --output console

# 로컬 파일로 저장
python -m patch_helper.cli generate \
  --repo dworks-cstalk \
  --mode tag \
  --from v1.0 --to v1.1 \
  --output file \
  --output-dir ./output

# 날짜 구간
python -m patch_helper.cli generate \
  --repo dworks-cstalk \
  --mode date \
  --branch develop \
  --from 2026-04-01 --to 2026-04-25 \
  --output console
```

### Slack Bot 실행

```bash
python -m patch_helper
```

실행되면 `⚡ Patch Helper Bot 시작!` 메시지가 출력됩니다.

Slack에서 테스트:
1. patch-helper 봇을 채널에 초대
2. `@patch-helper 생성해줘` 입력
3. 서비스 선택 → 비교 방식 선택 → 태그 입력 → 결과 확인

---

## 8. 트러블슈팅

### "Token not found" 에러
→ `.env` 파일이 프로젝트 루트에 있는지 확인

### "not_in_channel" 에러
→ Slack에서 봇을 채널에 초대했는지 확인 (`/invite @patch-helper`)

### GitHub API rate limit
→ 토큰이 올바른지 확인, 인증 없으면 시간당 60회 제한

### OpenAI 응답이 느림
→ 정상. diff 분석에 10~30초 소요될 수 있음

### 패치 대상 파일이 0개
→ classifier.py의 패턴 확인. 실제 파일명이 `*Jpo.java`, `*Doc.java` 패턴과 맞는지 확인
→ 필요하면 패턴 추가/수정

---

## 체크리스트

```
[ ] Slack App 생성 완료
[ ] SLACK_BOT_TOKEN (xoxb-) 발급
[ ] SLACK_APP_TOKEN (xapp-) 발급
[ ] GitHub Token 발급
[ ] OpenAI API Key 발급
[ ] patch-guides repo 생성 (선택)
[ ] .env 파일 작성
[ ] 의존성 설치
[ ] CLI 테스트 성공
[ ] Slack Bot 실행 성공
[ ] Slack에서 패치가이드 생성 테스트
```
