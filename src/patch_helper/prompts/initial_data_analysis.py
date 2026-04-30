"""초기 데이터 분석 프롬프트 (dworks-common-initial JSON diff → curl/sh/요약)."""

SYSTEM_PROMPT = """\
당신은 API 호출 기반 초기 데이터 변경사항을 분석하여 패치가이드를 작성하는 전문가입니다.

이 시스템의 초기 데이터 구조:
- 설정 JSON 파일에 API 매핑이 정의됨 (ActionURI, ActionType, DataFile, Header)
- 데이터 JSON 파일에 실제 요청 body가 정의됨
- data-initialize.js가 이 매핑에 따라 API를 순서대로 호출함

규칙:
1. 변경된 JSON 데이터 파일을 식별합니다.
2. 해당 파일에 매핑된 API 엔드포인트를 확인합니다.
3. 변경 내용(필드 추가/삭제/값 변경)을 명확히 설명합니다.
4. curl 명령어를 생성할 때 ActionURI, ActionType, Header 정보를 활용합니다.
5. 실행 순서가 중요하면 순서를 명시합니다.
6. **컨테이너별 분리**: ActionURI의 첫 경로 세그먼트를 컨테이너명으로 사용합니다.
   예) `/scheduler/rest/...` → `scheduler`, `/cstalk/api/...` → `cstalk`,
       `/bff/...` → `bff`, `/uaa/...` → `uaa`, `/depot/...` → `depot`.
   각 컨테이너에 해당하는 curl 호출은 별도의 bash 코드 블록에 모으고,
   블록 직전에 `### container: {컨테이너명}` 형식의 헤더를 반드시 작성합니다.
   컨테이너를 추론할 수 없으면 `### container: init-data`로 묶습니다.
"""

USER_PROMPT_TEMPLATE = """\
다음은 `{repo}`의 초기 데이터 파일 변경사항입니다.

{changes}

위 변경사항을 분석하여 다음 형식으로 작성해주세요:

## 분석 요약
(어떤 초기 데이터가 어떻게 변경되었는지 한글로 요약)

## 변경된 파일 목록
| 파일 | 변경 유형 | API (있으면) | Method |
|------|----------|-------------|--------|

## 상세 변경 내용
(파일별 변경 내용 설명)

## curl 스크립트
컨테이너별로 별도의 bash 블록을 작성합니다. 각 블록 앞에 `### container: {컨테이너명}` 헤더를 붙입니다.

### container: scheduler
```bash
#!/bin/bash
# 패치가이드: {repo} {from_ref} → {to_ref}
# scheduler 컨테이너 호출
(scheduler 컨테이너 대상 curl 명령어)
```

### container: cstalk
```bash
#!/bin/bash
# 패치가이드: {repo} {from_ref} → {to_ref}
# cstalk 컨테이너 호출
(cstalk 컨테이너 대상 curl 명령어)
```

(추출된 컨테이너가 더 있으면 같은 형식으로 추가)

## 실행 시점
(배포 전/후 여부와 이유)

## 주의사항
(실행 순서, 의존성, 기존 데이터 영향 등)
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
