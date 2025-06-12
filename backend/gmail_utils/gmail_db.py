from gmail_utils.gmail_fetch import get_full_email,parse_mcp_email_list # Import Gmail utils for email fetching and OAuth
from document_utils.document_utils import process_document_step # Import document processing step function
from gmail_utils.gmail_auth import fetch_access_token_for_user
from agent.summary_agent import get_summary_and_type_from_llm
from db_utils import (
    insert_document_db, insert_new_email_db, log_generic_action_db,
    fetch_active_workflows_db, find_existing_email_db,
    delete_email_and_audit_for_duplicate_db, create_processing_task_db,
    update_email_document_ids_db,log_email_action_db
)
import asyncio
from typing import Callable, Any, Dict, Optional, List # Ensure Optional is imported
import datetime
import json
import os
import re
import asyncpg # Assuming asyncpg is used for database connection
import logging # Ensure logging is imported
import base64 # For dummy PDF
logger = logging.getLogger(__name__) # Ensure logger is defined
logger.setLevel(logging.INFO)

async def del_if_exists(
    db_pool: asyncpg.pool.Pool,
    message_id: str,        # Gmail message ID
    sender: str,            # Raw 'From' header value
    email_subject_str: str,
    email_body_str: str
    
) -> Optional[str]:      # Changed return type hint to Optional[str]
    """
    Checks if an email already exists. If it's a duplicate, it's deleted.
    Returns the sender's email address if it's a new email, otherwise None.
    """
    sender_email_match = re.search(r'<(.+?)>', sender)
    if sender_email_match:
        sender_email = sender_email_match.group(1)
    elif isinstance(sender, str) and '@' in sender:
        sender_email = sender
    else:
        sender_email = 'Unknown Sender'
    logger.info(f"Extracted sender email: {sender_email} from raw sender: '{sender}'")

    if not message_id: # Should be Gmail ID
        # In your original code, this used email_data.get('subject', 'N/A') which is not available here.
        # Using email_subject_str instead for the log.
        logger.warning(f"Skipping email due to missing Gmail message ID: Subject='{email_subject_str}'")
        return None # Cannot process without a message_id, effectively skipping

    logger.info(f"Checking for existing email with Subject='{email_subject_str}', Sender='{sender_email}' using db_utils.find_existing_email_db")
    existing_email_id = await find_existing_email_db(
        db_pool=db_pool,
        subject=email_subject_str,
        sender=sender_email,
        body=email_body_str # Use decoded body for comparison
    )

    if existing_email_id:
        logger.info(f"Duplicate email found. Existing DB email ID: {existing_email_id}. Subject='{email_subject_str}'. Deleting using db_utils.delete_email_and_audit_for_duplicate_db.")
        try:
            await delete_email_and_audit_for_duplicate_db(
                db_pool=db_pool,
                email_id=existing_email_id,
                original_subject=email_subject_str
            )
            logger.info(f"Successfully deleted duplicate email (DB ID: {existing_email_id}, Subject: '{email_subject_str}'). Skipping further processing for this email.")
            return None # Signal that this email was a duplicate and has been handled
        except Exception as e:
            logger.error(f"Error deleting duplicate email (DB ID: {existing_email_id}, Subject: '{email_subject_str}'): {e}", exc_info=True)
            # If deletion fails, we might still want to skip processing it as a new email, 
            # or handle it differently. For now, returning None to skip.
            return None 
    else:
        logger.info(f"New email detected: Subject='{email_subject_str}', Sender='{sender_email}'. Proceeding with summary and processing.")
        return sender_email # It's a new email, return sender_email for processing
async def store_email_in_db(
    db_pool: asyncpg.pool.Pool,
    email_data: Dict[str, Any],
    topic: str,
    short_description: str,
    received_at: datetime.datetime,
    email_subject_str: str,
    email_body_str: str,
    sender_email: str,
    message_id: str
) -> Optional[int]: # Return type was None, changed to Optional[int] to match potential return of inserted_email_id
    print("--- DEBUG: store_email_in_db WURDE AUFGERUFEN ---") # DIAGNOSTIC PRINT
    logger.info("--- LOGGER DEBUG: store_email_in_db WURDE AUFGERUFEN ---") # DIAGNOSTIC LOGGER
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

    await log_email_action_db(
            db_pool,
            email_id=inserted_email_id,
            action=f"New email received. Subject: '{email_subject_str}'. Assigned DB ID: {inserted_email_id}",
            user="system_processing",
            data={"insert": f"Subject: '{email_subject_str}'", "message_id": message_id},
        )
    logger.info(f"Logged email insertion action for email ID {email_data.keys()} with message ID {message_id}.")
    attachments_to_save = email_data.get('attachments', [])
    if attachments_to_save:
        document_ids_for_update = []
        for att_data in attachments_to_save:
            try:
                logger.info(f"Inserting attachment '{att_data}' for email DB ID {inserted_email_id} using db_utils.insert_document_db.")
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
    return inserted_email_id # Return the ID
