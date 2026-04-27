"""Slack Block Kit 메시지를 구성하고 전송한다."""

from __future__ import annotations

from slack_sdk import WebClient

from patch_helper.config import settings
from patch_helper.core.models import ClassifiedChanges, PatchGuide


class SlackPublisher:
    """패치가이드 결과를 Slack으로 전송한다."""

    MAX_BLOCK_TEXT_LENGTH = 3000  # Slack block text 제한

    def __init__(self, token: str | None = None):
        self._client = WebClient(token=token or settings.slack_bot_token)

    def publish_summary(
        self,
        channel: str,
        classified: ClassifiedChanges,
        guide: PatchGuide,
        thread_ts: str | None = None,
    ) -> dict:
        """요약 메시지 + 버튼을 전송한다."""
        counts = classified.summary
        repo_name = guide.repo.split("/")[-1] if "/" in guide.repo else guide.repo

        summary_lines = []
        if counts["db"] > 0:
            summary_lines.append(f"🗄️ DB 변경: {counts['db']}건 (MySQL + Oracle)")
        if counts["es"] > 0:
            summary_lines.append(f"🔍 ES 변경: {counts['es']}건")
        if counts["config"] > 0:
            summary_lines.append(f"⚙️ 설정 변경: {counts['config']}건")
        if counts["init_data"] > 0:
            summary_lines.append(f"📦 Init Data: {counts['init_data']}건")
        if counts["initial_data"] > 0:
            summary_lines.append(f"📦 초기 데이터: {counts['initial_data']}건")

        if not summary_lines:
            summary_lines.append("패치가이드 대상 변경사항이 없습니다.")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"✅ {repo_name} 패치가이드 ({guide.from_ref} → {guide.to_ref})",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(summary_lines),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "📋 상세 보기"},
                        "action_id": "patch_guide_detail",
                        "value": f"{guide.repo}|{guide.from_ref}|{guide.to_ref}",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "💾 repo에 저장"},
                        "action_id": "patch_guide_save",
                        "value": f"{guide.repo}|{guide.from_ref}|{guide.to_ref}",
                        "style": "primary",
                    },
                ],
            },
        ]

        result = self._client.chat_postMessage(
            channel=channel,
            blocks=blocks,
            text=f"패치가이드: {repo_name} {guide.from_ref} → {guide.to_ref}",
            thread_ts=thread_ts,
        )
        return result.data

    def publish_detail(
        self,
        channel: str,
        guide: PatchGuide,
        thread_ts: str,
    ) -> list[dict]:
        """스레드에 상세 내용을 펼친다."""
        results = []

        for analysis in guide.analyses:
            content = analysis.content
            # Slack 메시지 길이 제한 대응
            chunks = self._split_content(content, self.MAX_BLOCK_TEXT_LENGTH)

            for i, chunk in enumerate(chunks):
                title = analysis.category
                if len(chunks) > 1:
                    title += f" ({i + 1}/{len(chunks)})"

                blocks = [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": title},
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": chunk},
                    },
                ]

                result = self._client.chat_postMessage(
                    channel=channel,
                    blocks=blocks,
                    text=title,
                    thread_ts=thread_ts,
                )
                results.append(result.data)

        # 생성된 파일 목록
        if guide.files:
            file_list = "\n".join(f"• `{name}`" for name in guide.files.keys())
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📁 생성된 파일:*\n{file_list}",
                    },
                },
            ]
            result = self._client.chat_postMessage(
                channel=channel,
                blocks=blocks,
                text="생성된 파일 목록",
                thread_ts=thread_ts,
            )
            results.append(result.data)

        return results

    def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
    ) -> dict:
        """일반 텍스트 메시지를 전송한다."""
        result = self._client.chat_postMessage(
            channel=channel,
            text=text,
            thread_ts=thread_ts,
        )
        return result.data

    def _split_content(self, content: str, max_length: int) -> list[str]:
        """긴 텍스트를 max_length 이하로 분할한다."""
        if len(content) <= max_length:
            return [content]

        chunks = []
        while content:
            if len(content) <= max_length:
                chunks.append(content)
                break

            # 줄바꿈 기준으로 자르기
            split_pos = content.rfind("\n", 0, max_length)
            if split_pos == -1:
                split_pos = max_length

            chunks.append(content[:split_pos])
            content = content[split_pos:].lstrip("\n")

        return chunks
