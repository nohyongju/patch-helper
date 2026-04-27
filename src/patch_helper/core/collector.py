"""GitHub API를 이용한 변경사항 수집."""

from __future__ import annotations

from datetime import datetime

from github import Github
from github.Comparison import Comparison
from github.Repository import Repository

from patch_helper.config import settings
from patch_helper.core.models import CompareMode, DiffResult, FileChange


class DiffCollector:
    """GitHub API로 두 버전 간 diff를 수집한다."""

    def __init__(self, token: str | None = None):
        self._github = Github(token or settings.github_token)

    def collect(
        self,
        repo_name: str,
        mode: CompareMode,
        from_ref: str,
        to_ref: str,
        branch: str | None = None,
    ) -> DiffResult:
        repo = self._get_repo(repo_name)

        if mode == CompareMode.TAG:
            return self._collect_by_tag(repo, repo_name, from_ref, to_ref)
        else:
            return self._collect_by_date(
                repo, repo_name, from_ref, to_ref, branch or "develop"
            )

    def _get_repo(self, repo_name: str) -> Repository:
        full_name = repo_name
        if "/" not in repo_name and settings.github_org:
            full_name = f"{settings.github_org}/{repo_name}"
        return self._github.get_repo(full_name)

    def _collect_by_tag(
        self, repo: Repository, repo_name: str, from_tag: str, to_tag: str
    ) -> DiffResult:
        comparison: Comparison = repo.compare(from_tag, to_tag)

        files = []
        for f in comparison.files:
            files.append(FileChange(
                filename=f.filename,
                status=f.status,
                patch=f.patch or "",
                previous_filename=f.previous_filename,
            ))

        return DiffResult(
            repo=repo_name,
            from_ref=from_tag,
            to_ref=to_tag,
            files=files,
            total_commits=comparison.total_commits,
        )

    def _collect_by_date(
        self,
        repo: Repository,
        repo_name: str,
        from_date: str,
        to_date: str,
        branch: str,
    ) -> DiffResult:
        since = datetime.fromisoformat(from_date)
        until = datetime.fromisoformat(to_date)

        commits = list(repo.get_commits(sha=branch, since=since, until=until))

        if not commits:
            return DiffResult(
                repo=repo_name,
                from_ref=f"{branch}@{from_date}",
                to_ref=f"{branch}@{to_date}",
                files=[],
                total_commits=0,
            )

        # 가장 오래된 커밋과 최신 커밋 사이의 diff
        oldest = commits[-1]
        newest = commits[0]

        # oldest의 부모와 newest를 비교
        if oldest.parents:
            base_sha = oldest.parents[0].sha
        else:
            base_sha = oldest.sha

        comparison = repo.compare(base_sha, newest.sha)

        files = []
        for f in comparison.files:
            files.append(FileChange(
                filename=f.filename,
                status=f.status,
                patch=f.patch or "",
                previous_filename=f.previous_filename,
            ))

        return DiffResult(
            repo=repo_name,
            from_ref=f"{branch}@{from_date}",
            to_ref=f"{branch}@{to_date}",
            files=files,
            total_commits=len(commits),
        )
