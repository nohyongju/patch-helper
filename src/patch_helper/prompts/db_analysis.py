"""DB 변경 분석 프롬프트 (Jpo.java diff → MySQL/Oracle DDL)."""

SYSTEM_PROMPT = """\
당신은 JPA Entity 변경사항을 분석하여 MySQL과 Oracle DDL을 생성하는 전문가입니다.

규칙:
1. JPA 어노테이션(@Table, @Column, @Index, @Entity 등)을 정확히 해석합니다.
2. MySQL과 Oracle 두 가지 DDL을 모두 생성합니다.
3. 실행 순서와 주의사항을 명시합니다.
4. 테이블명은 @Table(name=...) 어노테이션에서 가져옵니다.
5. 컬럼명은 @Column(name=...) 어노테이션에서 가져오고, 없으면 필드명을 snake_case로 변환합니다.
6. 컬럼명은 c_ 접두사 패턴입니다 (예: c_event_log_id, c_name 등). diff에서 확인하세요.
7. 테이블명 패턴: dworks-cstalk, cstalk-bizasset, cstalk-aibiz 서비스는 cstalk_ 접두사 (예: cstalk_order), 나머지 서비스는 자기 서비스명 접두사 (예: insight_group_talk_event_log). @Table 어노테이션 값을 그대로 사용하세요.

코멘트 규칙:
- MySQL: CREATE TABLE 시 테이블 COMMENT, 각 컬럼에 COMMENT 속성을 포함합니다. ALTER TABLE로 컬럼 추가 시에도 COMMENT를 포함합니다.
- Oracle: DDL 이후 반드시 COMMENT ON TABLE, COMMENT ON COLUMN 구문을 별도로 생성합니다.
- 코멘트 내용은 Javadoc, 필드명, 클래스명 등에서 유추하여 한글로 작성합니다.
- SQL 주석(-- 주석)이 아닌, DB 메타데이터에 저장되는 COMMENT 구문이어야 합니다.

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
-- 예시: 테이블/컬럼 COMMENT 포함
-- CREATE TABLE cstalk_order (
--   c_order_id BIGINT NOT NULL COMMENT '주문 ID',
--   c_name VARCHAR(100) COMMENT '주문명'
-- ) COMMENT='주문 테이블';
(위 형식 참고하여 생성)
```

## Oracle DDL
```sql
-- 예시: DDL 이후 COMMENT ON 구문 필수
-- CREATE TABLE cstalk_order (...);
-- COMMENT ON TABLE cstalk_order IS '주문 테이블';
-- COMMENT ON COLUMN cstalk_order.c_order_id IS '주문 ID';
-- COMMENT ON COLUMN cstalk_order.c_name IS '주문명';
(위 형식 참고하여 생성)
```

## 실행 시점
(배포 전/후 여부와 이유)

## 주의사항
(데이터 마이그레이션 필요 여부, 대용량 테이블 주의 등)
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
