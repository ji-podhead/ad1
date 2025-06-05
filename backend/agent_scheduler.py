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
import asyncpg # Assuming asyncpg is used for database connection
from backend.tools_wrapper import list_emails # Import list_emails

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


async def check_new_emails(db_pool: asyncpg.pool.Pool):
    """
    Checks for new emails, inserts them into the database, and creates corresponding tasks.
    """
    print("Checking for new emails...")
    try:
        emails_from_tool: List[Dict[str, Any]] = await list_emails()
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return

    async with db_pool.acquire() as connection:
        for email_data in emails_from_tool:
            # Assume email_data contains 'id' (as messageId), 'subject', 'sender', 'body'
            # 'sender' might be a dict like {'email': 'address'}, adapt as necessary
            # For now, assume 'sender' is a simple string.
            # Also, 'list_emails' doesn't provide a received_date, so we'll use now().
            message_id = email_data.get('id')
            subject = email_data.get('subject', 'No Subject')
            sender = email_data.get('sender', 'Unknown Sender')
            body = email_data.get('body', '')
            received_at = datetime.datetime.now(datetime.timezone.utc)

            if not message_id:
                print(f"Skipping email due to missing message ID: {email_data}")
                continue

            try:
                # Check if email already exists
                existing_email = await connection.fetchrow(
                    "SELECT id FROM emails WHERE subject = $1 AND sender = $2 AND body = $3", # Using combination as message_id might not be in DB
                    subject, sender, body # A more robust check would be against a unique message_id if available and stored
                ) # Fallback if message_id from tool is not what we expect to store or not available for query directly

                if not existing_email:
                    # Insert new email
                    # The subtask implies that the `emails.id` is a SERIAL.
                    # We also need to consider if the `message_id` from the tool should be stored.
                    # Let's assume for now that the `emails` table should have a `message_id` column for the external ID.
                    # If not, the current check for duplicates is (subject, sender, body), which is not ideal.
                    # For now, I'll proceed without storing message_id from the tool directly,
                    # and rely on the combination check, acknowledging its weakness.
                    # The previous subtask did not add a message_id column to the emails table.

                    inserted_email_id = await connection.fetchval(
                        """
                        INSERT INTO emails (subject, sender, body, received_at, label)
                        VALUES ($1, $2, $3, $4, $5)
                        RETURNING id
                        """,
                        subject,
                        sender,
                        body,
                        received_at,
                        None  # Default label or None
                    )
                    print(f"Inserted new email with ID: {inserted_email_id}")

                    # Insert corresponding task
                    await connection.execute(
                        """
                        INSERT INTO tasks (email_id, status, created_at, updated_at)
                        VALUES ($1, 'pending', $2, $3)
                        """,
                        inserted_email_id,
                        received_at,  # Using received_at for created_at for the task
                        received_at   # Using received_at for updated_at for the task
                    )
                    print(f"Created task for email ID: {inserted_email_id}")
                else:
                    print(f"Email already exists, skipping: Subject='{subject}', Sender='{sender}'")

            except Exception as e:
                print(f"Error processing email (Subject: '{subject}', Sender: '{sender}'): {e}")
