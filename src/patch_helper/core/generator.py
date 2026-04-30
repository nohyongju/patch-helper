"""Jinja2 템플릿 기반 패치가이드 문서 생성."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from patch_helper.core.classifier import detect_repo_type
from patch_helper.core.models import (
    AnalysisResult,
    ClassifiedChanges,
    PatchGuide,
    RepoType,
)

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

        # 1. README.md (항상 생성, release-guide 표준 키)
        guide.files["README.md"] = self._render("patch-guide.md.j2", {
            **common_ctx,
            "summary_counts": classified.summary,
            "analyses": [
                {"category": a.category, "content": a.content}
                for a in guide.analyses
            ],
            "summary": guide.summary,
        })

        # 2. MySQL DDL+DML 합본 (script/DB/patch-mysql.sql)
        mysql_ddl = self._collect_field(guide.analyses, "mysql_ddl")
        mysql_dml = self._collect_field(guide.analyses, "mysql_dml")
        if mysql_ddl or mysql_dml:
            guide.files["script/DB/patch-mysql.sql"] = self._render(
                "patch-mysql.sql.j2",
                {**common_ctx, "mysql_ddl": mysql_ddl, "mysql_dml": mysql_dml},
            )

        # 3. Oracle DDL+DML 합본 (script/DB/patch-oracle.sql)
        oracle_ddl = self._collect_field(guide.analyses, "oracle_ddl")
        oracle_dml = self._collect_field(guide.analyses, "oracle_dml")
        if oracle_ddl or oracle_dml:
            guide.files["script/DB/patch-oracle.sql"] = self._render(
                "patch-oracle.sql.j2",
                {**common_ctx, "oracle_ddl": oracle_ddl, "oracle_dml": oracle_dml},
            )

        # 4. yml 변경분 발췌 — config/talk 또는 config/registry 하위로 라우팅
        config_yml_files = self._collect_yml_files(guide.analyses)
        if config_yml_files:
            config_subdir = (
                "config/registry"
                if detect_repo_type(guide.repo) == RepoType.CONFIG
                else "config/talk"
            )
            for filename, body in config_yml_files.items():
                guide.files[f"{config_subdir}/{filename}"] = body

        # 5. curl 스크립트 — 컨테이너별로 script/API/{container}.http.sh 생성
        curl_by_container = self._collect_curl_by_container(guide.analyses)
        if curl_by_container:
            for container, body in curl_by_container.items():
                guide.files[f"script/API/{container}.http.sh"] = self._render(
                    "init-data.sh.j2", {**common_ctx, "curl_script": body}
                )
        else:
            # 컨테이너 분리 실패 시 단일 init-data.http.sh fallback
            curl_script = self._collect_field(guide.analyses, "curl_script")
            if curl_script:
                guide.files["script/API/init-data.http.sh"] = self._render(
                    "init-data.sh.j2", {**common_ctx, "curl_script": curl_script}
                )

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

    def _collect_yml_files(
        self, analyses: list[AnalysisResult]
    ) -> dict[str, str]:
        """모든 분석 결과의 config_yml_files를 파일별로 병합한다."""
        merged: dict[str, str] = {}
        for a in analyses:
            yml_files = getattr(a, "config_yml_files", None) or {}
            for filename, body in yml_files.items():
                if not body or not body.strip():
                    continue
                if filename in merged:
                    merged[filename] = merged[filename].rstrip() + "\n\n" + body
                else:
                    merged[filename] = body
        return merged

    def _collect_curl_by_container(
        self, analyses: list[AnalysisResult]
    ) -> dict[str, str]:
        """모든 분석 결과의 curl_scripts를 컨테이너별로 병합한다."""
        merged: dict[str, str] = {}
        for a in analyses:
            scripts = getattr(a, "curl_scripts", None) or {}
            for container, body in scripts.items():
                if not body:
                    continue
                if container in merged:
                    merged[container] = merged[container] + "\n\n" + body
                else:
                    merged[container] = body
        return merged
