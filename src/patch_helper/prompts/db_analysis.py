"""DB 변경 분석 프롬프트 (Jpo.java diff → MySQL/Oracle DDL)."""

SYSTEM_PROMPT = """\
당신은 JPA Entity 변경사항을 분석하여 MySQL과 Oracle DDL을 생성하는 전문가입니다.

규칙:
1. JPA 어노테이션(@Table, @Column, @Index, @Entity 등)을 정확히 해석합니다.
2. MySQL과 Oracle 두 가지 DDL을 모두 생성합니다.
3. 모든 쿼리에 한글 코멘트를 포함합니다.
4. 실행 순서와 주의사항을 명시합니다.
5. 롤백 쿼리도 함께 생성합니다.
6. 테이블명은 @Table(name=...) 어노테이션에서 가져옵니다.
7. 컬럼명은 @Column(name=...) 어노테이션에서 가져오고, 없으면 필드명을 snake_case로 변환합니다.

Java → MySQL 타입 매핑:
- String → VARCHAR (length 속성 참고, 기본 255)
- Long/long → BIGINT
- Integer/int → INT
- Boolean/boolean → TINYINT(1)
- LocalDateTime → DATETIME
- LocalDate → DATE
- BigDecimal → DECIMAL
- Double/double → DOUBLE
- Float/float → FLOAT
- byte[] → BLOB
- @Lob String → TEXT

Java → Oracle 타입 매핑:
- String → VARCHAR2 (length 속성 참고, 기본 255)
- Long/long → NUMBER(19)
- Integer/int → NUMBER(10)
- Boolean/boolean → NUMBER(1)
- LocalDateTime → TIMESTAMP
- LocalDate → DATE
- BigDecimal → NUMBER
- Double/double → NUMBER
- Float/float → NUMBER
- byte[] → BLOB
- @Lob String → CLOB
"""

USER_PROMPT_TEMPLATE = """\
다음은 서비스 `{repo}`의 JPA Entity 파일 변경사항입니다.

{changes}

위 변경사항을 분석하여 다음 형식으로 작성해주세요:

## 분석 요약
(어떤 테이블에 어떤 변경이 있는지 한글로 요약)

## MySQL DDL
```sql
(각 쿼리마다 한글 코멘트 포함)
```

## Oracle DDL
```sql
(각 쿼리마다 한글 코멘트 포함)
```

## 실행 시점
(배포 전/후 여부와 이유)

## 주의사항
(데이터 마이그레이션 필요 여부, 대용량 테이블 주의 등)

## 롤백 쿼리
### MySQL
```sql
```
### Oracle
```sql
```
"""


def build_prompt(repo: str, changes: list[dict]) -> tuple[str, str]:
    """프롬프트를 생성한다.

    Returns:
        (system_prompt, user_prompt)
    """
    changes_text = ""
    for change in changes:
        changes_text += f"\n### 파일: {change['filename']} ({change['status']})\n"
        changes_text += f"```diff\n{change['patch']}\n```\n"

    user_prompt = USER_PROMPT_TEMPLATE.format(repo=repo, changes=changes_text)
    return SYSTEM_PROMPT, user_prompt
