import re
import asyncio
import httpx
from config import config

class MentionHandler:
    def __init__(self):
        self.bot = None
        self.pending_mentions = {}  # mention_id -> mention data

    def set_bot(self, bot):
        self.bot = bot

    def clean_text(self, text: str) -> str:
        """Replace Slack user IDs with readable names."""
        text = re.sub(r'<@' + config.SLACK_USER_ID + r'>', '@you', text)
        text = re.sub(r'<@[A-Z0-9]+>', '@someone', text)
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

        # Store for response handling
        mention_id = mention["id"]
        self.pending_mentions[mention_id] = {
            "mention": mention,
            "suggested_reply": analysis.get("suggested_reply", "On it!")
        }

        # Build notification
        type_emoji = "\U0001f6a8" if analysis.get("type") == "urgent" else "\U0001f514"

        message = (
            f"{type_emoji} *{username}* mentioned you in *#{channel}*\n\n"
            f"_{clean}_\n\n"
            f"\U0001f916 {analysis.get('summary', 'Someone mentioned you.')}\n\n"
            f"Reply:\n"
            f"`ack {mention_id}` \u2014 Acknowledge on Slack\n"
            f"`ignore {mention_id}` \u2014 Ignore"
        )

        await self.bot.send_message(
            chat_id=config.ALLOWED_USER_ID,
            text=message,
            parse_mode="Markdown"
        )

    async def acknowledge(self, mention_id: str) -> bool:
        """Post acknowledgement to Slack."""
        if mention_id not in self.pending_mentions:
            return False

        data = self.pending_mentions[mention_id]
        mention = data["mention"]
        reply = data["suggested_reply"]
        channel_id = mention.get("channel_id", "")

        if not channel_id:
            return False

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"},
                json={
                    "channel": channel_id,
                    "text": reply,
                    "thread_ts": mention.get("ts")  # reply in thread
                }
            )
            data_resp = response.json()
            if data_resp.get("ok"):
                del self.pending_mentions[mention_id]
                return True
            return False

    def ignore(self, mention_id: str):
        """Dismiss a mention."""
        self.pending_mentions.pop(mention_id, None)

mention_handler = MentionHandler()
