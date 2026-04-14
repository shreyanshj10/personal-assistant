import asyncio
import logging
import httpx
from config import config

logger = logging.getLogger(__name__)

class SlackService:
    BASE_URL = "https://slack.com/api"

    async def _post_with_retry(self, url: str, headers: dict, payload: dict, max_retries: int = 3) -> dict:
        """POST with exponential backoff retry."""
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    data = response.json()
                    if data.get("ok"):
                        return data
                    # Slack-specific retryable errors
                    if data.get("error") in ["ratelimited", "service_unavailable"]:
                        wait = 2 ** attempt
                        logger.warning(f"Slack retryable error: {data.get('error')}. Waiting {wait}s...")
                        await asyncio.sleep(wait)
                        continue
                    raise Exception(f"Slack error: {data.get('error')}")
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning(f"Slack attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)

    async def post_message(self, text: str):
        await self._post_with_retry(
            f"{self.BASE_URL}/chat.postMessage",
            headers={"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"},
            payload={"channel": config.SLACK_CHANNEL_ID, "text": text}
        )

    async def schedule_message(self, text: str, unix_timestamp: int):
        await self._post_with_retry(
            f"{self.BASE_URL}/chat.scheduleMessage",
            headers={"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"},
            payload={
                "channel": config.SLACK_CHANNEL_ID,
                "text": text,
                "post_at": unix_timestamp
            }
        )

slack_service = SlackService()
