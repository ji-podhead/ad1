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
import asyncpg # Assuming asyncpg is used for database connection
# Remove direct google.genai import if pydantic_ai handles it internally, or keep if needed for types
# from google import genai
# from google.genai.types import GenerateContentConfig, HttpOptions
from google.adk.agents import Agent as AdkAgent # Alias to avoid name conflict
from google.adk.models.lite_llm import LiteLlm
from litellm import experimental_mcp_client
from tools_wrapper import list_emails # Import list_emails
import aiohttp
import logging # Added for explicit logging
import base64 # For dummy PDF
from mcp.client.sse import sse_client
from mcp import ClientSession
from pydantic import BaseModel # Import BaseModel from pydantic
from pydantic_ai import Agent # Import Agent from pydantic_ai
from pydantic_ai.models.gemini import GeminiModel, GeminiModelSettings # Import GeminiModel and Settings

from backend.gmail_utils import get_email # Import Gmail utils for email fetching and OAuth
from  backend.document_utils import process_document_step # Import document processing step function
from backend.gmail_auth import fetch_access_token_for_user
# Define Pydantic models for LLM response
class ClassificationResult(BaseModel):
    type: str
    score: float

class EmailClassificationResponse(BaseModel):
    classifications: List[ClassificationResult]
    short_description: str

# Setup basic logging if not already configured elsewhere globally
# logging.basicConfig(level=logging.INFO) # Already configured in backend_main.py, avoid reconfiguring.
# Instead, get a logger instance if needed for this specific module:
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # <--- explizit setzen!
# logging.getLogger("aiohttp").setLevel(logging.WARNING) # Optional: Quieten aiohttp's own logs

# Configure Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# The pydantic_ai GeminiModel should pick up the API key from the environment variable
# if GEMINI_API_KEY:
#     client = genai.Client(api_key=GEMINI_API_KEY)

# else:
#     print("Warning: GEMINI_API_KEY not found in environment. LLM features will not work.")


# Helper function to get summary and type from LLM
async def get_summary_and_type_from_llm(
    email_subject: str,
    email_body: str,
    llm_model_name: str,
    possible_types: List[str], # Add possible types parameter
    system_instruction: Optional[str] = None, # Add configurable system instruction
    max_tokens: Optional[int] = None, # Add configurable max tokens
    attachments_info: Optional[List[Dict[str, Any]]] = None # Add attachments info parameter
) -> Dict[str, Any]: # Return type can be more specific, but Dict[str, Any] is flexible
    """
    Analyzes email content using an LLM to determine document type, a short description,
    and provides scores for a list of possible types using pydantic_ai.
    Includes attachment information in the prompt if available.
    Returns a dictionary with "document_type", "short_description", and "classifications".
    """
    logger.info(f"get_summary_and_type_from_llm called with model: {llm_model_name}")
    if not GEMINI_API_KEY:
        logger.error("Error: GEMINI_API_KEY not configured. Cannot get summary from LLM.")
        return {
            "document_type": "Default/Unknown (LLM Error)",
            "short_description": "Gemini not available (LLM Error).",
            "classifications": []
        }

    # Update prompt to include possible types and ask for scores
    prompt = f"""Analyze the following email content and provide a short description and a classification score for each of the following document types: {', '.join(possible_types)}.
    Return your response *only* as a valid JSON object matching the following structure:
    {{
    "classifications": [
        {{"type": "Type1", "score": 0.9}},
        {{"type": "Type2", "score": 0.1}}
    ],
    "short_description": "A short summary of the email."
    }}
    Ensure scores are between 0.0 and 1.0.

    Subject: {email_subject}

    Body:
    {email_body[:4000]}
    """ # Limiting body length to manage token usage, adjust as needed

    # Add attachment information to the prompt if available
    if attachments_info:
        attachment_list_str = ", ".join([f"{att.get('filename', 'unnamed')} ({att.get('mimeType', 'unknown type')})" for att in attachments_info])
        prompt += f"\n\nThis email has the following attachments: {attachment_list_str}. Please include information about the attachments in the short description if relevant."


    logger.info(f"Sending prompt to LLM ({llm_model_name}) for subject: {email_subject}")

    response = None # Initialize response to None

    try:
        # Configure model settings using GeminiModelSettings
        model_settings = GeminiModelSettings(
            system_instruction=[system_instruction] if system_instruction else None, # Pass system instruction as a list
            max_output_tokens=max_tokens,
            # Add other settings like safety_settings if needed from workflow config
            # gemini_safety_settings=[...]
        )

        # Create GeminiModel and Agent instances
        model = GeminiModel(llm_model_name)
        agent = Agent(model, model_settings=model_settings)

        # Use the async run method from the pydantic_ai Agent
        response = await agent.run(prompt)
        logger.info(f"LLM call completed, response received.")
        logger.info(f"LLM response: {response}")  # Log full response for debugging
    except Exception as e:
        logger.error(f"Error during LLM call using pydantic_ai: {e}")
        return {
            "document_type": "Default/Unknown (API Error)",
            "short_description": "Summary not available (API Error).",
            "classifications": []
        }

    # Check if response is None or missing the 'output' attribute
    if response is None or not hasattr(response, 'output') or response.output is None:
         logger.error("LLM response is None or missing output attribute.")

         return {
            "document_type": "Default/Unknown (API Error)",
            "short_description": "Summary not available (API Error).",
            "classifications": []
        }

    logger.info(f"LLM response text: {response.output}") # Log raw response text (using .output)

    # Attempt to clean and parse the JSON response using Pydantic
    cleaned_response_text = response.output.strip() # Use .output here
    if cleaned_response_text.startswith("```json"):
        cleaned_response_text = cleaned_response_text[7:]
    elif cleaned_response_text.startswith("```"):
         cleaned_response_text = cleaned_response_text[3:]
    if cleaned_response_text.endswith("```"):
        cleaned_response_text = cleaned_response_text[:-3]

    cleaned_response_text = cleaned_response_text.strip()

    try:
        # Parse with Pydantic model
        classification_response = EmailClassificationResponse.model_validate_json(cleaned_response_text)

        # Determine the document_type based on the highest score
        document_type = "Default/Unknown (No Classifications)"
        if classification_response.classifications:
            # Sort by score descending and pick the top one
            best_classification = sorted(classification_response.classifications, key=lambda x: x.score, reverse=True)[0]
            document_type = best_classification.type

        logger.info(f"LLM result - Type: {document_type}, Description: {classification_response.short_description}, Classifications: {classification_response.classifications}")

        return {
            "document_type": document_type,
            "short_description": classification_response.short_description,
            "classifications": [c.model_dump() for c in classification_response.classifications] # Return as dicts
        }

    except Exception as e: # Catch Pydantic validation errors or other parsing issues
        logger.error(f"Error parsing or validating JSON from LLM response: {e}")
        logger.error(f"LLM response text that failed parsing: '{cleaned_response_text}'")
        return {
            "document_type": "Default/Unknown (JSON Error)",
            "short_description": "Summary not available (JSON Error).",
            "classifications": []
        }

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

import re

def parse_mcp_email_list(raw_content):
    # Split by double newlines (jede Mail ist ein Block)
    blocks = [block.strip() for block in raw_content.strip().split('\n\n') if block.strip()]
    emails = []
    for block in blocks:
        # Extrahiere Felder mit Regex
        id_match = re.search(r'ID: (.+)', block)
        subject_match = re.search(r'Subject: (.+)', block)
        from_match = re.search(r'From: (.+)', block)
        date_match = re.search(r'Date: (.+)', block)
        # Extrahiere alle Attachments (kann mehrfach vorkommen)
        attachment_matches = re.findall(r'Attachment: (.+)', block)
        emails.append({
            'id': id_match.group(1) if id_match else None,
            'subject': subject_match.group(1) if subject_match else None,
            'sender': from_match.group(1) if from_match else None,
            'date': date_match.group(1) if date_match else None,
            'attachments': attachment_matches if attachment_matches else []
            
        })
    return emails

async def check_new_emails(db_pool: asyncpg.pool.Pool, interval_seconds: int = 60):
    """
    Checks for new emails, summarizes them by topic, and executes all active workflows matching the topic.
    Uses MCP SSE session and tools for all email operations.
    """
    logger.info(f"[Scheduler] Checking for new emails (with SSE/MCP)... Interval: {interval_seconds}s")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp-server/sse/")
    try:
        async with sse_client(MCP_SERVER_URL) as streams:
            async with ClientSession(*streams) as session:
                logger.info("[Scheduler] MCP session established.")
                await session.initialize()
                logger.info("getting tools.")
                oauth_token = await fetch_access_token_for_user(db_pool,"leo@orchestra-nexus.com")
                logger.info(f"OAuth token for user obtained.") # Removed token from log
                mcp_tools = await experimental_mcp_client.load_mcp_tools(session=session, format="mcp")
                if not mcp_tools:
                    logger.warning("No MCP tools available.")
                    return
                # Use the correct tool: search_emails with query 'after:<ts> before:<ts>'
                search_emails_tool = None
                logger.info("[Scheduler] Loaded MCP tools:")
                for tool in mcp_tools:
                    logger.info(f" - {tool.name}")
                    if hasattr(tool, 'name') and tool.name == 'search_emails':
                        search_emails_tool = tool
                        break
                if not search_emails_tool:
                    logger.warning("No 'search_emails' tool found in MCP tools.")
                    return
                # Calculate the correct time window for the query
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                after_dt = now_utc - datetime.timedelta(hours=interval_seconds)
                # Convert to Unix timestamps (seconds since epoch)
                after_ts = int(after_dt.timestamp())
                before_ts = int(now_utc.timestamp())
                # Build Gmail-style query string
                gmail_query = f"after:{after_ts} before:{before_ts}"
                logger.info(f"Using Gmail query: {gmail_query}")
                # Call the tool via the session with the correct parameters
                result = await session.call_tool(search_emails_tool.name, arguments={"query": gmail_query})
                logger.info(f"Search result from MCP tool: {result}") # Removed raw result from log
                # Defensive: Log and check the raw response before parsing
                raw_content = result.content[0].text if result and result.content and len(result.content) > 0 else None
                logger.info(f"Raw MCP tool response: {raw_content!r}")
                if not raw_content or not raw_content.strip():
                    logger.warning("MCP tool 'search_emails' returned empty or whitespace-only response. Skipping email processing.")
                    return

                logger.info(f"Raw MCP tool response length: {type(raw_content)} characters")
                emails=parse_mcp_email_list(raw_content)
                if not emails:
                    logger.error("No new emails found in MCP tool response.")
                    return
                async def read_emails_and_log(email):
                    """
                    Für jede E-Mail: Hole den vollständigen Inhalt, parse ihn, und lade ggf. Attachments herunter.
                    """
                    results = []
                    message_id = email.get('id')
                    if not message_id:
                        logger.warning(f"Email without ID: {email}")
                        return
                    try:
                        email= await get_email(db_pool,"leo@orchestra-nexus.com", message_id,oauth_token) # TODO: Get actual user email
                        logger.info(f"Processing email ID: {message_id} - Subject: {email.get('subject', 'N/A')}") # Added subject to log
                        results.append(email)  # Store the full email data for later processing

                    except Exception as e:
                        logger.error(f"Error reading email {message_id}: {e}")
                    return results

                processed_emails = []
                for email in emails:
                    results = await read_emails_and_log(email)
                    processed_emails.extend(results)

                async with db_pool.acquire() as connection:
                    logger.info("[Scheduler] Acquired DB connection for email processing.")
                    logger.info(f"Found {len(processed_emails)} new emails to process.")
                    for email_data in processed_emails:
                        logger.info(f"Processing email data keys: {email_data.keys()}") # Log keys for debugging
                        headers = email_data.get('headers', {}) # Get the headers dictionary
                        message_id = email_data.get('id')
                        email_subject_str = headers.get('Subject', 'No Subject') # Extract Subject from headers
                        sender = headers.get('From', 'Unknown Sender') # Extract From from headers

                        email_body_str = email_data.get('body', '')
                        # Convert received_at to timezone-naive UTC before inserting into DB
                        received_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

                        logger.info(f"Processing email: ID={message_id}, Subject='{email_subject_str}', Sender='{sender}'")

                        inserted_email_id = None # Initialize inserted_email_id to None

                        try: # Add try-except block here
                            # The 'sender' extracted from headers is likely a string like 'Name <email@example.com>'
                            # We need to parse the email address from this string.
                            # A simple approach is to find the email within the angle brackets.
                            sender_email_match = re.search(r'<(.+?)>', sender)
                            if sender_email_match:
                                sender_email = sender_email_match.group(1)
                            elif isinstance(sender, str):
                                # If no angle brackets, assume the whole string is the email
                                sender_email = sender
                            else:
                                sender_email = 'Unknown Sender'
                            logger.info(f"Extracted sender email: {sender_email}")


                            if not message_id:
                                logger.info(f"Skipping email due to missing message ID: {email_data}")
                                continue

                            # Check if email already exists
                            logger.info(f"Checking for existing email with Subject='{email_subject_str}', Sender='{sender_email}'")
                            existing_email = await connection.fetchrow(
                                "SELECT id FROM emails WHERE subject = $1 AND sender = $2 AND body = $3",
                                email_subject_str, sender_email, email_body_str
                            )
                            if existing_email:
                                existing_email_id = existing_email['id']
                                logger.info(f"Duplicate email found. Deleting existing email ID: {existing_email_id} and associated audit trail entries.")

                                # Delete associated audit trail entries first
                                await connection.execute("DELETE FROM audit_trail WHERE email_id = $1", existing_email_id)
                                logger.info(f"Deleted audit trail entries for email ID: {existing_email_id}")

                                # Now delete the existing email
                                await connection.execute("DELETE FROM emails WHERE id = $1", existing_email_id)
                                logger.info(f"Deleted existing email ID: {existing_email_id}")

                                # Log the deletion of the duplicate email (this log entry itself won't have an email_id reference anymore)
                                try:
                                    await connection.execute(
                                        "INSERT INTO audit_trail (action, username, timestamp) VALUES ($1, $2, NOW())",
                                        f"Duplicate email received. Deleted existing email ID: {existing_email_id}. Subject: '{email_subject_str}'",
                                        "system_email_processing"
                                    )
                                except Exception as log_e:
                                    logger.error(f"Audit log failure for duplicate email deletion: {log_e}")
                                # Continue processing to insert the new email

                            logger.info(f"New email detected: Subject='{email_subject_str}', Sender='{sender_email}'. Proceeding with summary and processing.")

                            # --- 1. SUMMARY/LLM STEP ---
                            llm_model_to_use = "gemini-1.5-flash"
                            # Define possible types for classification
                            possible_types = ["Google", "Important", "Health", "Marketing", "Spam", "Other"] # Example types, adjust as needed

                            # Prepare attachments info for the LLM
                            attachments_info_for_llm = []
                            downloaded_attachments = email_data.get('attachments', [])
                            for att in downloaded_attachments:
                                attachments_info_for_llm.append({
                                    'filename': att.get('filename', 'unnamed'),
                                    'mimeType': att.get('mimeType', 'application/octet-stream')
                                })
                            logger.info(f"Calling get_summary_and_type_from_llm for email ID: {message_id} with attachments: {attachments_info_for_llm}")

                            llm_summary_data = await get_summary_and_type_from_llm(
                                email_subject=email_subject_str,
                                email_body=email_body_str,
                                llm_model_name=llm_model_to_use,
                                possible_types=possible_types, # Pass possible types
                                attachments_info=attachments_info_for_llm # Pass attachments info
                            )
                            logger.info(f"Received LLM summary data for email ID {message_id}: {llm_summary_data}")
                            topic = llm_summary_data.get("document_type", "Default/LLMError")
                            short_description = llm_summary_data.get("short_description", "Summary N/A (LLMError)")
                            logger.info(f"LLM summary for email ID {message_id}: topic={topic}, desc={short_description}")

                            # Insert email
                            logger.info(f"Inserting email ID {message_id} into database.")
                            inserted_email_id = await connection.fetchval(
                                """
                                INSERT INTO emails (subject, sender, body, received_at, label, type, short_description)
                                VALUES ($1, $2, $3, $4, $5, $6, $7)
                                RETURNING id
                                """,
                                email_subject_str,
                                sender_email, # Use the extracted sender_email
                                email_body_str,
                                received_at, # Use timezone-naive datetime
                                None,  # Default label
                                topic,
                                short_description
                            )
                            logger.info(f"Inserted new email ID: {inserted_email_id}, Topic: {topic}")

                            await connection.execute(
                                "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                                inserted_email_id,
                                f"New email received. Subject: '{email_subject_str}'. Assigned ID: {inserted_email_id}",
                                "system_email_processing"
                            )

                            # --- 2. WORKFLOW MATCHING & EXECUTION ---
                            logger.info(f"Fetching active workflows for email ID {inserted_email_id}.")
                            workflow_rows = await connection.fetch(
                                "SELECT id, workflow_name, workflow_config FROM scheduler_tasks WHERE status = 'active' AND trigger_type = 'cron'"
                            )
                            logger.info(f"Found {len(workflow_rows)} active workflows for email ID {inserted_email_id}.")
                            for wf_row in workflow_rows:
                                wf_config = wf_row['workflow_config']
                                if isinstance(wf_config, str):
                                    try:
                                        wf_config = json.loads(wf_config)
                                    except Exception:
                                        wf_config = {}

                                selected_topic = wf_config.get('selected_topic')
                                if selected_topic and selected_topic != topic:
                                    logger.info(f"Skipping workflow '{wf_row['workflow_name']}' for email ID {inserted_email_id} due to topic mismatch (required: {selected_topic}, email topic: {topic}).")
                                    continue  # Only run workflows matching this topic

                                logger.info(f"Executing workflow '{wf_row['workflow_name']}' for topic '{topic}' on email {inserted_email_id}")

                                task_id = await connection.fetchval(
                                    """
                                    INSERT INTO tasks (email_id, status, created_at, updated_at, workflow_type)
                                    VALUES ($1, $2, $3, $4, $5)
                                    RETURNING id
                                    """,
                                    inserted_email_id,
                                    wf_config.get('initial_status', 'pending'),
                                    received_at,
                                    received_at,
                                    topic
                                )
                                await connection.execute(
                                    "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                                    inserted_email_id,
                                    f"Task created for workflow '{wf_row['workflow_name']}' (Task ID: {task_id}) for topic '{topic}'",
                                    "system_workflow_init"
                                )

                                if wf_config and "document_processing" in wf_config.get("steps", []):
                                    logger.info(f"Initiating document processing step for task {task_id}, email ID {inserted_email_id}.")
                                    await process_document_step(
                                        task_id=task_id,
                                        email_id=inserted_email_id,
                                        db_conn_for_audit=connection,
                                        workflow_config=wf_config
                                    )
                                else:
                                    logger.info(f"No document_processing step in workflow for task {task_id}.")

                            # --- 1b. ATTACHMENT HANDLING ---
                            logger.info(f"Processing attachments for email ID {inserted_email_id}.")
                            document_ids = []
                            # downloaded_attachments is already available from the get_email call
                            # downloaded_attachments = email_data.get('attachments', []) # This line is redundant
                            logger.info(f"Found {len(downloaded_attachments)} downloaded attachments for email ID {inserted_email_id}.")
                            for att_data in downloaded_attachments:
                                try:
                                    logger.info(f"Inserting attachment '{att_data.get('filename', 'unnamed')}' for email ID {inserted_email_id} into database.")
                                    # The 'data' field in downloaded_att is bytes, encode it to base64 for the database
                                    data_b64 = base64.b64encode(att_data['data']).decode('utf-8')

                                    doc_id = await connection.fetchval(
                                        """
                                        INSERT INTO documents (email_id, filename, content_type, data_b64, is_processed, created_at)
                                        VALUES ($1, $2, $3, $4, $5, $6)
                                        RETURNING id
                                        """,
                                        inserted_email_id, # Use the inserted email ID
                                        att_data.get('filename', 'unnamed'),
                                        att_data.get('mimeType', 'application/octet-stream'),
                                        data_b64, # Use the base64 encoded data
                                        False, # is_processed
                                        received_at # created_at
                                    )
                                    document_ids.append(doc_id)
                                    logger.info(f"Inserted document ID {doc_id} for email {inserted_email_id} (attachment: {att_data.get('filename')})")
                                except Exception as e:
                                    logger.error(f"Failed to insert document for email {inserted_email_id} (attachment: {att_data.get('filename')}): {e}")

                            # Update emails row with document_ids if any attachments
                            if document_ids:
                                try:
                                    logger.info(f"Updating email {inserted_email_id} with document_ids: {document_ids}")
                                    await connection.execute(
                                        "UPDATE emails SET document_ids = $1 WHERE id = $2",
                                        document_ids,
                                        inserted_email_id
                                    )
                                    logger.info(f"Updated email {inserted_email_id} with document_ids: {document_ids}")
                                except Exception as e:
                                    logger.error(f"Failed to update email {inserted_email_id} with document_ids: {e}")
                            logger.info(f"Finished processing email ID {message_id}.")

                        except Exception as e: # Catch exceptions during processing of a single email
                            logger.error(f"Error processing email 1 (Subject: '{email_subject_str}', Sender: '{sender_email}', Message ID: {message_id}): {e}")
                            # Log to audit trail only if email insertion was successful
                            if inserted_email_id is not None:
                                try:
                                    await connection.execute(
                                        "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                                        inserted_email_id,
                                        f"Error processing email after insertion. Subject: '{email_subject_str}'. Error: {str(e)}",
                                        "system_email_processing_error"
                                    )
                                except Exception as log_e:
                                    logger.error(f"Audit log failure for email processing error (after insert): {log_e}")
                            else:
                                # Log a generic error if email insertion failed
                                try:
                                     await connection.execute(
                                        "INSERT INTO audit_trail (action, username, timestamp) VALUES ($1, $2, NOW())",
                                        f"Error processing email insert (insertion failed). Subject: '{email_subject_str}', Message ID: {message_id}. Error: {str(e)}",
                                        "system_email_processing_error"
                                    )
                                except Exception as log_e:
                                    logger.error(f"Audit log failure for email processing error (before insert): {log_e}")

                            continue # Continue to the next email

    except Exception as e:
        logger.error(f"[Scheduler] Error during email check: {e}")
    finally:
        if 'session' in locals() and session:
            logger.info("[Scheduler] Closing MCP session.")
      