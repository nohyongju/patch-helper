"""로컬 테스트용 CLI."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from patch_helper.core.analyzer import Analyzer
from patch_helper.core.classifier import classify, supplement_jpo_id_files
from patch_helper.core.collector import DiffCollector
from patch_helper.core.generator import Generator
from patch_helper.core.models import CompareMode
from patch_helper.publisher.github_publisher import GitHubPublisher

app = typer.Typer(help="패치가이드 자동 생성 도구")
console = Console()


@app.command()
def generate(
    repo: str = typer.Option(..., help="서비스 repo (예: org/dworks-cstalk 또는 dworks-cstalk)"),
    mode: str = typer.Option(..., help="비교 방식: tag 또는 date"),
    from_ref: str = typer.Option(..., "--from", help="시작 태그 또는 날짜"),
    to_ref: str = typer.Option(..., "--to", help="종료 태그 또는 날짜"),
    branch: str = typer.Option(None, help="브랜치 (date 모드일 때)"),
    output: str = typer.Option("console", help="출력: console, file, github"),
    output_dir: str = typer.Option("./output", help="file 모드일 때 출력 디렉토리"),
    target_repo: str = typer.Option(None, help="github 모드일 때 PR 대상 repo"),
):
    """패치가이드를 생성한다."""
    compare_mode = CompareMode(mode)

    # Step 1: diff 수집
    console.print(f"\n⏳ [bold]{repo}[/bold] ({from_ref} → {to_ref}) diff 수집 중...")
    collector = DiffCollector()
    diff = collector.collect(repo, compare_mode, from_ref, to_ref, branch)

    if not diff.files:
        console.print("[yellow]변경사항이 없습니다.[/yellow]")
        raise typer.Exit()

    console.print(f"  변경 파일: {len(diff.files)}개, 커밋: {diff.total_commits}개")

    # Step 2: 파일 분류
    console.print("⏳ 파일 분류 중...")
    classified = classify(diff)

    # Step 2.5: Jpo 파일에 대응하는 JpoId 파일 보강 (PK 정보 확보)
    supplement_jpo_id_files(classified, collector, diff.head_sha)

    if not classified.has_changes:
        console.print("[yellow]패치가이드 대상 변경사항이 없습니다.[/yellow]")
        counts = classified.summary
        console.print(f"  (총 {len(diff.files)}개 파일 중 패치 대상 0개)")
        raise typer.Exit()

    counts = classified.summary
    console.print(f"  DB: {counts['db']}, ES: {counts['es']}, "
                  f"설정: {counts['config']}, Init: {counts['init_data']}, "
                  f"초기 데이터: {counts['initial_data']}")

    # Step 3: AI 분석
    console.print("⏳ AI 분석 중... (시간이 걸릴 수 있습니다)")
    analyzer = Analyzer()
    guide = analyzer.analyze(classified)

    # Step 4: 문서 생성
    console.print("⏳ 문서 생성 중...")
    generator = Generator()
    guide = generator.generate(classified, guide)

    console.print(f"  생성된 파일: {', '.join(guide.files.keys())}")

    # Step 5: 결과 전달
    if output == "console":
        _output_console(guide)
    elif output == "file":
        _output_file(guide, output_dir)
    elif output == "github":
        _output_github(guide, target_repo)

    console.print("\n[bold green]✅ 완료![/bold green]")


def _output_console(guide):
    """콘솔에 결과를 출력한다."""
    for filename, content in guide.files.items():
        console.print(Panel(
            content,
            title=f"📄 {filename}",
            border_style="blue",
        ))


def _output_file(guide, output_dir: str):
    """로컬 파일로 저장한다."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    for filename, content in guide.files.items():
        file_path = out_path / filename
        file_path.write_text(content, encoding="utf-8")
        console.print(f"  📁 {file_path}")


def _output_github(guide, target_repo: str | None):
    """GitHub repo에 PR을 생성한다."""
    publisher = GitHubPublisher()
    pr_url = publisher.publish(guide, target_repo)
    console.print(f"  📎 PR: {pr_url}")


if __name__ == "__main__":
    app()
