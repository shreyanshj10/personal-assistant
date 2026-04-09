import httpx
from config import config

class SlackService:
    BASE_URL = "https://slack.com/api"

    async def post_message(self, text: str):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/chat.postMessage",
                headers={"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"},
                json={"channel": config.SLACK_CHANNEL_ID, "text": text}
            )
            data = response.json()
            if not data.get("ok"):
                raise Exception(f"Slack error: {data.get('error')}")

    async def schedule_message(self, text: str, unix_timestamp: int):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/chat.scheduleMessage",
                headers={"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"},
                json={
                    "channel": config.SLACK_CHANNEL_ID,
                    "text": text,
                    "post_at": unix_timestamp
                }
            )
            data = response.json()
            if not data.get("ok"):
                raise Exception(f"Slack schedule error: {data.get('error')}")

slack_service = SlackService()
