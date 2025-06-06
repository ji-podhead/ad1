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
async def get_summary_and_type_from_llm(
    email_subject: str,
    email_body: str,
    llm_model_name: str,
    extraction_parameter_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyzes email content using an LLM to determine document type, a short description,
    and optionally extract a specific parameter.
    Returns a dictionary with "document_type", "short_description", and optionally "extracted_parameter".
    """
    if not GEMINI_API_KEY:
        print("Error: Gemini API key not configured. Cannot get summary from LLM.")
        return {
            "document_type": "Default/Unknown (LLM Error)",
            "short_description": "Summary not available (LLM Error).",
            "extracted_parameter": None
        }

    extraction_prompt_part = ""
    if extraction_parameter_name:
        extraction_prompt_part = f"""
Additionally, extract the value for the parameter "{extraction_parameter_name}".
The JSON response should include an "extracted_parameter" object with "name" and "value" keys, like this:
"extracted_parameter": {{"name": "{extraction_parameter_name}", "value": "extracted_value_here"}}
If the parameter is not found, the value should be null or an empty string.
"""

    prompt = f"""Analyze the following email content.
Return your response *only* as a valid JSON object.
The JSON object must have keys "document_type" and "short_description".
Ensure the "document_type" is a concise category (e.g., "Invoice", "Support Request", "Marketing Email", "Sick Note", "Order Confirmation").
Ensure the "short_description" is a 1-2 sentence summary of the email's main content.
{extraction_prompt_part}
Subject: {email_subject}

Body:
{email_body[:4000]}

Your JSON response:
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
            extracted_param = data.get("extracted_parameter") # This could be None if not in response

            result = {
                "document_type": str(doc_type),
                "short_description": str(short_desc),
                "extracted_parameter": extracted_param # Will be None if not found or not requested
            }
            print(f"LLM result - Type: {doc_type}, Description: {short_desc}, Extracted: {extracted_param}")
            return result
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from LLM response: {e}")
            print(f"LLM response text that failed parsing: '{cleaned_response_text}'")
            return {
                "document_type": "Default/Unknown (JSON Error)",
                "short_description": "Summary not available (JSON Error).",
                "extracted_parameter": None
            }

    except Exception as e:
        print(f"Error during LLM call: {e}")
        return {
            "document_type": "Default/Unknown (API Error)",
            "short_description": "Summary not available (API Error).",
            "extracted_parameter": None
        }

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
                print(f"Skipping email due to missing message ID: {email_data}")
                continue

            # Default values before workflow specific logic
            current_email_workflow_type = "Default/NoWorkflow"
            current_task_initial_status = "pending"
            current_email_short_description = "Not processed by LLM."
            llm_model_to_use = "gemini-pro" # Default LLM model
            applied_workflow_config_dict = {} # Ensure it's always a dict
            extraction_param_name_from_config: Optional[str] = None
            extracted_data_for_db: Optional[dict] = None


            if email_receive_workflows:
                first_workflow = email_receive_workflows[0]
                raw_workflow_config = first_workflow['workflow_config'] # Use a new var name
                applied_workflow_name = first_workflow['workflow_name']
                logger.info(f"Applying email_receive workflow: {applied_workflow_name}")

                if raw_workflow_config:
                    if isinstance(raw_workflow_config, str):
                        try:
                            applied_workflow_config_dict = json.loads(raw_workflow_config)
                        except json.JSONDecodeError:
                            logger.warning(f"Could not parse workflow_config JSON for {applied_workflow_name}: {raw_workflow_config}")
                            # applied_workflow_config_dict remains {}
                    elif isinstance(raw_workflow_config, dict):
                        applied_workflow_config_dict = raw_workflow_config
                    else:
                        logger.warning(f"workflow_config for {applied_workflow_name} is neither string nor dict. Type: {type(raw_workflow_config)}")
                        # applied_workflow_config_dict remains {}

                if applied_workflow_config_dict: # Check if dict is not empty after parsing attempt
                    llm_model_to_use = applied_workflow_config_dict.get("model", llm_model_to_use)
                    current_task_initial_status = applied_workflow_config_dict.get("initial_status", current_task_initial_status)
                    extraction_param_name_from_config = applied_workflow_config_dict.get("extraction_parameter_name")
                    # extraction_parameter_details = applied_workflow_config_dict.get("extraction_parameter_details") # For future use

                    # Call LLM for summary, type, and optional parameter extraction
                    llm_summary_data = await get_summary_and_type_from_llm(
                        email_subject=email_subject_str,
                        email_body=email_body_str,
                        llm_model_name=llm_model_to_use,
                        extraction_parameter_name=extraction_param_name_from_config
                    )
                    current_email_workflow_type = llm_summary_data.get("document_type", "Default/LLMError")
                    current_email_short_description = llm_summary_data.get("short_description", "Summary N/A (LLMError)")
                    extracted_parameter_info = llm_summary_data.get("extracted_parameter")

                    llm_log_message = f"LLM processing for Email Subject: '{email_subject_str}'. Model: '{llm_model_to_use}'. Type: '{current_email_workflow_type}', Desc: '{current_email_short_description}'"

                    if extracted_parameter_info and isinstance(extracted_parameter_info, dict):
                        param_name = extracted_parameter_info.get("name")
                        param_value = extracted_parameter_info.get("value")
                        if param_name and param_value is not None: # Ensure value can be empty string but not None if key exists
                            extracted_data_for_db = {"custom_extract": {param_name: param_value}}
                            llm_log_message += f", Extracted: '{param_name}':'{param_value}'"
                        else:
                             logger.warning(f"LLM returned extracted_parameter with missing name/value: {extracted_parameter_info}")


                    print(f"LLM derived - Type: {current_email_workflow_type}, Description: {current_email_short_description}, Status: {current_task_initial_status}, Extracted: {extracted_parameter_info}")

                    # Log LLM processing action
                    await connection.execute(
                        "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                        None,
                        llm_log_message,
                        "system_llm_agent"
                    )
                else:
                    print(f"No workflow_config for {applied_workflow_name}, using defaults and skipping LLM.")
            else:
                print("No active 'email_receive' workflows. Email will use default types, task status, and no LLM summary.")

            try:
                existing_email = await connection.fetchrow(
                    "SELECT id FROM emails WHERE subject = $1 AND sender = $2 AND body = $3",
                    email_subject_str, sender_email, email_body_str
                )

                if not existing_email:
                    inserted_email_id = await connection.fetchval(
                        """
                        INSERT INTO emails (subject, sender, body, received_at, label, type, short_description, extracted_data)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        RETURNING id
                        """,
                        email_subject_str,
                        sender_email,
                        email_body_str,
                        received_at,
                        None,  # Default label
                        current_email_workflow_type, # Type from LLM or default
                        current_email_short_description, # Description from LLM or default
                        json.dumps(extracted_data_for_db) if extracted_data_for_db else None # Store as JSON string or NULL
                    )
                    print(f"Inserted new email ID: {inserted_email_id}, Type: {current_email_workflow_type}, Extracted Data: {extracted_data_for_db}")

                    # Log email ingestion
                    await connection.execute(
                        "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                        inserted_email_id,
                        f"New email received. Subject: '{email_subject_str}'. Assigned ID: {inserted_email_id}",
                        "system_email_processing"
                    )

                    # Update LLM audit log with actual email_id if it was a new email
                    # This is a bit tricky as the LLM log above might not have email_id yet.
                    # For simplicity, we might log LLM action after email insertion or accept it might lack email_id if logged before.
                    # The current placement logs LLM action before knowing `inserted_email_id`.
                    # Addressed by logging LLM action after email insertion if new, or with None if not.

                    task_insert_query = """
                        INSERT INTO tasks (email_id, status, created_at, updated_at, workflow_type)
                        VALUES ($1, $2, $3, $4, $5)
                        RETURNING id
                    """
                    new_task_id = await connection.fetchval(
                        task_insert_query,
                        inserted_email_id,
                        current_task_initial_status,
                        received_at,
                        received_at,
                        current_email_workflow_type
                    )
                    logger.info(f"Created task ID: {new_task_id} for email ID: {inserted_email_id}, Workflow Type: {current_email_workflow_type}, Status: {current_task_initial_status}")

                    await connection.execute(
                        "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                        inserted_email_id,
                        f"Task created for new email. Task ID: {new_task_id}. Workflow Type: '{current_email_workflow_type}', Initial Status: '{current_task_initial_status}'",
                        "system_workflow_init"
                    )

                    # If document processing step is part of this workflow, call it
                    if applied_workflow_config_dict and "document_processing" in applied_workflow_config_dict.get("steps", []):
                        logger.info(f"Document processing step found for task {new_task_id}, email {inserted_email_id}. Initiating.")
                        await process_document_step(
                            task_id=new_task_id,
                            email_id=inserted_email_id,
                            db_conn_for_audit=connection,
                            workflow_config=applied_workflow_config_dict
                        )
                    else:
                        logger.info(f"No document_processing step in workflow for task {new_task_id}.")

                else: # Email already exists
                    logger.info(f"Email already exists, skipping insertion: Subject='{email_subject_str}', Sender='{sender_email}'")

            except Exception as e:
                logger.error(f"Error processing email (Subject: '{email_subject_str}', Sender: '{sender_email}'): {e}")

async def process_document_step(task_id: int, email_id: int, db_conn_for_audit: Any, workflow_config: Dict[str, Any]):
    """
    Processes a document related to an email by calling the document processing microservice.
    db_conn_for_audit here is expected to be an acquired connection from asyncpg.pool.Pool for audit logging.
    """
    pdf_bytes: Optional[bytes] = None
    email_subject_for_filename = f"Email_ID_{email_id}_Task_{task_id}"

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
