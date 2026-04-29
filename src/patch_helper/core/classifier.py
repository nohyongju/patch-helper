"""변경된 파일을 카테고리별로 분류한다."""

from __future__ import annotations

import fnmatch
import logging

from patch_helper.core.models import (
    ClassifiedChanges,
    DiffResult,
    FileCategory,
    FileChange,
    RepoType,
)

logger = logging.getLogger(__name__)

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


def supplement_jpo_id_files(
    classified: ClassifiedChanges,
    collector,
    head_ref: str,
) -> None:
    """db_changes의 Jpo 파일에 대응하는 JpoId 파일이 없으면 GitHub에서 가져와 추가한다.

    Jpo 파일의 PK는 @EmbeddedId로 참조하는 JpoId 클래스에 정의되어 있다.
    JpoId가 변경 목록에 없어도, Jpo 분석 시 PK 정보가 필요하므로
    head 시점의 JpoId 파일 전체 내용을 가져와 db_changes에 함께 포함시킨다.
    """
    if not classified.db_changes:
        return

    existing_basenames = {
        c.filename.split("/")[-1] for c in classified.db_changes
    }

    jpo_files = [
        c for c in classified.db_changes
        if c.filename.split("/")[-1].endswith("Jpo.java")
        and not c.filename.split("/")[-1].endswith("JpoId.java")
    ]

    for jpo in jpo_files:
        jpo_basename = jpo.filename.split("/")[-1]
        jpo_id_basename = jpo_basename.replace("Jpo.java", "JpoId.java")

        if jpo_id_basename in existing_basenames:
            continue  # 이미 변경 목록에 있음

        # JpoId 파일 경로 추정: 같은 디렉토리
        jpo_dir = "/".join(jpo.filename.split("/")[:-1])
        jpo_id_path = f"{jpo_dir}/{jpo_id_basename}" if jpo_dir else jpo_id_basename

        # GitHub에서 head 시점의 파일 내용 조회
        content = collector.get_file_content(
            classified.repo, jpo_id_path, head_ref,
        )

        if content is None:
            # 경로 추정 실패 시 tree에서 검색
            found_path = collector.find_file_in_tree(
                classified.repo, jpo_id_basename, head_ref,
            )
            if found_path:
                content = collector.get_file_content(
                    classified.repo, found_path, head_ref,
                )
                jpo_id_path = found_path

        if content:
            logger.info(f"  JpoId 보강: {jpo_id_path}")
            # 전체 내용을 patch로 넣어 OpenAI가 PK 구조를 파악할 수 있게 한다
            classified.db_changes.append(
                FileChange(
                    filename=jpo_id_path,
                    status="reference",
                    patch=content,
                    category=FileCategory.DB_CHANGE,
                )
            )
        else:
            logger.warning(f"  JpoId 파일을 찾을 수 없음: {jpo_id_basename}")
