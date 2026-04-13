import time
import logging
import httpx
from config import config

logger = logging.getLogger(__name__)

class SlackMonitor:
    SEARCH_BUFFER = 300  # 5 min buffer for Slack search indexing delay

    def __init__(self):
        self.last_checked = int(time.time()) - self.SEARCH_BUFFER
        self.processed_ids = set()

    async def resolve_channel_name(self, channel_id: str) -> str:
        if not channel_id:
            return "unknown"
        if channel_id.startswith("D"):
            return "DM"
        if channel_id.startswith("U"):
            return "DM"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://slack.com/api/conversations.info",
                    headers={"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"},
                    params={"channel": channel_id}
                )
                data = response.json()
                return data.get("channel", {}).get("name", channel_id)
        except:
            return channel_id

    async def get_mentions(self) -> list:
        """Search Slack for new messages mentioning the user since last check."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://slack.com/api/search.messages",
                    headers={"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"},
                    params={
                        "query": f"<@{config.SLACK_USER_ID}>",
                        "sort": "timestamp",
                        "sort_dir": "desc",
                        "count": 10
                    }
                )
                data = response.json()

                if not data.get("ok"):
                    print(f"Slack search error: {data.get('error')}")
                    return []

                messages = data.get("messages", {}).get("matches", [])
                total = data.get("messages", {}).get("total", 0)
                logger.info(f"Slack search: {total} total results, {len(messages)} matches returned, last_checked={self.last_checked}")
                new_mentions = []

                for msg in messages:
                    msg_ts = float(msg.get("ts", 0))
                    msg_id = msg.get("iid", msg.get("ts", ""))
                    logger.info(f"  msg ts={msg_ts}, last_checked={self.last_checked}, new={msg_ts > self.last_checked}, id={msg_id}, processed={msg_id in self.processed_ids}")

                    if msg_ts > self.last_checked and msg_id not in self.processed_ids:
                        channel_info = msg.get("channel", {})
                        channel_name = channel_info.get("name", "")
                        channel_id = channel_info.get("id", "")

                        # If name is empty or looks like a user ID, resolve it
                        if not channel_name or channel_name.startswith("U"):
                            channel_name = await self.resolve_channel_name(channel_id)

                        new_mentions.append({
                            "text": msg.get("text", ""),
                            "username": msg.get("username", "Someone"),
                            "channel_name": channel_name,
                            "channel_id": channel_id,
                            "ts": msg_ts,
                            "id": msg_id
                        })
                        self.processed_ids.add(msg_id)

                self.last_checked = int(time.time()) - self.SEARCH_BUFFER

                # Prevent set from growing too large
                if len(self.processed_ids) > 500:
                    self.processed_ids = set(list(self.processed_ids)[-250:])

                return new_mentions

        except Exception as e:
            print(f"Slack monitor error: {e}")
            return []

slack_monitor = SlackMonitor()
