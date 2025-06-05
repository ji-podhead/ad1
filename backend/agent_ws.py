import asyncio
import json
import os
import logging
import warnings
from dotenv import load_dotenv
import google.generativeai as genai
from mcp import ClientSession
from mcp.client.sse import sse_client
from litellm import experimental_mcp_client
from ws_manager import ConnectionManager

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp-server/sse/")

manager = ConnectionManager()

async def test_agent_with_manager():
    """
    Testet die MCP-Tools und testet die WebSocket-Kommunikation mit dem ConnectionManager ohne Simulation.
    """
    session_id = "test-session"
    await manager.connect(None, session_id)  # Kein echtes WebSocket-Objekt nötig
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        # Testdaten direkt übergeben
        data = "summarize recent emails"
        async with sse_client(MCP_SERVER_URL) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                print("Session initialized")
                mcp_tools = await experimental_mcp_client.load_mcp_tools(session=session, format="mcp")
                print("MCP Tools loaded:", mcp_tools)
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[data],
                    config={
                        "system_instruction": ["You are a Gmail agent. Your task is to use the available tools."],
                        "tools": mcp_tools
                    },
                )
                result_text = ""
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'function_call') and part.function_call is not None:
                            function_call = part.function_call
                            result = await session.call_tool(
                                function_call.name, arguments=dict(function_call.args)
                            )
                            try:
                                email_data = json.loads(result.content[0].text)
                                result_text = json.dumps(email_data)
                            except Exception:
                                result_text = result.content[0].text
                        else:
                            if response.text:
                                result_text = response.text
                else:
                    result_text = "Keine Antwort vom Agenten."
                print("[TestManager] Antwort:", result_text)
                manager.send_personal_message(session_id, {"message": result_text})
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Agent error: {str(e)}\n{tb}")
    finally:
        manager.disconnect(session_id)

if __name__ == "__main__":
    asyncio.run(test_agent_with_manager())
