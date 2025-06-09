      
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
