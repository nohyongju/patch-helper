"""패치 헬퍼 설정 관리."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Slack
    slack_bot_token: str = ""
    slack_app_token: str = ""

    # GitHub
    github_token: str = ""
    github_org: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # 서비스 repo 목록 (쉼표 구분)
    service_repos: str = "dworks-cstalk,bizasset,aibiz,dworks-common-resource,dworks-common-initial"

    # 결과 저장 repo
    patch_guides_repo: str = ""

    @property
    def service_repo_list(self) -> list[str]:
        return [r.strip() for r in self.service_repos.split(",") if r.strip()]

    @property
    def github_org_prefix(self) -> str:
        return f"{self.github_org}/" if self.github_org else ""


settings = Settings()
