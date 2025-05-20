from typing import List, Dict, Union

import openai
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Set Azure OpenAI configurations
openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT")
openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
openai.api_type = "azure"
openai.api_version = "2023-05-15"  # Use your current Azure API version
DEFAULT_DEPLOYMENT = "rabbit"

SYSTEM_PROMPT = """
You are an insurance‑policy compliance assistant. 
Your job is to find every clause that describes:

 • Actions the MSP is explicitly allowed to take during or after a security incident  
 • Actions the MSP is explicitly forbidden to take  
 • Conditions the MSP must meet to keep the policy in force (e.g. MFA, forensics, notification deadlines)

Return ONLY valid JSON: a list of objects with these fields:
  - requirement: the full text of the clause  
  - category: one of ["permitted","prohibited","coverage_condition"]  
"""



async def query_openai(prompt: str, max_tokens: int = 100, temperature: float = 0.7):
    """
    Sends a prompt to the Azure-hosted OpenAI API and returns the response.

    Args:
        prompt (str): The input text prompt for OpenAI.
        max_tokens (int): The maximum number of tokens to generate in the response.
        temperature (float): The sampling temperature to use.

    Returns:
        str: The response text from OpenAI.
    """
    try:
        response = openai.Completion.create(
            engine="your-deployment-name",  # Specify your deployment name
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].text.strip()
    except Exception as e:
        raise RuntimeError(f"Failed to get response from OpenAI: {e}")


async def secondary_query_openai(
    prompt: SYSTEM_PROMPT,
    max_tokens: int = 400,
    temperature: float = 0.7,
    deployment: str | None = None,
) -> str:
    """
    Async wrapper around Azure Chat Completions.
    • prompt = str  → wrapped as one user message
    • prompt = list → treated as full chat history
    """
    messages = (
        [{"role": "user", "content": prompt}]
        if isinstance(prompt, str)
        else prompt
    )

    resp = await openai.ChatCompletion.acreate(
        engine=deployment or DEFAULT_DEPLOYMENT,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        n=1,
    )
    return resp.choices[0].message.content.strip()