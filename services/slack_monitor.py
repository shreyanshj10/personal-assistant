import time
import httpx
from config import config

class SlackMonitor:
    def __init__(self):
        # Set last_checked to current time on startup
        # This means we only get NEW mentions after bot starts
        self.last_checked = time.time()
        self.processed_keys = set()  # "channel_id:ts" keys

    async def get_mentions(self) -> list:
        """Search Slack for new messages mentioning the user since last check."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://slack.com/api/search.messages",
                    headers={"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"},
                    params={
                        "query": f"<@{config.SLACK_USER_ID}>",
                        "sort": "timestamp",
                        "sort_dir": "desc",
                        "count": 20
                    }
                )
                data = response.json()

                if not data.get("ok"):
                    print(f"Slack search error: {data.get('error')}")
                    return []

                messages = data.get("messages", {}).get("matches", [])
                new_mentions = []
                current_time = time.time()

                for msg in messages:
                    msg_ts = float(msg.get("ts", 0))
                    channel_id = msg.get("channel", {}).get("id", "")

                    # Create unique key from channel + timestamp
                    unique_key = f"{channel_id}:{msg_ts}"

                    # Only process if:
                    # 1. Message is newer than when bot started
                    # 2. Message hasn't been processed before
                    # 3. Message is newer than last check
                    if (msg_ts > self.last_checked and
                        unique_key not in self.processed_keys):

                        channel_info = msg.get("channel", {})
                        channel_name = channel_info.get("name", "")

                        # Resolve channel name if it looks wrong
                        if not channel_name or channel_name.startswith("U"):
                            channel_name = await self.resolve_channel_name(channel_id)

                        new_mentions.append({
                            "text": msg.get("text", ""),
                            "username": msg.get("username", "Someone"),
                            "channel_name": channel_name,
                            "channel_id": channel_id,
                            "ts": msg_ts,
                            "unique_key": unique_key
                        })
                        self.processed_keys.add(unique_key)

                # Update last_checked to NOW after processing
                self.last_checked = current_time

                # Prevent set from growing too large
                if len(self.processed_keys) > 1000:
                    self.processed_keys = set(list(self.processed_keys)[-500:])

                return new_mentions

        except Exception as e:
            print(f"Slack monitor error: {e}")
            return []

    async def resolve_channel_name(self, channel_id: str) -> str:
        if not channel_id:
            return "unknown"
        if channel_id.startswith("D") or channel_id.startswith("U"):
            return "DM"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    "https://slack.com/api/conversations.info",
                    headers={"Authorization": f"Bearer {config.SLACK_USER_TOKEN}"},
                    params={"channel": channel_id}
                )
                data = response.json()
                return data.get("channel", {}).get("name", channel_id)
        except:
            return channel_id

slack_monitor = SlackMonitor()
