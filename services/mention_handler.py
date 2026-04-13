import re
import asyncio
import httpx
from config import config

class MentionHandler:
    def __init__(self):
        self.bot = None
        self.pending_mentions = {}  # number -> mention data
        self.counter = 0

    def set_bot(self, bot):
        self.bot = bot

    def clean_text(self, text: str) -> str:
        """Replace Slack user IDs with readable names."""
        text = re.sub(r'<@' + config.SLACK_USER_ID + r'(\|[^>]*)?>', '@you', text)
        text = re.sub(r'<@[A-Z0-9]+(\|[^>]*)?>', '@someone', text)
        text = re.sub(r'<#[A-Z0-9]+\|([^>]+)>', r'#\1', text)
        return text

    async def analyze(self, text: str, username: str, channel: str) -> dict:
        """Use Claude to analyze the mention."""
        from brain import analyze_mention
        return await analyze_mention(text, username, channel)

    async def notify(self, mention: dict):
        """Send Telegram notification for a mention."""
        if not self.bot:
            return

        clean = self.clean_text(mention["text"])
        username = mention["username"]
        channel = mention["channel_name"]

        analysis = await self.analyze(mention["text"], username, channel)

        # Store with simple number
        self.counter += 1
        mention_num = self.counter
        self.pending_mentions[str(mention_num)] = {
            "mention": mention,
            "suggested_reply": analysis.get("suggested_reply", "On it!")
        }

        # Build notification
        type_emoji = "\U0001f6a8" if analysis.get("type") == "urgent" else "\U0001f514"

        message = (
            f"{type_emoji} *{username}* mentioned you in *#{channel}*\n\n"
            f"_{clean}_\n\n"
            f"\U0001f916 {analysis.get('summary', 'Someone mentioned you.')}\n\n"
            f"Reply *ack {mention_num}* to acknowledge on Slack\n"
            f"or *ignore {mention_num}* to dismiss"
        )

        await self.bot.send_message(
            chat_id=config.ALLOWED_USER_ID,
            text=message,
            parse_mode="Markdown"
        )

    def get_mention_data(self, mention_id: str) -> dict:
        """Get mention data for starting ack session. Returns None if not found."""
        if mention_id not in self.pending_mentions:
            return None
        data = self.pending_mentions[mention_id]
        mention = data["mention"]
        return {
            "mention_num": mention_id,
            "reply_text": data["suggested_reply"],
            "channel_id": mention.get("channel_id", ""),
            "thread_ts": str(mention.get("ts", "")),
            "username": mention.get("username", "Someone"),
        }

    def remove_mention(self, mention_id: str):
        """Remove a mention after successful ack."""
        self.pending_mentions.pop(mention_id, None)

    async def send_ack(self, channel_id: str, thread_ts: str, reply_text: str) -> bool:
        """Post acknowledgement reply to Slack."""
        if not channel_id:
            return False

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"},
                json={
                    "channel": channel_id,
                    "text": reply_text,
                    "thread_ts": thread_ts
                }
            )
            data_resp = response.json()
            return data_resp.get("ok", False)

    def ignore(self, mention_id: str):
        """Dismiss a mention."""
        self.pending_mentions.pop(mention_id, None)

mention_handler = MentionHandler()
