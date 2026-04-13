import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")
    SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")
    ZOHO_EMAIL = os.getenv("ZOHO_EMAIL")
    ZOHO_PASSWORD = os.getenv("ZOHO_PASSWORD")
    ZOHO_RECIPIENT = os.getenv("ZOHO_RECIPIENT")
    YOUR_NAME = os.getenv("YOUR_NAME", "Shreyansh Jain")
    SLACK_USER_ID = os.getenv("SLACK_USER_ID", "U0AL5KAJGD6")

    def validate(self):
        required = ["TELEGRAM_BOT_TOKEN", "ALLOWED_USER_ID", "ANTHROPIC_API_KEY",
                   "SLACK_USER_TOKEN", "SLACK_CHANNEL_ID", "ZOHO_EMAIL",
                   "ZOHO_PASSWORD", "ZOHO_RECIPIENT"]
        for key in required:
            if not getattr(self, key):
                raise ValueError(f"Missing required env var: {key}")

config = Config()
