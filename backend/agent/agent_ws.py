"""Module for handling agent-related WebSocket communications.

This module defines the WebSocket endpoint for agent interactions, including
message handling, connection management, and integration with services like
email categorization using AI models (e.g., Gemini) and MCP (Mail Control Protocol) tools.
"""
import asyncio
import json
from dotenv import load_dotenv
import os
import warnings
import logging
from fastapi import WebSocket, WebSocketDisconnect
from google.genai import types
from mcp import ClientSession
from mcp.client.sse import sse_client
from litellm import experimental_mcp_client
from ws.ws_manager import ConnectionManager
from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
import litellm
from pydantic import BaseModel

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp-server/sse/")

logger = logging.getLogger("agent_ws") # Consider moving to top if not already there

manager = ConnectionManager()

async def categorize_email(email_body: str) -> Union[dict, str]:
    """Categorizes email content using the Gemini API and MCP tools.

    This function connects to an MCP server to access email processing tools.
    It then uses the Gemini large language model, configured with these MCP tools,
    to process a given email body (or a query related to an email). The model
    is expected to generate a function call to one of the MCP tools (e.g., to fetch
    email details or attachments). The result from the MCP tool is then processed
    and returned.

    Args:
        email_body (str): The content or query related to an email that needs categorization
                          or processing. Currently, the implementation uses a hardcoded
                          query within the function for demonstration/testing.

    Returns:
        Union[dict, str]: If successful and the MCP tool returns structured JSON data
                          (e.g., email details), a dictionary representing that data is returned.
                          If an error occurs, or if no specific function call is made,
                          or if the MCP tool returns non-JSON data, a string (often "unknown"
                          or an error message) is returned.

    Raises:
        ConnectionError: If connection to MCP server or other services fails.
        RuntimeError: For various runtime issues during API calls or processing.
        ValueError: If API keys or configurations are improper.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    async with sse_client(MCP_SERVER_URL) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            mcp_tools = await experimental_mcp_client.load_mcp_tools(session=session, format="mcp")
            logger.info(len(mcp_tools))
            if not mcp_tools:
                logger.warning("No MCP tools available.")
                return "unknown"
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[" lies die email: 'ID: 1974a06441cf5b55\nSubject: test2\nFrom: Leonardo Jacobi und gib mir die Anhänge."],
                config=GenerateContentConfig(
                    system_instruction=["You are a Gmail agent. Your task is to use the available tools."],
                    tools=mcp_tools
                ),
            )
            logger.info("making response")
            logger.info(response)

            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call is not None:
                        function_call = part.function_call
                        logger.info(f"Function call: {function_call}")
                        try:
                            result = await session.call_tool(
                                function_call.name, arguments=dict(function_call.args)
                            )
                            logger.info(f"Result: {result.content}")
                            try:
                                email_data = json.loads(result.content[0].text)
                                return email_data
                            except json.JSONDecodeError:
                                logger.error("MCP server returned non-JSON response:")
                                logger.error(result.content[0].text)
                            except (IndexError, AttributeError):
                                logger.error("Unexpected result structure from MCP server:")
                                logger.error(result)
                        except Exception as mcp_e:
                            logger.error(f"Error calling MCP tool {function_call.name}: {mcp_e}")
                    else:
                        logger.info("No function call was generated by the model.")
                        if response.text:
                            logger.info("Model response:")
                            logger.info(response.text)
            else:
                logger.warning("No candidates or content parts in the response.")

            return "unknown"


# --- WebSocket Agent Chat Logic ---
async def agent_websocket(websocket: WebSocket):
    """Handles the WebSocket lifecycle for an agent chat session.

    This function manages the connection, message reception, processing via
    `categorize_email`, and error handling for a single WebSocket client connection.
    It uses a `ConnectionManager` to track active connections.

    Args:
        websocket (WebSocket): The FastAPI WebSocket object representing the client connection.

    Workflow:
    1. Establishes connection and assigns a session ID.
    2. Sends a confirmation message to the client.
    3. Enters a loop to receive messages from the client:
        a. Receives a text message.
        b. Calls `categorize_email` to process the message.
        c. Sends the result or an error message back to the client.
    4. Handles `WebSocketDisconnect` gracefully.
    5. Catches other exceptions during message handling or communication,
       attempts to send an error message, and then breaks the loop.
    6. Ensures disconnection from the `ConnectionManager` in a `finally` block.
    """
    session_id = None
    try:
        session_id = str(id(websocket)) # Simple session ID based on websocket object ID
        await manager.connect(websocket, session_id)
        await manager.send_personal_message(session_id, {"message": "Agent chat connected.", "session_id": session_id})

        while True:
            try:
                data = await websocket.receive_text()
                logging.info(f"Received message from {session_id}: {data}")

                try:
                    result = await categorize_email(data) # This now takes 'data' as input
                    await manager.send_personal_message(session_id, {"message": result})
                except (ValueError, ConnectionError, RuntimeError) as e_cat:
                    logging.error(f"Categorization error for session {session_id}: {e_cat}", exc_info=True)
                    error_message = str(e_cat)
                    if isinstance(e_cat, ConnectionError):
                        error_message = "Could not connect to a required service. Please try again later."
                    elif "API Key" in str(e_cat) or "API policy" in str(e_cat): # More specific error check
                         error_message = "There's an issue with the categorization service configuration."
                    await manager.send_personal_message(session_id, {"error": error_message})
                except Exception as e_inner_loop:
                    logging.error(f"Unexpected error during categorization for session {session_id}: {e_inner_loop}", exc_info=True)
                    await manager.send_personal_message(session_id, {"error": "An unexpected error occurred while processing your request."})

            except WebSocketDisconnect:
                logging.info(f"WebSocket disconnected for session {session_id}.")
                break
            except Exception as e_outer_loop:
                logging.error(f"Error in WebSocket communication for session {session_id}: {e_outer_loop}", exc_info=True)
                try:
                    await manager.send_personal_message(session_id, {"error": "A communication error occurred."})
                except Exception:
                    pass # Ignore if sending also fails, as connection is likely broken
                break

    except Exception as e_connect:
        logging.error(f"Error during WebSocket setup or initial message for session {session_id or 'unknown'}: {e_connect}", exc_info=True)
    finally:
        if session_id: # Ensure session_id was assigned
            logging.info(f"Disconnecting session {session_id} in finally block.")
            manager.disconnect(session_id)

# # Optional: Standalone test
# if __name__ == '__main__':
#     asyncio.run(categorize_email(" lies die email: 'ID: 1974a06441cf5b55\nSubject: test2\nFrom: Leonardo Jacobi und gib mir die Anhänge."))
