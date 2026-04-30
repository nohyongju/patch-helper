"""GitHub API를 이용하여 patch-guides repo에 파일을 push하고 PR을 생성한다."""

from __future__ import annotations

import base64
from datetime import date

from github import Github, GithubException
from github.Repository import Repository

from patch_helper.config import settings
from patch_helper.core.models import PatchGuide


class GitHubPublisher:
    """패치가이드 결과를 GitHub repo에 저장하고 PR을 생성한다."""

    def __init__(self, token: str | None = None):
        self._github = Github(token or settings.github_token)

    def publish(
        self,
        guide: PatchGuide,
        target_repo: str | None = None,
    ) -> str:
        """patch-guides repo에 파일을 push하고 PR을 생성한다.

        Returns:
            PR URL
        """
        repo_name = target_repo or settings.patch_guides_repo
        repo = self._github.get_repo(repo_name)

        # 브랜치명/폴더명 생성
        # 서비스 repo 이름에서 'dworks-' prefix 제거하여 표준 폴더명으로 매핑
        # (예: dworks-cstalk → cstalk, dworks-common-resource → common-resource)
        repo_basename = guide.repo.split("/")[-1] if "/" in guide.repo else guide.repo
        service_folder = (
            repo_basename[len("dworks-"):]
            if repo_basename.startswith("dworks-")
            else repo_basename
        )

        def _safe(ref: str) -> str:
            return ref.replace("/", "-").replace("@", "_")

        def _format_refs(from_ref: str, to_ref: str) -> str:
            """폴더용 ref pair 문자열을 만든다.

            date 모드(`{branch}@YYYY-MM-DD`)에서 from/to의 브랜치가 같으면
            브랜치명을 한 번만 두고 날짜는 `-`를 제거한 YYYYMMDD 형태로 합친다.
            예) develop@2026-01-15 + develop@2026-01-30
                → develop_20260115_20260130
            그 외 (tag 모드 등) 기존 방식: {from}_{to}
            """
            if "@" in from_ref and "@" in to_ref:
                from_branch, from_date = from_ref.split("@", 1)
                to_branch, to_date = to_ref.split("@", 1)
                if from_branch == to_branch:
                    return (
                        f"{_safe(from_branch)}"
                        f"_{from_date.replace('-', '')}"
                        f"_{to_date.replace('-', '')}"
                    )
            return f"{_safe(from_ref)}_{_safe(to_ref)}"

        # 폴더 패턴: {service}_{ref-pair}
        folder_path = f"{service_folder}_{_format_refs(guide.from_ref, guide.to_ref)}"
        branch_name = f"patch-guide/{folder_path}"

        # 기본 브랜치에서 새 브랜치 생성
        default_branch = repo.default_branch
        base_ref = repo.get_git_ref(f"heads/{default_branch}")
        try:
            repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=base_ref.object.sha,
            )
        except GithubException as e:
            if e.status == 422:  # 이미 존재하면 삭제 후 재생성
                repo.get_git_ref(f"heads/{branch_name}").delete()
                repo.create_git_ref(
                    ref=f"refs/heads/{branch_name}",
                    sha=base_ref.object.sha,
                )
            else:
                raise

        # 파일들을 새 브랜치에 push
        for filename, content in guide.files.items():
            file_path = f"{folder_path}/{filename}"
            repo.create_file(
                path=file_path,
                message=f"Add patch guide: {service_name} {guide.from_ref} → {guide.to_ref}",
                content=content,
                branch=branch_name,
            )

        # PR 생성
        pr = repo.create_pull(
            title=f"📋 패치가이드: {service_name} {guide.from_ref} → {guide.to_ref}",
            body=self._build_pr_body(guide),
            head=branch_name,
            base=default_branch,
        )

        return pr.html_url

    def _build_pr_body(self, guide: PatchGuide) -> str:
        counts = {}
        for a in guide.analyses:
            counts[a.category] = True

        body = f"## 패치가이드: {guide.repo} ({guide.from_ref} → {guide.to_ref})\n\n"
        body += f"생성일: {date.today().isoformat()}\n\n"
        body += "### 포함된 변경사항\n"
        for category in counts:
            body += f"- {category}\n"
        body += "\n### 생성된 파일\n"
        for filename in guide.files:
            body += f"- `{filename}`\n"

        return body
