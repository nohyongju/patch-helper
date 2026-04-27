"""Jinja2 템플릿 기반 패치가이드 문서 생성."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from patch_helper.core.models import AnalysisResult, ClassifiedChanges, PatchGuide

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class Generator:
    """분석 결과를 패치가이드 문서로 변환한다."""

    def __init__(self):
        self._env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(
        self, classified: ClassifiedChanges, guide: PatchGuide
    ) -> PatchGuide:
        """분석 결과로부터 최종 문서 파일들을 생성한다."""
        today = date.today().isoformat()
        common_ctx = {
            "repo": guide.repo,
            "from_ref": guide.from_ref,
            "to_ref": guide.to_ref,
            "generated_date": today,
        }

        # 1. patch-guide.md (항상 생성)
        guide.files["patch-guide.md"] = self._render("patch-guide.md.j2", {
            **common_ctx,
            "summary_counts": classified.summary,
            "analyses": [
                {"category": a.category, "content": a.content}
                for a in guide.analyses
            ],
            "summary": guide.summary,
        })

        # 2. MySQL DDL (DB 변경이 있을 때)
        mysql_ddl = self._collect_field(guide.analyses, "mysql_ddl")
        if mysql_ddl:
            guide.files["mysql-ddl.sql"] = self._render("mysql-ddl.sql.j2", {
                **common_ctx,
                "mysql_ddl": mysql_ddl,
            })

        # 3. Oracle DDL (DB 변경이 있을 때)
        oracle_ddl = self._collect_field(guide.analyses, "oracle_ddl")
        if oracle_ddl:
            guide.files["oracle-ddl.sql"] = self._render("oracle-ddl.sql.j2", {
                **common_ctx,
                "oracle_ddl": oracle_ddl,
            })

        # 4. MySQL Init Data DML
        mysql_dml = self._collect_field(guide.analyses, "mysql_dml")
        if mysql_dml:
            guide.files["mysql-init-data.sql"] = self._render(
                "mysql-init-data.sql.j2", {**common_ctx, "mysql_dml": mysql_dml}
            )

        # 5. Oracle Init Data DML
        oracle_dml = self._collect_field(guide.analyses, "oracle_dml")
        if oracle_dml:
            guide.files["oracle-init-data.sql"] = self._render(
                "oracle-init-data.sql.j2", {**common_ctx, "oracle_dml": oracle_dml}
            )

        # 6. curl 스크립트 (초기 데이터가 있을 때)
        curl_script = self._collect_field(guide.analyses, "curl_script")
        if curl_script:
            guide.files["init-data.sh"] = self._render("init-data.sh.j2", {
                **common_ctx,
                "curl_script": curl_script,
            })

        return guide

    def _render(self, template_name: str, context: dict) -> str:
        template = self._env.get_template(template_name)
        return template.render(**context)

    def _collect_field(self, analyses: list[AnalysisResult], field: str) -> str:
        """모든 분석 결과에서 특정 필드를 합친다."""
        parts = []
        for a in analyses:
            value = getattr(a, field, "")
            if value:
                parts.append(value)
        return "\n\n".join(parts)
