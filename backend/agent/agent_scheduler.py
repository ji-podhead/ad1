"""Module for AgentScheduler, handling task scheduling.

AgentScheduler provides functionalities for scheduling various types of tasks:
- Email: Schedule sending an email at a specific time.
- Cronjob: Run any function periodically at specified intervals.
- AgentEvent: (Conceptual) An agent checks a semantic condition (e.g., in emails or documents)
  and triggers an action if the condition is met. This is not fully implemented
  in the current version of `_run_agent_event`.

The scheduler uses asyncio for managing asynchronous tasks.
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
logger.setLevel(logging.INFO)

class AgentScheduler:
    """Manages and schedules various types of background tasks.

    Attributes:
        tasks (Dict[str, asyncio.Task]): A dictionary mapping task IDs (typically from
            the database) to their corresponding asyncio.Task objects. This allows
            for tracking and cancellation of scheduled tasks.
    """
    def __init__(self):
        """Initializes the AgentScheduler with an empty task dictionary."""
        self.tasks: Dict[str, asyncio.Task] = {}

    def schedule_email(self, task_id: str, send_func: Callable, to: str, subject: str, body: str, when: datetime.datetime):
        """Schedules an email to be sent at a specific future time.

        Note: The actual sending mechanism `_run_at` is not implemented in this version.

        Args:
            task_id (str): The unique ID for this scheduled task.
            send_func (Callable): The function to call to send the email.
            to (str): The recipient's email address.
            subject (str): The subject of the email.
            body (str): The body content of the email.
            when (datetime.datetime): The specific date and time to send the email.
        """
        # self.tasks[task_id] = asyncio.create_task(self._run_at(send_func, to, subject, body, when))
        logger.info(f"Email task {task_id} would be scheduled if _run_at was implemented.")
        # Placeholder as _run_at is not defined. In a real scenario, it would run send_func at 'when'.

    def schedule_cron(self, task_id: str, func: Callable, interval_seconds: int, *args, **kwargs):
        """Schedules a function to run periodically.

        Args:
            task_id (str): The unique ID for this cron job.
            func (Callable): The asynchronous function to execute periodically.
            interval_seconds (int): The interval in seconds between executions.
            *args: Positional arguments to pass to the function `func`.
            **kwargs: Keyword arguments to pass to the function `func`.
        """
        self.tasks[task_id] = asyncio.create_task(self._run_cron(func, interval_seconds, *args, **kwargs))
        logger.info(f"Scheduled cron task '{task_id}' to run every {interval_seconds} seconds.")

    def schedule_agent_event(self, task_id: str, agent_func: Callable, condition: str, interval_seconds: int, action: Callable, *args, **kwargs):
        """Schedules an agent event to check a condition and trigger an action.

        Note: The actual condition checking and action triggering mechanism
              `_run_agent_event` is not fully implemented in this version.

        Args:
            task_id (str): The unique ID for this agent event.
            agent_func (Callable): The function that checks the semantic condition.
            condition (str): The condition to check.
            interval_seconds (int): The interval in seconds between condition checks.
            action (Callable): The function to call if the condition is met.
            *args: Positional arguments for the action function.
            **kwargs: Keyword arguments for the action function.
        """
        # self.tasks[task_id] = asyncio.create_task(self._run_agent_event(agent_func, condition, interval_seconds, action, *args, **kwargs))
        logger.info(f"Agent event task {task_id} would be scheduled if _run_agent_event was implemented.")
        # Placeholder as _run_agent_event is not defined.

    def cancel_task(self, task_id: str) -> bool:
        """Cancels a specific scheduled task by its ID.

        Args:
            task_id (str): The ID of the task to cancel.

        Returns:
            bool: True if the task was found and cancelled, False otherwise.
        """
        task = self.tasks.pop(task_id, None)
        if task:
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled task {task_id}.")
            else:
                logger.info(f"Task {task_id} was already done.")
            return True
        logger.warning(f"Attempted to cancel non-existent or already removed task {task_id}.")
        return False

    def cancel_all(self):
        """Cancels all currently scheduled tasks.

        This is typically used during application shutdown.
        """
        logger.info("Cancelling all scheduled tasks...")
        for task_id, task in list(self.tasks.items()): # Iterate over a copy for safe removal
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled task {task_id} during cancel_all.")
            else:
                logger.info(f"Task {task_id} was already done during cancel_all.")
        self.tasks.clear()
        logger.info("All tasks dictionary cleared.")

    def start(self, db_pool=None, interval_seconds=86400):
        """Starts or restarts the global email checking cron job.

        This method is intended to ensure the main email checking routine is scheduled.
        It avoids scheduling duplicate global cron jobs if one is already active.

        Args:
            db_pool (Optional[asyncpg.pool.Pool], optional): The database pool
                to be passed to the `check_new_emails` function. Defaults to None.
            interval_seconds (int, optional): The interval for the cron job in seconds.
                Defaults to 86400 (24 hours).
        """
        global_cron_id = 'global_email_cron'
        if global_cron_id in self.tasks and not self.tasks[global_cron_id].done():
            logger.info(f"Global email cron job ('{global_cron_id}') is already running.")
            return

        # Import is here to avoid circular dependency issues at module load time.
        from backend_main import check_new_emails

        self.schedule_cron(global_cron_id, check_new_emails, interval_seconds, db_pool)
        logger.info(f"Global email cron job ('{global_cron_id}') has been started/restarted to run every {interval_seconds} seconds.")

    def is_running(self) -> bool:
        """Checks if the global email checking cron job is currently scheduled and not done.

        Returns:
            bool: True if the global email cron job is active, False otherwise.
        """
        task = self.tasks.get('global_email_cron')
        return task is not None and not task.done()

    async def _run_cron(self, func: Callable, interval_seconds: int, *args, **kwargs):
        """Internal method to run a function periodically.

        This coroutine loops indefinitely, calling the provided function
        and then sleeping for the specified interval.

        Args:
            func (Callable): The asynchronous function to execute.
            interval_seconds (int): The sleep interval in seconds.
            *args: Positional arguments for `func`.
            **kwargs: Keyword arguments for `func`.
        """
        while True:
            try:
                logger.debug(f"Executing cron function: {func.__name__}")
                await func(*args, **kwargs)
                logger.debug(f"Cron function {func.__name__} completed.")
            except asyncio.CancelledError:
                logger.info(f"Cron job {func.__name__} was cancelled.")
                break # Exit loop if task is cancelled
            except Exception as e:
                logger.error(f"[Scheduler] Error in cron job '{func.__name__}': {e}", exc_info=True)

            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                logger.info(f"Sleep interrupted for cron job {func.__name__}; task cancelled.")
                break # Exit loop if task is cancelled during sleep

# Example functions (not part of AgentScheduler class)
async def example_agent_func(condition: str) -> bool:
    """Example agent function that checks a semantic condition.

    This is a dummy implementation. A real agent function might call an LLM or other tools.

    Args:
        condition (str): The condition string to check.

    Returns:
        bool: True if the condition is met (e.g., "trigger" is in the string), False otherwise.
    """
    logger.info(f"Example agent checking condition: {condition}")
    # Dummy: Condition is true if "trigger" is in the string
    return "trigger" in condition

async def example_send_email(to: str, subject: str, body: str):
    """Example action function to simulate sending an email.

    Args:
        to (str): The recipient's email address.
        subject (str): The email subject.
        body (str): The email body.
    """
    logger.info(f"Simulating sending email to {to}: Subject='{subject}', Body='{body}'")
    # In a real scenario, this would use an email sending library or API.

# Example usage (can be used in backend):
# scheduler = AgentScheduler()
# scheduler.schedule_email(example_send_email, "test@example.com", "Test", "Hello!", datetime.datetime.now() + datetime.timedelta(seconds=60))
# scheduler.schedule_cron(example_send_email, 3600, "cron@example.com", "Cron", "Every hour!")
# scheduler.schedule_agent_event(example_agent_func, "trigger", 300, example_send_email, "agent@example.com", "Agent Event", "Condition met!")


