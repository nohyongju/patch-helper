"""Slack 버튼/인터랙션 핸들러."""

from __future__ import annotations

import logging
import threading

from slack_bolt import App

from patch_helper.bot.commands import (
    SERVICE_CHECKBOXES_ACTION_ID,
    SERVICE_CHECKBOXES_BLOCK_ID,
    SERVICE_SELECT_DONE_ACTION_ID,
)
from patch_helper.core.analyzer import Analyzer
from patch_helper.core.classifier import classify, supplement_jpo_id_files
from patch_helper.core.collector import DiffCollector
from patch_helper.core.generator import Generator
from patch_helper.core.models import CompareMode, PatchGuide
from patch_helper.publisher.github_publisher import GitHubPublisher
from patch_helper.publisher.slack_publisher import SlackPublisher

logger = logging.getLogger(__name__)

# 세션 상태를 임시 저장 (실제 운영에서는 Redis 등 사용 권장)
# 세션 스키마:
#   repos: list[str]                   — 선택된 서비스 repo 목록
#   mode: "tag" | "date"
#   from_ref, to_ref: str              — 모든 repos에 일괄 적용
#   branch: str | None                 — date 모드 전용
#   output: "slack" | "github"
#   guides: dict[repo, PatchGuide]     — repo별 생성 결과
_sessions: dict[str, dict] = {}


def register_views(app: App):
    """버튼 인터랙션 핸들러를 등록한다."""

    # --- 서비스 선택 (체크박스 변경 시 ack만 처리) ---
    @app.action(SERVICE_CHECKBOXES_ACTION_ID)
    def handle_service_checkboxes(ack):
        ack()

    # --- 서비스 선택 완료 (다음 버튼) ---
    @app.action(SERVICE_SELECT_DONE_ACTION_ID)
    def handle_service_select_done(ack, body, say):
        ack()
        thread_ts = _get_thread_ts(body)
        user = body["user"]["id"]

        repos = _extract_selected_repos(body)
        if not repos:
            say(
                text="⚠️ 서비스를 1개 이상 선택해주세요.",
                thread_ts=thread_ts,
            )
            return

        # 세션 저장 (다중 repo)
        session_key = f"{user}_{thread_ts}"
        _sessions[session_key] = {"repos": repos}

        repos_list = "\n".join(f"• `{r}`" for r in repos)
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*선택된 서비스 ({len(repos)}개):*\n{repos_list}\n\n"
                        "비교 방식을 선택해주세요. (모든 서비스에 동일하게 적용됩니다)"
                    ),
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

    # --- 메시지 통합 핸들러 (스레드 입력 + DM) ---
    @app.event("message")
    def handle_message(event, say, client):
        """스레드 내 태그/날짜 입력 및 DM 메시지를 처리한다."""
        if event.get("bot_id"):
            return

        thread_ts = event.get("thread_ts")

        # DM에서 새 메시지 (스레드가 아닌 경우)
        if not thread_ts and event.get("channel_type") == "im":
            text = event.get("text", "").lower()
            if "생성" in text or "패치" in text or "가이드" in text:
                from patch_helper.bot.commands import _show_service_selection
                _show_service_selection(say, event.get("ts"))
            else:
                say(
                    text="패치가이드를 생성하려면 `생성해줘` 라고 말씀해주세요.",
                    thread_ts=event.get("ts"),
                )
            return

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

        # 이미 출력 방식까지 선택 완료된 세션이면 무시
        if "output" in session:
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
                if not _is_valid_date(parts[1]) or not _is_valid_date(parts[2]):
                    say(
                        text="날짜 형식이 올바르지 않습니다. `YYYY-MM-DD` 형식으로 입력해주세요.\n예: `develop 2026-04-01 2026-04-25`",
                        thread_ts=thread_ts,
                    )
                    return
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
        repos = session.get("repos") or []
        say(
            text=(
                f"⏳ {len(repos)}개 서비스 패치가이드 생성 중...\n"
                f"({session['from_ref']} → {session['to_ref']})"
            ),
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
        repos = session.get("repos") or []
        say(
            text=(
                f"⏳ {len(repos)}개 서비스 패치가이드 생성 + PR 생성 중...\n"
                f"({session['from_ref']} → {session['to_ref']})"
            ),
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
        guide = _find_guide(repo, from_ref, to_ref)

        if guide is not None:
            publisher = SlackPublisher()
            publisher.publish_detail(channel, guide, thread_ts)
        else:
            say(text="세션이 만료되었습니다. 다시 생성해주세요.", thread_ts=thread_ts)

    # --- 모두 저장 버튼 (모든 서비스를 단일 PR로 통합 생성) ---
    @app.action("patch_guide_save_all")
    def handle_save_all(ack, body, say):
        ack()
        thread_ts = _get_thread_ts(body)
        session_key = body["actions"][0]["value"]

        session = _sessions.get(session_key)
        guides = (session or {}).get("guides") or {}
        if not guides:
            say(text="세션이 만료되었습니다. 다시 생성해주세요.", thread_ts=thread_ts)
            return

        say(
            text=f"💾 {len(guides)}개 서비스를 단일 PR로 묶어 생성합니다...",
            thread_ts=thread_ts,
        )

        try:
            gh_publisher = GitHubPublisher()
            pr_url = gh_publisher.publish_batch(list(guides.values()))
            say(
                text=f"✅ 단일 PR 생성 완료 ({len(guides)}개 서비스 통합)\n📎 {pr_url}",
                thread_ts=thread_ts,
            )
        except Exception as e:
            logger.exception("일괄 PR 생성 실패")
            say(text=f"❌ 일괄 PR 생성 실패: {e}", thread_ts=thread_ts)

    # --- repo에 저장 버튼 (단일 — 호환용, 이전 메시지의 버튼 클릭 대응) ---
    @app.action("patch_guide_save")
    def handle_save(ack, body, say):
        ack()
        thread_ts = _get_thread_ts(body)
        value = body["actions"][0]["value"]

        repo, from_ref, to_ref = value.split("|")
        guide = _find_guide(repo, from_ref, to_ref)

        if guide is not None:
            say(text=f"💾 *{repo}* repo에 저장 중...", thread_ts=thread_ts)

            try:
                gh_publisher = GitHubPublisher()
                pr_url = gh_publisher.publish(guide)
                say(
                    text=f"✅ *{repo}* PR 생성 완료\n📎 {pr_url}",
                    thread_ts=thread_ts,
                )
            except Exception as e:
                logger.exception("PR 생성 실패")
                say(text=f"❌ *{repo}* PR 생성 실패: {e}", thread_ts=thread_ts)
        else:
            say(text="세션이 만료되었습니다. 다시 생성해주세요.", thread_ts=thread_ts)


def _is_valid_date(value: str) -> bool:
    """YYYY-MM-DD 형식인지 검증한다."""
    from datetime import datetime
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


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
    """백그라운드에서 선택된 모든 서비스의 패치가이드를 순차 생성한다.

    한 서비스가 실패해도 나머지 서비스는 계속 처리한다.
    """
    publisher = SlackPublisher()
    repos: list[str] = session.get("repos") or []
    mode = CompareMode(session["mode"])
    from_ref = session["from_ref"]
    to_ref = session["to_ref"]
    branch = session.get("branch")
    output = session.get("output", "slack")

    session.setdefault("guides", {})

    success_count = 0
    fail_count = 0
    skip_count = 0

    for idx, repo in enumerate(repos, start=1):
        prefix = f"[{idx}/{len(repos)}] *{repo}*"
        try:
            publisher.send_message(channel, f"▶️ {prefix} 시작", thread_ts)

            collector = DiffCollector()
            diff = collector.collect(repo, mode, from_ref, to_ref, branch)

            if not diff.files:
                publisher.send_message(
                    channel,
                    f"⏭️ {prefix} 변경사항이 없어 건너뜁니다.",
                    thread_ts,
                )
                skip_count += 1
                continue

            classified = classify(diff)
            supplement_jpo_id_files(classified, collector, diff.head_sha)

            if not classified.has_changes:
                publisher.send_message(
                    channel,
                    f"⏭️ {prefix} 패치가이드 대상 변경사항이 없어 건너뜁니다. "
                    f"(변경 파일 {len(diff.files)}개 중 패치 대상 0개)",
                    thread_ts,
                )
                skip_count += 1
                continue

            analyzer = Analyzer()
            guide = analyzer.analyze(classified)

            generator = Generator()
            guide = generator.generate(classified, guide)

            # 가이드 저장 (상세 보기/저장 버튼이 조회)
            session["guides"][repo] = guide

            # 결과 요약 + 버튼 (개별 PR은 만들지 않음 — 마지막에 일괄 처리)
            publisher.publish_summary(channel, classified, guide, thread_ts)

            success_count += 1

        except Exception as e:
            logger.exception("%s 패치가이드 생성 실패", repo)
            publisher.send_message(
                channel,
                f"❌ {prefix} 생성 실패: {e}",
                thread_ts,
            )
            fail_count += 1

    # 최종 요약
    publisher.send_message(
        channel,
        (
            f"🏁 전체 완료 — 성공 {success_count}, 실패 {fail_count}, "
            f"건너뜀 {skip_count} / 총 {len(repos)}"
        ),
        thread_ts,
    )

    guides = session.get("guides") or {}

    # github 모드: 모든 성공한 가이드를 단일 PR로 일괄 생성
    if output == "github" and guides:
        try:
            gh_publisher = GitHubPublisher()
            pr_url = gh_publisher.publish_batch(list(guides.values()))
            publisher.send_message(
                channel,
                f"✅ 단일 PR 생성 완료 ({len(guides)}개 서비스 통합)\n📎 {pr_url}",
                thread_ts,
            )
        except Exception as e:
            logger.exception("일괄 PR 생성 실패")
            publisher.send_message(
                channel,
                f"❌ 일괄 PR 생성 실패: {e}",
                thread_ts,
            )

    # slack 모드: '모두 저장' 버튼 게시 (사용자가 누르면 단일 PR 생성)
    elif output == "slack" and guides:
        _post_save_all_button(publisher, channel, thread_ts, session)


def _get_thread_ts(body: dict) -> str:
    """인터랙션 body에서 thread_ts를 추출한다."""
    message = body.get("message", {})
    return message.get("thread_ts") or message.get("ts", "")


def _post_save_all_button(
    publisher: SlackPublisher, channel: str, thread_ts: str, session: dict
) -> None:
    """다중 서비스 가이드 생성 후 '모두 저장' 버튼을 thread에 게시한다."""
    # session → session_key 역조회 (버튼 value로 사용)
    session_key = next(
        (k for k, v in _sessions.items() if v is session),
        None,
    )
    if session_key is None:
        return
    guides = session.get("guides") or {}
    repos_text = ", ".join(f"`{r}`" for r in guides.keys())
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{len(guides)}개 가이드*가 준비되었습니다: {repos_text}\n"
                    "아래 버튼을 누르면 모든 서비스의 PR을 일괄 생성합니다."
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📦 모두 저장 (일괄 PR)"},
                    "action_id": "patch_guide_save_all",
                    "value": session_key,
                    "style": "primary",
                }
            ],
        },
    ]
    publisher._client.chat_postMessage(
        channel=channel,
        blocks=blocks,
        text="모두 저장",
        thread_ts=thread_ts,
    )


def _extract_selected_repos(body: dict) -> list[str]:
    """다음 버튼 클릭 body에서 체크된 서비스 repo 목록을 추출한다."""
    state = body.get("state") or {}
    values = state.get("values") or {}
    block = values.get(SERVICE_CHECKBOXES_BLOCK_ID) or {}
    action = block.get(SERVICE_CHECKBOXES_ACTION_ID) or {}
    selected = action.get("selected_options") or []
    return [opt.get("value") for opt in selected if opt.get("value")]


def _find_guide(repo: str, from_ref: str, to_ref: str) -> PatchGuide | None:
    """다중 세션 중 repo/ref에 매칭되는 가이드를 찾는다.

    버튼 value의 ref는 guide.from_ref/to_ref(`branch@YYYY-MM-DD` 등 collector가
    가공한 형태) 기준이므로, 세션 입력 ref가 아니라 guide 자체의 ref와 매칭한다.
    """
    for session in _sessions.values():
        guides = session.get("guides") or {}
        guide = guides.get(repo)
        if guide and guide.from_ref == from_ref and guide.to_ref == to_ref:
            return guide
    return None
