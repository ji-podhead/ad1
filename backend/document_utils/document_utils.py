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
from db_utils import log_generic_action_db, get_document_content_db, update_document_processed_data_db # Import necessary db_utils

async def process_document_step(
    task_id: int,
    # email_id: int, # email_id might still be useful for context or logging, but document_id is primary
    document_id: int, # New parameter: ID of the document to process
    db_pool: asyncpg.pool.Pool, # Changed from db_conn_for_audit
    workflow_config: Dict[str, Any] # workflow_config might contain settings for the processing service
):
    """Processes a specific document via an external microservice and updates the DB.

    Fetches the document content from the database using its ID,
    sends this document to a configured document processing microservice,
    and then stores the processed result back into the document's record in the database.
    Audit trails are logged at various stages.

    Args:
        task_id (int): The ID of the current task.
        document_id (int): The ID of the document in the 'documents' table to process.
        db_pool (asyncpg.pool.Pool): The database connection pool.
        workflow_config (Dict[str, Any]): Configuration for the current workflow.
    """
    logger = logging.getLogger(__name__)
    pdf_bytes: Optional[bytes] = None
    filename_for_service = f"doc_{document_id}_task_{task_id}.pdf" # Default filename

    await log_generic_action_db(
        db_pool=db_pool,
        action_description=f"Attempting document processing for Document ID: {document_id}, Task ID: {task_id}",
        username="system_workflow_step",
        document_id=document_id,
        task_id=task_id
    )

    try:
        # 1. Fetch document content from DB
        logger.info(f"Fetching content for Document ID: {document_id}")
        doc_content_data = await get_document_content_db(db_pool, document_id)

        if not doc_content_data or not doc_content_data.get('data_b64'):
            logger.error(f"Document content (data_b64) not found for Document ID: {document_id}. Skipping processing.")
            await log_generic_action_db(
                db_pool=db_pool,
                action_description=f"Document content not found for Document ID: {document_id}. Processing skipped.",
                username="system_workflow_step",
                document_id=document_id,
                task_id=task_id
            )
            return

        pdf_bytes = base64.b64decode(doc_content_data['data_b64'])
        filename_for_service = doc_content_data.get('filename', filename_for_service) # Use actual filename if available
        logger.info(f"Successfully fetched and decoded Document ID: {document_id} for Task {task_id}.")

    except Exception as e:
        logger.error(f"Error fetching/decoding document ID {document_id} for Task {task_id}: {e}", exc_info=True)
        await log_generic_action_db(
            db_pool=db_pool,
            action_description=f"Error fetching/decoding document for Task ID: {task_id}, Doc ID: {document_id}. Error: {str(e)}",
            username="system_workflow_error",
            document_id=document_id,
            task_id=task_id
        )
        return

    doc_service_url = os.getenv("DOC_PROCESSING_SERVICE_URL")
    if not doc_service_url:
        logger.error(f"DOC_PROCESSING_SERVICE_URL environment variable is not set. Cannot process document for Task {task_id}, Doc ID {document_id}.")
        await log_generic_action_db(
            db_pool=db_pool,
            action_description=f"DOC_PROCESSING_SERVICE_URL not set. Document processing skipped for Task ID: {task_id}, Doc ID: {document_id}.",
            username="system_config_error",
            document_id=document_id,
            task_id=task_id
        )
        return

    processed_text_result: Optional[str] = None
    try:
        async with aiohttp.ClientSession() as session:
            form_data = aiohttp.FormData()
            form_data.add_field(
                'file',
                pdf_bytes,
                filename=filename_for_service, # Use fetched or generated filename
                content_type=doc_content_data.get('content_type', 'application/pdf') # Use fetched content_type
            )

            logger.info(f"Calling Document Processing Service for Task ID: {task_id}, Doc ID: {document_id} at URL: {doc_service_url}")
            await log_generic_action_db(db_pool, f"Calling external document processing for Doc ID: {document_id}", document_id=document_id, task_id=task_id)

            async with session.post(doc_service_url, data=form_data, timeout=300) as response:
                response_text = await response.text()
                response_status = response.status
            
            if response_status == 200:
                try:
                    response_json = json.loads(response_text)
                    # Assuming the service returns JSON with a key like 'processed_text' or 'text_content'
                    processed_text_result = response_json.get('processed_text') # Adjust key based on actual service response
                    if not processed_text_result: # Fallback if specific key not found but response is JSON
                         processed_text_result = response_json.get('text') # Common alternative
                    if not processed_text_result and isinstance(response_json, dict) : # Fallback to full JSON string if it's a dict
                         processed_text_result = json.dumps(response_json)


                    if processed_text_result:
                        logger.info(f"Document processing successful for Task ID: {task_id}, Doc ID: {document_id}. Result snippet: {processed_text_result[:200]}...")
                        await log_generic_action_db(db_pool, f"Document processing successful for Doc ID: {document_id}.", document_id=document_id, task_id=task_id)
                        
                        # 3. Store processed data
                        update_success = await update_document_processed_data_db(
                            db_pool=db_pool,
                            document_id=document_id,
                            processed_data_text=processed_text_result,
                            username="system_doc_processing"
                        )
                        if update_success:
                            logger.info(f"Successfully updated Doc ID {document_id} with processed data.")
                        else:
                            logger.error(f"Failed to update Doc ID {document_id} with processed data in DB.")
                            # Log this failure specifically
                            await log_generic_action_db(db_pool, f"Failed to store processed data for Doc ID: {document_id}", document_id=document_id, task_id=task_id, username="system_workflow_error")
                    else:
                        logger.warning(f"Document processing service returned 200 but no processable text found for Doc ID: {document_id}. Response: {response_text[:500]}")
                        await log_generic_action_db(db_pool, f"Document processing for Doc ID: {document_id} returned 200 but no text. Response: {response_text[:200]}", document_id=document_id, task_id=task_id)

                except json.JSONDecodeError:
                    logger.warning(f"Response from document service for Task {task_id}, Doc ID {document_id} was 200 but not valid JSON. Storing raw response. Raw: {response_text[:200]}...")
                    processed_text_result = response_text # Store raw text if not JSON
                    # Store raw text
                    update_success = await update_document_processed_data_db(
                            db_pool=db_pool,
                            document_id=document_id,
                            processed_data_text=processed_text_result,
                            username="system_doc_processing_raw"
                        )
                    if update_success:
                        logger.info(f"Successfully updated Doc ID {document_id} with raw processed data.")
                    else:
                        logger.error(f"Failed to update Doc ID {document_id} with raw processed data in DB.")

            else: # Non-200 response
                logger.error(f"Document processing failed for Task ID: {task_id}, Doc ID: {document_id}. Status: {response_status}, Response: {response_text}")
                await log_generic_action_db(db_pool, f"Document processing failed for Doc ID: {document_id}. Status: {response_status}, Details: {response_text[:200]}", document_id=document_id, task_id=task_id, username="system_workflow_error")

    except aiohttp.ClientConnectorError as e:
        logger.error(f"Connection error calling document processing service for Task ID {task_id}, Doc ID {document_id} at {doc_service_url}: {e}", exc_info=True)
        await log_generic_action_db(db_pool, f"Connection error for document processing (Doc ID: {document_id}, Task ID: {task_id}): {str(e)}", document_id=document_id, task_id=task_id, username="system_network_error")
    except asyncio.TimeoutError:
        logger.error(f"Timeout calling document processing service for Task ID {task_id}, Doc ID {document_id} at {doc_service_url}", exc_info=True)
        await log_generic_action_db(db_pool, f"Timeout during document processing (Doc ID: {document_id}, Task ID: {task_id})", document_id=document_id, task_id=task_id, username="system_timeout_error")
    except Exception as e:
        logger.error(f"Generic error during document processing service call for Task ID {task_id}, Doc ID {document_id}: {e}", exc_info=True)
        await log_generic_action_db(db_pool, f"Error in document processing step (Doc ID: {document_id}, Task ID: {task_id}): {str(e)}", document_id=document_id, task_id=task_id, username="system_workflow_error")
