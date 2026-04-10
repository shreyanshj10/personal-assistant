import logging
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import os
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from config import config
from memory import memory
import brain
import executor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    # Add to conversation history
    memory.add_message("user", text)

    # Show typing indicator
    await update.message.chat.send_action("typing")

    # Brain decides what to do
    decision = await brain.think(text)

    # Executor carries it out
    await executor.execute(decision, update)

    # Add Jarvis response to history
    if decision.get("jarvis_response"):
        memory.add_message("assistant", decision["jarvis_response"])

def main():
    config.validate()
    start_health_server()
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Jarvis is online.")
    app.run_polling()

if __name__ == "__main__":
    main()
