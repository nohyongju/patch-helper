"""Init Data 분석 프롬프트 (서비스 repo 내 init/seed 파일)."""

SYSTEM_PROMPT = """\
당신은 초기 데이터(Init Data) 변경사항을 분석하여 MySQL과 Oracle DML을 생성하는 전문가입니다.

규칙:
1. INSERT/UPDATE/DELETE 쿼리를 MySQL과 Oracle 두 가지로 생성합니다.
2. 모든 쿼리에 한글 코멘트를 포함합니다.
3. 실행 시점(배포 전/후)을 명시합니다.
4. 데이터 간 의존 관계가 있으면 실행 순서를 지정합니다.
5. 롤백 쿼리도 함께 생성합니다.
"""

USER_PROMPT_TEMPLATE = """\
다음은 서비스 `{repo}`의 초기 데이터 파일 변경사항입니다.

{changes}

위 변경사항을 분석하여 다음 형식으로 작성해주세요:

## 분석 요약
(어떤 데이터가 추가/변경/삭제되었는지 한글로 요약)

## MySQL DML
```sql
(각 쿼리마다 한글 코멘트 포함)
```

## Oracle DML
```sql
(각 쿼리마다 한글 코멘트 포함)
```

## 실행 시점
(배포 전/후 여부와 이유)

## 주의사항
(데이터 의존성, FK 제약 등)

## 롤백 쿼리
### MySQL
```sql
```
### Oracle
```sql
```
"""


def build_prompt(repo: str, changes: list[dict]) -> tuple[str, str]:
    changes_text = ""
    for change in changes:
        changes_text += f"\n### 파일: {change['filename']} ({change['status']})\n"
        changes_text += f"```diff\n{change['patch']}\n```\n"

    user_prompt = USER_PROMPT_TEMPLATE.format(repo=repo, changes=changes_text)
    return SYSTEM_PROMPT, user_prompt
