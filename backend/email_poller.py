import logging
import asyncio
import asyncpg # For type hinting and eventually direct use if pool is passed
import uuid # For generating document and task IDs
from backend.tools_wrapper import list_emails, get_email
# We'll need a way to access the database pool.
# For now, functions will accept 'db_pool' as an argument.
# from dateutil import parser # Would be needed for robust date parsing
# from datetime import datetime, timezone # For date parsing examples

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def email_exists(db_pool: asyncpg.Pool, email_id: str) -> bool:
    '''Checks if an email with the given ID already exists in the database.'''
    async with db_pool.acquire() as connection:
        exists = await connection.fetchval("SELECT EXISTS(SELECT 1 FROM emails WHERE id = $1)", email_id)
        return exists

async def insert_email(db_pool: asyncpg.Pool, email_data: dict):
    '''Inserts a single email into the database.'''
    required_fields = ['id', 'sender', 'received_at']
    for field in required_fields:
        if field not in email_data or email_data[field] is None:
            logger.error(f"Email data missing required field '{field}' for email ID: {email_data.get('id')}")
            return None

    email_data.setdefault('topic', None)
    email_data.setdefault('recipient', None)
    email_data.setdefault('cc', None)
    email_data.setdefault('bcc', None)
    email_data.setdefault('subject', None)
    email_data.setdefault('body_html', None)
    email_data.setdefault('body_text', None)
    email_data.setdefault('user_id', None)
    email_data.setdefault('archived', False)
    email_data.setdefault('read', False)
    email_data.setdefault('labels', [])

    async with db_pool.acquire() as connection:
        try:
            await connection.execute(
                """
                INSERT INTO emails (id, topic, sender, recipient, cc, bcc, subject, body_html, body_text,
                                  received_at, user_id, archived, read, labels, imported_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
                ON CONFLICT (id) DO NOTHING;
                """,
                email_data['id'], email_data.get('topic'), email_data['sender'],
                email_data.get('recipient'), email_data.get('cc'), email_data.get('bcc'),
                email_data.get('subject'), email_data.get('body_html'), email_data.get('body_text'),
                email_data['received_at'], email_data.get('user_id'),
                email_data.get('archived', False), email_data.get('read', False),
                email_data.get('labels', [])
            )
            logger.info(f"Successfully inserted or confirmed email ID: {email_data['id']}")
            return email_data['id']
        except Exception as e:
            logger.error(f"Error inserting email ID {email_data.get('id')}: {e}", exc_info=True)
            return None

async def process_and_store_attachments(db_pool: asyncpg.Pool, email_id: str, attachments_data: list):
    '''Processes attachment data, stores metadata, and links to the email.'''
    if not attachments_data: return
    logger.info(f"Processing {len(attachments_data)} attachments for email {email_id}...")
    async with db_pool.acquire() as connection:
        for attachment_item in attachments_data:
            try:
                doc_id = str(uuid.uuid4())
                filename = attachment_item.get('filename', 'untitled_attachment')
                content_type = attachment_item.get('contentType', attachment_item.get('mimeType', 'application/octet-stream'))
                size_bytes = attachment_item.get('size')
                if size_bytes is None:
                    logger.warning(f"Attachment '{filename}' for email {email_id} missing 'size'. Storing size as 0.")
                    size_bytes = 0
                storage_path = None # Placeholder

                await connection.execute(
                    "INSERT INTO documents (id, filename, content_type, size_bytes, storage_path, created_at) "
                    "VALUES ($1, $2, $3, $4, $5, NOW()) ON CONFLICT (id) DO NOTHING;",
                    doc_id, filename, content_type, size_bytes, storage_path
                )
                logger.info(f"Stored document metadata for '{filename}' (ID: {doc_id}) for email {email_id}.")
                await connection.execute(
                    "INSERT INTO email_documents (email_id, document_id) VALUES ($1, $2) "
                    "ON CONFLICT (email_id, document_id) DO NOTHING;",
                    email_id, doc_id
                )
                logger.info(f"Linked document {doc_id} to email {email_id}.")
            except Exception as e:
                item_name = attachment_item.get('filename', 'unknown_attachment')
                logger.error(f"Error processing attachment '{item_name}' for email {email_id}: {e}", exc_info=True)

async def fetch_new_emails(db_pool: asyncpg.Pool):
    '''Fetches new emails, processes, stores them and their attachments.'''
    logger.info("Checking for new emails...")
    try:
        email_metas = await list_emails(max_results=20)
        if not email_metas:
            logger.info("No emails found from source.")
            return []
        processed_email_ids = []
        for meta in reversed(email_metas):
            email_id = meta.get('id')
            if not email_id:
                logger.warning(f"Email metadata missing 'id': {meta}"); continue
            if await email_exists(db_pool, email_id):
                logger.info(f"Email ID {email_id} already exists. Skipping."); continue
            logger.info(f"Email ID {email_id} is new. Fetching details...")
            try:
                email_detail = await get_email(email_id)
                if email_detail:
                    received_at = None
                    date_value = email_detail.get('internalDate')
                    if date_value:
                        try:
                            from datetime import datetime, timezone
                            received_at = datetime.fromtimestamp(int(date_value) / 1000, tz=timezone.utc)
                        except Exception: logger.warning(f"Could not parse internalDate '{date_value}' for {email_id}.")
                    if not received_at:
                        date_str = email_detail.get('date')
                        if date_str:
                            try:
                                from dateutil import parser; from datetime import timezone
                                received_at = parser.parse(date_str)
                                if received_at.tzinfo is None: received_at = received_at.replace(tzinfo=timezone.utc)
                            except Exception as e: logger.error(f"Could not parse date string '{date_str}' for {email_id}: {e}"); continue
                        else: logger.error(f"Email {email_id} missing date. Skipping."); continue

                    mapped_email_data = {
                        'id': email_detail.get('id'), 'sender': email_detail.get('from') or email_detail.get('sender'),
                        'recipient': email_detail.get('to'), 'cc': email_detail.get('cc'), 'bcc': email_detail.get('bcc'),
                        'subject': email_detail.get('subject'),
                        'body_html': email_detail.get('body_html') or email_detail.get('body'),
                        'body_text': email_detail.get('body_text'), 'received_at': received_at,
                        'labels': email_detail.get('labels', []), 'topic': email_detail.get('topic'),
                    }
                    inserted_id = await insert_email(db_pool, mapped_email_data)
                    if inserted_id:
                        processed_email_ids.append(inserted_id)
                        attachments = email_detail.get('attachments', [])
                        if attachments: await process_and_store_attachments(db_pool, inserted_id, attachments)
                else: logger.warning(f"Could not retrieve details for email ID: {email_id}")
            except Exception as e: logger.error(f"Error processing email ID {email_id}: {e}", exc_info=True)
        if processed_email_ids: logger.info(f"Batch finished. {len(processed_email_ids)} new emails stored: {processed_email_ids}")
        else: logger.info("Batch finished. No new emails stored.")
        return processed_email_ids
    except Exception as e: logger.error(f"Email fetching error: {e}", exc_info=True); return []

# --- Task related functions ---
async def create_task(db_pool: asyncpg.Pool, title: str, description: str = None, status: str = 'todo',
                      priority: str = 'medium', due_date = None, user_id: int = None) -> str:
    '''Creates a new task. Returns task ID.'''
    task_id = str(uuid.uuid4())
    async with db_pool.acquire() as connection:
        try:
            await connection.execute(
                "INSERT INTO tasks (id, user_id, title, description, status, priority, due_date, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())",
                task_id, user_id, title, description, status, priority, due_date
            )
            logger.info(f"Created task ID: {task_id} with title '{title}'")
            return task_id
        except Exception as e:
            logger.error(f"Error creating task '{title}': {e}", exc_info=True); raise

async def link_task_to_email(db_pool: asyncpg.Pool, email_id: str, task_id: str):
    '''Links a task to an email.'''
    async with db_pool.acquire() as connection:
        try:
            await connection.execute(
                "INSERT INTO email_tasks (email_id, task_id) VALUES ($1, $2) "
                "ON CONFLICT (email_id, task_id) DO NOTHING;",
                email_id, task_id
            )
            logger.info(f"Linked task {task_id} to email {email_id}")
        except Exception as e:
            logger.error(f"Error linking task {task_id} to email {email_id}: {e}", exc_info=True); raise

async def create_task_from_email(db_pool: asyncpg.Pool, email_id: str, title: str,
                                 description: str = None, status: str = 'todo',
                                 priority: str = 'medium', due_date = None, user_id: int = None) -> str:
    '''Creates a task and links it to an email. Returns task ID.'''
    if not await email_exists(db_pool, email_id): # Check email existence first
        logger.error(f"Cannot create task: Email ID {email_id} does not exist.")
        raise ValueError(f"Email ID {email_id} does not exist.")
    task_id = await create_task(db_pool, title, description, status, priority, due_date, user_id)
    # Task creation raises on failure, so task_id should be valid if we proceed.
    await link_task_to_email(db_pool, email_id, task_id)
    logger.info(f"Task {task_id} created from and linked to email {email_id}.")
    return task_id

if __name__ == '__main__':
    async def main_test():
        class MockConnection:
            _email_exists_called_for_id = None # Used to simulate email_exists for create_task_from_email

            async def fetchval(self, query, *args):
                if "SELECT EXISTS(SELECT 1 FROM emails WHERE id = $1)" in query:
                    # For create_task_from_email, make sure email_exists returns True for the specific ID
                    if args[0] == self._email_exists_called_for_id:
                        logger.info(f"Mock DB: email_exists for {args[0]} returning True")
                        return True
                    logger.info(f"Mock DB: email_exists for {args[0]} returning False")
                    return False
                return None
            async def execute(self, query, *args): pass # Mock
            async def __aenter__(self): return self
            async def __aexit__(self, exc_type, exc, tb): pass

        class MockDBPool:
            _connection_instance = MockConnection()
            async def acquire(self):
                return self._connection_instance

        mock_pool = MockDBPool()

        global list_emails, get_email
        original_list_emails, original_get_email = list_emails, get_email

        async def mock_list_emails(max_results=1): # Keep this simple for task testing focus
            return [{'id': 'test_email_for_task_1', 'subject': 'Test Email for Task Creation'}]

        async def mock_get_email(email_id):
            from datetime import datetime, timezone
            if email_id == 'test_email_for_task_1':
                return {
                    'id': 'test_email_for_task_1', 'from': 'sender@example.com',
                    'subject': 'Test Email Subject for Task',
                    'internalDate': str(int(datetime.now(timezone.utc).timestamp() * 1000))
                }
            return None

        list_emails = mock_list_emails; get_email = mock_get_email

        logger.info("Starting conceptual test including task creation...")
        try:
            from dateutil import parser # Ensure it's "imported" for the test context if date fallback is hit
        except ImportError: logger.warning("dateutil.parser not available for test.")

        processed_ids = await fetch_new_emails(mock_pool)

        if processed_ids:
            sample_email_id = processed_ids[0]
            logger.info(f"Attempting to create task for email ID: {sample_email_id}")
            # Set the ID for which email_exists should return True in the mock
            mock_pool._connection_instance._email_exists_called_for_id = sample_email_id
            try:
                new_task_id = await create_task_from_email(mock_pool, sample_email_id,
                                                           "Follow up: Test email task",
                                                           description="This task was auto-generated for testing.")
                if new_task_id:
                    logger.info(f"Test: Created task {new_task_id} linked to email {sample_email_id}")
            except Exception as e_task_create:
                logger.error(f"Test: Error during create_task_from_email: {e_task_create}", exc_info=True)

        try:
            standalone_task_id = await create_task(mock_pool, "General standalone task", description="Standalone test.")
            if standalone_task_id:
                logger.info(f"Test: Created standalone task {standalone_task_id}")
        except Exception as e_standalone_task:
            logger.error(f"Test: Error during standalone task creation: {e_standalone_task}", exc_info=True)

        list_emails, get_email = original_list_emails, original_get_email # Restore
        logger.info("Conceptual test finished.")

    # asyncio.run(main_test())
    pass
