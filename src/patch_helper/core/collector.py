"""GitHub API를 이용한 변경사항 수집."""

from __future__ import annotations

import difflib
import fnmatch
import logging
from datetime import datetime

from github import Github
from github.Comparison import Comparison
from github.Repository import Repository

from patch_helper.config import settings
from patch_helper.core.models import CompareMode, DiffResult, FileChange

logger = logging.getLogger(__name__)

# 분류 대상 파일 패턴 (classifier.py의 패턴과 동일)
# compare API 300파일 제한 시 이 패턴에 해당하는 누락 파일만 보충 수집한다.
CLASSIFY_TARGET_PATTERNS: list[str] = [
    # SERVICE repo
    "*Jpo.java",
    "*Doc.java",
    "*init*",
    "*seed*",
    "*data.sql",
    "*.yml",
    "*.yaml",
    # CONFIG repo
    "registry-config/*.yml",
    "registry-config/**/*.yml",
    # INITIAL repo
    "setup/*/json-data/**/*.json",
    "setup/*/json-data/*.json",
    "setup/*/*.sh",
    "setup/*/*.js",
    "setup/*/*.properties",
]


def _is_classify_target(filename: str) -> bool:
    """파일명이 분류 대상 패턴에 해당하는지 확인한다."""
    basename = filename.split("/")[-1]
    for pattern in CLASSIFY_TARGET_PATTERNS:
        if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(basename, pattern):
            return True
    return False


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

        compare_files = list(comparison.files)
        files = [
            FileChange(
                filename=f.filename,
                status=f.status,
                patch=f.patch or "",
                previous_filename=f.previous_filename,
            )
            for f in compare_files
        ]

        # GitHub compare API는 최대 300개 파일만 반환한다.
        # 300개에 도달하면 분류 대상 파일이 누락됐을 수 있으므로 커밋별로 보충한다.
        if len(compare_files) >= 300:
            logger.info(
                f"  compare API 파일 수 제한(300) 도달 — "
                f"분류 대상 누락 파일을 커밋별로 보충합니다."
            )
            files = self._supplement_missing_files(
                repo, files, from_tag, to_tag,
            )

        logger.info(f"  수집 완료: 태그 {from_tag}..{to_tag} → 파일 {len(files)}개")

        return DiffResult(
            repo=repo_name,
            from_ref=from_tag,
            to_ref=to_tag,
            files=files,
            total_commits=comparison.total_commits,
            head_sha=comparison.commits[-1].sha if comparison.commits else to_tag,
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

        # 가장 오래된 커밋의 부모 vs 가장 최신 커밋을 compare하여
        # 기간 내 중간 수정을 모두 취합한 최종 diff를 가져온다.
        oldest_commit = commits[-1]
        newest_commit = commits[0]

        base_sha = oldest_commit.parents[0].sha if oldest_commit.parents else oldest_commit.sha
        head_sha = newest_commit.sha

        comparison: Comparison = repo.compare(base_sha, head_sha)

        compare_files = list(comparison.files)
        files = [
            FileChange(
                filename=f.filename,
                status=f.status,
                patch=f.patch or "",
                previous_filename=f.previous_filename,
            )
            for f in compare_files
        ]

        # 300개 제한 도달 시 분류 대상 누락 파일 보충
        if len(compare_files) >= 300:
            logger.info(
                f"  compare API 파일 수 제한(300) 도달 — "
                f"분류 대상 누락 파일을 커밋별로 보충합니다."
            )
            files = self._supplement_missing_files(
                repo, files, base_sha, head_sha,
            )

        logger.info(f"  수집 완료: 커밋 {len(commits)}개 기간의 최종 diff → 파일 {len(files)}개")

        return DiffResult(
            repo=repo_name,
            from_ref=f"{branch}@{from_date}",
            to_ref=f"{branch}@{to_date}",
            files=files,
            total_commits=len(commits),
            head_sha=head_sha,
        )

    def _supplement_missing_files(
        self,
        repo: Repository,
        compare_files: list[FileChange],
        base_sha: str,
        head_sha: str,
    ) -> list[FileChange]:
        """compare 결과에서 누락된 분류 대상 파일을 Tree SHA 비교로 찾아 보충한다.

        1. base/head 시점의 git tree를 각각 조회 (recursive)
        2. 분류 대상 패턴 파일만 필터링
        3. SHA가 다르거나 한쪽에만 존재하는 파일 = 변경된 파일
        4. compare 결과에 이미 있는 파일은 제외
        5. 누락된 파일은 base..head 간 파일 내용을 비교하여 정확한 diff 생성
        """
        existing_filenames = {f.filename for f in compare_files}

        # base/head 시점의 전체 tree 조회 (API 2회)
        base_tree = repo.get_git_tree(base_sha, recursive=True)
        head_tree = repo.get_git_tree(head_sha, recursive=True)

        # 분류 대상 파일만 추출하여 {경로: blob SHA} 맵 구성
        base_map: dict[str, str] = {}
        for item in base_tree.tree:
            if item.type == "blob" and _is_classify_target(item.path):
                base_map[item.path] = item.sha

        head_map: dict[str, str] = {}
        for item in head_tree.tree:
            if item.type == "blob" and _is_classify_target(item.path):
                head_map[item.path] = item.sha

        # SHA가 다르거나 한쪽에만 존재 = 이 기간에 변경된 파일
        all_target_paths = set(base_map.keys()) | set(head_map.keys())
        changed_targets: dict[str, str] = {}  # filename → status
        for path in all_target_paths:
            base_sha_blob = base_map.get(path)
            head_sha_blob = head_map.get(path)

            if base_sha_blob == head_sha_blob:
                continue  # 변경 없음

            if path in existing_filenames:
                continue  # compare 결과에 이미 포함됨

            if base_sha_blob is None:
                changed_targets[path] = "added"
            elif head_sha_blob is None:
                changed_targets[path] = "removed"
            else:
                changed_targets[path] = "modified"

        if not changed_targets:
            logger.info("  보충 대상 파일 없음 — 분류 대상 파일이 모두 compare 결과에 포함됨")
            return compare_files

        logger.info(
            f"  분류 대상 누락 파일 {len(changed_targets)}개 발견: "
            f"{list(changed_targets.keys())}"
        )

        # 누락 파일별로 base..head 간 정확한 diff를 가져온다.
        supplemented = list(compare_files)
        for filename, status in changed_targets.items():
            patch = self._get_file_diff(repo, base_sha, head_sha, filename)
            supplemented.append(
                FileChange(
                    filename=filename,
                    status=status,
                    patch=patch,
                )
            )

        return supplemented

    def _get_file_diff(
        self, repo: Repository, base_sha: str, head_sha: str, filename: str
    ) -> str:
        """두 SHA 간 특정 파일의 diff를 가져온다.

        base와 head 각각의 파일 내용을 가져와 비교한다.
        GitHub Contents API를 사용하여 정확한 최종 상태를 얻는다.
        """
        base_content = ""
        head_content = ""

        try:
            content = repo.get_contents(filename, ref=base_sha)
            if not isinstance(content, list):
                base_content = content.decoded_content.decode("utf-8", errors="replace")
        except Exception:
            pass  # 파일이 base에 없으면 신규 파일

        try:
            content = repo.get_contents(filename, ref=head_sha)
            if not isinstance(content, list):
                head_content = content.decoded_content.decode("utf-8", errors="replace")
        except Exception:
            pass  # 파일이 head에 없으면 삭제된 파일

        if not base_content and not head_content:
            return ""

        # unified diff 생성
        base_lines = base_content.splitlines(keepends=True)
        head_lines = head_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            base_lines,
            head_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
        return "".join(diff)

    def get_file_content(self, repo_name: str, filepath: str, ref: str) -> str | None:
        """특정 ref 시점의 파일 내용을 가져온다. 없으면 None."""
        repo = self._get_repo(repo_name)
        try:
            content = repo.get_contents(filepath, ref=ref)
            if not isinstance(content, list):
                return content.decoded_content.decode("utf-8", errors="replace")
        except Exception:
            return None
        return None

    def find_file_in_tree(self, repo_name: str, filename: str, ref: str) -> str | None:
        """ref 시점의 tree에서 파일명으로 검색하여 전체 경로를 반환한다. 없으면 None."""
        repo = self._get_repo(repo_name)
        try:
            tree = repo.get_git_tree(ref, recursive=True)
            for item in tree.tree:
                if item.type == "blob" and item.path.endswith(filename):
                    return item.path
        except Exception:
            return None
        return None
