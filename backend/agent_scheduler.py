# agent_scheduler.py
"""
AgentScheduler: Task scheduling for the dashboard (Email, Cronjob, AgentEvent)
- Email: Schedule sending an email at a specific time
- Cronjob: Run any function periodically
- AgentEvent: Agent checks a semantic condition (e.g. in emails/documents) and triggers an action
"""
import asyncio
from typing import Callable, Any, Dict, Optional
import datetime
import json

class AgentScheduler:
    def __init__(self):
        self.tasks = []  # List of all scheduled tasks

    def schedule_email(self, send_func: Callable, to: str, subject: str, body: str, when: datetime.datetime):
        """Schedule an email to be sent at a specific time."""
        self.tasks.append(asyncio.create_task(self._run_at(send_func, to, subject, body, when)))

    def schedule_cron(self, func: Callable, interval_seconds: int, *args, **kwargs):
        """Schedule a periodic task (classic cronjob)."""
        self.tasks.append(asyncio.create_task(self._run_cron(func, interval_seconds, *args, **kwargs)))

    def schedule_agent_event(self, agent_func: Callable, condition: str, interval_seconds: int, action: Callable, *args, **kwargs):
        """Schedule an AgentEvent: Agent periodically checks a semantic condition and triggers an action if true."""
        self.tasks.append(asyncio.create_task(self._run_agent_event(agent_func, condition, interval_seconds, action, *args, **kwargs)))

    async def _run_at(self, send_func, to, subject, body, when):
        now = datetime.datetime.now()
        delay = (when - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await send_func(to, subject, body)

    async def _run_cron(self, func, interval_seconds, *args, **kwargs):
        while True:
            await func(*args, **kwargs)
            await asyncio.sleep(interval_seconds)

    async def _run_agent_event(self, agent_func, condition, interval_seconds, action, *args, **kwargs):
        while True:
            result = await agent_func(condition)
            if result:
                await action(*args, **kwargs)
            await asyncio.sleep(interval_seconds)

    def cancel_all(self):
        for t in self.tasks:
            t.cancel()
        self.tasks.clear()

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
