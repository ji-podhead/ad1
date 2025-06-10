"""Utility functions for document processing related tasks.

This module provides functionalities to interact with external document
processing services, handle document data, and log relevant audit trails
during the document processing steps within a workflow.
"""
import asyncio
from typing import Callable, Any, Dict, Optional, List
import datetime
import json
import os
import asyncpg # Assuming asyncpg is used for database connection
import logging # Added for explicit logging
import base64
import aiohttp
async def process_document_step(
    task_id: int,
    email_id: int,
    db_conn_for_audit: Any,
    workflow_config: Dict[str, Any]
):
    """Processes a document associated with an email task via an external microservice.

    This function simulates fetching a PDF document (currently uses a dummy PDF for email_id 1),
    then sends this document to a configured document processing microservice.
    It logs audit trails at various stages of the process using the provided
    database connection.

    Args:
        task_id (int): The ID of the current task.
        email_id (int): The ID of the email associated with this task/document.
        db_conn_for_audit (Any): An active database connection (e.g., from asyncpg.pool.Pool)
            to be used for inserting audit trail records.
        workflow_config (Dict[str, Any]): The configuration for the current workflow,
            though it's not directly used in this function's current placeholder logic
            for PDF fetching beyond logging.

    Note:
        The PDF fetching logic is currently a placeholder. For `email_id == 1`, it uses
        a dummy base64 encoded PDF. For other `email_id`s, it logs that no PDF
        fetching logic is implemented and skips processing.
        The document processing service URL is read from the environment variable
        `DOC_PROCESSING_SERVICE_URL`.
    """
    pdf_bytes: Optional[bytes] = None
    email_subject_for_filename = f"Email_ID_{email_id}_Task_{task_id}" # Used for naming the file sent to service
    logger = logging.getLogger(__name__) # Local logger instance

    async def _log_audit(action: str, username: str = "system_workflow_step", current_email_id: Optional[int] = email_id):
        """Helper to log audit messages."""
        try:
            await db_conn_for_audit.execute(
                "INSERT INTO audit_trail (email_id, action, username, timestamp) VALUES ($1, $2, $3, NOW())",
                current_email_id, action, username
            )
        except Exception as log_e:
            logger.error(f"Audit log failure for action '{action}': {log_e}")

    await _log_audit(f"Attempting document processing for Task ID: {task_id}")

    try:
        # Placeholder PDF fetching logic
        if email_id == 1:
            dummy_pdf_b64 = "JVBERi0xLjQKJVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            pdf_bytes = base64.b64decode(dummy_pdf_b64)
            logger.info(f"Using dummy PDF for email_id {email_id}, Task {task_id}.")
            await _log_audit(f"Using dummy PDF for Task ID: {task_id}.")
        else:
            logger.warning(f"No actual PDF fetching logic for email_id {email_id}, Task {task_id}. Skipping document processing unless email_id is 1.")
            await _log_audit(f"Document processing skipped for Task ID: {task_id} - No PDF found (placeholder logic).")
            return

        if not pdf_bytes: # Should only be reached if email_id is not 1 and logic changes
            logger.error(f"PDF bytes are None for Task {task_id}, Email {email_id} after fetching logic. This shouldn't happen.")
            await _log_audit(f"PDF content missing unexpectedly for Task ID: {task_id}.")
            return

    except Exception as e:
        logger.error(f"Error obtaining/generating PDF for Task {task_id}, Email {email_id}: {e}", exc_info=True)
        await _log_audit(f"Error obtaining PDF for Task ID: {task_id}. Error: {str(e)}")
        return

    doc_service_url = os.getenv("DOC_PROCESSING_SERVICE_URL") # Default can be set in getenv too
    if not doc_service_url:
        logger.error(f"DOC_PROCESSING_SERVICE_URL environment variable is not set. Cannot process document for Task {task_id}.")
        await _log_audit(f"DOC_PROCESSING_SERVICE_URL not set. Document processing skipped for Task ID: {task_id}.", username="system_config_error")
        return

    try:
        async with aiohttp.ClientSession() as session:
            form_data = aiohttp.FormData()
            form_data.add_field(
                'file',
                pdf_bytes,
                filename=f'{email_subject_for_filename}.pdf',
                content_type='application/pdf'
            )

            logger.info(f"Calling Document Processing Service for Task ID: {task_id} (Email ID: {email_id}) at URL: {doc_service_url}")

            async with session.post(doc_service_url, data=form_data, timeout=300) as response:
                response_text = await response.text()
                try:
                    # Attempt to parse as JSON, but store raw if it fails
                    response_data = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.warning(f"Response from document service for Task {task_id} was not valid JSON. Raw response: {response_text[:200]}...") # Log snippet
                    response_data = {"raw_response": response_text}

                if response.status == 200:
                    logger.info(f"Document processing successful for Task ID: {task_id}. Response: {response_data}")
                    await _log_audit(f"Document processing successful for Task ID: {task_id}. Results: {json.dumps(response_data)[:1500]}")
                else:
                    logger.error(f"Document processing failed for Task ID: {task_id}. Status: {response.status}, Response: {response_text}")
                    await _log_audit(f"Document processing failed for Task ID: {task_id}. Status: {response.status}, Details: {response_text[:1500]}")

    except aiohttp.ClientConnectorError as e:
        logger.error(f"Connection error calling document processing service for Task ID {task_id} at {doc_service_url}: {e}", exc_info=True)
        await _log_audit(f"Connection error for document processing (Task ID: {task_id}): {str(e)}", username="system_network_error")
    except asyncio.TimeoutError:
        logger.error(f"Timeout calling document processing service for Task ID {task_id} at {doc_service_url}", exc_info=True)
        await _log_audit(f"Timeout during document processing (Task ID: {task_id})", username="system_timeout_error")
    except Exception as e:
        logger.error(f"Generic error during document processing service call for Task ID {task_id}: {e}", exc_info=True)
        await _log_audit(f"Error in document processing step (Task ID: {task_id}): {str(e)}", username="system_workflow_error")
