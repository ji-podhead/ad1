
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
logger.setLevel(logging.INFO)  # <--- explizit setzen!


async def check_new_emails(db_pool: asyncpg.pool.Pool, interval_seconds: int = 60):
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
      