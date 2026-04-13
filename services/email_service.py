import smtplib
import ssl
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import config

class EmailService:
    def __init__(self):
        self._scheduled_timers = []

    async def send_email(self, body: str, subject: str, extra_recipients: list = []):
        all_recipients = config.ZOHO_RECIPIENTS + extra_recipients

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config.YOUR_NAME} <{config.ZOHO_EMAIL}>"
        msg["To"] = ", ".join(all_recipients)

        # Send as HTML so <b> tags render
        html_body = body.replace("\n", "<br>")
        msg.attach(MIMEText(html_body, "html"))

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.zoho.in", 465, context=context) as server:
            server.login(config.ZOHO_EMAIL, config.ZOHO_PASSWORD)
            server.sendmail(config.ZOHO_EMAIL, all_recipients, msg.as_string())

    def schedule_email(self, body: str, subject: str, unix_timestamp: int, extra_recipients: list = [], notify_callback=None):
        """Schedule email to send at unix_timestamp. Optionally call notify_callback when sent."""
        import pytz
        from datetime import datetime
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        delay = unix_timestamp - now.timestamp()

        if delay <= 0:
            raise ValueError("Scheduled time is in the past")

        def send_and_notify():
            import asyncio
            import smtplib, ssl
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from config import config as cfg

            all_recipients = cfg.ZOHO_RECIPIENTS + extra_recipients
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{cfg.YOUR_NAME} <{cfg.ZOHO_EMAIL}>"
            msg["To"] = ", ".join(all_recipients)
            html_body = body.replace("\n", "<br>")
            msg.attach(MIMEText(html_body, "html"))

            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.zoho.in", 465, context=context) as server:
                server.login(cfg.ZOHO_EMAIL, cfg.ZOHO_PASSWORD)
                server.sendmail(cfg.ZOHO_EMAIL, all_recipients, msg.as_string())

            if notify_callback:
                notify_callback()

        timer = threading.Timer(delay, send_and_notify)
        timer.daemon = True
        timer.start()
        self._scheduled_timers.append(timer)
        return delay

email_service = EmailService()
