import logging
import asyncio
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import os
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from config import config
from memory import memory
import brain
import executor
from services.slack_monitor import slack_monitor
from services.mention_handler import mention_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_time_from_message(text: str) -> str:
    """Extract time from message using regex. Returns time string or None."""
    pattern = r'\b(\d{1,2}:\d{2}\s*[ap]m|\d{1,2}\s*[ap]m|\d{2}:\d{2})\b'
    match = re.search(pattern, text.strip(), re.IGNORECASE)
    return match.group(0) if match else None

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ['/', '/health']:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Jarvis is alive')
        else:
            self.send_response(404)
            self.end_headers()

    def do_HEAD(self):
        if self.path in ['/', '/health']:
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass

def start_health_server():
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = (update.message.text or "").strip()

    # Security — single user only
    if user_id != str(config.ALLOWED_USER_ID):
        return

    if not text:
        return

    # Smart ack handling — natural language or "ack N"
    if any(word in text.lower() for word in ['acknowledge', 'ack', 'reply']):
        # Determine which mention number
        mention_num = None
        if text.lower().startswith("ack "):
            mention_num = text[4:].strip()
        elif len(mention_handler.pending_mentions) == 1:
            mention_num = list(mention_handler.pending_mentions.keys())[0]
        elif len(mention_handler.pending_mentions) > 1:
            await update.message.reply_text(
                f"You have {len(mention_handler.pending_mentions)} pending mentions. Which one?\n" +
                "\n".join([f"ack {k}" for k in mention_handler.pending_mentions.keys()])
            )
            return

        if mention_num:
            data = mention_handler.get_mention_data(mention_num)
            if not data:
                await update.message.reply_text("\u274c Mention not found or already handled.")
                return
            # Start ack confirmation session
            memory.start_session("ack_confirmation", {
                "mention_num": mention_num,
                "reply_text": data["reply_text"],
                "channel_id": data["channel_id"],
                "thread_ts": data["thread_ts"],
                "username": data["username"],
                "step": "awaiting_ack_confirmation"
            })
            await update.message.reply_text(
                f"\U0001f4dd Here's what I'll send to {data['username']}:\n\n"
                f"\"{data['reply_text']}\"\n\n"
                f"Reply *yes* to send, or tell me what to change.",
                parse_mode="Markdown"
            )
            return

    # Handle mention ignore
    if text.lower().startswith("ignore "):
        mention_num = text[7:].strip()
        mention_handler.ignore(mention_num)
        await update.message.reply_text("\U0001f44d Ignored.")
        return

    # Add to conversation history
    memory.add_message("user", text)

    # Show typing indicator
    await update.message.chat.send_action("typing")

    # Direct time detection for scheduling steps — bypasses brain entirely
    current_step = memory.get_session_data("step")
    if current_step in ["awaiting_slack_time", "awaiting_email_time"]:
        time_str = extract_time_from_message(text)
        if time_str:
            if current_step == "awaiting_slack_time":
                decision = {
                    "intent": "slack_time",
                    "jarvis_response": "",
                    "action": "send_slack_scheduled",
                    "action_data": {"time_str": time_str}
                }
            else:
                decision = {
                    "intent": "email_time",
                    "jarvis_response": "",
                    "action": "email_time",
                    "action_data": {"time_str": time_str}
                }
            await executor.execute(decision, update)
            return

    # Brain decides what to do
    decision = await brain.think(text)

    # Executor carries it out
    await executor.execute(decision, update)

    # Add Jarvis response to history
    if decision.get("jarvis_response"):
        memory.add_message("assistant", decision["jarvis_response"])

async def poll_slack(app):
    """Background task — polls Slack for mentions every 60 seconds."""
    mention_handler.set_bot(app.bot)
    while True:
        try:
            mentions = await slack_monitor.get_mentions()
            for m in mentions:
                await mention_handler.notify(m)
        except Exception as e:
            print(f"Slack poll error: {e}")
        await asyncio.sleep(60)


async def post_init(app):
    asyncio.create_task(poll_slack(app))


def main():
    config.validate()
    start_health_server()
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Jarvis is online.")
    app.run_polling()

if __name__ == "__main__":
    main()
