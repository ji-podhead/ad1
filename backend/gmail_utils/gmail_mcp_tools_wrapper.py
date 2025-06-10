"""Wrappers for direct MCP (Mail Control Protocol) tool API calls for email operations.

This module provides asynchronous functions that act as clients to an MCP server,
which exposes an API for various email-related actions such as listing emails,
getting email details, sending emails, managing labels, and performing batch operations.
These wrappers simplify interactions with the MCP server for other parts of the
application, like the dashboard and agents.
"""
import os
import aiohttp
from typing import Any, Dict, List, Optional

MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8000") # Base URL for the MCP server

async def list_emails() -> List[Dict[str, Any]]:
    """Lists all emails via the MCP server.

    Sends a GET request to the `/emails` endpoint of the MCP server.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary
        represents an email and contains its details.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{MCP_BASE_URL}/emails") as resp:
            resp.raise_for_status()
            return await resp.json()

async def get_email(email_id: str) -> Dict[str, Any]:
    """Retrieves details for a specific email via the MCP server.

    Sends a GET request to the `/emails/{email_id}` endpoint.

    Args:
        email_id (str): The ID of the email to retrieve.

    Returns:
        Dict[str, Any]: A dictionary containing the details of the specified email.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{MCP_BASE_URL}/emails/{email_id}") as resp:
            resp.raise_for_status()
            return await resp.json()

async def label_email(email_id: str, label: str) -> Dict[str, Any]:
    """Applies a label to a specific email via the MCP server.

    Sends a POST request to the `/emails/{email_id}/label` endpoint.

    Args:
        email_id (str): The ID of the email to label.
        label (str): The label to apply.

    Returns:
        Dict[str, Any]: The response from the MCP server, typically confirming the action.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/emails/{email_id}/label", json={"label": label}) as resp:
            resp.raise_for_status()
            return await resp.json()

async def send_email(
    to: List[str],
    subject: str,
    body: str,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    mimeType: str = "text/plain",
    htmlBody: Optional[str] = None
) -> Dict[str, Any]:
    """Sends an email via the MCP server.

    Sends a POST request to the `/send_email` endpoint.

    Args:
        to (List[str]): A list of recipient email addresses.
        subject (str): The subject of the email.
        body (str): The plain text body of the email.
        cc (Optional[List[str]], optional): A list of CC recipient email addresses. Defaults to None.
        bcc (Optional[List[str]], optional): A list of BCC recipient email addresses. Defaults to None.
        mimeType (str, optional): The MIME type of the email body. Defaults to "text/plain".
        htmlBody (Optional[str], optional): The HTML body of the email, if sending an HTML email.
                                           Defaults to None.

    Returns:
        Dict[str, Any]: The response from the MCP server, typically confirming the send action.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    payload: Dict[str, Any] = {"to": to, "subject": subject, "body": body, "mimeType": mimeType}
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

async def draft_email(to: List[str], subject: str, body: str, cc: Optional[List[str]] = None) -> Dict[str, Any]:
    """Creates an email draft via the MCP server.

    Sends a POST request to the `/draft_email` endpoint.

    Args:
        to (List[str]): A list of recipient email addresses for the draft.
        subject (str): The subject of the draft.
        body (str): The body content of the draft.
        cc (Optional[List[str]], optional): A list of CC recipients for the draft. Defaults to None.

    Returns:
        Dict[str, Any]: The response from the MCP server, likely containing details of the created draft.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    payload: Dict[str, Any] = {"to": to, "subject": subject, "body": body}
    if cc:
        payload["cc"] = cc
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/draft_email", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def read_email(messageId: str) -> Dict[str, Any]:
    """Reads the content of a specific email via the MCP server.

    Sends a POST request to the `/read_email` endpoint. This might seem
    unconventional for a "read" operation (usually GET), but it matches the
    provided interface.

    Args:
        messageId (str): The ID of the message to read.

    Returns:
        Dict[str, Any]: A dictionary containing the email content and details.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    payload = {"messageId": messageId}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/read_email", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def search_emails(query: str, maxResults: int = 10) -> Dict[str, Any]:
    """Searches emails using Gmail search syntax via the MCP server.

    Sends a POST request to the `/search_emails` endpoint.

    Args:
        query (str): The Gmail search query string (e.g., "from:user@example.com is:unread").
        maxResults (int, optional): The maximum number of results to return. Defaults to 10.

    Returns:
        Dict[str, Any]: The response from the MCP server, typically a list of matching emails.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    payload = {"query": query, "maxResults": maxResults}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/search_emails", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def modify_email(
    messageId: str,
    addLabelIds: Optional[List[str]] = None,
    removeLabelIds: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Modifies labels for a specific email via the MCP server.

    Sends a POST request to the `/modify_email` endpoint. Allows adding and/or
    removing labels from an email.

    Args:
        messageId (str): The ID of the email to modify.
        addLabelIds (Optional[List[str]], optional): A list of label IDs to add. Defaults to None.
        removeLabelIds (Optional[List[str]], optional): A list of label IDs to remove. Defaults to None.

    Returns:
        Dict[str, Any]: The response from the MCP server, typically confirming the modification.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    payload: Dict[str, Any] = {"messageId": messageId}
    if addLabelIds:
        payload["addLabelIds"] = addLabelIds
    if removeLabelIds:
        payload["removeLabelIds"] = removeLabelIds
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/modify_email", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def delete_email(messageId: str) -> Dict[str, Any]:
    """Deletes an email permanently via the MCP server.

    Sends a POST request to the `/delete_email` endpoint.

    Args:
        messageId (str): The ID of the email to delete.

    Returns:
        Dict[str, Any]: The response from the MCP server, typically confirming deletion.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    payload = {"messageId": messageId}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/delete_email", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def list_email_labels() -> Dict[str, Any]:
    """Lists all available Gmail labels via the MCP server.

    Sends a POST request to the `/list_email_labels` endpoint.

    Returns:
        Dict[str, Any]: The response from the MCP server, containing a list of labels.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/list_email_labels", json={}) as resp: # Empty JSON payload
            resp.raise_for_status()
            return await resp.json()

async def create_label(name: str, messageListVisibility: str = "show", labelListVisibility: str = "labelShow") -> Dict[str, Any]:
    """Creates a new Gmail label via the MCP server.

    Sends a POST request to the `/create_label` endpoint.

    Args:
        name (str): The name of the new label to create.
        messageListVisibility (str, optional): Visibility of messages with this label in the
            message list. Defaults to "show". Other common values might be "hide".
        labelListVisibility (str, optional): Visibility of the label in the label list.
            Defaults to "labelShow". Other common values might be "labelHide".

    Returns:
        Dict[str, Any]: The response from the MCP server, typically containing details of the created label.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    payload = {"name": name, "messageListVisibility": messageListVisibility, "labelListVisibility": labelListVisibility}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{MCP_BASE_URL}/create_label", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

async def update_label(
    label_id: str, # Renamed 'id' to 'label_id' to avoid conflict with built-in id
    name: Optional[str] = None,
    messageListVisibility: Optional[str] = None,
    labelListVisibility: Optional[str] = None
) -> Dict[str, Any]:
    """Updates an existing Gmail label via the MCP server.

    Sends a POST request to the `/update_label` endpoint.

    Args:
        label_id (str): The ID of the label to update.
        name (Optional[str], optional): The new name for the label. Defaults to None (no change).
        messageListVisibility (Optional[str], optional): New message list visibility. Defaults to None.
        labelListVisibility (Optional[str], optional): New label list visibility. Defaults to None.

    Returns:
        Dict[str, Any]: The response from the MCP server, typically the updated label details.

    Raises:
        aiohttp.ClientResponseError: If the MCP server returns an HTTP error status.
    """
    payload: Dict[str, Any] = {"id": label_id} # MCP server expects 'id'
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
