"""패치 헬퍼 핵심 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CompareMode(str, Enum):
    TAG = "tag"
    DATE = "date"


class FileCategory(str, Enum):
    DB_CHANGE = "db_change"          # *Jpo.java
    ES_CHANGE = "es_change"          # *Doc.java
    CONFIG_CHANGE = "config_change"  # *.yml (registry-config)
    INIT_DATA = "init_data"          # init/seed 파일
    INITIAL_DATA = "initial_data"    # dworks-common-initial JSON
    IGNORED = "ignored"              # 패치가이드 대상 아님


class RepoType(str, Enum):
    SERVICE = "service"              # 서비스 repo (dworks-cstalk 등)
    CONFIG = "config"                # 설정 repo (dworks-common-resource)
    INITIAL = "initial"              # 초기 데이터 repo (dworks-common-initial)


class OutputMode(str, Enum):
    SLACK = "slack"
    GITHUB_PR = "github_pr"
    FILE = "file"


@dataclass
class FileChange:
    """변경된 파일 하나의 정보."""
    filename: str
    status: str           # added, modified, removed, renamed
    patch: str            # diff 내용
    previous_filename: str | None = None  # renamed일 때
    category: FileCategory = FileCategory.IGNORED


@dataclass
class DiffResult:
    """GitHub API에서 가져온 diff 결과."""
    repo: str
    from_ref: str
    to_ref: str
    files: list[FileChange] = field(default_factory=list)
    total_commits: int = 0
    head_sha: str = ""  # head 시점의 commit SHA (파일 내용 조회에 사용)


@dataclass
class ClassifiedChanges:
    """카테고리별로 분류된 변경사항."""
    repo: str
    repo_type: RepoType
    from_ref: str
    to_ref: str
    db_changes: list[FileChange] = field(default_factory=list)
    es_changes: list[FileChange] = field(default_factory=list)
    config_changes: list[FileChange] = field(default_factory=list)
    init_data_changes: list[FileChange] = field(default_factory=list)
    initial_data_changes: list[FileChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any([
            self.db_changes,
            self.es_changes,
            self.config_changes,
            self.init_data_changes,
            self.initial_data_changes,
        ])

    @property
    def summary(self) -> dict[str, int]:
        return {
            "db": len(self.db_changes),
            "es": len(self.es_changes),
            "config": len(self.config_changes),
            "init_data": len(self.init_data_changes),
            "initial_data": len(self.initial_data_changes),
        }


@dataclass
class AnalysisResult:
    """AI 분석 결과 (카테고리별)."""
    category: str
    content: str          # AI가 생성한 분석 내용 (마크다운)
    mysql_ddl: str = ""
    oracle_ddl: str = ""
    mysql_dml: str = ""
    oracle_dml: str = ""
    es_commands: str = ""
    curl_script: str = ""
    # 컨테이너별 curl 스크립트 (key: 컨테이너명, value: bash 본문)
    # 비어 있으면 generator는 curl_script로 fallback
    curl_scripts: dict[str, str] = field(default_factory=dict)
    # yml 변경분 발췌 (key: 파일명 또는 상대경로, value: 발췌 yml 본문)
    # generator가 repo_type에 따라 config/talk 또는 config/registry 하위로 라우팅
    config_yml_files: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PatchGuide:
    """최종 패치가이드 결과."""
    repo: str
    from_ref: str
    to_ref: str
    summary: str                              # 전체 요약 (마크다운)
    analyses: list[AnalysisResult] = field(default_factory=list)
    deploy_order: str = ""                    # 배포 순서
    checklist: str = ""                       # 검증 체크리스트

    # 생성된 파일들
    files: dict[str, str] = field(default_factory=dict)
    # 예: {"patch-guide.md": "...", "mysql-ddl.sql": "...", ...}
