"""OpenAI API를 이용한 변경사항 분석."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

from openai import OpenAI

from patch_helper.config import settings
from patch_helper.core.models import (
    AnalysisResult,
    ClassifiedChanges,
    FileChange,
    PatchGuide,
    RepoType,
)
from patch_helper.prompts import (
    config_analysis,
    data_analysis,
    db_analysis,
    es_analysis,
    initial_data_analysis,
    summary,
)


class Analyzer:
    """분류된 변경사항을 OpenAI API로 분석한다."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._client = OpenAI(api_key=api_key or settings.openai_api_key)
        self._model = model or settings.openai_model

    def analyze(self, classified: ClassifiedChanges) -> PatchGuide:
        analyses: list[AnalysisResult] = []

        # 카테고리별 분석
        if classified.db_changes:
            result = self._analyze_db(classified.repo, classified.db_changes)
            analyses.append(result)

        if classified.es_changes:
            result = self._analyze_es(classified.repo, classified.es_changes)
            analyses.append(result)

        if classified.config_changes:
            result = self._analyze_config(classified.repo, classified.config_changes)
            analyses.append(result)

        if classified.init_data_changes:
            result = self._analyze_init_data(classified.repo, classified.init_data_changes)
            analyses.append(result)

        if classified.initial_data_changes:
            result = self._analyze_initial_data(
                classified.repo,
                classified.initial_data_changes,
                classified.from_ref,
                classified.to_ref,
            )
            analyses.append(result)

        # 전체 종합 (분석 결과가 있을 때만)
        summary_text = ""
        deploy_order = ""
        checklist = ""
        if analyses:
            summary_result = self._summarize(
                classified.repo, classified.from_ref, classified.to_ref, analyses
            )
            summary_text = summary_result.content
            deploy_order = summary_result.content  # 종합 결과에 포함
            checklist = summary_result.content

        return PatchGuide(
            repo=classified.repo,
            from_ref=classified.from_ref,
            to_ref=classified.to_ref,
            summary=summary_text,
            analyses=analyses,
            deploy_order=deploy_order,
            checklist=checklist,
        )

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    def _changes_to_dicts(self, changes: list[FileChange]) -> list[dict]:
        return [
            {
                "filename": c.filename,
                "status": c.status,
                "patch": c.patch,
            }
            for c in changes
        ]

    def _analyze_db(self, repo: str, changes: list[FileChange]) -> AnalysisResult:
        # Jpo와 JpoId를 묶어서 분석한다.
        # 예: GroupTalkEventLogJpo.java + GroupTalkEventLogJpoId.java → 함께 전달
        jpo_files: dict[str, list[FileChange]] = {}  # base_name → [Jpo, JpoId]

        for change in changes:
            basename = change.filename.split("/")[-1]
            if basename.endswith("JpoId.java"):
                # JpoId → 대응하는 Jpo의 그룹에 추가
                base_name = basename.replace("JpoId.java", "Jpo")
                jpo_files.setdefault(base_name, []).append(change)
            elif basename.endswith("Jpo.java"):
                base_name = basename.replace(".java", "")
                jpo_files.setdefault(base_name, []).insert(0, change)

        all_contents: list[str] = []
        all_mysql_ddl: list[str] = []
        all_oracle_ddl: list[str] = []

        for base_name, group in jpo_files.items():
            filenames = [c.filename for c in group]
            logger.info(f"  DB 분석 중: {filenames}")
            sys_prompt, user_prompt = db_analysis.build_prompt(
                repo, self._changes_to_dicts(group)
            )
            content = self._call_openai(sys_prompt, user_prompt)

            all_contents.append(content)

            mysql_ddl = self._extract_sql_block(content, "MySQL DDL")
            oracle_ddl = self._extract_sql_block(content, "Oracle DDL")
            if mysql_ddl:
                all_mysql_ddl.append(mysql_ddl)
            if oracle_ddl:
                all_oracle_ddl.append(oracle_ddl)

        combined_content = "\n\n---\n\n".join(all_contents)

        return AnalysisResult(
            category="DB 변경",
            content=combined_content,
            mysql_ddl="\n\n".join(all_mysql_ddl),
            oracle_ddl="\n\n".join(all_oracle_ddl),
        )

    def _analyze_es(self, repo: str, changes: list[FileChange]) -> AnalysisResult:
        # 신규 Doc.java(added)는 새 인덱스이므로 분석 제외
        modified_changes = [c for c in changes if c.status != "added"]

        if not modified_changes:
            logger.info("  ES 변경: 신규 인덱스만 존재하여 분석 생략")
            return AnalysisResult(
                category="ES 변경",
                content="신규 인덱스 추가만 존재하여 별도 ES 작업이 불필요합니다.",
            )

        # 파일별 개별 분석 후 결과 합산
        all_contents: list[str] = []
        all_es_commands: list[str] = []

        for change in modified_changes:
            logger.info(f"  ES 분석 중: {change.filename}")
            sys_prompt, user_prompt = es_analysis.build_prompt(
                repo, self._changes_to_dicts([change])
            )
            content = self._call_openai(sys_prompt, user_prompt)

            all_contents.append(content)

            es_commands = self._extract_code_block(content)
            if es_commands:
                all_es_commands.append(es_commands)

        combined_content = "\n\n---\n\n".join(all_contents)

        return AnalysisResult(
            category="ES 변경",
            content=combined_content,
            es_commands="\n\n".join(all_es_commands),
        )

    def _analyze_config(self, repo: str, changes: list[FileChange]) -> AnalysisResult:
        sys_prompt, user_prompt = config_analysis.build_prompt(
            repo, self._changes_to_dicts(changes)
        )
        content = self._call_openai(sys_prompt, user_prompt)

        return AnalysisResult(
            category="설정 변경",
            content=content,
        )

    def _analyze_init_data(
        self, repo: str, changes: list[FileChange]
    ) -> AnalysisResult:
        sys_prompt, user_prompt = data_analysis.build_prompt(
            repo, self._changes_to_dicts(changes)
        )
        content = self._call_openai(sys_prompt, user_prompt)

        mysql_dml = self._extract_sql_block(content, "MySQL DML")
        oracle_dml = self._extract_sql_block(content, "Oracle DML")

        return AnalysisResult(
            category="Init Data",
            content=content,
            mysql_dml=mysql_dml,
            oracle_dml=oracle_dml,
        )

    def _analyze_initial_data(
        self,
        repo: str,
        changes: list[FileChange],
        from_ref: str,
        to_ref: str,
    ) -> AnalysisResult:
        sys_prompt, user_prompt = initial_data_analysis.build_prompt(
            repo, self._changes_to_dicts(changes), from_ref, to_ref
        )
        content = self._call_openai(sys_prompt, user_prompt)

        curl_script = self._extract_bash_block(content)

        return AnalysisResult(
            category="초기 데이터",
            content=content,
            curl_script=curl_script,
        )

    def _summarize(
        self,
        repo: str,
        from_ref: str,
        to_ref: str,
        analyses: list[AnalysisResult],
    ) -> AnalysisResult:
        analyses_dicts = [
            {"category": a.category, "content": a.content} for a in analyses
        ]
        sys_prompt, user_prompt = summary.build_prompt(
            repo, from_ref, to_ref, analyses_dicts
        )
        content = self._call_openai(sys_prompt, user_prompt)

        return AnalysisResult(category="종합", content=content)

    def _extract_sql_block(self, content: str, heading: str) -> str:
        """마크다운에서 특정 헤딩 아래의 SQL 코드 블록을 추출한다."""
        pattern = rf"##\s*{re.escape(heading)}.*?```sql\s*\n(.*?)```"
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _extract_code_block(self, content: str) -> str:
        """마크다운에서 첫 번째 코드 블록을 추출한다."""
        pattern = r"```(?:\w*)\s*\n(.*?)```"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _extract_bash_block(self, content: str) -> str:
        """마크다운에서 bash 코드 블록을 추출한다."""
        pattern = r"```bash\s*\n(.*?)```"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1).strip() if match else ""
