import time
import httpx
from config import config

class SlackMonitor:
    def __init__(self):
        self.last_checked = int(time.time())
        self.processed_ids = set()

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
                new_mentions = []

                for msg in messages:
                    msg_ts = float(msg.get("ts", 0))
                    msg_id = msg.get("iid", msg.get("ts", ""))

                    if msg_ts > self.last_checked and msg_id not in self.processed_ids:
                        new_mentions.append({
                            "text": msg.get("text", ""),
                            "username": msg.get("username", "Someone"),
                            "channel_name": msg.get("channel", {}).get("name", "unknown"),
                            "channel_id": msg.get("channel", {}).get("id", ""),
                            "ts": msg_ts,
                            "id": msg_id
                        })
                        self.processed_ids.add(msg_id)

                self.last_checked = int(time.time())

                # Prevent set from growing too large
                if len(self.processed_ids) > 500:
                    self.processed_ids = set(list(self.processed_ids)[-250:])

                return new_mentions

        except Exception as e:
            print(f"Slack monitor error: {e}")
            return []

slack_monitor = SlackMonitor()
