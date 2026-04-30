"""Slack 메시지/멘션 핸들러."""

from __future__ import annotations

import logging

from slack_bolt import App

from patch_helper.config import settings

logger = logging.getLogger(__name__)

# 체크박스 블록 식별용 (views.py에서 state.values 조회 시 사용)
SERVICE_CHECKBOXES_BLOCK_ID = "service_checkboxes_block"
SERVICE_CHECKBOXES_ACTION_ID = "service_checkboxes"
SERVICE_SELECT_DONE_ACTION_ID = "service_select_done"


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
    """서비스 선택 체크박스(다중 선택) + 다음 버튼을 표시한다."""
    options = [
        {
            "text": {"type": "plain_text", "text": repo},
            "value": repo,
        }
        for repo in settings.service_repo_list
    ]

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "패치가이드를 생성할 서비스를 선택해주세요. *(다중 선택 가능)*",
            },
        },
        {
            "type": "actions",
            "block_id": SERVICE_CHECKBOXES_BLOCK_ID,
            "elements": [
                {
                    "type": "checkboxes",
                    "action_id": SERVICE_CHECKBOXES_ACTION_ID,
                    "options": options,
                }
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "다음 ▶"},
                    "action_id": SERVICE_SELECT_DONE_ACTION_ID,
                    "style": "primary",
                }
            ],
        },
    ]

    say(blocks=blocks, text="서비스를 선택해주세요.", thread_ts=thread_ts)
