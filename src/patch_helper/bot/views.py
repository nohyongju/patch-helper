"""Slack 버튼/인터랙션 핸들러."""

from __future__ import annotations

import logging
import re
import threading

from slack_bolt import App

from patch_helper.core.analyzer import Analyzer
from patch_helper.core.classifier import classify
from patch_helper.core.collector import DiffCollector
from patch_helper.core.generator import Generator
from patch_helper.core.models import CompareMode, PatchGuide
from patch_helper.publisher.github_publisher import GitHubPublisher
from patch_helper.publisher.slack_publisher import SlackPublisher

logger = logging.getLogger(__name__)

# 세션 상태를 임시 저장 (실제 운영에서는 Redis 등 사용 권장)
_sessions: dict[str, dict] = {}


def register_views(app: App):
    """버튼 인터랙션 핸들러를 등록한다."""

    # --- 서비스 선택 ---
    @app.action(re.compile(r"^select_service_(.+)$"))
    def handle_service_select(ack, action, body, say):
        ack()
        repo = action["value"]
        thread_ts = _get_thread_ts(body)
        channel = body["channel"]["id"]
        user = body["user"]["id"]

        # 세션 저장
        session_key = f"{user}_{thread_ts}"
        _sessions[session_key] = {"repo": repo}

        # 비교 방식 선택
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{repo}* 선택됨.\n비교 방식을 선택해주세요.",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🏷️ 태그 비교"},
                        "action_id": "select_mode_tag",
                        "value": "tag",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "📅 날짜 구간"},
                        "action_id": "select_mode_date",
                        "value": "date",
                    },
                ],
            },
        ]
        say(blocks=blocks, text="비교 방식을 선택해주세요.", thread_ts=thread_ts)

    # --- 비교 방식 선택: 태그 ---
    @app.action("select_mode_tag")
    def handle_mode_tag(ack, body, say):
        ack()
        thread_ts = _get_thread_ts(body)
        user = body["user"]["id"]

        session_key = f"{user}_{thread_ts}"
        if session_key in _sessions:
            _sessions[session_key]["mode"] = "tag"

        say(
            text="시작 태그와 종료 태그를 입력해주세요.\n예: `v1.0 v1.1`",
            thread_ts=thread_ts,
        )

    # --- 비교 방식 선택: 날짜 ---
    @app.action("select_mode_date")
    def handle_mode_date(ack, body, say):
        ack()
        thread_ts = _get_thread_ts(body)
        user = body["user"]["id"]

        session_key = f"{user}_{thread_ts}"
        if session_key in _sessions:
            _sessions[session_key]["mode"] = "date"

        say(
            text="브랜치명, 시작일, 종료일을 입력해주세요.\n예: `develop 2026-04-01 2026-04-25`",
            thread_ts=thread_ts,
        )

    # --- 태그/날짜 입력 처리 (스레드 메시지) ---
    @app.event("message")
    def handle_thread_message(event, say, client):
        """스레드 내 메시지를 처리하여 태그/날짜 입력을 받는다."""
        if event.get("bot_id"):
            return

        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return

        user = event.get("user", "")
        text = event.get("text", "").strip()
        channel = event.get("channel", "")
        session_key = f"{user}_{thread_ts}"

        session = _sessions.get(session_key)
        if not session or "mode" not in session:
            return

        mode = session["mode"]

        # 이미 ref가 설정되어 있으면 무시 (중복 처리 방지)
        if "from_ref" in session:
            return

        if mode == "tag":
            parts = text.split()
            if len(parts) >= 2:
                session["from_ref"] = parts[0]
                session["to_ref"] = parts[1]
                session["branch"] = None
                _show_output_selection(say, thread_ts)
            else:
                say(
                    text="태그 두 개를 입력해주세요.\n예: `v1.0 v1.1`",
                    thread_ts=thread_ts,
                )
        elif mode == "date":
            parts = text.split()
            if len(parts) >= 3:
                session["branch"] = parts[0]
                session["from_ref"] = parts[1]
                session["to_ref"] = parts[2]
                _show_output_selection(say, thread_ts)
            else:
                say(
                    text="브랜치, 시작일, 종료일을 입력해주세요.\n예: `develop 2026-04-01 2026-04-25`",
                    thread_ts=thread_ts,
                )

    # --- 결과 처리 선택 ---
    @app.action("select_output_slack")
    def handle_output_slack(ack, body, say, client):
        ack()
        thread_ts = _get_thread_ts(body)
        user = body["user"]["id"]
        channel = body["channel"]["id"]

        session_key = f"{user}_{thread_ts}"
        session = _sessions.get(session_key)
        if not session:
            say(text="세션이 만료되었습니다. 다시 시작해주세요.", thread_ts=thread_ts)
            return

        session["output"] = "slack"
        say(
            text=f"⏳ {session['repo']} ({session['from_ref']} → {session['to_ref']}) 패치가이드 생성 중...",
            thread_ts=thread_ts,
        )

        # 백그라운드에서 처리
        threading.Thread(
            target=_run_generation,
            args=(session, channel, thread_ts),
            daemon=True,
        ).start()

    @app.action("select_output_github")
    def handle_output_github(ack, body, say, client):
        ack()
        thread_ts = _get_thread_ts(body)
        user = body["user"]["id"]
        channel = body["channel"]["id"]

        session_key = f"{user}_{thread_ts}"
        session = _sessions.get(session_key)
        if not session:
            say(text="세션이 만료되었습니다. 다시 시작해주세요.", thread_ts=thread_ts)
            return

        session["output"] = "github"
        say(
            text=f"⏳ {session['repo']} ({session['from_ref']} → {session['to_ref']}) 패치가이드 생성 + PR 생성 중...",
            thread_ts=thread_ts,
        )

        threading.Thread(
            target=_run_generation,
            args=(session, channel, thread_ts),
            daemon=True,
        ).start()

    # --- 상세 보기 버튼 ---
    @app.action("patch_guide_detail")
    def handle_detail(ack, body, say):
        ack()
        thread_ts = _get_thread_ts(body)
        channel = body["channel"]["id"]
        value = body["actions"][0]["value"]

        repo, from_ref, to_ref = value.split("|")
        session_key = _find_session_by_refs(repo, from_ref, to_ref)

        if session_key and "guide" in _sessions.get(session_key, {}):
            guide = _sessions[session_key]["guide"]
            publisher = SlackPublisher()
            publisher.publish_detail(channel, guide, thread_ts)
        else:
            say(text="세션이 만료되었습니다. 다시 생성해주세요.", thread_ts=thread_ts)

    # --- repo에 저장 버튼 ---
    @app.action("patch_guide_save")
    def handle_save(ack, body, say):
        ack()
        thread_ts = _get_thread_ts(body)
        channel = body["channel"]["id"]
        value = body["actions"][0]["value"]

        repo, from_ref, to_ref = value.split("|")
        session_key = _find_session_by_refs(repo, from_ref, to_ref)

        if session_key and "guide" in _sessions.get(session_key, {}):
            guide = _sessions[session_key]["guide"]
            say(text="💾 repo에 저장 중...", thread_ts=thread_ts)

            try:
                gh_publisher = GitHubPublisher()
                pr_url = gh_publisher.publish(guide)
                say(
                    text=f"✅ PR 생성 완료\n📎 {pr_url}",
                    thread_ts=thread_ts,
                )
            except Exception as e:
                logger.exception("PR 생성 실패")
                say(text=f"❌ PR 생성 실패: {e}", thread_ts=thread_ts)
        else:
            say(text="세션이 만료되었습니다. 다시 생성해주세요.", thread_ts=thread_ts)


def _show_output_selection(say, thread_ts: str):
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "결과를 어떻게 받으시겠어요?",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "💬 여기서 바로 보기"},
                    "action_id": "select_output_slack",
                    "value": "slack",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📂 repo에 PR 생성"},
                    "action_id": "select_output_github",
                    "value": "github",
                    "style": "primary",
                },
            ],
        },
    ]
    say(blocks=blocks, text="결과를 어떻게 받으시겠어요?", thread_ts=thread_ts)


def _run_generation(session: dict, channel: str, thread_ts: str):
    """백그라운드에서 패치가이드를 생성한다."""
    publisher = SlackPublisher()

    try:
        repo = session["repo"]
        mode = CompareMode(session["mode"])
        from_ref = session["from_ref"]
        to_ref = session["to_ref"]
        branch = session.get("branch")

        # Step 1: diff 수집
        collector = DiffCollector()
        diff = collector.collect(repo, mode, from_ref, to_ref, branch)

        if not diff.files:
            publisher.send_message(
                channel,
                f"ℹ️ {repo} ({from_ref} → {to_ref}) 변경사항이 없습니다.",
                thread_ts,
            )
            return

        # Step 2: 파일 분류
        classified = classify(diff)

        if not classified.has_changes:
            publisher.send_message(
                channel,
                f"ℹ️ {repo} ({from_ref} → {to_ref}) 패치가이드 대상 변경사항이 없습니다.\n(변경 파일 {len(diff.files)}개 중 패치 대상 0개)",
                thread_ts,
            )
            return

        # Step 3: AI 분석
        analyzer = Analyzer()
        guide = analyzer.analyze(classified)

        # Step 4: 문서 생성
        generator = Generator()
        guide = generator.generate(classified, guide)

        # 세션에 가이드 저장 (상세 보기/저장 버튼용)
        session["guide"] = guide

        # Step 5: 결과 전달
        publisher.publish_summary(channel, classified, guide, thread_ts)

        # github 모드면 자동으로 PR도 생성
        if session.get("output") == "github":
            gh_publisher = GitHubPublisher()
            pr_url = gh_publisher.publish(guide)
            publisher.send_message(
                channel,
                f"✅ PR 생성 완료\n📎 {pr_url}",
                thread_ts,
            )

    except Exception as e:
        logger.exception("패치가이드 생성 실패")
        publisher.send_message(
            channel,
            f"❌ 패치가이드 생성 실패: {e}",
            thread_ts,
        )


def _get_thread_ts(body: dict) -> str:
    """인터랙션 body에서 thread_ts를 추출한다."""
    message = body.get("message", {})
    return message.get("thread_ts") or message.get("ts", "")


def _find_session_by_refs(repo: str, from_ref: str, to_ref: str) -> str | None:
    """repo/ref로 세션을 찾는다."""
    for key, session in _sessions.items():
        if (
            session.get("repo") == repo
            and session.get("from_ref") == from_ref
            and session.get("to_ref") == to_ref
        ):
            return key
    return None
