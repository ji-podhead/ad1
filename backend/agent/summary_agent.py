import asyncio
from typing import Callable, Any, Dict, Optional, List
import datetime
import json
import os
import asyncpg # Assuming asyncpg is used for database connection
from google.adk.agents import Agent as AdkAgent # Alias to avoid name conflict
from google.adk.models.lite_llm import LiteLlm
from litellm import experimental_mcp_client
import aiohttp
import logging # Added for explicit logging
import base64 # For dummy PDF
from mcp.client.sse import sse_client
from mcp import ClientSession
from pydantic import BaseModel # Import BaseModel from pydantic
from pydantic_ai import Agent # Import Agent from pydantic_ai
from pydantic_ai.models.gemini import GeminiModel, GeminiModelSettings # Import GeminiModel and Settings
class ClassificationResult(BaseModel):
    type: str
    score: float

class EmailClassificationResponse(BaseModel):
    classifications: List[ClassificationResult]
    short_description: str
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # <--- explizit setzen!
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
async def get_summary_and_type_from_llm(
    email_subject: str,
    email_body: str,
    llm_model_name: str,
    possible_types: List[str], # Add possible types parameter
    system_instruction: Optional[str] = None, # Add configurable system instruction
    max_tokens: Optional[int] = None, # Add configurable max tokens
    attachments_info: Optional[List[Dict[str, Any]]] = None # Add attachments info parameter
) -> Dict[str, Any]: # Return type can be more specific, but Dict[str, Any] is flexible
    """
    Analyzes email content using an LLM to determine document type, a short description,
    and provides scores for a list of possible types using pydantic_ai.
    Includes attachment information in the prompt if available.
    Returns a dictionary with "document_type", "short_description", and "classifications".
    """
    logger.info(f"get_summary_and_type_from_llm called with model: {llm_model_name}")
    if not GEMINI_API_KEY:
        logger.error("Error: GEMINI_API_KEY not configured. Cannot get summary from LLM.")
        return {
            "document_type": "Default/Unknown (LLM Error)",
            "short_description": "Gemini not available (LLM Error).",
            "classifications": []
        }

    # Update prompt to include possible types and ask for scores
    prompt = f"""Analyze the following email content and provide a short description and a classification score for each of the following document types: {', '.join(possible_types)}.
    Return your response *only* as a valid JSON object matching the following structure:
    {{
    "classifications": [
        {{"type": "Type1", "score": 0.9}},
        {{"type": "Type2", "score": 0.1}}
    ],
    "short_description": "A short summary of the email."
    }}
    Ensure scores are between 0.0 and 1.0.

    Subject: {email_subject}

    Body:
    {email_body[:4000]}
    """ # Limiting body length to manage token usage, adjust as needed
    if attachments_info:
        attachment_list_str = ", ".join([f"{att.get('filename', 'unnamed')} ({att.get('mimeType', 'unknown type')})" for att in attachments_info])
        prompt += f"\n\nThis email has the following attachments: {attachment_list_str}. Please include information about the attachments in the short description if relevant."
    logger.info(f"Sending prompt to LLM ({llm_model_name}) for subject: {email_subject}")
    response = None # Initialize response to None
    try:
        model_settings = GeminiModelSettings(
            system_instruction=[system_instruction] if system_instruction else None, # Pass system instruction as a list
            max_output_tokens=max_tokens,
        )
        model = GeminiModel(llm_model_name)
        agent = Agent(model, model_settings=model_settings)
        response = await agent.run(prompt)
        logger.info(f"LLM call completed, response received.")
        logger.info(f"LLM response: {response}")  # Log full response for debugging
    except Exception as e:
        logger.error(f"Error during LLM call using pydantic_ai: {e}")
        return {
            "document_type": "Default/Unknown (API Error)",
            "short_description": "Summary not available (API Error).",
            "classifications": []
        }

    # Check if response is None or missing the 'output' attribute
    if response is None or not hasattr(response, 'output') or response.output is None:
         logger.error("LLM response is None or missing output attribute.")

         return {
            "document_type": "Default/Unknown (API Error)",
            "short_description": "Summary not available (API Error).",
            "classifications": []
        }

    logger.info(f"LLM response text: {response.output}") # Log raw response text (using .output)
    cleaned_response_text = response.output.strip() # Use .output here
    if cleaned_response_text.startswith("```json"):
        cleaned_response_text = cleaned_response_text[7:]
    elif cleaned_response_text.startswith("```"):
         cleaned_response_text = cleaned_response_text[3:]
    if cleaned_response_text.endswith("```"):
        cleaned_response_text = cleaned_response_text[:-3]

    cleaned_response_text = cleaned_response_text.strip()

    try:
        # Parse with Pydantic model
        classification_response = EmailClassificationResponse.model_validate_json(cleaned_response_text)

        # Determine the document_type based on the highest score
        document_type = "Default/Unknown (No Classifications)"
        if classification_response.classifications:
            # Sort by score descending and pick the top one
            best_classification = sorted(classification_response.classifications, key=lambda x: x.score, reverse=True)[0]
            document_type = best_classification.type

        logger.info(f"LLM result - Type: {document_type}, Description: {classification_response.short_description}, Classifications: {classification_response.classifications}")

        return {
            "document_type": document_type,
            "short_description": classification_response.short_description,
            "classifications": [c.model_dump() for c in classification_response.classifications] # Return as dicts
        }

    except Exception as e: # Catch Pydantic validation errors or other parsing issues
        logger.error(f"Error parsing or validating JSON from LLM response: {e}")
        logger.error(f"LLM response text that failed parsing: '{cleaned_response_text}'")
        return {
            "document_type": "Default/Unknown (JSON Error)",
            "short_description": "Summary not available (JSON Error).",
            "classifications": []
        }
