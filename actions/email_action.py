from services.email_service import email_service

class EmailAction:
    async def send(self, body: str, subject: str, extra_recipients: list = []):
        await email_service.send_email(body, subject, extra_recipients)

email_action = EmailAction()
