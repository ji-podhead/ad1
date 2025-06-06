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
    Checks for new emails, determines their type based on 'email_receive' scheduler tasks,
    inserts them into the database with the determined type, and creates corresponding tasks
    in the 'tasks' table with an appropriate workflow_type.
    """
    print("Checking for new emails...")
    try:
        emails_from_tool: List[Dict[str, Any]] = await list_emails()
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return

    async with db_pool.acquire() as connection:
        # Fetch active 'email_receive' scheduler tasks
        email_receive_workflows = await connection.fetch(
            "SELECT workflow_config, workflow_name FROM scheduler_tasks WHERE status = 'active' AND trigger_type = 'email_receive'"
        )

        applied_workflow_config = None
        applied_workflow_name = None
        email_workflow_type = "default_email_model" # Default if no matching workflow or config
        task_initial_status = "pending" # Default task status

        if email_receive_workflows:
            # Assume the first active 'email_receive' workflow applies for now
            # More sophisticated matching logic can be added later (e.g., based on sender, subject patterns)
            first_workflow = email_receive_workflows[0]
            applied_workflow_config = first_workflow['workflow_config']
            applied_workflow_name = first_workflow['workflow_name']
            print(f"Applying email_receive workflow: {applied_workflow_name}")

            if applied_workflow_config:
                if isinstance(applied_workflow_config, str): # Handle if JSON string is returned
                    try:
                        applied_workflow_config = json.loads(applied_workflow_config)
                    except json.JSONDecodeError:
                        print(f"Warning: Could not parse workflow_config JSON for {applied_workflow_name}: {applied_workflow_config}")
                        applied_workflow_config = {} # Use empty dict to avoid errors

                email_workflow_type = applied_workflow_config.get("model", email_workflow_type)
                task_initial_status = applied_workflow_config.get("initial_status", task_initial_status)
                print(f"Determined email_workflow_type: {email_workflow_type}, task_initial_status: {task_initial_status} from {applied_workflow_name}")
            else:
                print(f"No workflow_config found for {applied_workflow_name}, using defaults.")
        else:
            print("No active 'email_receive' workflows found. Using default types and statuses.")


        for email_data in emails_from_tool:
            message_id = email_data.get('id') # This is the external message ID from the email provider
            subject = email_data.get('subject', 'No Subject')
            sender = email_data.get('sender', 'Unknown Sender') # Potentially a dict {'email': 'address'}
            body = email_data.get('body', '')
            received_at = datetime.datetime.now(datetime.timezone.utc)

            # Extract simple sender email if it's a dict, otherwise use as is
            if isinstance(sender, dict) and 'email' in sender:
                sender_email = sender['email']
            elif isinstance(sender, str):
                sender_email = sender
            else:
                sender_email = 'Unknown Sender'


            if not message_id: # Should ideally be the unique ID from the email service
                print(f"Skipping email due to missing message ID: {email_data}")
                continue

            try:
                # Check if email already exists based on a combination of fields.
                # Ideally, we'd store and check against the external message_id if the 'emails' table had a column for it.
                # The current check (subject, sender, body) is weak and prone to false negatives/positives.
                existing_email = await connection.fetchrow(
                    "SELECT id FROM emails WHERE subject = $1 AND sender = $2 AND body = $3", # Using combination
                    subject, sender_email, body
                )

                if not existing_email:
                    inserted_email_id = await connection.fetchval(
                        """
                        INSERT INTO emails (subject, sender, body, received_at, label, type)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        RETURNING id
                        """,
                        subject,
                        sender_email,
                        body,
                        received_at,
                        None,  # Default label or None
                        email_workflow_type # Set the email type
                    )
                    print(f"Inserted new email with ID: {inserted_email_id}, Type: {email_workflow_type}")

                    # Insert corresponding task with workflow_type
                    await connection.execute(
                        """
                        INSERT INTO tasks (email_id, status, created_at, updated_at, workflow_type)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        inserted_email_id,
                        task_initial_status, # Use status from workflow config or default
                        received_at,
                        received_at,
                        email_workflow_type # Set the task's workflow_type
                    )
                    print(f"Created task for email ID: {inserted_email_id}, Workflow Type: {email_workflow_type}, Status: {task_initial_status}")
                else:
                    print(f"Email already exists, skipping: Subject='{subject}', Sender='{sender_email}'")

            except Exception as e:
                print(f"Error processing email (Subject: '{subject}', Sender: '{sender_email}'): {e}")
