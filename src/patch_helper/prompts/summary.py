"""전체 종합 프롬프트 (배포 순서, 체크리스트)."""

SYSTEM_PROMPT = """\
당신은 MSA 서비스의 패치가이드를 종합하여 배포 순서와 검증 체크리스트를 작성하는 전문가입니다.

규칙:
1. DB 변경 → ES 변경 → 설정 변경 → 서비스 배포 → Init Data 순서를 기본으로 합니다.
2. 각 단계의 의존 관계를 고려하여 순서를 조정합니다.
3. 검증 체크리스트는 구체적이고 실행 가능해야 합니다.
4. 롤백 계획도 포함합니다.
"""

USER_PROMPT_TEMPLATE = """\
다음은 서비스 `{repo}` ({from_ref} → {to_ref}) 패치의 카테고리별 분석 결과입니다.

{analyses}

위 분석 결과를 종합하여 다음 형식으로 작성해주세요:

## 배포 순서
(번호 매겨서 순서대로, 각 단계에 대한 설명 포함)

## 검증 체크리스트
- [ ] (구체적인 검증 항목)

## 롤백 계획
(문제 발생 시 롤백 순서)

## 전체 소요 예상
(각 단계별 예상 소요 시간, 총 소요 시간)
"""


def build_prompt(
    repo: str, from_ref: str, to_ref: str, analyses: list[dict]
) -> tuple[str, str]:
    analyses_text = ""
    for analysis in analyses:
        analyses_text += f"\n### {analysis['category']}\n"
        analyses_text += f"{analysis['content']}\n"

    user_prompt = USER_PROMPT_TEMPLATE.format(
        repo=repo, from_ref=from_ref, to_ref=to_ref, analyses=analyses_text
    )
    return SYSTEM_PROMPT, user_prompt
