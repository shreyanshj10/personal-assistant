import logging
import asyncio
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, CommandHandler, filters, ContextTypes
from config import config
from memory import memory
from utils.scheduler_store import scheduler_store
import brain
import executor
import pytz
from services.slack_monitor import slack_monitor
from services.mention_handler import mention_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
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
                await update.message.reply_text("❌ Mention not found or already handled.")
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
                f"📝 Here's what I'll send to {data['username']}:\n\n"
                f"\"{data['reply_text']}\"\n\n"
                f"Tap *Send* or tell me what to change.",
                parse_mode="Markdown",
                reply_markup=executor.ack_keyboard()
            )
            return

    # Handle mention ignore
    if text.lower().startswith("ignore "):
        mention_num = text[7:].strip()
        mention_handler.ignore(mention_num)
        await update.message.reply_text("👍 Ignored.")
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


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    if user_id != str(config.ALLOWED_USER_ID):
        return

    data = query.data

    # Remove keyboard from the pressed message
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass  # Message might be too old to edit

    # Handle mention ack/ignore buttons
    if data.startswith("mention_ack_"):
        mention_num = data.replace("mention_ack_", "")
        mention_data = mention_handler.get_mention_data(mention_num)
        if not mention_data:
            await query.message.reply_text("❌ Mention not found or already handled.")
            return
        memory.start_session("ack_confirmation", {
            "mention_num": mention_num,
            "reply_text": mention_data["reply_text"],
            "channel_id": mention_data["channel_id"],
            "thread_ts": mention_data["thread_ts"],
            "username": mention_data["username"],
            "step": "awaiting_ack_confirmation"
        })
        await query.message.reply_text(
            f"📝 Here's what I'll send to {mention_data['username']}:\n\n"
            f"\"{mention_data['reply_text']}\"\n\n"
            f"Tap *Send* or tell me what to change.",
            parse_mode="Markdown",
            reply_markup=executor.ack_keyboard()
        )
        return

    if data.startswith("mention_ignore_"):
        mention_num = data.replace("mention_ignore_", "")
        mention_handler.ignore(mention_num)
        await query.message.reply_text("👍 Ignored.")
        return

    # Map button presses to executor decisions
    BUTTON_MAP = {
        "eod_yes": {"intent": "confirm_yes", "jarvis_response": "", "action": "confirm_yes", "action_data": {}},
        "eod_cancel": {"intent": "cancel", "jarvis_response": "", "action": "cancel_session", "action_data": {}},
        "slack_now": {"intent": "slack_now", "jarvis_response": "", "action": "send_slack_now", "action_data": {}},
        "slack_schedule": {"intent": "slack_schedule", "jarvis_response": "", "action": "schedule_slack", "action_data": {}},
        "email_now": {"intent": "email_now", "jarvis_response": "", "action": "send_email_now", "action_data": {}},
        "email_schedule": {"intent": "email_schedule", "jarvis_response": "", "action": "email_schedule", "action_data": {}},
        "email_skip": {"intent": "email_skip", "jarvis_response": "", "action": "skip_email", "action_data": {}},
        "ack_send": {"intent": "confirm_yes", "jarvis_response": "", "action": "send_ack", "action_data": {}},
        "ack_cancel": {"intent": "cancel", "jarvis_response": "", "action": "cancel_session", "action_data": {}},
    }

    if data in BUTTON_MAP:
        decision = BUTTON_MAP[data]
        # Add to conversation history for context
        label = data.replace("_", " ").title()
        memory.add_message("user", label)
        await executor.execute(decision, update)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Jarvis status: active session, pending mentions, scheduled emails."""
    user_id = str(update.message.from_user.id)
    if user_id != str(config.ALLOWED_USER_ID):
        return

    ist = pytz.timezone("Asia/Kolkata")
    lines = ["*Jarvis Status*\n"]

    # Active session
    if memory.has_session():
        session = memory.get_session()
        step = memory.get_session_data("step") or "unknown"
        lines.append(f"*Active session:* {session.get('type')} ({step})")
        actions = memory.get_actions()
        if actions:
            lines.append("*Actions done:*")
            for a in actions:
                lines.append(f"  {a}")
    else:
        lines.append("No active session")

    lines.append("")

    # Pending mentions
    pending = mention_handler.pending_mentions
    if pending:
        lines.append(f"*Pending mentions:* {len(pending)}")
        for num, data in pending.items():
            m = data["mention"]
            lines.append(f"  {num}. From {m['username']} in #{m['channel_name']}")
    else:
        lines.append("No pending mentions")

    lines.append("")

    # Scheduled emails
    tasks = scheduler_store.get_all()
    if tasks:
        lines.append(f"*Scheduled emails:* {len(tasks)}")
        for task in tasks:
            dt = datetime.fromtimestamp(task["unix_timestamp"], tz=ist)
            time_str = dt.strftime("%I:%M %p, %d %b")
            subj = task["subject"][:40]
            lines.append(f"  - {subj}... at {time_str}")
            lines.append(f"    Cancel: `/cancel {task['id']}`")
    else:
        lines.append("No scheduled emails")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel active session or a scheduled email by ID."""
    user_id = str(update.message.from_user.id)
    if user_id != str(config.ALLOWED_USER_ID):
        return

    args = context.args

    # Cancel active session
    if not args or args[0] == "session":
        if memory.has_session():
            memory.end_session()
            await update.message.reply_text("Active session cancelled.")
        else:
            await update.message.reply_text("No active session to cancel.")
        return

    # Cancel scheduled email by ID
    task_id = args[0]
    tasks = scheduler_store.get_all()
    task = next((t for t in tasks if t["id"] == task_id), None)

    if task:
        scheduler_store.remove_task(task_id)
        await update.message.reply_text(f"Scheduled email cancelled: {task['subject'][:50]}")
    else:
        await update.message.reply_text(f"No scheduled task found with ID: {task_id}")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset conversation memory and active session."""
    user_id = str(update.message.from_user.id)
    if user_id != str(config.ALLOWED_USER_ID):
        return
    memory.end_session()
    memory.conversation.clear()
    await update.message.reply_text("Memory and session cleared.")


async def poll_slack(app):
    """Background task — polls Slack for mentions every 60 seconds."""
    mention_handler.set_bot(app.bot)
    while True:
        try:
            mentions = await slack_monitor.get_mentions()
            for m in mentions:
                await mention_handler.notify(m)
        except Exception as e:
            logger.error(f"Slack poll error: {e}")
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
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    logger.info("Jarvis is online.")
    app.run_polling()

if __name__ == "__main__":
    main()
