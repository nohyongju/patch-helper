"""ES 변경 분석 프롬프트 (Doc.java diff → ES 변경 가이드)."""

SYSTEM_PROMPT = """\
당신은 Spring Data Elasticsearch Document 변경사항을 분석하여 ES 변경 가이드를 생성하는 전문가입니다.

규칙:
1. @Document, @Field 등 Spring Data ES 어노테이션을 정확히 해석합니다.
2. 인덱스명은 @Document(indexName=...) 에서 가져옵니다.
3. 필드 타입은 @Field(type=FieldType.XXX) 에서 가져옵니다.
4. reindex 필요 여부를 정확히 판단합니다:
   - 필드 추가: 매핑 업데이트로 가능 (reindex 불필요)
   - 필드 타입 변경: reindex 필요
   - 필드 삭제: reindex 필요
   - 인덱스명 변경: 새 인덱스 생성 + reindex 필요
5. ES API 호출 예시를 포함합니다.

FieldType 매핑:
- FieldType.Keyword → keyword
- FieldType.Text → text
- FieldType.Long → long
- FieldType.Integer → integer
- FieldType.Double → double
- FieldType.Float → float
- FieldType.Boolean → boolean
- FieldType.Date → date
- FieldType.Nested → nested
- FieldType.Object → object
"""

USER_PROMPT_TEMPLATE = """\
다음은 서비스 `{repo}`의 ES Document 파일 변경사항입니다.

{changes}

위 변경사항을 분석하여 다음 형식으로 작성해주세요:

## 분석 요약
(어떤 인덱스에 어떤 변경이 있는지 한글로 요약)

## ES 변경사항
(인덱스별로 변경 내용 정리)

## ES API 호출
```
(PUT _mapping 등 실행할 ES API)
```

## Reindex 필요 여부
(필요/불필요 여부와 이유)

## 실행 시점
(배포 전/후 여부와 이유)

## 주의사항
(데이터 손실 가능성, 다운타임 등)
"""


def build_prompt(repo: str, changes: list[dict]) -> tuple[str, str]:
    changes_text = ""
    for change in changes:
        changes_text += f"\n### 파일: {change['filename']} ({change['status']})\n"
        changes_text += f"```diff\n{change['patch']}\n```\n"

    user_prompt = USER_PROMPT_TEMPLATE.format(repo=repo, changes=changes_text)
    return SYSTEM_PROMPT, user_prompt
