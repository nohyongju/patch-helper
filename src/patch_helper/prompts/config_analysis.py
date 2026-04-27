"""설정 변경 분석 프롬프트 (*.yml diff → 설정 변경 정리)."""

SYSTEM_PROMPT = """\
당신은 Spring Boot 설정 파일(YAML) 변경사항을 분석하여 패치가이드를 작성하는 전문가입니다.

규칙:
1. 추가/삭제/변경된 설정 항목을 명확히 구분합니다.
2. 각 설정의 목적과 영향을 설명합니다.
3. 환경별(dev/stg/prod) 주의사항을 명시합니다.
4. 설정 누락 시 발생할 수 있는 문제를 경고합니다.
5. 민감한 설정(비밀번호, API 키 등)은 별도로 표시합니다.
"""

USER_PROMPT_TEMPLATE = """\
다음은 `{repo}`의 설정 파일(YAML) 변경사항입니다.

{changes}

위 변경사항을 분석하여 다음 형식으로 작성해주세요:

## 분석 요약
(어떤 설정이 어떻게 변경되었는지 한글로 요약)

## 변경 내역

### 추가된 설정
| 키 | 값 | 설명 |
|---|---|---|

### 변경된 설정
| 키 | 변경 전 | 변경 후 | 설명 |
|---|---|---|---|

### 삭제된 설정
| 키 | 기존 값 | 설명 |
|---|---|---|

## 환경별 주의사항
(dev/stg/prod 환경에서 각각 확인해야 할 사항)

## 주의사항
(설정 누락 시 영향, 의존성 등)
"""


def build_prompt(repo: str, changes: list[dict]) -> tuple[str, str]:
    changes_text = ""
    for change in changes:
        changes_text += f"\n### 파일: {change['filename']} ({change['status']})\n"
        changes_text += f"```diff\n{change['patch']}\n```\n"

    user_prompt = USER_PROMPT_TEMPLATE.format(repo=repo, changes=changes_text)
    return SYSTEM_PROMPT, user_prompt
