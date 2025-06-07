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
import google.genai as genai
from google.genai.types import GenerateContentConfig, HttpOptions
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from litellm import experimental_mcp_client
from tools_wrapper import list_emails # Import list_emails
import aiohttp
import logging # Added for explicit logging
import base64 # For dummy PDF
from mcp.client.sse import sse_client
from mcp import ClientSession

# Setup basic logging if not already configured elsewhere globally
# logging.basicConfig(level=logging.INFO) # Already configured in backend_main.py, avoid reconfiguring.
# Instead, get a logger instance if needed for this specific module:
logger = logging.getLogger(__name__)
# logging.getLogger("aiohttp").setLevel(logging.WARNING) # Optional: Quieten aiohttp's own logs

# Configure Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

else:
    print("Warning: GEMINI_API_KEY not found in environment. LLM features will not work.")

# Helper function to get summary and type from LLM
async def get_summary_and_type_from_llm(email_subject: str, email_body: str, llm_model_name: str) -> Dict[str, str]:
    """
    Analyzes email content using an LLM to determine document type and a short description.
    Returns a dictionary with "document_type" and "short_description".
    """
    if not GEMINI_API_KEY:
        print("Error: Gemini API key not configured. Cannot get summary from LLM.")
        return {"document_type": "Default/Unknown (LLM Error)", "short_description": "Summary not available (LLM Error)."}

    prompt = f"""Analyze the following email content and provide a document type and a short description.
Return your response *only* as a valid JSON object with keys "document_type" and "short_description".
Ensure the "document_type" is a concise category (e.g., "Invoice", "Support Request", "Marketing Email", "Sick Note", "Order Confirmation").
Ensure the "short_description" is a 1-2 sentence summary of the email's main content.

Subject: {email_subject}

Body:
{email_body[:4000]}
""" # Limiting body length to manage token usage, adjust as needed



    print(f"Sending prompt to LLM ({llm_model_name}) for subject: {email_subject}")
    try:
        model = genai.GenerativeModel(llm_model_name)
        response = await model.generate_content_async(prompt)
        response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[ prompt],
                config=GenerateContentConfig(
                    system_instruction=["summarize the email and classify it into a document type."],
                    ),
            )
        # Debug: Print raw response text
        # print(f"LLM raw response: {response.text}")

        # Attempt to clean and parse the JSON response
        # LLMs sometimes add markdown backticks or "json" prefix
        cleaned_response_text = response.text.strip()
        if cleaned_response_text.startswith("```json"):
            cleaned_response_text = cleaned_response_text[7:]
        elif cleaned_response_text.startswith("```"):
             cleaned_response_text = cleaned_response_text[3:]
        if cleaned_response_text.endswith("```"):
            cleaned_response_text = cleaned_response_text[:-3]

        cleaned_response_text = cleaned_response_text.strip()

        try:
            data = json.loads(cleaned_response_text)
            doc_type = data.get("document_type", "Default/Unknown (LLM Parse Error)")
            short_desc = data.get("short_description", "Summary not available (LLM Parse Error).")
            print(f"LLM result - Type: {doc_type}, Description: {short_desc}")
            return {"document_type": str(doc_type), "short_description": str(short_desc)}
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from LLM response: {e}")
            print(f"LLM response text that failed parsing: '{cleaned_response_text}'")
            return {"document_type": "Default/Unknown (JSON Error)", "short_description": "Summary not available (JSON Error)."}

    except Exception as e:
        print(f"Error during LLM call: {e}")
        return {"document_type": "Default/Unknown (API Error)", "short_description": "Summary not available (API Error)."}

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


async def check_new_emails(db_pool: asyncpg.pool.Pool, interval_seconds: int = 60):
    """
    Checks for new emails, summarizes them by topic, and executes all active workflows matching the topic.
    Uses MCP SSE session and tools for all email operations.
    """
    logger.info(f"[Scheduler] Checking for new emails (with SSE/MCP)... Interval: {interval_seconds}s (IGNORED, using 24h window for testing)")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp-server/sse/")
    try:
        async with sse_client(MCP_SERVER_URL) as streams:
            async with ClientSession(*streams) as session:
                logger.info("[Scheduler] MCP session established.")
                await session.initialize()
                logger.info("getting tools.")
                mcp_tools = await experimental_mcp_client.load_mcp_tools(session=session, format="mcp")
                if not mcp_tools:
                    logger.warning("No MCP tools available.")
                    return
                # Use a fixed 24h window for testing
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                after_dt = now_utc - datetime.timedelta(hours=24)
                after_ts = int(after_dt.timestamp())
                before_ts = int(now_utc.timestamp())
                # Build Gmail-style query string
                gmail_query = f"after:{after_ts} before:{before_ts}"
                logger.info(f"Using Gmail query (24h): {gmail_query}")
                # Call the tool via the session with the correct parameters
                result = await session.call_tool(search_emails_tool.name, arguments={"query": gmail_query})
                logger.info(result)
                print(result)
                logger.info(f"Search result from MCP tool: {result}")
                # Defensive: Log and check the raw response before parsing
                raw_content = result.content[0].text if result and result.content and len(result.content) > 0 else None
                logger.info(f"Raw MCP tool response: {raw_content!r}")
                if not raw_content or not raw_content.strip():
                    logger.warning("MCP tool 'search_emails' returned empty or whitespace-only response. Skipping email processing.")
                    return
                logger.info("Parsing emails from MCP tool response...")
                logger.info(f"Raw content length: {(raw_content)}")
                try:
                    emails_from_tool = raw_content.splitlines()
                    emails_from_tool = [json.loads(email.strip()) for email in emails_from_tool if email.strip()]
                except Exception as e:
                    logger.error(f"Error parsing emails from MCP tool: {e}. Raw response: {raw_content!r}")
                    return
                for email in emails_from_tool:
                    logger.debug(f"Parsed email data: {email}")
                async with db_pool.acquire() as connection:
                    for email_data in emails_from_tool:
                        message_id = email_data.get('id')
                        email_subject_str = email_data.get('subject', 'No Subject')
                        sender = email_data.get('sender', 'Unknown Sender')
                        email_body_str = email_data.get('body', '')
                        received_at = datetime.datetime.now(datetime.timezone.utc)
                        if isinstance(sender, dict) and 'email' in sender:
                            sender_email = sender['email']
                        elif isinstance(sender, str):
                            sender_email = sender
                        else:
                            sender_email = 'Unknown Sender'
                        if not message_id:
                            logger.warning(f"Skipping email due to missing message ID: {email_data}")
                            continue
                        # Check if email already exists
                        existing_email = await connection.fetchrow(
                            "SELECT id FROM emails WHERE subject = $1 AND sender = $2 AND body = $3",
                            email_subject_str, sender_email, email_body_str
                        )
                        if existing_email:
                            logger.info(f"Email already exists, skipping: Subject='{email_subject_str}', Sender='{sender_email}'")
                            continue
                        # --- 1. SUMMARY/LLM STEP ---
                        logger.info(f"Processing new email: Subject='{email_subject_str}', Sender='{sender_email}'")
                        # Use Gemini Pro for summary and classification
                        llm_model_to_use = "gemini-pro"
                        llm_summary_data = await get_summary_and_type_from_llm(
                            email_subject=email_subject_str,
                            email_body=email_body_str,
                            llm_model_name=llm_model_to_use
                        )
                        topic = llm_summary_data.get("document_type", "Default/LLMError")
                        short_description = llm_summary_data.get("short_description", "Summary N/A (LLMError)")
                        logger.info(f"LLM summary: topic={topic}, desc={short_description}")
                        # Insert email
                        inserted_email_id = await connection.fetchval(
                            """
                            INSERT INTO emails (subject, sender, body, received_at, label, type, short_description)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            RETURNING id
                            """,
                            email_subject_str,
                            sender_email,
                            email_body_str,
                            received_at,
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
                        workflow_rows = await connection.fetch(
                            "SELECT id, workflow_name, workflow_config FROM scheduler_tasks WHERE status = 'active' AND trigger_type = 'cron'"
                        )
                        for wf_row in workflow_rows:
                            wf_config = wf_row['workflow_config']
                            if isinstance(wf_config, str):
                                try:
                                    wf_config = json.loads(wf_config)
                                except Exception:
                                    wf_config = {}
                            selected_topic = wf_config.get('selected_topic')
                            if selected_topic and selected_topic != topic:
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
                                await process_document_step(
                                    task_id=task_id,
                                    email_id=inserted_email_id,
                                    db_conn_for_audit=connection,
                                    workflow_config=wf_config
                                )
                            else:
                                logger.info(f"No document_processing step in workflow for task {task_id}.")
                        # --- 1b. ATTACHMENT HANDLING ---
                        attachments = []
                        try:
                            # Try to fetch attachments/documents for this email via MCP tool if available
                            mcp_attachment_tool = None
                            for tool in mcp_tools:
                                if hasattr(tool, 'name') and tool.name in ['get_attachments', 'download_attachments', 'fetch_attachments']:
                                    mcp_attachment_tool = tool
                                    break
                            if mcp_attachment_tool:
                                logger.info(f"Fetching attachments for message_id={message_id} using MCP tool '{mcp_attachment_tool.name}'")
                                att_result = await session.call_tool(mcp_attachment_tool.name, arguments={"message_id": message_id})
                                att_content = att_result.content[0].text if att_result and att_result.content and len(att_result.content) > 0 else None
                                if att_content:
                                    try:
                                        attachments = json.loads(att_content)
                                        logger.info(f"Fetched {len(attachments)} attachments for message_id={message_id}")
                                    except Exception as e:
                                        logger.warning(f"Could not parse attachments JSON for message_id={message_id}: {e}")
                                else:
                                    logger.info(f"No attachments found for message_id={message_id}")
                            else:
                                logger.info("No MCP attachment tool found, skipping attachment fetch.")
                        except Exception as e:
                            logger.error(f"Error fetching attachments for message_id={message_id}: {e}")
                        document_ids = []
                        for att in attachments:
                            try:
                                doc_id = await connection.fetchval(
                                    """
                                    INSERT INTO documents (email_id, filename, content_type, data_b64, is_processed, created_at)
                                    VALUES ($1, $2, $3, $4, $5, $6)
                                    RETURNING id
                                    """,
                                    inserted_email_id,
                                    att.get('filename', 'unnamed'),
                                    att.get('content_type', 'application/octet-stream'),
                                    att.get('data_b64', ''),
                                    False,
                                    received_at
                                )
                                document_ids.append(doc_id)
                                logger.info(f"Inserted document ID {doc_id} for email {inserted_email_id} (attachment: {att.get('filename')})")
                            except Exception as e:
                                logger.error(f"Failed to insert document for email {inserted_email_id}: {e}")
                        # Update emails row with document_ids if any attachments
                        if document_ids:
                            try:
                                await connection.execute(
                                    "UPDATE emails SET document_ids = $1 WHERE id = $2",
                                    document_ids,
                                    inserted_email_id
                                )
                                logger.info(f"Updated email {inserted_email_id} with document_ids: {document_ids}")
                            except Exception as e:
                                logger.error(f"Failed to update email {inserted_email_id} with document_ids: {e}")
    except Exception as e:
        logger.error(f"[Scheduler] Error during email check: {e}")
    finally:
        if 'session' in locals() and session:
            logger.info("[Scheduler] Closing MCP session.")
async def process_document_step(task_id: int, email_id: int, db_conn_for_audit: Any, workflow_config: Dict[str, Any]):
    """
    Processes a document related to an email by calling the document processing microservice.
    db_conn_for_audit here is expected to be an acquired connection from asyncpg.pool.Pool for audit logging.
    """
    import base64
    import aiohttp
    import os
    import json
    import logging
    pdf_bytes: Optional[bytes] = None
    email_subject_for_filename = f"Email_ID_{email_id}_Task_{task_id}"
    logger = logging.getLogger(__name__)
    try:
        await db_conn_for_audit.execute(
            "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
            email_id, f"Attempting document processing for Task ID: {task_id}", "system_workflow_step"
        )
    except Exception as log_e:
        logger.error(f"Audit log failure (attempt doc processing): {log_e}")
    try:
        if email_id == 1: # Placeholder: Dummy PDF for email_id 1
            dummy_pdf_b64 = "JVBERi0xLjQKJVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            pdf_bytes = base64.b64decode(dummy_pdf_b64)
            logger.info(f"Using dummy PDF for email_id {email_id} in document processing step for Task {task_id}.")
        else:
            logger.warning(f"No actual PDF fetching logic for email_id {email_id} (Task {task_id}). Document processing step will be skipped unless email_id is 1.")
            await db_conn_for_audit.execute(
                "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                email_id, f"Document processing skipped for Task ID: {task_id} - No PDF found (placeholder logic).", "system_workflow_step"
            )
            return
        if not pdf_bytes: return
    except Exception as e:
        logger.error(f"Error obtaining/generating PDF for task {task_id}, email {email_id}: {e}")
        try:
            await db_conn_for_audit.execute(
                "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                email_id, f"Error obtaining PDF for Task ID: {task_id}. Error: {str(e)}", "system_workflow_step"
            )
        except Exception as log_e:
            logger.error(f"Audit log failure (PDF fetch error): {log_e}")
        return
    doc_service_url = os.getenv("DOC_PROCESSING_SERVICE_URL", "http://doc-processing-service:8000/process_pdf/")
    if not doc_service_url:
        logger.error(f"DOC_PROCESSING_SERVICE_URL is not set. Cannot process document for Task {task_id}.")
        try:
            await db_conn_for_audit.execute(
                "INSERT INTO audit_trail (action, username, timestamp) VALUES ($1, $2, NOW())",
                f"DOC_PROCESSING_SERVICE_URL not set. Document processing skipped for Task ID: {task_id}.", "system_config_error"
            )
        except Exception as log_e:
            logger.error(f"Audit log failure (config error): {log_e}")
        return
    try:
        async with aiohttp.ClientSession() as session:
            form_data = aiohttp.FormData()
            form_data.add_field('file', pdf_bytes, filename=f'{email_subject_for_filename}.pdf', content_type='application/pdf')
            logger.info(f"Calling Document Processing Service for Task ID: {task_id} (Email ID: {email_id}) at {doc_service_url}")
            async with session.post(doc_service_url, data=form_data, timeout=300) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError:
                    response_data = {"raw_response": response_text}
                if response.status == 200:
                    logger.info(f"Document processing successful for Task ID: {task_id}. Response: {response_data}")
                    await db_conn_for_audit.execute(
                        "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                        email_id, f"Document processing successful for Task ID: {task_id}. Results: {json.dumps(response_data)[:1500]}",
                        "system_workflow_step"
                    )
                else:
                    logger.error(f"Document processing failed for Task ID: {task_id}. Status: {response.status}, Response: {response_text}")
                    await db_conn_for_audit.execute(
                        "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                        email_id, f"Document processing failed for Task ID: {task_id}. Status: {response.status}, Details: {response_text[:1500]}",
                        "system_workflow_step"
                    )
    except aiohttp.ClientConnectorError as e:
        logger.error(f"Connection error calling document processing service for Task ID: {task_id}: {e}")
        try:
            await db_conn_for_audit.execute(
                "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                 email_id, f"Connection error for document processing (Task ID: {task_id}): {str(e)}", "system_network_error"
            )
        except Exception as log_e:
            logger.error(f"Audit log failure (connection error): {log_e}")
    except asyncio.TimeoutError:
        logger.error(f"Timeout calling document processing service for Task ID: {task_id}")
        try:
            await db_conn_for_audit.execute(
                "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                 email_id, f"Timeout during document processing (Task ID: {task_id})", "system_timeout_error"
            )
        except Exception as log_e:
            logger.error(f"Audit log failure (timeout error): {log_e}")
    except Exception as e:
        logger.error(f"Generic error calling document processing service for Task ID: {task_id}: {e}")
        try:
            await db_conn_for_audit.execute(
                "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                 email_id, f"Error in document processing step (Task ID: {task_id}): {str(e)}", "system_workflow_error"
            )
        except Exception as log_e:
            logger.error(f"Audit log failure (generic error): {log_e}")
