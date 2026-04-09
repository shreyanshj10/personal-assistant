from services.slack_service import slack_service
from utils.scheduler import parse_time_to_unix

class SlackAction:
    async def send_now(self, text: str):
        await slack_service.post_message(text)

    async def schedule(self, text: str, time_str: str):
        unix_ts = parse_time_to_unix(time_str)
        await slack_service.schedule_message(text, unix_ts)
        return unix_ts

slack_action = SlackAction()
