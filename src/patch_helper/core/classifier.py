"""변경된 파일을 카테고리별로 분류한다."""

from __future__ import annotations

import fnmatch

from patch_helper.core.models import (
    ClassifiedChanges,
    DiffResult,
    FileCategory,
    FileChange,
    RepoType,
)

# 서비스 repo 분류 규칙
SERVICE_PATTERNS: list[tuple[str, FileCategory]] = [
    ("*Jpo.java", FileCategory.DB_CHANGE),
    ("*Doc.java", FileCategory.ES_CHANGE),
    ("*init*", FileCategory.INIT_DATA),
    ("*seed*", FileCategory.INIT_DATA),
    ("*data.sql", FileCategory.INIT_DATA),
]

# 설정 repo 분류 규칙
CONFIG_PATTERNS: list[tuple[str, FileCategory]] = [
    ("registry-config/*.yml", FileCategory.CONFIG_CHANGE),
    ("registry-config/**/*.yml", FileCategory.CONFIG_CHANGE),
]

# 초기 데이터 repo 분류 규칙
INITIAL_PATTERNS: list[tuple[str, FileCategory]] = [
    ("setup/*/json-data/**/*.json", FileCategory.INITIAL_DATA),
    ("setup/*/json-data/*.json", FileCategory.INITIAL_DATA),
    ("setup/*/*.sh", FileCategory.INITIAL_DATA),
    ("setup/*/*.js", FileCategory.INITIAL_DATA),
    ("setup/*/*.properties", FileCategory.INITIAL_DATA),
]

# repo 이름으로 타입 추론
REPO_TYPE_MAP: dict[str, RepoType] = {
    "dworks-common-resource": RepoType.CONFIG,
    "dworks-common-initial": RepoType.INITIAL,
}


def detect_repo_type(repo_name: str) -> RepoType:
    """repo 이름에서 타입을 추론한다."""
    # org/repo 형태에서 repo만 추출
    name = repo_name.split("/")[-1] if "/" in repo_name else repo_name
    return REPO_TYPE_MAP.get(name, RepoType.SERVICE)


def _match_file(filename: str, patterns: list[tuple[str, FileCategory]]) -> FileCategory:
    """파일명이 패턴에 매칭되는지 확인한다."""
    # 파일명에서 경로의 마지막 부분 추출
    basename = filename.split("/")[-1]

    for pattern, category in patterns:
        # 전체 경로 매칭
        if fnmatch.fnmatch(filename, pattern):
            return category
        # 파일명만 매칭
        if fnmatch.fnmatch(basename, pattern):
            return category
    return FileCategory.IGNORED


def classify(diff: DiffResult) -> ClassifiedChanges:
    """DiffResult를 카테고리별로 분류한다."""
    repo_type = detect_repo_type(diff.repo)

    # repo 타입에 따라 패턴 선택
    if repo_type == RepoType.CONFIG:
        patterns = CONFIG_PATTERNS
    elif repo_type == RepoType.INITIAL:
        patterns = INITIAL_PATTERNS
    else:
        patterns = SERVICE_PATTERNS

    result = ClassifiedChanges(
        repo=diff.repo,
        repo_type=repo_type,
        from_ref=diff.from_ref,
        to_ref=diff.to_ref,
    )

    for file_change in diff.files:
        category = _match_file(file_change.filename, patterns)
        file_change.category = category

        if category == FileCategory.DB_CHANGE:
            result.db_changes.append(file_change)
        elif category == FileCategory.ES_CHANGE:
            result.es_changes.append(file_change)
        elif category == FileCategory.CONFIG_CHANGE:
            result.config_changes.append(file_change)
        elif category == FileCategory.INIT_DATA:
            result.init_data_changes.append(file_change)
        elif category == FileCategory.INITIAL_DATA:
            result.initial_data_changes.append(file_change)

    return result
