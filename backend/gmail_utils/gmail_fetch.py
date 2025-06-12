"""Utility functions for fetching and parsing Gmail email data.

This module provides functions to:
- Parse raw text content (presumably from an MCP server response) into a structured
  list of email header information.
- Fetch the full details of a specific email message from the Gmail API,
  including its body and attachments.
- Download individual attachments from a Gmail message.

It uses `aiohttp` for asynchronous HTTP requests to the Gmail API and
relies on OAuth2 tokens for authentication.
"""
import asyncio
from typing import Callable, Any, Dict, Optional, List
import datetime
import json
import os
import asyncpg # Assuming asyncpg is used for database connection
# Remove direct google.genai import if pydantic_ai handles it internally, or keep if needed for types
# from google import genai
# from google.genai.types import GenerateContentConfig, HttpOptions
from .gmail_mcp_tools_wrapper import list_emails # Corrected relative import
import aiohttp
import logging # Added for explicit logging
import base64 # For dummy PDF
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # <--- explizit setzen!
import re
from litellm import experimental_mcp_client
from mcp.client.sse import sse_client
from mcp import ClientSession
from db_utils import (
    insert_document_db, insert_new_email_db, log_generic_action_db,
    fetch_active_workflows_db, find_existing_email_db,
    delete_email_and_audit_for_duplicate_db, create_processing_task_db,
    update_email_document_ids_db
)
from gmail_utils.gmail_auth import fetch_access_token_for_user

logger = logging.getLogger(__name__)

def parse_mcp_email_list(raw_content: str) -> List[Dict[str, Any]]:
    """
    Parses raw text content from an MCP-like service into a list of email dicts.

    The raw content is expected to be a string where each email's information
    is a block separated by double newlines. Each block contains fields like
    ID, Subject, From, Date, and Attachments, identified by prefixes.

    Args:
        raw_content (str): The raw string content containing email information.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary
        represents an email with keys 'id', 'subject', 'sender', 'date',
        and 'attachments' (a list of attachment filenames).
        Returns an empty list if raw_content is empty or no blocks are found.
    """
    if not raw_content or not raw_content.strip():
        return []

    # Split by double newlines (each email is a block)
    blocks = [block.strip() for block in raw_content.strip().split('\n\n') if block.strip()]
    emails = []
    for block in blocks:
        # Extract fields using regex
        id_match = re.search(r'ID: (.+)', block)
        subject_match = re.search(r'Subject: (.+)', block)
        from_match = re.search(r'From: (.+)', block)
        date_match = re.search(r'Date: (.+)', block)
        # Extract all attachments (can occur multiple times)
        attachment_matches = re.findall(r'Attachment: (.+)', block)

        emails.append({
            'id': id_match.group(1) if id_match else None,
            'subject': subject_match.group(1) if subject_match else None,
            'sender': from_match.group(1) if from_match else None, # 'sender' is used in other parts of code
            'date': date_match.group(1) if date_match else None,
            'attachments': attachment_matches if attachment_matches else []
        })
    return emails


async def read_emails_and_log(db_pool: asyncpg.pool.Pool, email: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Für jede E-Mail: Hole den vollständigen Inhalt, parse ihn, und lade ggf. Attachments herunter.
    """
    results = []
    oauth_token = await fetch_access_token_for_user(db_pool,"leo@orchestra-nexus.com")
    message_id = email.get('id')
    if not message_id:
        logger.warning(f"Email without ID: {email}")
        return
    try:
        email= await get_full_email(db_pool,"leo@orchestra-nexus.com", message_id,oauth_token) # TODO: Get actual user email
        logger.info(f"Processing email ID: {message_id} - Subject: {email.get('subject', 'N/A')}") # Added subject to log
        results.append(email)  # Store the full email data for later processing

    except Exception as e:
        logger.error(f"Error reading email {message_id}: {e}")
    return results



async def fetch_new_emails_with_mcp(db_pool: asyncpg.pool.Pool, query: str, max_results: int) -> None:
    """
    Fetches new emails using MCP tools via SSE (Server-Sent Events).
    This function connects to an MCP server to access email processing tools.
    It then uses the 'search_emails' tool to find emails received within the
    last `interval_seconds` seconds. The function logs the results and
    processes the emails accordingly.
    Args:
        db_pool (asyncpg.pool.Pool): The database connection pool for asyncpg.
        interval_seconds (int): The time interval in seconds to look back for new emails.
    Returns:        
        None
    """
    try:
        MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp-server/sse/")
        async with sse_client(MCP_SERVER_URL) as streams:
            async with ClientSession(*streams) as session:
                logger.info("[Scheduler] MCP session established.")
                await session.initialize()
                logger.info("getting tools.")
                
                
                mcp_tools = await experimental_mcp_client.load_mcp_tools(session=session, format="mcp")
                if not mcp_tools:
                    logger.warning("No MCP tools available.")
                    return
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
                logger.info(f"Using Gmail query: {query}")
                result = await session.call_tool(search_emails_tool.name, arguments={"query": query, "maxResults": max_results})
                logger.info(f"Search result from MCP tool: {result}") # Removed raw result from log
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
                else:
                    logger.info(f"processed {len(emails)} new emails in MCP tool response.")
                    return emails
    except Exception as e:
        logger.error(f"Exception during MCP email fetch: {e}")
        return
    finally:
        if 'session' in locals() and session:
            logger.info("[Scheduler] Closing MCP session.")

async def get_full_email(
    db_pool: asyncpg.pool.Pool,
    user_email: str,
    message_id: str,
    access_token: str
) -> Optional[Dict[str, Any]]:
    """
    Fetches full email details from Gmail API, including body and attachments.

    This function retrieves a specific email message using the Gmail API. It parses
    the message payload to extract headers, body content (prioritizing text/plain
    over text/html), and information about attachments. It then attempts to
    download each attachment. The processed email details, along with downloaded
    attachment data, are saved to a local JSON file and returned as a dictionary.

    Args:
        db_pool (asyncpg.pool.Pool): The database connection pool (currently unused in
            this specific function but often passed to utility functions).
        user_email (str): The email address of the user whose Gmail account is being accessed.
            (Used for logging/context, token implies user).
        message_id (str): The ID of the Gmail message to fetch.
        access_token (str): The OAuth2 access token for authenticating with the Gmail API.

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing detailed information about the
        email if successful, including 'id', 'threadId', 'snippet', 'payload' (raw),
        'headers', 'body' (decoded string), and 'attachments' (list of attachment IDs,
        though the downloaded attachment data is saved to a file and not directly part of
        this list in the final returned dict from this specific implementation path).
        The function also saves this dictionary to a local JSON file named
        `./backend/attachments/{message_id}_{message_id}.json`.
        Returns None if fetching or processing fails.
    """
    
    try:
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        logger.info(f"Attempting to fetch full message {message_id} from Gmail API.")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                logger.info(f"Full message fetch response status: {resp.status}")
                response_data = await resp.json()
                # logger.info(f"Full message fetch response data: {json.dumps(response_data, indent=2)}") # Logge die Antwort - kann sehr groß sein
                if resp.status != 200:
                    logger.error(f"Failed to fetch full message {message_id}: HTTP {resp.status}")
                    return None

                email_details = {
                    'id': response_data.get('id'),
                    'threadId': response_data.get('threadId'),
                    'snippet': response_data.get('snippet'),
                    'payload': response_data.get('payload'),
                    'sizeEstimate': response_data.get('sizeEstimate'),
                    'historyId': response_data.get('historyId'),
                    'internalDate': response_data.get('internalDate'),
                    'headers': {},
                    'body': '', # Will be populated below
                    'attachments': [] # List to store downloaded attachment data
                }

                # Extract headers
                if 'payload' in response_data and 'headers' in response_data['payload']:
                    for header in response_data['payload']['headers']:
                        email_details['headers'][header['name']] = header['value']

                # --- Extract Body and Attachment Info ---
                body_content = ''
                attachment_info_list = []
                body_parts = [] # To collect potential body parts

                def find_email_content_recursive(parts):
                    """Recursively finds body parts and attachment info."""
                    current_body_parts = []
                    current_attachments = []
                    for part in parts:
                        # Collect potential body parts (plain and html)
                        if part.get('mimeType') in ['text/plain', 'text/html'] and 'body' in part and 'data' in part['body']:
                            current_body_parts.append(part)
                        # Collect attachment info
                        elif 'body' in part and 'attachmentId' in part['body'] and part.get('filename'):
                             current_attachments.append({
                                'attachmentId': part['body']['attachmentId'],
                                'filename': part['filename'],
                                'mimeType': part.get('mimeType'),
                                'size': part['body'].get('size', 0)
                            })
                             logger.info(f"Found attachment info: {part.get('filename')} (ID: {part['body']['attachmentId']}) in message {message_id}")

                        # Recurse into nested parts
                        if 'parts' in part:
                            nested_body, nested_attachments = find_email_content_recursive(part['parts'])
                            current_body_parts.extend(nested_body)
                            current_attachments.extend(nested_attachments)
                    return current_body_parts, current_attachments

                # Handle simple emails first (payload has body data directly)
                if 'payload' in response_data and 'body' in response_data['payload'] and 'data' in response_data['payload']['body']:
                     try:
                        body_content = base64.urlsafe_b64decode(response_data['payload']['body']['data'] + '==').decode('utf-8')
                        logger.info(f"Decoded simple email body for message {message_id}.")
                     except Exception as e:
                        logger.warning(f"Could not decode simple email body for message {message_id}: {e}")
                # If not a simple email, process parts recursively
                elif 'payload' in response_data and 'parts' in response_data['payload']:
                    body_parts, attachment_info_list = find_email_content_recursive(response_data['payload']['parts'])

                    # Prioritize text/plain body
                    preferred_body_part = None
                    for part in body_parts:
                        if part.get('mimeType') == 'text/plain':
                            preferred_body_part = part
                            break # Found plain text, use this one

                    # If no text/plain, look for text/html
                    if preferred_body_part is None:
                        for part in body_parts:
                            if part.get('mimeType') == 'text/html':
                                preferred_body_part = part
                                break # Found html, use this one

                    # Decode the preferred body part if found
                    if preferred_body_part:
                        try:
                            body_content = base64.urlsafe_b64decode(preferred_body_part['body']['data'] + '==').decode('utf-8')
                            logger.info(f"Decoded preferred body part ({preferred_body_part.get('mimeType')}) for message {message_id}.")
                            # Note: If text/html is used, this will still contain HTML tags.
                        except Exception as e:
                            logger.warning(f"Could not decode preferred body part ({preferred_body_part.get('mimeType')}) for message {message_id}: {e}")

                email_details['body'] = preferred_body_part['body']['data'] 

                # Download attachments using the collected info
                email_details['attachments'] = []  # Initialisieren/Zurücksetzen für korrekt strukturierte Anhänge

                for att_info in attachment_info_list: # att_info enthält Metadaten wie attachmentId, filename, mimeType
                    downloaded_att = await download_gmail_attachment(
                        db_pool,
                        user_email,
                        message_id,
                        att_info['attachmentId'],
                        att_info['filename'],
                        access_token
                    )
                    if downloaded_att:
                        # downloaded_att enthält {'filename': ..., 'data': file_bytes, 'size': ..., 'attachment_id': ...}
                        
                        # Rohe Bytes in einen base64-String kodieren
                        data_b64_str = base64.b64encode(downloaded_att['data']).decode('utf-8')

                        # Das korrekte Dictionary für die Datenbankaufbereitung und Weitergabe erstellen
                        attachment_data_for_processing = {
                            'filename': downloaded_att['filename'],
                            'mimeType': att_info['mimeType'], # mimeType aus den ursprünglichen Metadaten
                            'data_b64': data_b64_str,        # Die base64-kodierten Daten
                            'size': downloaded_att.get('size') # Optional die Größe hinzufügen
                        }
                        
                        # Das verarbeitete Anhangs-Dictionary (mit data_b64) hinzufügen
                        email_details['attachments'].append(attachment_data_for_processing)
                        logger.info(f"Successfully processed attachment for email_details: {attachment_data_for_processing['filename']} for message {message_id}.")
                    else:
                        logger.error(f"Failed to download attachment: {att_info['filename']} for message {message_id}.")
                
                return email_details
    except Exception as e:
        logger.error(f"Exception during full message fetch and attachment download for message {message_id}: {e}")
        return None

async def download_gmail_attachment(db_pool: asyncpg.pool.Pool, user_email: str, message_id: str, attachment_id: str, filename: str, user_oauth_token: str) -> dict:
    """
    Downloads an attachment from Gmail using the Gmail API and OAuth2 token.
    db_pool: asyncpg.pool.Pool - Database connection pool.
    user_email: string - The email address of the user whose token to use.
    message_id: string
    attachment_id: string
    filename: string (nur für Logging/DB)
    Returns a dict with filename, data (bytes), size (int), attachment_id (str)
    """
    logger = logging.getLogger(__name__)
    # Use 'me' for the authenticated user in the Gmail API URL
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/attachments/{attachment_id}"
    headers = {
        "Authorization": f"Bearer {user_oauth_token}",
        "Accept": "application/json"
    }
    try:
        logger.info(f"Attempting to download attachment {attachment_id} for message {message_id} using token.") # Added log
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                logger.info(f"Attachment download response status: {resp.status}") # Added log
                if resp.status != 200:
                    logger.error(f"Failed to download attachment {attachment_id} for message {message_id}: HTTP {resp.status}")
                    return None
                data = await resp.json()

                b64data = data.get("data")
                size = data.get("size")
                att_id = data.get("attachmentId")
                if not b64data:
                    logger.error(f"No data field in Gmail API response for attachment {attachment_id}")
                    return None
                # Gmail API uses base64url encoding, which might not have padding
                file_bytes = base64.urlsafe_b64decode(b64data + '==')
                logger.info(f"Downloaded attachment '{filename}' ({size} bytes) from Gmail API.")
                        
                return {
                    "filename": filename, # Add filename to the returned dict
                    "data": file_bytes,
                    "size": size,
                    "attachment_id": att_id
                }
    except Exception as e:
        logger.error(f"Exception downloading Gmail attachment {attachment_id}: {e}")
        return None
    
# saving files:   #email_details['attachments'] = downloaded_attachments
                
                # filename=message_id
                # # Define save directory and create if it doesn't exist
                # backend_dir = os.path.dirname(__file__)
                # save_dir = os.path.join(backend_dir, 'attachments')
                # os.makedirs(save_dir, exist_ok=True)

                # # Create a unique filename using message_id and original filename
                # # Sanitize filename to avoid issues with special characters
                # safe_filename = "".join([c for c in filename if c.isalnum() or c in ('.', '_', '-')])
                # if not safe_filename:
                #     safe_filename = "attachment" # Fallback if filename is empty or invalid

                # file_path = os.path.join(save_dir, f"{message_id}_{safe_filename}.json")

                # Save the file
                # try:
                #     with open(file_path, 'w', encoding='utf-8') as f:
                #             json.dump(email_details, f, ensure_ascii=False, indent=4)
                #     logger.info(f"Saved attachment to: {file_path}")
                #     return email_details # Return the path to the saved file
                # except Exception as e:
                #     logger.error(f"Failed to save attachment {filename} for message {message_id} to {file_path}: {e}")
                #     return None