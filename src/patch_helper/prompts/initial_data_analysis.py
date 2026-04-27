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
```bash
#!/bin/bash
# 패치가이드: {repo} {from_ref} → {to_ref}
(변경된 데이터에 대응하는 curl 명령어)
(Header가 있으면 -H 옵션 포함)
```

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
