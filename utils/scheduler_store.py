import json
import os
import threading
import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)
STORE_FILE = "scheduled_tasks.json"

class SchedulerStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._timers = {}
        self._load_and_reschedule()

    def _load(self) -> list:
        if not os.path.exists(STORE_FILE):
            return []
        try:
            with open(STORE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, tasks: list):
        with open(STORE_FILE, "w") as f:
            json.dump(tasks, f, indent=2)

    def add_task(self, task_id: str, body: str, subject: str, unix_timestamp: int, extra_recipients: list = []):
        with self._lock:
            tasks = self._load()
            tasks.append({
                "id": task_id,
                "body": body,
                "subject": subject,
                "unix_timestamp": unix_timestamp,
                "extra_recipients": extra_recipients
            })
            self._save(tasks)
        self._schedule_timer(task_id, body, subject, unix_timestamp, extra_recipients)

    def remove_task(self, task_id: str):
        with self._lock:
            tasks = self._load()
            tasks = [t for t in tasks if t["id"] != task_id]
            self._save(tasks)
        # Cancel timer if exists
        if task_id in self._timers:
            self._timers[task_id].cancel()
            del self._timers[task_id]

    def get_all(self) -> list:
        return self._load()

    def _schedule_timer(self, task_id: str, body: str, subject: str, unix_timestamp: int, extra_recipients: list):
        import asyncio

        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist).timestamp()
        delay = unix_timestamp - now

        if delay <= 0:
            logger.warning(f"Task {task_id} is in the past, skipping")
            self.remove_task(task_id)
            return

        def send_and_remove():
            from services.email_service import email_service
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(email_service.send_email(body, subject, extra_recipients))
                logger.info(f"Scheduled email {task_id} sent successfully")
            except Exception as e:
                logger.error(f"Scheduled email {task_id} failed: {e}")
            finally:
                self.remove_task(task_id)
                loop.close()

        timer = threading.Timer(delay, send_and_remove)
        timer.daemon = True
        timer.start()
        self._timers[task_id] = timer

    def _load_and_reschedule(self):
        """On startup, reschedule any tasks that survived a restart."""
        tasks = self._load()
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist).timestamp()

        valid_tasks = []
        for task in tasks:
            if task["unix_timestamp"] > now:
                valid_tasks.append(task)
                self._schedule_timer(
                    task["id"], task["body"], task["subject"],
                    task["unix_timestamp"], task.get("extra_recipients", [])
                )
                logger.info(f"Rescheduled task {task['id']}")
            else:
                logger.warning(f"Dropping expired task {task['id']}")

        # Save only valid tasks
        self._save(valid_tasks)

scheduler_store = SchedulerStore()
