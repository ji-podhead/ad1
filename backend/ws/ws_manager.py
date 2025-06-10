"""Manages WebSocket connections and broadcasts task progress updates.

This module provides a `ConnectionManager` class to keep track of active
WebSocket connections, allowing for personal messages to be sent to specific
clients and for broadcasting messages (like task updates) to all connected clients.
It also defines a `Task` dataclass for representing task state.
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Any
from dataclasses import dataclass
import asyncio
import json

@dataclass
class Task:
    """Represents a task with its status, progress, and potential sub-tasks.

    Attributes:
        id (str): The unique identifier for the task.
        status (str): The current status of the task (e.g., "running", "completed", "failed").
        progress (float): The progress of the task, typically a value between 0.0 and 1.0.
        children (List['Task']): A list of sub-tasks, if any.
    """
    id: str
    status: str
    progress: float
    children: List['Task'] # Type hint for children tasks

class ConnectionManager:
    """Manages active WebSocket connections and facilitates message broadcasting.

    This class keeps track of connected WebSocket clients using a session ID.
    It allows sending messages to specific clients or broadcasting to all.
    It also includes (though currently less utilized in provided context)
    attributes for managing tasks and responses, which might be for a more
    complex task management system.

    Attributes:
        active_connections (Dict[str, WebSocket]): A dictionary mapping session IDs
            to WebSocket connection objects.
        tasks (Dict[str, Task]): A dictionary to store task objects, keyed by task ID.
            (Note: Populating and using this `tasks` attribute is not shown in detail
            in the provided `agent_ws.py` or `stream_task_progress`.)
        respondMsgs (dict): A dictionary presumably for storing responses related to
            specific messages, keyed by a UUID. (Note: Its usage is unclear from
            the provided context and the `receive_text` method using it is marked as potentially unused.)
    """
    def __init__(self):
        """Initializes the ConnectionManager with empty dictionaries for connections, tasks, and responses."""
        self.active_connections: Dict[str, WebSocket] = {}
        self.tasks: Dict[str, Task] = {} # For storing Task dataclass instances
        self.respondMsgs: Dict[str, Any] = {} # For storing responses related to specific messages

    async def connect(self, websocket: WebSocket, session_id: str):
        """Accepts a new WebSocket connection and stores it.

        Args:
            websocket (WebSocket): The WebSocket connection object from FastAPI.
            session_id (str): A unique identifier for this client session.
        """
        await websocket.accept()
        self.active_connections[session_id] = websocket
        print(f"WebSocket connection established for session_id: {session_id}")

    def disconnect(self, session_id: str):
        """Removes a WebSocket connection from the active connections.

        Args:
            session_id (str): The session ID of the client to disconnect.
        """
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            print(f"WebSocket connection disconnected for session_id: {session_id}")
        else:
            print(f"Attempted to disconnect non-existent session_id: {session_id}")

    async def send_personal_message(self, session_id: str, message: dict):
        """Sends a JSON message to a specific connected WebSocket client.

        Args:
            session_id (str): The session ID of the client to send the message to.
            message (dict): The message to send, will be converted to JSON.

        Raises:
            WebSocketDisconnect: If the session_id is not found in active connections,
                                 implying the client is disconnected.
        """
        print(f"Attempting to send personal message to session_id: {session_id}")
        connection = self.active_connections.get(session_id)
        if connection:
            try:
                await connection.send_json(message)
                print(f"Sent personal message to {session_id}: {message}")
            except Exception as e: # More specific exceptions like RuntimeError can also be caught
                print(f"Error sending message to {session_id}: {e}. Removing connection.")
                self.disconnect(session_id) # Clean up broken connection
                # Optionally re-raise or handle as a disconnect
                raise WebSocketDisconnect(code=1011, reason=f"Error during send, session {session_id} removed.") from e
        else:
            print(f"Session not found for personal message: {session_id}")
            # This behavior (raising WebSocketDisconnect) is consistent with original,
            # but one might also just log an error if preferred.
            raise WebSocketDisconnect(code=1008, reason=f"Session {session_id} not found or already disconnected.")


    async def broadcast_task_update(self, task_id: str, status: str, progress: float):
        """Broadcasts a task update message to all connected WebSocket clients.

        Args:
            task_id (str): The ID of the task being updated.
            status (str): The new status of the task.
            progress (float): The new progress value of the task.
        """
        update = {"task_id": task_id, "status": status, "progress": progress}
        disconnected_sessions: List[str] = []
        for session_id, ws in self.active_connections.items():
            try:
                await ws.send_json(update)
            except Exception as e: # Catch potential errors during send (e.g., client disconnected abruptly)
                print(f"Error broadcasting to session {session_id}: {e}. Marking for removal.")
                disconnected_sessions.append(session_id)

        for session_id in disconnected_sessions:
            self.disconnect(session_id)

    async def receive_text(self, uuid: str, websocket: WebSocket) -> Optional[str]:
        """Receives text from a WebSocket connection (seems to be an alternative receive logic).

        Note:
            This method appears to be an alternative way to handle incoming messages,
            storing them in `self.respondMsgs`. However, `agent_ws.py` uses
            `websocket.receive_text()` directly within its `agent_websocket` handler.
            This method might be part of an uncompleted feature or deprecated.
            The `uuid` argument suggests it's intended to correlate responses.

        Args:
            uuid (str): A unique identifier, presumably to correlate requests and responses.
            websocket (WebSocket): The WebSocket connection to receive text from.

        Returns:
            Optional[str]: The text message received, or None if the connection
                           is disconnected.
        """
        # TODO: This method seems unused by agent_ws.py (which uses websocket.receive_text() directly). Review for removal.
        try:
            self.respondMsgs[uuid] = None # Initialize or clear previous response for this uuid
            response = await websocket.receive_text()
            print(f"respond uuid: {uuid} response: {response}")
            # self.respondMsgs[uuid] = response # Storing response, but it's returned directly
            return response
        except WebSocketDisconnect:
            print(f"WebSocket disconnected while receiving text for uuid: {uuid}")
            if uuid in self.respondMsgs:
                del self.respondMsgs[uuid] # Clean up
            return None


async def stream_task_progress(manager: ConnectionManager, task_id: str):
    """Asynchronously streams progress updates for a specific task.

    This generator function yields JSON strings representing the state of a task
    (ID, status, progress) at regular intervals (currently 1 second).
    It fetches task information from the `ConnectionManager.tasks` dictionary.

    Args:
        manager (ConnectionManager): The connection manager instance holding task information.
        task_id (str): The ID of the task whose progress is to be streamed.

    Yields:
        str: A JSON string representing the task's current state.
             Example: '{"task_id": "some_id", "status": "running", "progress": 0.5}'

    Note:
        This function assumes that the `manager.tasks` dictionary is being updated
        externally with the progress of the specified `task_id`.
    """
    while True:
        task = manager.tasks.get(task_id)
        if task: # Only yield if task exists
            yield json.dumps({
                "task_id": task.id,
                "status": task.status,
                "progress": task.progress
            })
        # Consider adding a condition to break the loop, e.g., if task is completed/failed
        # or if the WebSocket connection associated with this stream closes.
        await asyncio.sleep(1)

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
from dataclasses import dataclass
import asyncio
import json

@dataclass
class Task:
    id: str
    status: str
    progress: float
    children: List['Task']

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.tasks: Dict[str, Task] = {}
        self.respondMsgs = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]

    async def send_personal_message(self, session_id: str, message: dict):
        print("Sending personal message to", session_id)
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(message)
        else:
            raise WebSocketDisconnect(code=404, reason="Session not found")

    async def broadcast_task_update(self, task_id: str, status: str, progress: float):
        update = {"task_id": task_id, "status": status, "progress": progress}
        for ws in self.active_connections.values():
            await ws.send_json(update)

    async def receive_text(self, uuid, websocket: WebSocket):
        """Receives text from the WebSocket in a parallel async task and returns a promise."""
        try:
            self.respondMsgs[uuid] = None
            response = await websocket.receive_text()
            print(f"respond uuid: {uuid} response: {response}")
            return response
        except WebSocketDisconnect:
            return None
        # TODO: This method seems unused by agent_ws.py (which uses websocket.receive_text() directly). Review for removal.

async def stream_task_progress(manager: ConnectionManager, task_id: str):
    while True:
        task = manager.tasks.get(task_id)
        if task:
            yield json.dumps({
                "task_id": task.id,
                "status": task.status,
                "progress": task.progress
            })
        await asyncio.sleep(1)
