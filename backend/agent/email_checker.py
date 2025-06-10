
"""Module for periodically checking and processing new emails.

This module defines the `check_new_emails` function, which is designed to be run
as a scheduled task (e.g., by AgentScheduler). It fetches new emails using
MCP (Mail Control Protocol) tools, processes them using an LLM for summarization
and topic classification, stores them in the database, and triggers relevant
workflows based on the email's topic. It also handles email attachments.
"""
import asyncio
from typing import Callable, Any, Dict, Optional, List
import datetime
import json
import os
import re
import asyncpg # Assuming asyncpg is used for database connection
import logging # Added for explicit logging
import base64 # For dummy PDF
from gmail_utils.gmail_fetch import get_email,parse_mcp_email_list # Import Gmail utils for email fetching and OAuth
from document_utils.document_utils import process_document_step # Import document processing step function
from gmail_utils.gmail_auth import fetch_access_token_for_user
from agent.summary_agent import get_summary_and_type_from_llm
from litellm import experimental_mcp_client
from mcp.client.sse import sse_client
from mcp import ClientSession
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def check_new_emails(db_pool: asyncpg.pool.Pool, interval_seconds: int = 60*60*24): # Default to 24 hours
    """Periodically checks for new emails and processes them.

    This function connects to an MCP server to list new emails received since the
    last check. For each new email, it:
    1. Fetches the full email content.
    2. Uses an LLM (Gemini) to get a summary and classify its topic.
    3. Stores the email and its summary/topic in the database.
    4. If attachments are present, they are downloaded and stored.
    5. Matches the email's topic against active workflows.
    6. For each matching workflow, creates a new task in the database and
       initiates processing steps (e.g., document processing if defined in the workflow).

    Args:
        db_pool (asyncpg.pool.Pool): The database connection pool.
        interval_seconds (int, optional): The time window in seconds to look back for
            new emails. Defaults to 86400 (24 hours). This determines the 'after'
            timestamp for the email search query.
    """
    logger.info(f"[EmailChecker] Starting new email check. Looking back {interval_seconds} seconds.")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Should be loaded once at module/app start
    MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp-server/sse/") # Should be loaded once
    session = None # Ensure session is defined for finally block
    try:
        async with sse_client(MCP_SERVER_URL) as streams:
            async with ClientSession(*streams) as session:
                logger.info("[EmailChecker] MCP session established.")
                await session.initialize()
                logger.info("[EmailChecker] Getting MCP tools.")
                # TODO: User email should be dynamic, not hardcoded.
                oauth_token = await fetch_access_token_for_user(db_pool, "leo@orchestra-nexus.com")
                if not oauth_token:
                    logger.error("[EmailChecker] Failed to obtain OAuth token. Cannot proceed with email check.")
                    return
                logger.info("[EmailChecker] OAuth token for user obtained.")

                mcp_tools = await experimental_mcp_client.load_mcp_tools(session=session, format="mcp")
                if not mcp_tools:
                    logger.warning("[EmailChecker] No MCP tools available.")
                    return

                search_emails_tool = None
                logger.info("[EmailChecker] Loaded MCP tools:")
                for tool in mcp_tools:
                    logger.info(f" - {tool.name}") # Log available tools
                    if hasattr(tool, 'name') and tool.name == 'search_emails':
                        search_emails_tool = tool
                        break

                if not search_emails_tool:
                    logger.warning("[EmailChecker] No 'search_emails' tool found in MCP tools.")
                    return

                now_utc = datetime.datetime.now(datetime.timezone.utc)
                # The interval_seconds defines how far back from 'now' we look.
                # So, 'after' is now - interval, and 'before' is now.
                after_dt = now_utc - datetime.timedelta(seconds=interval_seconds)
                after_ts = int(after_dt.timestamp())
                before_ts = int(now_utc.timestamp())

                gmail_query = f"after:{after_ts} before:{before_ts}"
                logger.info(f"[EmailChecker] Using Gmail query: '{gmail_query}' with search_emails tool.")

                result = await session.call_tool(search_emails_tool.name, arguments={"query": gmail_query})

                raw_content = result.content[0].text if result and result.content and result.content[0] and hasattr(result.content[0], 'text') else None
                if not raw_content or not raw_content.strip():
                    logger.info("[EmailChecker] MCP tool 'search_emails' returned no new emails or an empty response.")
                    return

                logger.debug(f"[EmailChecker] Raw MCP 'search_emails' response: {raw_content!r}")

                # Assuming parse_mcp_email_list returns a list of dicts with at least 'id'
                email_headers_list = parse_mcp_email_list(raw_content)
                if not email_headers_list:
                    logger.info("[EmailChecker] No new emails found after parsing MCP response.")
                    return

                logger.info(f"[EmailChecker] Found {len(email_headers_list)} new email headers from search.")

                async def read_full_email_content(email_header_info: dict) -> Optional[dict]:
                    """Fetches full email content using its ID.

                    Args:
                        email_header_info (dict): A dictionary containing email header info,
                                                  must include an 'id' key for the message ID.

                    Returns:
                        Optional[dict]: The full email data as a dictionary if successful,
                                        None otherwise.
                    """
                    message_id = email_header_info.get('id')
                    if not message_id:
                        logger.warning(f"[EmailChecker] Email header info missing 'id': {email_header_info}")
                        return None
                    try:
                        # TODO: User email for get_email should be dynamic.
                        full_email_data = await get_email(db_pool, "leo@orchestra-nexus.com", message_id, oauth_token)
                        logger.info(f"[EmailChecker] Successfully fetched full content for email ID: {message_id} - Subject: {full_email_data.get('subject', 'N/A')}")
                        return full_email_data
                    except Exception as e:
                        logger.error(f"[EmailChecker] Error reading full content for email ID {message_id}: {e}", exc_info=True)
                        return None

                # Fetch full content for all found email headers
                full_email_tasks = [read_full_email_content(header) for header in email_headers_list]
                processed_emails_results = await asyncio.gather(*full_email_tasks)

                # Filter out None results (emails that failed to fetch)
                valid_processed_emails = [email for email in processed_emails_results if email is not None]

                if not valid_processed_emails:
                    logger.info("[EmailChecker] No emails could be fully processed after fetching content.")
                    return

                async with db_pool.acquire() as connection:
                    logger.info(f"[EmailChecker] Acquired DB connection. Processing {len(valid_processed_emails)} fully fetched emails.")
                    logger.info(f"[EmailChecker] Found {len(valid_processed_emails)} new emails to process after fetching full content.")
                    for email_data in valid_processed_emails:
                        if not isinstance(email_data, dict): # Defensive check
                            logger.warning(f"[EmailChecker] Expected email_data to be a dict, got {type(email_data)}. Skipping.")
                            continue

                        headers = email_data.get('headers', {})
                        message_id = email_data.get('id') # This is the Gmail message ID
                        email_subject_str = headers.get('Subject', 'No Subject')
                        sender_header = headers.get('From', 'Unknown Sender')
                        email_body_str = email_data.get('body', '')

                        # Use 'internalDate' from email_data if available and parse it, otherwise fallback to now_utc
                        # Gmail 'internalDate' is Unix millisecond timestamp as string.
                        received_at_str = headers.get('Date') # Prefer Date header if available
                        if email_data.get('internalDate'):
                             try:
                                received_at_ts = int(email_data['internalDate']) / 1000
                                received_at = datetime.datetime.fromtimestamp(received_at_ts, datetime.timezone.utc)
                             except (ValueError, TypeError):
                                logger.warning(f"Could not parse internalDate '{email_data['internalDate']}'. Falling back for email ID {message_id}.")
                                received_at = now_utc # Fallback
                        elif received_at_str:
                            try:
                                # Attempt to parse Date header (can be complex due to formats)
                                # This is a simplified parse, mail.utils.parsedate_to_datetime is better
                                from email.utils import parsedate_to_datetime
                                received_at = parsedate_to_datetime(received_at_str)
                                if received_at.tzinfo is None: # Ensure timezone aware
                                    received_at = received_at.replace(tzinfo=datetime.timezone.utc)
                            except Exception:
                                logger.warning(f"Could not parse Date header '{received_at_str}'. Falling back for email ID {message_id}.")
                                received_at = now_utc # Fallback
                        else:
                            received_at = now_utc # Fallback if no date info found

                        received_at = received_at.replace(tzinfo=None) # Convert to naive UTC for DB

                        logger.info(f"[EmailChecker] Processing email: ID={message_id}, Subject='{email_subject_str}', From='{sender_header}', Received='{received_at}'")
                        inserted_email_id = None

                        try:
                            sender_email_match = re.search(r'<(.+?)>', sender_header)
                            sender_email = sender_email_match.group(1) if sender_email_match else sender_header

                            if not message_id: # Should not happen if emails are from valid_processed_emails
                                logger.warning(f"[EmailChecker] Skipping email due to missing message ID: {email_data.get('subject', 'N/A')}")
                                continue

                            # Duplicate check based on message_id (Gmail ID) should be more robust
                            # If your DB `emails` table has a column for gmail_message_id:
                            # existing_email_by_gmail_id = await connection.fetchrow("SELECT id FROM emails WHERE gmail_message_id = $1", message_id)
                            # For now, using subject/sender/body as in original code, but this is less reliable for true duplicates.
                            existing_email = await connection.fetchrow(
                                "SELECT id FROM emails WHERE subject = $1 AND sender = $2 AND body = $3", # Consider adding received_at to duplicate check
                                email_subject_str, sender_email, email_body_str
                            )
                            if existing_email:
                                existing_email_id_val = existing_email['id']
                                logger.info(f"[EmailChecker] Duplicate email content detected (Subject/Sender/Body match). Deleting existing email ID: {existing_email_id_val} and related audit entries before re-inserting.")
                                await connection.execute("DELETE FROM audit_trail WHERE email_id = $1", existing_email_id_val)
                                await connection.execute("DELETE FROM emails WHERE id = $1", existing_email_id_val)
                                await connection.execute(
                                    "INSERT INTO audit_trail (action, username, timestamp) VALUES ($1, $2, NOW())",
                                    f"Duplicate email content. Deleted existing DB email ID: {existing_email_id_val}. Subject: '{email_subject_str}'", "system_email_processing"
                                )

                            logger.info(f"[EmailChecker] New email for LLM processing: Subject='{email_subject_str}', Sender='{sender_email}'.")
                            llm_model_to_use = "gemini-1.5-flash" # Or from config
                            possible_types = ["Invoice", "Support Request", "Quotation", "Marketing", "Personal", "Spam", "Other"] # Example

                            attachments_info_for_llm = [{'filename': att.get('filename', 'unnamed'), 'mimeType': att.get('mimeType', 'application/octet-stream')} for att in email_data.get('attachments', [])]

                            llm_summary_data = await get_summary_and_type_from_llm(
                                email_subject=email_subject_str, email_body=email_body_str,
                                llm_model_name=llm_model_to_use, possible_types=possible_types,
                                attachments_info=attachments_info_for_llm
                            )
                            topic = llm_summary_data.get("document_type", "Other") # Default if LLM fails
                            short_description = llm_summary_data.get("short_description", "Summary not available.")
                            logger.info(f"[EmailChecker] LLM summary for email ID {message_id}: Topic='{topic}', Description='{short_description}'")

                            inserted_email_id = await connection.fetchval(
                                """INSERT INTO emails (subject, sender, body, received_at, label, type, short_description, gmail_message_id)
                                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
                                email_subject_str, sender_email, email_body_str, received_at,
                                None, topic, short_description, message_id # Storing Gmail message_id
                            )
                            logger.info(f"[EmailChecker] Inserted new email into DB with ID: {inserted_email_id}, Gmail ID: {message_id}, Topic: {topic}")
                            await connection.execute(
                                "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                                inserted_email_id, f"New email received. Subject: '{email_subject_str}'. DB ID: {inserted_email_id}", "system_email_processing"
                            )

                            # Attachment handling
                            downloaded_attachments = email_data.get('attachments', [])
                            document_db_ids = []
                            if downloaded_attachments:
                                logger.info(f"[EmailChecker] Processing {len(downloaded_attachments)} attachments for email DB ID {inserted_email_id}.")
                                for att_data in downloaded_attachments:
                                    try:
                                        data_b64 = base64.b64encode(att_data['data']).decode('utf-8')
                                        doc_db_id = await connection.fetchval(
                                            """INSERT INTO documents (email_id, filename, content_type, data_b64, is_processed, created_at)
                                               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                                            inserted_email_id, att_data.get('filename', 'unnamed'),
                                            att_data.get('mimeType', 'application/octet-stream'),
                                            data_b64, False, received_at
                                        )
                                        document_db_ids.append(doc_db_id)
                                        logger.info(f"[EmailChecker] Inserted document DB ID {doc_db_id} for email DB ID {inserted_email_id} (Attachment: {att_data.get('filename')})")
                                    except Exception as e_att:
                                        logger.error(f"[EmailChecker] Failed to insert document for email DB ID {inserted_email_id} (Attachment: {att_data.get('filename')}): {e_att}", exc_info=True)
                                if document_db_ids:
                                    await connection.execute("UPDATE emails SET document_ids = $1 WHERE id = $2", document_db_ids, inserted_email_id)
                                    logger.info(f"[EmailChecker] Updated email DB ID {inserted_email_id} with document DB IDs: {document_db_ids}")

                            # Workflow matching and execution
                            workflow_rows = await connection.fetch("SELECT id, workflow_name, workflow_config FROM scheduler_tasks WHERE status = 'active' AND trigger_type = 'cron'") # Assuming 'cron' also means email_receive for now
                            logger.info(f"[EmailChecker] Found {len(workflow_rows)} active workflows to check for topic match for email DB ID {inserted_email_id}.")
                            for wf_row in workflow_rows:
                                wf_config_str = wf_row['workflow_config']
                                wf_config = json.loads(wf_config_str) if isinstance(wf_config_str, str) else wf_config_str or {}

                                selected_topic = wf_config.get('selected_topic')
                                if selected_topic and selected_topic.lower() != topic.lower(): # Case-insensitive topic match
                                    logger.debug(f"Skipping workflow '{wf_row['workflow_name']}' for email DB ID {inserted_email_id}: Topic mismatch (Workflow: '{selected_topic}', Email: '{topic}').")
                                    continue

                                logger.info(f"[EmailChecker] Executing workflow '{wf_row['workflow_name']}' for topic '{topic}' on email DB ID {inserted_email_id}")
                                task_db_id = await connection.fetchval(
                                    """INSERT INTO tasks (email_id, status, created_at, updated_at, workflow_type)
                                       VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                                    inserted_email_id, wf_config.get('initial_status', 'pending'),
                                    received_at, received_at, topic # or wf_row['workflow_name'] as workflow_type
                                )
                                await connection.execute(
                                    "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                                    inserted_email_id, f"Task created (ID: {task_db_id}) for workflow '{wf_row['workflow_name']}' due to topic '{topic}'.", "system_workflow_init"
                                )

                                if "document_processing" in wf_config.get("steps", []):
                                    logger.info(f"[EmailChecker] Initiating document processing step for task DB ID {task_db_id}, email DB ID {inserted_email_id}.")
                                    await process_document_step(task_id=task_db_id, email_id=inserted_email_id, db_conn_for_audit=connection, workflow_config=wf_config)
                                else:
                                    logger.debug(f"No 'document_processing' step in workflow '{wf_row['workflow_name']}' for task DB ID {task_db_id}.")

                            logger.info(f"[EmailChecker] Finished processing for email with Gmail ID {message_id}, DB ID {inserted_email_id}.")

                        except Exception as e_single_email:
                            logger.error(f"[EmailChecker] Error processing single email (Gmail ID: {message_id}, Subject: '{email_subject_str}'): {e_single_email}", exc_info=True)
                            log_action = f"Error processing email (Gmail ID: {message_id}, Subject: '{email_subject_str}'). Error: {str(e_single_email)}"
                            log_email_id = inserted_email_id # Log with DB ID if available
                            try:
                                await connection.execute(
                                    "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                                    log_email_id, log_action, "system_email_processing_error"
                                )
                            except Exception as log_e:
                                logger.error(f"Audit log failure for email processing error: {log_e}", exc_info=True)
                            continue # Move to the next email

    except ConnectionRefusedError:
        logger.error(f"[EmailChecker] MCP Server connection refused at {MCP_SERVER_URL}. Ensure MCP server is running.")
    except aiohttp.ClientConnectorError as e:
        logger.error(f"[EmailChecker] MCP Server connection error for {MCP_SERVER_URL}: {e}")
    except Exception as e_outer:
        logger.error(f"[EmailChecker] Error during email check cycle: {e_outer}", exc_info=True)
    finally:
        if session: # Check if session was successfully created
            logger.info("[EmailChecker] Closing MCP session.")
            # Add session.close() or similar if available/needed, depends on ClientSession implementation
      