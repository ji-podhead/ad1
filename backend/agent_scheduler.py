# agent_scheduler.py
import asyncio
from typing import Callable, Any, Dict, Optional, List
import datetime
import json
import os
import asyncpg
import google.genai as genai
from google.genai.types import GenerateContentConfig
import logging
import base64 # For decoding email body parts
from tools_wrapper import get_gmail_email_details, list_gmail_messages # Gmail specific
# Note: download_attachment is also Gmail specific now, but not directly used in this file.

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Configure Gemini API Key (remains the same)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY) # Updated way to configure
else:
    print("Warning: GEMINI_API_KEY not found in environment. LLM features will not work.")

# Helper function to get summary and type from LLM (remains largely the same)
async def get_summary_and_type_from_llm(email_subject: str, email_body: str, llm_model_name: str) -> Dict[str, str]:
    if not GEMINI_API_KEY:
        return {"document_type": "Default/Unknown (LLM Error)", "short_description": "Summary not available (LLM Error)."}
    prompt = f"""Analyze the following email content and provide a document type and a short description.
Return your response *only* as a valid JSON object with keys "document_type" and "short_description".
Ensure the "document_type" is a concise category (e.g., "Invoice", "Support Request", "Marketing Email", "Sick Note", "Order Confirmation").
Ensure the "short_description" is a 1-2 sentence summary of the email's main content.

Subject: {email_subject}

Body:
{email_body[:4000]}
"""
    logger.info(f"Sending prompt to LLM ({llm_model_name}) for subject: {email_subject}")
    try:
        model = genai.GenerativeModel(llm_model_name)
        # The previous code had a mix of sync and async calls for Gemini, simplifying to async if possible
        # or ensuring the client used supports async calls properly.
        # For genai client, generate_content_async is the way.
        response = await model.generate_content_async(prompt) # Assuming client.models.generate_content was a typo for model.generate_content_async

        cleaned_response_text = response.text.strip()
        if cleaned_response_text.startswith("```json"):
            cleaned_response_text = cleaned_response_text[7:]
        elif cleaned_response_text.startswith("```"):
             cleaned_response_text = cleaned_response_text[3:]
        if cleaned_response_text.endswith("```"):
            cleaned_response_text = cleaned_response_text[:-3]
        cleaned_response_text = cleaned_response_text.strip()

        data = json.loads(cleaned_response_text)
        doc_type = data.get("document_type", "Default/Unknown (LLM Parse Error)")
        short_desc = data.get("short_description", "Summary not available (LLM Parse Error).")
        return {"document_type": str(doc_type), "short_description": str(short_desc)}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from LLM response: {e}. Response text: '{cleaned_response_text}'")
        return {"document_type": "Default/Unknown (JSON Error)", "short_description": "Summary not available (JSON Error)."}
    except Exception as e:
        logger.error(f"Error during LLM call: {e}", exc_info=True)
        return {"document_type": "Default/Unknown (API Error)", "short_description": "Summary not available (API Error)."}

class AgentScheduler:
    # ... (constructor and other scheduling methods like schedule_email, schedule_cron remain unchanged) ...
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}

    def schedule_email(self, task_id: str, send_func: Callable, to: str, subject: str, body: str, when: datetime.datetime):
        self.tasks[task_id] = asyncio.create_task(self._run_at(send_func, to, subject, body, when))
        logger.info(f"Scheduled email task {task_id}.")

    def schedule_cron(self, task_id: str, func: Callable, interval_seconds: int, *args, **kwargs):
        self.tasks[task_id] = asyncio.create_task(self._run_cron(func, interval_seconds, *args, **kwargs))
        logger.info(f"Scheduled cron task {task_id} to run every {interval_seconds} seconds.")

    async def _run_cron(self, func, interval_seconds, *args, **kwargs):
        while True:
            try:
                await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"[Scheduler] Error in cron job '{func.__name__}': {e}", exc_info=True)
            await asyncio.sleep(interval_seconds)

    def cancel_task(self, task_id: str):
        task = self.tasks.pop(task_id, None)
        if task:
            task.cancel()
            logger.info(f"Cancelled task {task_id}.")
            return True
        logger.warning(f"Attempted to cancel non-existent task {task_id}.")
        return False

    def cancel_all(self):
        for task_id, task in list(self.tasks.items()):
            task.cancel()
            logger.info(f"Cancelled task {task_id} during shutdown.")
        self.tasks.clear()

    async def _run_at(self, send_func, to, subject, body, when): # Added from context if it was missing
        delay = (when - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await send_func(to, subject, body)


# --- Gmail Specific Helper Functions ---
def _extract_header(headers: List[Dict[str, str]], name: str) -> str:
    for header in headers:
        if header['name'].lower() == name.lower():
            return header['value']
    return ""

def _decode_base64url(data: str) -> str:
    """Decodes base64url string, handling padding."""
    missing_padding = len(data) % 4
    if missing_padding:
        data += '=' * (4 - missing_padding)
    try:
        return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
    except Exception as e:
        logger.error(f"Error decoding base64url data: {e}")
        return "" # Return empty string or handle error as appropriate

def _extract_text_plain_body_from_payload(payload: Dict[str, Any]) -> str:
    """Extracts text/plain body from Gmail message payload."""
    body_str = ""
    if payload.get('mimeType') == 'text/plain' and payload.get('body', {}).get('data'):
        body_str = _decode_base64url(payload['body']['data'])
    elif 'parts' in payload:
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                body_str = _decode_base64url(part['body']['data'])
                break # Found text/plain part
            elif part.get('mimeType') == 'multipart/alternative': # Recurse for multipart/alternative
                # This is a common pattern where text/plain and text/html are nested
                body_str = _extract_text_plain_body_from_payload(part)
                if body_str: break # Found it in nested part
    return body_str

def _extract_attachments_from_payload(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extracts attachment metadata from Gmail message payload."""
    attachments = []
    parts = payload.get('parts', [])
    for part in parts:
        if part.get('filename') and part.get('body', {}).get('attachmentId'):
            attachments.append({
                'filename': part['filename'],
                'mimeType': part.get('mimeType', 'application/octet-stream'),
                'google_attachment_id': part['body']['attachmentId'], # This is the ID for downloads
                'partId': part.get('partId') # This is the part's own ID within the message structure
            })
        # Recursively check nested parts (e.g., for emails with multiple levels of multipart/*)
        if 'parts' in part:
            attachments.extend(_extract_attachments_from_payload(part))
    return attachments

async def check_new_emails(db_pool: asyncpg.pool.Pool):
    """
    Checks for new emails for configured users using Gmail API,
    stores them, and triggers workflows.
    """
    logger.info("[Scheduler/Gmail] Starting check_new_emails job.")

    # Placeholder for user iteration and token fetching.
    # In a real system, this would loop through users who have granted permissions.
    # For this subtask, assume one user or a predefined list.
    # TODO: Replace with actual user and token management.
    users_to_check = [
        {"user_db_id": 1, "google_user_id": "me", "email_address": "placeholder_user@example.com"}
    ]

    for user_info in users_to_check:
        user_db_id = user_info["user_db_id"] # Internal DB ID of the user
        google_user_id = user_info["google_user_id"] # "me" or actual Google User ID
        user_email_address = user_info["email_address"] # For logging/reference

        logger.info(f"[Scheduler/Gmail] Checking emails for user: {user_email_address} (DB ID: {user_db_id})")

        access_token = None
        try:
            # Fetch access token for the user from the database
            # Assuming 'users' table has 'id' and 'google_access_token' columns
            token_record = await db_pool.fetchrow("SELECT google_access_token FROM users WHERE email = $1", user_email_address) # Or use user_db_id
            if token_record and token_record['google_access_token']:
                access_token = token_record['google_access_token']
            else:
                logger.warning(f"No google_access_token found for user {user_email_address}. Skipping email check.")
                continue
        except Exception as e:
            logger.error(f"Error fetching access token for {user_email_address}: {e}", exc_info=True)
            continue

        try:
            # 1. List new messages from Gmail
            # Query 'is:unread' or more specific based on last check time (more complex)
            message_summaries = await list_gmail_messages(google_user_id, access_token, query="is:unread", max_results=10) # Adjust max_results
            if not message_summaries:
                logger.info(f"No new messages found for user {user_email_address}.")
                continue

            logger.info(f"Found {len(message_summaries)} new messages for {user_email_address}.")

            async with db_pool.acquire() as connection:
                for msg_summary in message_summaries:
                    gmail_message_id = msg_summary['id']
                    logger.info(f"Processing Gmail message ID: {gmail_message_id} for user {user_email_address}")

                    try:
                        # 2. Fetch full email details
                        gmail_message_data = await get_gmail_email_details(google_user_id, gmail_message_id, access_token)

                        payload = gmail_message_data.get('payload', {})
                        headers = payload.get('headers', [])

                        subject = _extract_header(headers, 'Subject')
                        sender = _extract_header(headers, 'From')
                        # Date header parsing can be complex; internalDate is usually more reliable (ms timestamp)
                        internal_date_ms = gmail_message_data.get('internalDate')
                        received_at = datetime.datetime.fromtimestamp(int(internal_date_ms)/1000, tz=datetime.timezone.utc) \
                            if internal_date_ms else datetime.datetime.now(datetime.timezone.utc)

                        body_text = _extract_text_plain_body_from_payload(payload)
                        if not body_text: # Fallback or alternative for HTML if text/plain is missing
                            logger.warning(f"No text/plain body found for message {gmail_message_id}. Consider HTML parsing.")
                            # For now, use empty or a placeholder if critical

                        # Check for duplicates based on source_message_id
                        existing_email = await connection.fetchval("SELECT id FROM emails WHERE source_message_id = $1", gmail_message_id)
                        if existing_email:
                            logger.info(f"Email with Gmail ID {gmail_message_id} already exists (DB ID: {existing_email}). Skipping.")
                            # TODO: Optionally, mark as read if it was successfully processed.
                            continue

                        # 3. LLM Summarization
                        llm_summary = await get_summary_and_type_from_llm(subject, body_text, "gemini-pro")
                        topic = llm_summary.get("document_type", "Unknown")
                        short_desc = llm_summary.get("short_description", "")

                        async with connection.transaction():
                            # 4. Insert Email into DB
                            inserted_email_id = await connection.fetchval(
                                """
                                INSERT INTO emails (subject, sender, body, received_at, type, short_description,
                                                    source_message_id, source_thread_id, document_ids)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id
                                """,
                                subject, sender, body_text, received_at, topic, short_desc,
                                gmail_message_id, gmail_message_data.get('threadId'), []
                            )
                            logger.info(f"Inserted email '{subject}' as DB ID {inserted_email_id} for Gmail ID {gmail_message_id}.")

                            # 5. Extract and Store Attachment Metadata
                            attachments_from_api = _extract_attachments_from_payload(payload)
                            db_document_ids = []
                            if attachments_from_api:
                                logger.info(f"Found {len(attachments_from_api)} attachments for Gmail ID {gmail_message_id}.")
                                for att_data in attachments_from_api:
                                    # Ensure google_attachment_id column exists in 'documents' table
                                    # CREATE TABLE documents ( ... google_attachment_id TEXT ... );
                                    db_doc_id = await connection.fetchval(
                                        """
                                        INSERT INTO documents (email_id, filename, content_type, google_attachment_id, created_at, is_processed)
                                        VALUES ($1, $2, $3, $4, NOW(), FALSE) RETURNING id
                                        """,
                                        inserted_email_id, att_data['filename'], att_data['mimeType'], att_data['google_attachment_id']
                                    )
                                    db_document_ids.append(db_doc_id)
                                    logger.info(f"Stored attachment '{att_data['filename']}' as doc ID {db_doc_id} (Gmail Att ID: {att_data['google_attachment_id']}) for email DB ID {inserted_email_id}.")

                            if db_document_ids:
                                await connection.execute("UPDATE emails SET document_ids = $1 WHERE id = $2", db_document_ids, inserted_email_id)
                                logger.info(f"Updated email DB ID {inserted_email_id} with document IDs: {db_document_ids}")

                            # Audit log for new email
                            await connection.execute(
                                "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                                inserted_email_id,
                                f"New Gmail email processed. Gmail ID: {gmail_message_id}. DB ID: {inserted_email_id}. Attachments: {len(db_document_ids)}",
                                f"gmail_processing_user:{user_email_address}"
                            )

                            # 6. Workflow Matching & Execution (remains conceptually similar)
                            # ... (This part can be adapted from the old check_new_emails, using inserted_email_id and topic) ...
                            # For brevity, this section is omitted but would follow the previous logic pattern.

                    except Exception as e:
                        logger.error(f"Failed to process Gmail message ID {gmail_message_id} for user {user_email_address}: {e}", exc_info=True)
                        # Optionally, add to a retry queue or mark as failed.

        except Exception as e:
            logger.error(f"Error in Gmail check loop for user {user_email_address}: {e}", exc_info=True)

    logger.info("[Scheduler/Gmail] Finished check_new_emails job.")


# --- Old MCP-based check_new_emails and helpers are now removed/replaced ---
# def parse_mcp_email_list(raw_content): ... (Removed)
# def parse_full_email(text: str): ... (Removed)
# The old async def check_new_emails that used MCP tools is replaced by the one above.

# process_document_step can remain if workflows use it.
async def process_document_step(task_id: int, email_id: int, db_conn_for_audit: Any, workflow_config: Dict[str, Any]):
    # ... (This function implementation remains unchanged as it's about a later step) ...
    import base64 # Already imported at top
    import aiohttp # Already imported at top
    # import os # Already imported at top
    # import json # Already imported at top
    # import logging # Already imported at top
    pdf_bytes: Optional[bytes] = None
    email_subject_for_filename = f"Email_ID_{email_id}_Task_{task_id}"
    # logger = logging.getLogger(__name__) # Use module logger

    try:
        await db_conn_for_audit.execute(
            "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
            email_id, f"Attempting document processing for Task ID: {task_id}", "system_workflow_step"
        )
    # ... (rest of the function is the same) ...
    except Exception as log_e:
        logger.error(f"Audit log failure (attempt doc processing): {log_e}")
    try:
        if email_id == 1: # Placeholder: Dummy PDF for email_id 1
            dummy_pdf_b64 = "JVBERi0xLjQKJVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            pdf_bytes = base64.b64decode(dummy_pdf_b64)
            logger.info(f"Using dummy PDF for email_id {email_id} in document processing step for Task {task_id}.")
        else:
            # In a real scenario, this would fetch a document from 'documents' table,
            # then call download_attachment if data_b64 is NULL, using google_attachment_id.
            # For now, this placeholder logic remains.
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
        # ... (logging for config error)
        return

    try:
        async with aiohttp.ClientSession() as http_session: # Renamed from 'session' to avoid conflict
            form_data = aiohttp.FormData()
            form_data.add_field('file', pdf_bytes, filename=f'{email_subject_for_filename}.pdf', content_type='application/pdf')
            logger.info(f"Calling Document Processing Service for Task ID: {task_id} (Email ID: {email_id}) at {doc_service_url}")
            async with http_session.post(doc_service_url, data=form_data, timeout=300) as response:
                # ... (response handling remains same) ...
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError:
                    response_data = {"raw_response": response_text} # Store raw if not JSON

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

    # ... (error handling for doc processing service call remains same) ...
    except aiohttp.ClientConnectorError as e:
        logger.error(f"Connection error calling document processing service for Task ID: {task_id}: {e}")
    except asyncio.TimeoutError:
        logger.error(f"Timeout calling document processing service for Task ID: {task_id}")
    except Exception as e:
        logger.error(f"Generic error calling document processing service for Task ID: {task_id}: {e}", exc_info=True)


# Note: download_gmail_attachment function was previously in this file for testing/example.
# The official one is now in tools_wrapper.py (download_attachment).
# Removing the local version to avoid confusion.
# async def download_gmail_attachment(...): ... (Removed)
