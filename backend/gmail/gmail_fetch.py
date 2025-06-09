
import asyncio
from typing import Callable, Any, Dict, Optional, List
import datetime
import json
import os
import asyncpg # Assuming asyncpg is used for database connection
# Remove direct google.genai import if pydantic_ai handles it internally, or keep if needed for types
# from google import genai
# from google.genai.types import GenerateContentConfig, HttpOptions
from tools_wrapper import list_emails # Import list_emails
import aiohttp
import logging # Added for explicit logging
import base64 # For dummy PDF
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # <--- explizit setzen!


async def fetch_access_token_for_user(db_pool: asyncpg.pool.Pool, user_email: str) -> str:
        logger.info(f"Attempting to fetch access token for user: {user_email} for message fetch test.")
        user_row = await db_pool.fetchrow("SELECT google_access_token FROM users")
        if not user_row or not user_row['google_access_token']:
            logger.error(f"Google access token not found for user: {user_email}. Cannot perform message fetch test.")
            return None
        user_oauth_token = user_row['google_access_token']
        logger.info(f"Successfully fetched access token for user: {user_email} for message fetch test.")
        return user_oauth_token

async def get_email(db_pool: asyncpg.pool.Pool, user_email: str, message_id: str, access_token: str):
    """
    Fetches the full email message from Gmail API, extracts attachment IDs, and downloads attachments.
    Prioritizes text/plain body over text/html.
    db_pool: asyncpg.pool.Pool - Database connection pool.
    user_email: string - The email address of the user whose token to use.
    message_id: string - The ID of the email message.
    access_token: string - The OAuth2 access token for the user.
    Returns a dict containing email details and a list of downloaded attachments.
    """
    logger = logging.getLogger(__name__)
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

                email_details['body'] = body_content

                # Download attachments using the collected info
                downloaded_attachments = []
                email_details['attachments']= []  # Reset to empty list for downloaded attachments
                for att_info in attachment_info_list:
                    downloaded_att = await download_gmail_attachment(
                        db_pool,
                        user_email,
                        message_id,
                        att_info['attachmentId'],
                        att_info['filename'],
                        access_token
                    )
                    if downloaded_att:
                        downloaded_att['mimeType'] = att_info['mimeType']  # Add mimeType to downloaded attachment info
                        downloaded_att["email_id"] = email_details['id']  # Link to email
                        
                        downloaded_attachments.append(downloaded_att)
                        
                        email_details['attachments'].append(att_info['attachmentId'])
                        
                        logger.info(f"Successfully downloaded attachment: {downloaded_att.keys()} for message {message_id}.")

                    else:
                        logger.error(f"Failed to download attachment: {att_info['filename']} for message {message_id}.")

                # email_details['attachments'] = downloaded_attachments
                
                filename=message_id
                # Define save directory and create if it doesn't exist
                backend_dir = os.path.dirname(__file__)
                save_dir = os.path.join(backend_dir, 'attachments')
                os.makedirs(save_dir, exist_ok=True)

                # Create a unique filename using message_id and original filename
                # Sanitize filename to avoid issues with special characters
                safe_filename = "".join([c for c in filename if c.isalnum() or c in ('.', '_', '-')])
                if not safe_filename:
                    safe_filename = "attachment" # Fallback if filename is empty or invalid

                file_path = os.path.join(save_dir, f"{message_id}_{safe_filename}.json")

                # Save the file
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(email_details, f, ensure_ascii=False, indent=4)
                    logger.info(f"Saved attachment to: {file_path}")
                    return email_details # Return the path to the saved file
                except Exception as e:
                    logger.error(f"Failed to save attachment {filename} for message {message_id} to {file_path}: {e}")
                    return None
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


