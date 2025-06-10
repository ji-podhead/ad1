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
from ..db_utils import (
    insert_document_db, insert_new_email_db, log_generic_action_db,
    fetch_active_workflows_db, find_existing_email_db,
    delete_email_and_audit_for_duplicate_db, create_processing_task_db,
    update_email_document_ids_db
)
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

                # The 'async with db_pool.acquire() as connection:' block might be removable
                # if all DB operations within the loop are covered by db_utils functions.
                # For now, we'll keep it and pass db_pool to db_utils functions.
                # If db_utils functions manage their own connections/transactions,
                # this explicit connection acquisition might become redundant.

                # async with db_pool.acquire() as connection: # Keep for now, or remove if all ops use db_pool
                logger.info("[Scheduler] DB Pool available for email processing.")
                logger.info(f"Found {len(processed_emails)} new emails to process.")
                for email_data in processed_emails:
                    logger.info(f"Processing email data keys: {email_data.keys()}") # Log keys for debugging
                    headers = email_data.get('headers', {}) # Get the headers dictionary
                    message_id = email_data.get('id') # This is the Gmail message ID
                    email_subject_str = headers.get('Subject', 'No Subject')
                    sender = headers.get('From', 'Unknown Sender')
                    email_body_str = email_data.get('body', '') # This is base64 encoded from get_email
                    
                    # Decode email_body_str if it's base64 encoded string
                    try:
                        if isinstance(email_body_str, str):
                            email_body_str = base64.b64decode(email_body_str + '==').decode('utf-8')
                    except Exception as e:
                        logger.warning(f"Could not decode email body for message ID {message_id}, assuming plain text or already decoded: {e}")


                    received_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                    logger.info(f"Processing email: Gmail ID={message_id}, Subject='{email_subject_str}', Sender='{sender}'")
                    inserted_email_id = None

                    try:
                        sender_email_match = re.search(r'<(.+?)>', sender)
                        if sender_email_match:
                            sender_email = sender_email_match.group(1)
                        elif isinstance(sender, str) and '@' in sender: # Basic check if sender string might be an email
                            sender_email = sender
                        else:
                            sender_email = 'Unknown Sender'
                        logger.info(f"Extracted sender email: {sender_email}")

                        if not message_id: # Should be Gmail ID
                            logger.warning(f"Skipping email due to missing Gmail message ID: {email_data.get('subject', 'N/A')}")
                            continue

                        logger.info(f"Checking for existing email with Subject='{email_subject_str}', Sender='{sender_email}' using db_utils.find_existing_email_db")
                        existing_email_id = await find_existing_email_db(
                            db_pool=db_pool,
                            subject=email_subject_str,
                            sender=sender_email,
                            body=email_body_str # Use decoded body for comparison
                        )

                        if existing_email_id:
                            logger.info(f"Duplicate email found. Existing DB email ID: {existing_email_id}. Deleting using db_utils.delete_email_and_audit_for_duplicate_db.")
                            await delete_email_and_audit_for_duplicate_db(
                                db_pool=db_pool,
                                email_id=existing_email_id,
                                original_subject=email_subject_str
                            )

                        logger.info(f"New email detected: Subject='{email_subject_str}', Sender='{sender_email}'. Proceeding with summary and processing.")

                        llm_model_to_use = "gemini-1.5-flash"
                        possible_types = ["Google", "Important", "Health", "Marketing", "Spam", "Other"]
                        attachments_info_for_llm = email_data.get('attachments_for_llm', [])
                        logger.info(f"Calling get_summary_and_type_from_llm for Gmail ID: {message_id} with attachments: {attachments_info_for_llm}")

                        llm_summary_data = await get_summary_and_type_from_llm(
                            email_subject=email_subject_str,
                            email_body=email_body_str, # Use decoded body
                            llm_model_name=llm_model_to_use,
                            possible_types=possible_types,
                            attachments_info=attachments_info_for_llm
                        )
                        topic = llm_summary_data.get("document_type", "Default/LLMError")
                        short_description = llm_summary_data.get("short_description", "Summary N/A (LLMError)")
                        logger.info(f"LLM summary for Gmail ID {message_id}: topic={topic}, desc={short_description}")

                        # Insert email using db_utils.insert_new_email_db
                        logger.info(f"Inserting email (Gmail ID {message_id}) into database using db_utils.insert_new_email_db.")
                        inserted_email_id = await insert_new_email_db(
                            db_pool=db_pool, # Use db_pool
                            subject=email_subject_str,
                            sender=sender_email,
                            body=email_body_str, # This should be the decoded body
                            received_at=received_at,
                            label=None,  # Default label
                            email_type=topic,
                            short_description=short_description,
                            document_ids=[] # Initialize with empty list, will be updated after attachments are processed
                        )
                        logger.info(f"Inserted new email with DB ID: {inserted_email_id}, Topic: {topic}")

                        # Log email insertion to audit trail using db_utils.log_generic_action_db
                        await log_generic_action_db(
                            db_pool=db_pool, # Use db_pool
                            action_description=f"New email received. Subject: '{email_subject_str}'. Assigned DB ID: {inserted_email_id}",
                            username="system_email_processing",
                            email_id=inserted_email_id
                        )

                        # --- 2. WORKFLOW MATCHING & EXECUTION ---
                        logger.info(f"Fetching active workflows for email DB ID {inserted_email_id} using db_utils.fetch_active_workflows_db.")
                        # Fetch active workflows using the centralized function
                        # The original SQL used trigger_type = 'cron'
                        workflow_rows = await fetch_active_workflows_db(
                            db_pool=db_pool, # Use db_pool
                            trigger_type='cron' 
                        )
                        # fetch_active_workflows_db returns a list of dicts, so no need to convert wf_row
                        logger.info(f"Found {len(workflow_rows)} active 'cron' triggered workflows.")
                        for wf_row in workflow_rows: # wf_row is already a dict
                            
                            wf_config = wf_row.get('workflow_config', {})
                            selected_topic = wf_config.get('selected_topic')
                            
                            if selected_topic and selected_topic != topic:
                                logger.info(f"Skipping workflow '{wf_row['workflow_name']}' for email DB ID {inserted_email_id} due to topic mismatch (required: {selected_topic}, email topic: {topic}).")
                                continue

                            logger.info(f"Executing workflow '{wf_row['workflow_name']}' for topic '{topic}' on email DB ID {inserted_email_id}")
                            
                            task_id = await create_processing_task_db(
                                db_pool=db_pool,
                                email_id=inserted_email_id,
                                initial_status=wf_config.get('initial_status', 'pending'),
                                workflow_type=wf_row['workflow_name'] # Using workflow_name as workflow_type for task
                            )
                            await log_generic_action_db(
                                db_pool=db_pool,
                                action_description=f"Task created for workflow '{wf_row['workflow_name']}' (Task ID: {task_id}) for topic '{topic}'",
                                username="system_workflow_init",
                                email_id=inserted_email_id,
                                task_id=task_id
                            )

                            if wf_config and "document_processing" in wf_config.get("steps", []):
                                logger.info(f"Initiating document processing step for task {task_id}, email DB ID {inserted_email_id}.")
                                await process_document_step(
                                    task_id=task_id,
                                    email_id=inserted_email_id,
                                    # process_document_step might need db_pool instead of a connection
                                    # For now, assuming it can handle db_pool or has been updated.
                                    # If it strictly needs a connection, this part needs care.
                                    db_conn_for_audit=db_pool, # Assuming process_document_step can use db_pool for audit
                                    workflow_config=wf_config
                                )
                            else:
                                logger.info(f"No document_processing step in workflow for task {task_id}.")

                        logger.info(f"Processing attachments for email DB ID {inserted_email_id}.")
                        document_ids_for_update = []
                        attachments_to_save = email_data.get('attachments_data_for_db', [])
                        logger.info(f"Found {len(attachments_to_save)} attachments to save for email DB ID {inserted_email_id}.")
                        
                        for att_data in attachments_to_save:
                            try:
                                logger.info(f"Inserting attachment '{att_data.get('filename', 'unnamed')}' for email DB ID {inserted_email_id} using db_utils.insert_document_db.")
                                doc_id = await insert_document_db(
                                    db_pool=db_pool,
                                    email_id=inserted_email_id,
                                    filename=att_data.get('filename', 'unnamed_attachment'),
                                    content_type=att_data.get('mimeType', 'application/octet-stream'),
                                    data_b64=att_data.get('data_b64'),
                                    created_at_dt=received_at,
                                    processed_data=None
                                )
                                if doc_id: # insert_document_db returns the ID
                                    document_ids_for_update.append(doc_id)
                                    logger.info(f"Inserted document ID {doc_id} for email {inserted_email_id} (attachment: {att_data.get('filename')})")
                                else:
                                    logger.error(f"Failed to insert document for attachment: {att_data.get('filename')}, no doc_id returned.")
                            except Exception as e:
                                logger.error(f"Failed to insert document for email {inserted_email_id} (attachment: {att_data.get('filename')}): {e}")

                        if document_ids_for_update:
                            logger.info(f"Updating email {inserted_email_id} with document_ids: {document_ids_for_update} using db_utils.update_email_document_ids_db")
                            await update_email_document_ids_db(
                                db_pool=db_pool,
                                email_id=inserted_email_id,
                                document_ids=document_ids_for_update
                            )
                            logger.info(f"Updated email {inserted_email_id} with document_ids: {document_ids_for_update}")
                        
                        logger.info(f"Finished processing email with Gmail ID {message_id}, DB ID {inserted_email_id}.")

                    except Exception as e:
                        logger.error(f"Error processing email (Subject: '{email_subject_str}', Sender: '{sender_email}', Gmail ID: {message_id}): {e}", exc_info=True)
                        action_desc_error = f"Error processing email. Subject: '{email_subject_str}', Gmail ID: {message_id}. Error: {str(e)}"
                        error_email_id_ref = inserted_email_id # Will be None if insertion failed

                        await log_generic_action_db(
                            db_pool=db_pool,
                            action_description=action_desc_error,
                            username="system_email_processing_error",
                            email_id=error_email_id_ref
                        )
                        continue
    except Exception as e:
        logger.error(f"[Scheduler] Error during email check: {e}")
    finally:
        if 'session' in locals() and session:
            logger.info("[Scheduler] Closing MCP session.")
