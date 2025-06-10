"""Agent for summarizing email content and classifying its type using an LLM.

This module provides functionality to analyze email content (subject, body, and
attachment information) using a large language model (LLM) like Gemini.
It aims to generate a concise summary of the email and classify its type based on
a predefined list of possible categories, providing confidence scores for each.
The results are returned in a structured dictionary format.
"""
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
    """Represents the classification result for a single document type.

    Attributes:
        type (str): The classified document type (e.g., "Invoice", "Support Request").
        score (float): The confidence score for this classification, between 0.0 and 1.0.
    """
    type: str
    score: float

class EmailClassificationResponse(BaseModel):
    """Pydantic model for parsing the LLM's JSON response for email classification.

    Attributes:
        classifications (List[ClassificationResult]): A list of classification results
            with scores for each possible type.
        short_description (str): A short summary of the email content.
    """
    classifications: List[ClassificationResult]
    short_description: str

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Explicitly set logging level

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Should be loaded at application startup ideally

async def get_summary_and_type_from_llm(
    email_subject: str,
    email_body: str,
    llm_model_name: str,
    possible_types: List[str],
    system_instruction: Optional[str] = None,
    max_tokens: Optional[int] = None,
    attachments_info: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Analyzes email content using an LLM for type classification and summarization.

    This function sends a crafted prompt including the email's subject, body, and
    information about its attachments (if any) to a specified LLM (e.g., Gemini).
    It instructs the LLM to return a JSON object containing a short description
    of the email and classification scores for a predefined list of `possible_types`.
    The function then parses this JSON response and determines the primary document
    type based on the highest classification score.

    Args:
        email_subject (str): The subject of the email.
        email_body (str): The body content of the email.
        llm_model_name (str): The name of the LiteLLM compatible model to use (e.g., "gemini-1.5-flash").
        possible_types (List[str]): A list of strings representing the possible document
            types for classification (e.g., ["Invoice", "Support", "Marketing"]).
        system_instruction (Optional[str], optional): An optional system instruction
            to guide the LLM's behavior. Defaults to None.
        max_tokens (Optional[int], optional): The maximum number of tokens for the
            LLM's response. Defaults to None (model's default).
        attachments_info (Optional[List[Dict[str, Any]]], optional): A list of
            dictionaries, where each dictionary contains information about an
            attachment (e.g., {'filename': 'doc.pdf', 'mimeType': 'application/pdf'}).
            Defaults to None.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - "document_type" (str): The document type with the highest classification score.
              Defaults to "Default/Unknown (LLM Error/API Error/JSON Error/No Classifications)"
              in case of issues.
            - "short_description" (str): A short summary of the email. Defaults to an
              error message or "Summary not available" in case of issues.
            - "classifications" (List[Dict[str, Any]]): A list of dictionaries, each
              representing a classification result with "type" and "score". Empty if
              an error occurs.
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
