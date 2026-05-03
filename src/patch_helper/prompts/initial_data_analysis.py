"""초기 데이터 분석 프롬프트 (dworks-common-initial JSON diff → curl/sh/요약)."""

SYSTEM_PROMPT = """\
당신은 API 호출 기반 초기 데이터 변경사항을 분석하여 패치가이드를 작성하는 전문가입니다.

이 시스템의 초기 데이터 구조:
- 설정 JSON 파일에 API 매핑이 정의됨 (ActionURI, ActionType, DataFile, Header)
- 데이터 JSON 파일은 entity 모음 (배열 또는 객체 맵)이며, 각 entity가 하나의 API 요청 body가 됨
- data-initialize.js가 이 매핑에 따라 API를 순서대로 호출함

변경 유형별 처리 (entity 단위로 판단):
1. **추가된 entity** (+로 새로 등장): 해당 entity 객체를 body로 하는 curl 1개 생성
2. **변경된 entity** (기존 객체 내 필드 변경): 변경 후 최종 entity 객체 전체를 body로 하는 curl 1개 생성
3. **삭제된 entity** (-로 사라짐): curl 생성하지 않음.
   `## 주의사항` 섹션에 삭제된 entity의 식별자(id/name 등)와 "운영에서 수동 삭제 필요" 명시

curl body 작성 규칙 (매우 중요):
- ❌ `{"dataFile": "..."}` 같은 파일 경로 래퍼 사용 금지
- ❌ JSON 파일 전체 내용을 그대로 임베드 금지 (변경 안 된 entity까지 포함되면 안 됨)
- ✅ 추가 또는 변경된 entity 객체만 인라인으로 임베드:
  ```
  -d '{
    "id": "new-job-1",
    ... 변경 후 entity 전체 필드 ...
  }'
  ```

규칙:
1. 변경된 JSON 데이터 파일을 식별합니다.
2. 해당 파일에 매핑된 API 엔드포인트(ActionURI, ActionType, Header)를 확인합니다.
3. diff에서 entity 단위로 추가/변경/삭제를 분리합니다.
4. 추가/변경된 entity별로 별도 curl 명령을 작성합니다 (entity 1개당 curl 1개).
5. 각 curl 직전에 한 줄 주석으로 `# 추가: {식별자}` 또는 `# 변경: {식별자}`를 표기합니다.
6. 삭제된 entity는 curl을 만들지 않고 주의사항에만 명시합니다.
7. **컨테이너별 분리**: ActionURI의 첫 경로 세그먼트를 컨테이너명으로 사용합니다.
   예) `/scheduler/rest/...` → `scheduler`, `/cstalk/api/...` → `cstalk`,
       `/bff/...` → `bff`, `/uaa/...` → `uaa`, `/depot/...` → `depot`.
   각 컨테이너의 curl들을 하나의 bash 코드 블록에 모으고,
   블록 직전에 `### container: {컨테이너명}` 헤더를 반드시 작성합니다.
   컨테이너를 추론할 수 없으면 `### container: init-data`로 묶습니다.
"""

USER_PROMPT_TEMPLATE = """\
다음은 `{repo}`의 초기 데이터 파일 변경사항입니다.

{changes}

위 변경사항을 분석하여 다음 형식으로 작성해주세요:

## 분석 요약
(어떤 초기 데이터가 어떻게 변경되었는지 한글로 요약)

## 변경 항목 요약
| 파일 | 추가 | 변경 | 삭제 | API |
|------|------|------|------|-----|

## 상세 변경 내용
(파일별·entity별 변경 내용 설명. 추가/변경/삭제를 구분해서 식별자와 함께 정리)

## curl 스크립트 (추가/변경된 항목만)
컨테이너별로 별도의 bash 블록을 작성합니다. 각 블록 앞에 `### container: {{컨테이너명}}` 헤더를 붙입니다.
**추가/변경된 entity 1개당 curl 1개**를 생성하고, body는 해당 entity 객체만 임베드합니다 (파일 전체 X).

### container: scheduler
```bash
# 추가: <식별자>
curl -X POST "http://scheduler/scheduler/rest/..." \\
  -H "Content-Type: application/json" \\
  -d '{{ ... 추가된 entity 객체 ... }}'

# 변경: <식별자>
curl -X POST "http://scheduler/scheduler/rest/..." \\
  -H "Content-Type: application/json" \\
  -d '{{ ... 변경 후 entity 객체 전체 ... }}'
```

(다른 컨테이너에 추가/변경된 entity가 있으면 같은 형식으로 추가)

## 삭제된 항목 (수동 처리 필요)
삭제된 entity는 curl을 만들지 않습니다. 운영 환경에서 수동으로 처리해야 합니다.

| 파일 | 식별자 | 비고 |
|------|--------|------|
(삭제 entity가 없으면 "삭제된 항목 없음" 으로 표기)

## 실행 시점
(배포 전/후 여부와 이유)

## 주의사항
(실행 순서, 의존성, 삭제 entity의 운영 영향 등)
"""


def build_prompt(
    repo: str, changes: list[dict], from_ref: str = "", to_ref: str = ""
) -> tuple[str, str]:
    changes_text = ""
    for change in changes:
        changes_text += f"\n### 파일: {change['filename']} ({change['status']})\n"
        changes_text += f"```diff\n{change['patch']}\n```\n"

    user_prompt = USER_PROMPT_TEMPLATE.format(
        repo=repo, changes=changes_text, from_ref=from_ref, to_ref=to_ref
    )
    return SYSTEM_PROMPT, user_prompt
