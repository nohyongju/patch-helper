"""Slack Bolt 앱 (Socket Mode 진입점)."""

from __future__ import annotations

import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from patch_helper.config import settings
from patch_helper.bot.commands import register_commands
from patch_helper.bot.views import register_views

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> App:
    app = App(token=settings.slack_bot_token)
    register_commands(app)
    register_views(app)
    return app


def main():
    app = create_app()
    handler = SocketModeHandler(app, settings.slack_app_token)
    logger.info("⚡ Patch Helper Bot 시작!")
    handler.start()


if __name__ == "__main__":
    main()
