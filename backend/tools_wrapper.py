# tools_wrapper.py
"""
Wrapper für direkte MCP-Tool-API-Calls (E-Mail-API) für das Dashboard und Agenten.
"""
import os
import aiohttp
from typing import Any, Dict, List, Optional

MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8000")

async def list_emails() -> List[Dict[str, Any]]:
    """Hole alle E-Mails über die MCP-Bridge."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{MCP_BASE_URL}/emails") as resp:
            resp.raise_for_status()
            return await resp.json()

async def get_email(email_id: str) -> Dict[str, Any]:
    """Hole Details zu einer E-Mail."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{MCP_BASE_URL}/emails/{email_id}") as resp:
            resp.raise_for_status()
            return await resp.json()

async def label_email(email_id: str, label: str) -> Dict[str, Any]:
    """Setze ein Label für eine E-Mail."""
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/emails/{email_id}/label", json={"label": label}) as resp:
            resp.raise_for_status()
            return await resp.json()

async def send_email(to: list, subject: str, body: str, cc: Optional[list] = None, bcc: Optional[list] = None, mimeType: str = "text/plain", htmlBody: Optional[str] = None) -> Dict[str, Any]:
    """Sende eine neue E-Mail sofort."""
    payload = {"to": to, "subject": subject, "body": body, "mimeType": mimeType}
    if cc:
        payload["cc"] = cc
    if bcc:
        payload["bcc"] = bcc
    if htmlBody:
        payload["htmlBody"] = htmlBody
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/send_email", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def draft_email(to: list, subject: str, body: str, cc: Optional[list] = None) -> Dict[str, Any]:
    """Erstelle einen E-Mail-Entwurf."""
    payload = {"to": to, "subject": subject, "body": body}
    if cc:
        payload["cc"] = cc
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/draft_email", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def read_email(messageId: str) -> Dict[str, Any]:
    """Lese den Inhalt einer bestimmten E-Mail."""
    payload = {"messageId": messageId}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/read_email", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def search_emails(query: str, maxResults: int = 10) -> Dict[str, Any]:
    """Suche E-Mails mit Gmail-Suchsyntax."""
    payload = {"query": query, "maxResults": maxResults}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/search_emails", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def modify_email(messageId: str, addLabelIds: Optional[list] = None, removeLabelIds: Optional[list] = None) -> Dict[str, Any]:
    """Füge Labels hinzu oder entferne sie von einer E-Mail."""
    payload = {"messageId": messageId}
    if addLabelIds:
        payload["addLabelIds"] = addLabelIds
    if removeLabelIds:
        payload["removeLabelIds"] = removeLabelIds
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/modify_email", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def delete_email(messageId: str) -> Dict[str, Any]:
    """Lösche eine E-Mail dauerhaft."""
    payload = {"messageId": messageId}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/delete_email", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def list_email_labels() -> Dict[str, Any]:
    """Hole alle verfügbaren Gmail-Labels."""
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/list_email_labels", json={}) as resp:
            resp.raise_for_status()
            return await resp.json()

async def create_label(name: str, messageListVisibility: str = "show", labelListVisibility: str = "labelShow") -> Dict[str, Any]:
    """Erstelle ein neues Gmail-Label."""
    payload = {"name": name, "messageListVisibility": messageListVisibility, "labelListVisibility": labelListVisibility}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/create_label", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def update_label(id: str, name: Optional[str] = None, messageListVisibility: Optional[str] = None, labelListVisibility: Optional[str] = None) -> Dict[str, Any]:
    """Aktualisiere ein bestehendes Gmail-Label."""
    payload = {"id": id}
    if name:
        payload["name"] = name
    if messageListVisibility:
        payload["messageListVisibility"] = messageListVisibility
    if labelListVisibility:
        payload["labelListVisibility"] = labelListVisibility
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/update_label", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def delete_label(id: str) -> Dict[str, Any]:
    """Lösche ein Gmail-Label."""
    payload = {"id": id}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/delete_label", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def get_or_create_label(name: str, messageListVisibility: str = "show", labelListVisibility: str = "labelShow") -> Dict[str, Any]:
    """Hole ein bestehendes Label oder erstelle es, falls nicht vorhanden."""
    payload = {"name": name, "messageListVisibility": messageListVisibility, "labelListVisibility": labelListVisibility}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/get_or_create_label", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def batch_modify_emails(messageIds: list, addLabelIds: Optional[list] = None, removeLabelIds: Optional[list] = None, batchSize: int = 50) -> Dict[str, Any]:
    """Modifiziere Labels für mehrere E-Mails in Batches."""
    payload = {"messageIds": messageIds, "batchSize": batchSize}
    if addLabelIds:
        payload["addLabelIds"] = addLabelIds
    if removeLabelIds:
        payload["removeLabelIds"] = removeLabelIds
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/batch_modify_emails", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def batch_delete_emails(messageIds: list, batchSize: int = 50) -> Dict[str, Any]:
    """Lösche mehrere E-Mails dauerhaft in Batches."""
    payload = {"messageIds": messageIds, "batchSize": batchSize}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/batch_delete_emails", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

import base64
import logging
import binascii

logger = logging.getLogger(__name__)

async def download_attachment(user_id: str, message_id: str, attachment_id: str, access_token: str) -> bytes:
    """
    Downloads an attachment from Gmail using the Gmail API and OAuth2 token.
    user_id: string ("me" for authentifizierten User oder echte E-Mail-Adresse)
    message_id: string
    attachment_id: string
    access_token: string (OAuth2 access token for Gmail API)
    Returns the decoded attachment data as bytes.
    Raises aiohttp.ClientResponseError for HTTP errors, ValueError for missing 'data' or decoding errors.
    """
    url = f"https://www.googleapis.com/gmail/v1/users/{user_id}/messages/{message_id}/attachments/{attachment_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"  # Gmail API for attachments returns JSON
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()  # Raises aiohttp.ClientResponseError for bad responses (4xx or 5xx)
            try:
                json_response = await resp.json()
                if 'data' not in json_response:
                    logger.error(f"Gmail API response missing 'data' field for attachment {attachment_id} in message {message_id}")
                    raise ValueError("Attachment data field missing in API response")

                base64url_data = json_response['data']
                # Python's urlsafe_b64decode handles padding issues automatically if needed.
                decoded_bytes = base64.urlsafe_b64decode(base64url_data)
                return decoded_bytes
            except json.JSONDecodeError as e: # Catch error if response is not valid JSON
                logger.error(f"Failed to decode JSON response from Gmail API for attachment {attachment_id}: {e}")
                raise ValueError(f"Invalid JSON response from Gmail API: {await resp.text()}")
            except KeyError: # Should be caught by 'data' not in json_response, but as a safeguard
                logger.error(f"Gmail API response missing 'data' field for attachment {attachment_id} (KeyError)")
                raise ValueError("Attachment data field missing (KeyError)")
            except (binascii.Error, TypeError) as e: # TypeError can occur with incorrect base64 string types
                logger.error(f"Base64 decoding error for attachment {attachment_id}: {e}")
                raise ValueError(f"Base64 decoding failed for attachment data: {e}")
            except Exception as e: # Catch any other unexpected errors
                logger.error(f"Unexpected error processing attachment {attachment_id} from Gmail API: {e}")
                raise # Re-raise other exceptions to understand them better


async def get_gmail_email_details(user_id: str, message_id: str, access_token: str) -> Dict[str, Any]:
    """
    Fetches the full details of an email from the Gmail API.
    user_id: User's email address or "me".
    message_id: The ID of the message to fetch.
    access_token: OAuth 2.0 access token for authorization.
    Returns the parsed JSON response from Gmail API (the full message resource).
    """
    url = f"https://www.googleapis.com/gmail/v1/users/{user_id}/messages/{message_id}?format=FULL"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    logger.debug(f"Fetching full email details for message ID: {message_id} for user: {user_id}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()  # Raises for 4xx/5xx responses
                email_details = await resp.json()
                logger.debug(f"Successfully fetched email details for message ID: {message_id}")
                return email_details
        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP error calling Gmail API for message {message_id}: {e.status} {e.message}")
            raise  # Re-raise to allow specific handling by the caller
        except Exception as e:
            logger.error(f"Unexpected error fetching email details for message {message_id} via Gmail API: {e}")
            raise RuntimeError(f"An unexpected error occurred while fetching email details: {e}")


async def list_gmail_messages(user_id: str, access_token: str, query: str = 'is:unread', max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Lists messages in the user's mailbox matching the query.
    user_id: User's email address or "me".
    access_token: OAuth 2.0 access token.
    query: String query to filter messages (e.g., 'is:unread label:my_label').
    max_results: Maximum number of messages to return.
    Returns a list of message resources (id and threadId).
    """
    url = f"https://www.googleapis.com/gmail/v1/users/{user_id}/messages"
    params = {"q": query, "maxResults": max_results}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    logger.debug(f"Listing Gmail messages for user {user_id} with query: {query}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, params=params) as resp:
                resp.raise_for_status()
                response_data = await resp.json()
                messages = response_data.get('messages', [])
                logger.info(f"Found {len(messages)} messages for user {user_id}.")
                return messages # List of {'id': '...', 'threadId': '...'}
        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP error listing Gmail messages for user {user_id}: {e.status} {e.message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing Gmail messages for user {user_id}: {e}")
            raise RuntimeError(f"An unexpected error occurred while listing messages: {e}")
