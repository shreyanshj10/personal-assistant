import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import config

class EmailService:
    async def send_email(self, body: str, subject: str, extra_recipients: list = []):
        all_recipients = [config.ZOHO_RECIPIENT] + extra_recipients

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

email_service = EmailService()
