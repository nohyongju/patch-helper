"""설정 변경 분석 프롬프트 (*.yml diff → 설정 변경 정리)."""

SYSTEM_PROMPT = """\
당신은 Spring Boot 설정 파일(YAML) 변경사항을 분석하여 패치가이드를 작성하는 전문가입니다.

규칙:
1. 추가/삭제/변경된 설정 항목을 명확히 구분합니다.
2. 각 설정의 목적과 영향을 설명합니다.
3. 환경별(dev/stg/prod) 주의사항을 명시합니다.
4. 설정 누락 시 발생할 수 있는 문제를 경고합니다.
5. 민감한 설정(비밀번호, API 키 등)은 별도로 표시합니다.
6. **변경분 발췌 yml**: 변경된 yml 파일별로 별도 코드 블록을 만들어
   변경된 부분만 발췌합니다.
   - 부모 노드는 유지하되 영향 없는 형제 노드는 `...` 으로 생략 표기합니다.
   - 코드 블록 직전에 `### file: {파일명}` 형식의 헤더를 반드시 작성합니다.
   - 파일명은 원본 경로의 basename만 사용합니다 (예: `cstalk.yml`,
     `apigateway-agent.yml`).
   - 코드 블록 언어는 `yml`로 지정합니다.
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

## 변경분 발췌 yml
변경된 yml 파일마다 별도의 헤더와 코드 블록을 출력합니다.
- 부모 경로는 유지하고, 변경 없는 형제는 `...` 으로 생략합니다.

### file: {{파일명}}.yml
```yml
...
parent:
  ...
  changed-key: changed-value
```

(변경된 yml 파일이 더 있으면 같은 형식으로 추가)
"""


def build_prompt(repo: str, changes: list[dict]) -> tuple[str, str]:
    changes_text = ""
    for change in changes:
        changes_text += f"\n### 파일: {change['filename']} ({change['status']})\n"
        changes_text += f"```diff\n{change['patch']}\n```\n"

    user_prompt = USER_PROMPT_TEMPLATE.format(repo=repo, changes=changes_text)
    return SYSTEM_PROMPT, user_prompt
