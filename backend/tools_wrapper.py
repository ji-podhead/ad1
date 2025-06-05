# tools_wrapper.py
"""
Wrapper für direkte MCP-Tool-API-Calls (E-Mail-API) für das Dashboard und Agenten.
"""
import os
import aiohttp
from typing import Any, Dict, List, Optional

MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://gmail:8000")

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
