# agent_scheduler.py
"""
AgentScheduler: Task scheduling for the dashboard (Email, Cronjob, AgentEvent)
- Email: Schedule sending an email at a specific time
- Cronjob: Run any function periodically
- AgentEvent: Agent checks a semantic condition (e.g. in emails/documents) and triggers an action
"""
import asyncio
from typing import Callable, Any, Dict, Optional, List
import datetime
import json
import os
import re
import asyncpg # Assuming asyncpg is used for database connection
import aiohttp
import logging # Added for explicit logging
import base64 # For dummy PDF
from gmail_utils.gmail_fetch import get_email,parse_mcp_email_list # Import Gmail utils for email fetching and OAuth
from document_utils.document_utils import process_document_step # Import document processing step function
from gmail_utils.gmail_auth import fetch_access_token_for_user
from agent.summary_agent import get_summary_and_type_from_llm
from agent.email_checker import check_new_emails
from gmail_utils.gmail_mcp_tools_wrapper import list_emails


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # <--- explizit setzen!

class AgentScheduler:
    def __init__(self):
        # Store tasks in a dictionary mapping task ID (from DB) to asyncio.Task
        self.tasks: Dict[str, asyncio.Task] = {}

    def schedule_email(self, task_id: str, send_func: Callable, to: str, subject: str, body: str, when: datetime.datetime):
        """Schedule an email to be sent at a specific time."""
        # Associate the asyncio task with the DB task_id
        self.tasks[task_id] = asyncio.create_task(self._run_at(send_func, to, subject, body, when))
        logger.info(f"Scheduled email task {task_id}.")

    def schedule_cron(self, task_id: str, func: Callable, interval_seconds: int, *args, **kwargs):
        """Schedule a periodic task (classic cronjob)."""
        # Associate the asyncio task with the DB task_id
        self.tasks[task_id] = asyncio.create_task(self._run_cron(func, interval_seconds, *args, **kwargs))
        logger.info(f"Scheduled cron task {task_id} to run every {interval_seconds} seconds.")

    def schedule_agent_event(self, task_id: str, agent_func: Callable, condition: str, interval_seconds: int, action: Callable, *args, **kwargs):
        """Schedule an AgentEvent: Agent periodically checks a semantic condition and triggers an action if true."""
        # Associate the asyncio task with the DB task_id
        self.tasks[task_id] = asyncio.create_task(self._run_agent_event(agent_func, condition, interval_seconds, action, *args, **kwargs))
        logger.info(f"Scheduled agent event task {task_id}.")

    def cancel_task(self, task_id: str):
        """Cancel a specific scheduled task by its ID."""
        task = self.tasks.pop(task_id, None)
        if task:
            task.cancel()
            logger.info(f"Cancelled task {task_id}.")
            return True
        logger.warning(f"Attempted to cancel non-existent task {task_id}.")
        return False

    def cancel_all(self):
        """Cancel all scheduled tasks."""
        for task_id, task in list(self.tasks.items()): # Iterate over a copy
            task.cancel()
            logger.info(f"Cancelled task {task_id} during shutdown.")
        self.tasks.clear()

    def start(self, db_pool=None, interval_seconds=86400):
        """Startet den globalen Cronjob erneut (z.B. nach Stop)."""
        # Verhindere mehrfaches Starten
        if 'global_email_cron' in self.tasks and not self.tasks['global_email_cron'].done():
            logger.info("Globaler Cronjob läuft bereits.")
            return
        from backend_main import check_new_emails  # Import hier, um Zirkularität zu vermeiden
        self.schedule_cron('global_email_cron', check_new_emails, interval_seconds, db_pool)
        logger.info(f"Globaler Cronjob wurde gestartet (alle {interval_seconds} Sekunden).")

    def is_running(self):
        """Gibt True zurück, wenn der globale Cronjob läuft."""
        task = self.tasks.get('global_email_cron')
        return task is not None and not task.done()

    async def _run_cron(self, func, interval_seconds, *args, **kwargs):
        while True:
            try:
                await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"[Scheduler] Error in cron job: {e}")
            await asyncio.sleep(interval_seconds)

# Example agent_func: checks a semantic condition (e.g. in emails)
async def example_agent_func(condition: str) -> bool:
    # Here you could call an LLM or tool
    # Dummy: Condition is true if "trigger" is in the string
    return "trigger" in condition

# Example action: send email
async def example_send_email(to, subject, body):
    print(f"Send email to {to}: {subject}\n{body}")

# Example usage (can be used in backend):
# scheduler = AgentScheduler()
# scheduler.schedule_email(example_send_email, "test@example.com", "Test", "Hello!", datetime.datetime.now() + datetime.timedelta(seconds=60))
# scheduler.schedule_cron(example_send_email, 3600, "cron@example.com", "Cron", "Every hour!")
# scheduler.schedule_agent_event(example_agent_func, "trigger", 300, example_send_email, "agent@example.com", "Agent Event", "Condition met!")


