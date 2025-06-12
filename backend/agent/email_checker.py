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
from gmail_utils.gmail_fetch import get_full_email,parse_mcp_email_list,fetch_new_emails_with_mcp,read_emails_and_log # Import Gmail utils for email fetching and OAuth
from document_utils.document_utils import process_document_step # Import document processing step function
from agent.summary_agent import get_summary_and_type_from_llm
from db_utils import (
    insert_document_db, insert_new_email_db, log_generic_action_db,
    fetch_active_workflows_db, find_existing_email_db,
    delete_email_and_audit_for_duplicate_db, create_processing_task_db,
    update_email_document_ids_db,get_settings_db
)
from gmail_utils.gmail_db import store_email_in_db,del_if_exists
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
    try:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        after_dt = now_utc - datetime.timedelta(minutes=40)
        # Convert to Unix timestamps (seconds since epoch)
        after_ts = int(after_dt.timestamp())
        before_ts = int(now_utc.timestamp())
        # Build Gmail-style query string
        gmail_query = f"after:{after_ts} before:{before_ts}"
        logger.info(f"[Scheduler] Checking for new emails (with SSE/MCP)... Interval: {interval_seconds}s")
        try:
            emails=await fetch_new_emails_with_mcp(
                db_pool=db_pool,
                query=gmail_query,
                max_results=100,  # Adjust as needed
            )
            
            processed_emails = []
            for email in emails:
                results = await read_emails_and_log(db_pool=db_pool, email=email)
                
                if results is None:
                    results = []
                processed_emails.extend(results)
            logger.info(f"Found {(processed_emails)} new emails to process.")
        except Exception as e:
            logger.error(f"Error fetching new emails via mcp: {e}", exc_info=True)
            
#       --- PROCESS EACH EMAIL ---
        for email_data in processed_emails:
            # Initialize variables that might be used in logging or further down in the loop
            message_id = email_data.get('id')
            headers = email_data.get('headers', {})
            email_subject_str = headers.get('Subject', 'No Subject')
            raw_sender_header = headers.get('From', 'Unknown Sender') # Use a distinct name for the raw header
            email_body_str = email_data.get('body', '')
            received_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            
            logger.info(f"Processing email: Gmail ID={message_id}, Subject='{email_subject_str}', Raw Sender='{raw_sender_header}'")
            
            inserted_email_id = None
            parsed_sender_email = "<Error: Not Parsed>" # Default for logging in case of early failure

#           --- DECODE EMAIL BODY ---
            try:
                if isinstance(email_body_str, str):
                    email_body_str = base64.b64decode(email_body_str + '==').decode('utf-8')
            except Exception as e:
                logger.warning(f"Could not decode email body for message ID {message_id}, assuming plain text or already decoded: {e}")
            try:
#               --- CHECK FOR DUPLICATES ---                
                parsed_sender_email = await del_if_exists(
                    db_pool=db_pool,
                    message_id=message_id,
                    sender=raw_sender_header, # Pass the raw sender header here
                    email_subject_str=email_subject_str,
                    email_body_str=email_body_str
                )
                if parsed_sender_email is None:
                    logger.info(f"Email with Subject='{email_subject_str}' and Raw Sender='{raw_sender_header}' already exists or error in del_if_exists. Skipping further processing.")
                    continue
                # If we reach here, parsed_sender_email is the successfully parsed sender email for a new email

#               --- LLM PROCESSING ---                
                llm_model_to_use = "gemini-1.5-flash"
                settings=await get_settings_db(db_pool=db_pool)
                logger.info(f"Fetched------------------------------------------------------- settings for LLM model: {llm_model_to_use} with settings: {settings}")
                possible_types = ["none"]
                if settings and "email_types" in settings:
                    for email_type in settings["email_types"]:
                        possible_types.append(f"{email_type['topic']}")
                #settings.get("email_types", ["Google", "Important", "Health", "Marketing", "Spam", "Other"])
                attachments_info_for_llm = email_data.get('attachments', [])
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
#               --- STORE EMAIL IN DB ---
                inserted_email_id = await store_email_in_db(
                    db_pool=db_pool,
                    email_data=email_data,
                    topic=topic,
                    short_description=short_description, # Verwende die Beschreibung vom LLM
                    received_at=received_at,
                    email_subject_str=email_subject_str,
                    email_body_str=email_body_str,  # Use decoded body
                    sender_email=parsed_sender_email, # Pass the parsed sender email here
                    message_id=message_id
                )
#               --- WORKFLOW MATCHING & EXECUTION ---
                logger.info(f"Fetching active workflows for email DB ID {inserted_email_id} using db_utils.fetch_active_workflows_db.")
                workflow_rows = await fetch_active_workflows_db(
                    db_pool=db_pool, # Use db_pool
                )
                logger.info(f"Found {len(workflow_rows)} active 'cron' triggered workflows.")
                for wf_row in workflow_rows: # wf_row is already a dict
                    wf_config = wf_row.get('workflow_config', {})
                    selected_topic = wf_config.get('selected_topic')
                    if selected_topic and selected_topic != topic:
                        logger.info(f"Skipping workflow '{wf_row['task_name']}' for email DB ID {inserted_email_id} due to topic mismatch (required: {selected_topic}, email topic: {topic}).")
                        continue
                    logger.info(f"Executing workflow '{wf_row['task_name']}' for topic '{topic}' on email DB ID {inserted_email_id}")
                    task_id = await create_processing_task_db(
                        db_pool=db_pool,
                        email_id=inserted_email_id,
                        initial_status=wf_config.get('initial_status', 'pending'),
                        workflow_type=wf_row['task_name'] # Using task_name as workflow_type for task
                    )
                    if wf_config and "document_processing" in wf_config.get("steps", []):
                        logger.info(f"Initiating document processing step for task {task_id}, email DB ID {inserted_email_id}.")
                        await process_document_step(
                            task_id=task_id,
                            email_id=inserted_email_id,
                            db_conn_for_audit=db_pool, 
                            workflow_config=wf_config
                        )
                    else:
                        logger.info(f"No document_processing step in workflow for task {task_id}.")
                logger.info(f"Processing attachments for email DB ID {inserted_email_id}.")
            except Exception as e:
                # Use raw_sender_header for logging if parsed_sender_email might not be set due to an early error
                logger.error(f"Error processing email (Subject: '{email_subject_str}', Raw Sender: '{raw_sender_header}', Gmail ID: {message_id}): {e}", exc_info=True)
                # action_desc_error = f"Error processing email. Subject: '{email_subject_str}', Gmail ID: {message_id}. Error: {str(e)}" # This line seems to be for a different logging mechanism
                # error_email_id_ref = inserted_email_id # This will be None or an int if store_email_in_db was reached

                continue # Continue to the next email
    except Exception as e:
        logger.error(f"[Scheduler] Error during email check: {e}")
