"""Slack 메시지/멘션 핸들러."""

from __future__ import annotations

import logging
import re

from slack_bolt import App

from patch_helper.config import settings

logger = logging.getLogger(__name__)

# 한 행에 표시할 버튼 수
BUTTONS_PER_ROW = 3


def register_commands(app: App):
    """앱 멘션 및 메시지 핸들러를 등록한다."""

    @app.event("app_mention")
    def handle_mention(event, say, client):
        """@patch-helper 멘션 처리."""
        text = event.get("text", "").lower()
        thread_ts = event.get("ts")

        if "생성" in text or "패치" in text or "가이드" in text:
            _show_service_selection(say, thread_ts)
        else:
            say(
                text="안녕하세요! 패치가이드를 생성하려면 `@patch-helper 생성해줘` 라고 말씀해주세요.",
                thread_ts=thread_ts,
            )

    # DM 메시지는 views.py의 통합 message 핸들러에서 처리


def _show_service_selection(say, thread_ts: str | None = None):
    """서비스 선택 버튼을 표시한다."""
    buttons = []
    for repo in settings.service_repo_list:
        buttons.append({
            "type": "button",
            "text": {"type": "plain_text", "text": repo},
            "action_id": f"select_service_{repo}",
            "value": repo,
        })

    # 버튼을 행별로 나누기
    action_blocks = []
    for i in range(0, len(buttons), BUTTONS_PER_ROW):
        action_blocks.append({
            "type": "actions",
            "elements": buttons[i : i + BUTTONS_PER_ROW],
        })

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "서비스를 선택해주세요.",
            },
        },
        *action_blocks,
    ]

    say(blocks=blocks, text="서비스를 선택해주세요.", thread_ts=thread_ts)
