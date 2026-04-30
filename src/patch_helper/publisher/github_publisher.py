"""GitHub API를 이용하여 patch-guides repo에 파일을 push하고 PR을 생성한다."""

from __future__ import annotations

from datetime import date

from github import Github, GithubException

from patch_helper.config import settings
from patch_helper.core.models import PatchGuide


class GitHubPublisher:
    """패치가이드 결과를 GitHub repo에 저장하고 PR을 생성한다.

    여러 서비스의 가이드를 한 번에 받아 단일 브랜치 + 단일 PR로 통합한다
    (`publish_batch`). 단일 가이드 흐름은 `publish`가 `publish_batch`에 위임한다.
    """

    def __init__(self, token: str | None = None):
        self._github = Github(token or settings.github_token)

    # ------------------------------------------------------------------ public

    def publish(
        self,
        guide: PatchGuide,
        target_repo: str | None = None,
    ) -> str:
        """단일 가이드용 — 내부적으로 batch 호출로 위임."""
        return self.publish_batch([guide], target_repo=target_repo)

    def publish_batch(
        self,
        guides: list[PatchGuide],
        target_repo: str | None = None,
    ) -> str:
        """여러 가이드를 단일 브랜치/단일 PR로 묶어 push한다.

        - 서비스별 파일은 `{service}_{ref-pair}/...` 폴더로 분리됨.
        - 모든 guide의 ref 쌍이 동일하다고 가정 (다중 서비스 일괄 적용 흐름).
          다르면 첫 번째 guide의 ref 쌍을 브랜치명에 사용.

        Returns:
            PR URL
        """
        if not guides:
            raise ValueError("publish_batch: guides가 비어있습니다.")

        repo_name = target_repo or settings.patch_guides_repo
        repo = self._github.get_repo(repo_name)

        first = guides[0]
        ref_pair = self._format_refs(first.from_ref, first.to_ref)
        branch_name = f"patch-guide/release_{ref_pair}"

        default_branch = repo.default_branch
        base_ref = repo.get_git_ref(f"heads/{default_branch}")
        try:
            repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=base_ref.object.sha,
            )
        except GithubException as e:
            if e.status == 422:  # 이미 존재 → 삭제 후 재생성
                repo.get_git_ref(f"heads/{branch_name}").delete()
                repo.create_git_ref(
                    ref=f"refs/heads/{branch_name}",
                    sha=base_ref.object.sha,
                )
            else:
                raise

        # 각 guide의 파일을 자기 폴더에 push
        for guide in guides:
            service_folder = self._service_folder(guide.repo)
            sub_path = (
                f"{service_folder}_"
                f"{self._format_refs(guide.from_ref, guide.to_ref)}"
            )
            for filename, content in guide.files.items():
                repo.create_file(
                    path=f"{sub_path}/{filename}",
                    message=(
                        f"Add patch guide: {service_folder} "
                        f"{guide.from_ref} → {guide.to_ref}"
                    ),
                    content=content,
                    branch=branch_name,
                )

        # PR 생성
        pr = repo.create_pull(
            title=self._build_pr_title(guides),
            body=self._build_pr_body(guides),
            head=branch_name,
            base=default_branch,
        )
        return pr.html_url

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _service_folder(repo: str) -> str:
        """서비스 repo 이름에서 'dworks-' prefix를 떼어 표준 폴더명을 만든다.

        예: dworks-cstalk → cstalk, dworks-common-resource → common-resource
        """
        basename = repo.split("/")[-1] if "/" in repo else repo
        if basename.startswith("dworks-"):
            return basename[len("dworks-"):]
        return basename

    @staticmethod
    def _safe(ref: str) -> str:
        return ref.replace("/", "-").replace("@", "_")

    @classmethod
    def _format_refs(cls, from_ref: str, to_ref: str) -> str:
        """폴더용 ref pair 문자열을 만든다.

        date 모드(`{branch}@YYYY-MM-DD`)에서 from/to의 브랜치가 같으면
        브랜치명을 한 번만 두고 날짜는 `-`를 제거한 YYYYMMDD 형태로 합친다.
        예) develop@2026-01-15 + develop@2026-01-30
            → develop_20260115_20260130
        그 외 (tag 모드 등): {from}_{to}
        """
        if "@" in from_ref and "@" in to_ref:
            from_branch, from_date = from_ref.split("@", 1)
            to_branch, to_date = to_ref.split("@", 1)
            if from_branch == to_branch:
                return (
                    f"{cls._safe(from_branch)}"
                    f"_{from_date.replace('-', '')}"
                    f"_{to_date.replace('-', '')}"
                )
        return f"{cls._safe(from_ref)}_{cls._safe(to_ref)}"

    def _build_pr_title(self, guides: list[PatchGuide]) -> str:
        services = [self._service_folder(g.repo) for g in guides]
        if len(services) == 1:
            service_text = services[0]
        elif len(services) <= 3:
            service_text = ", ".join(services)
        else:
            service_text = f"{', '.join(services[:3])} 외 {len(services) - 3}개"
        first = guides[0]
        return (
            f"📋 패치가이드: {service_text} "
            f"({first.from_ref} → {first.to_ref})"
        )

    def _build_pr_body(self, guides: list[PatchGuide]) -> str:
        body = "## 패치가이드 일괄 생성\n\n"
        body += f"생성일: {date.today().isoformat()}\n\n"

        body += f"### 포함된 서비스 ({len(guides)}개)\n"
        for g in guides:
            service = self._service_folder(g.repo)
            body += f"- **{service}** (`{g.repo}`): {g.from_ref} → {g.to_ref}\n"

        # 카테고리 모음
        categories: dict[str, int] = {}
        for g in guides:
            for a in g.analyses:
                categories[a.category] = categories.get(a.category, 0) + 1
        if categories:
            body += "\n### 변경 카테고리\n"
            for cat, count in categories.items():
                body += f"- {cat}: {count}건\n"

        # 서비스별 생성 파일 목록
        body += "\n### 생성된 파일\n"
        for g in guides:
            service = self._service_folder(g.repo)
            sub_path = f"{service}_{self._format_refs(g.from_ref, g.to_ref)}"
            body += f"\n**{sub_path}/**\n"
            for filename in g.files:
                body += f"- `{filename}`\n"

        return body
