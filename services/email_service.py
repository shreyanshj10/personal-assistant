import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import config

class EmailService:
    def __init__(self):
        self._scheduled_timers = []

    async def send_email(self, body: str, subject: str, extra_recipients: list = []):
        """Send email via Zoho SMTP with fallback methods."""
        all_recipients = config.ZOHO_RECIPIENTS + extra_recipients

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config.YOUR_NAME} <{config.ZOHO_EMAIL}>"
        msg["To"] = ", ".join(all_recipients)

        # Send as HTML so <b> tags render properly
        html_body = f"<html><body>{body.replace(chr(10), '<br>')}</body></html>"
        text_body = body  # plain text fallback

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Try SSL first (port 465), then TLS (port 587)
        last_error = None

        # Method 1: SSL on port 465
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.zoho.in", 465, context=context, timeout=30) as server:
                server.login(config.ZOHO_EMAIL, config.ZOHO_PASSWORD)
                server.sendmail(config.ZOHO_EMAIL, all_recipients, msg.as_string())
                return True
        except Exception as e:
            last_error = e
            print(f"SSL method failed: {e}")

        # Method 2: TLS on port 587
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP("smtp.zoho.in", 587, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(config.ZOHO_EMAIL, config.ZOHO_PASSWORD)
                server.sendmail(config.ZOHO_EMAIL, all_recipients, msg.as_string())
                return True
        except Exception as e:
            last_error = e
            print(f"TLS method failed: {e}")

        # Both failed
        raise Exception(f"Email failed with both SSL and TLS: {last_error}")

    def schedule_email(self, body: str, subject: str, unix_timestamp: int, extra_recipients: list = []):
        """Schedule email using threading.Timer."""
        import threading
        import pytz
        from datetime import datetime

        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        delay = unix_timestamp - now.timestamp()

        if delay <= 0:
            raise ValueError("Scheduled time is in the past")

        def send_sync():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self.send_email(body, subject, extra_recipients)
                )
            except Exception as e:
                print(f"Scheduled email failed: {e}")
            finally:
                loop.close()

        timer = threading.Timer(delay, send_sync)
        timer.daemon = True
        timer.start()
        self._scheduled_timers.append(timer)
        return delay

email_service = EmailService()
