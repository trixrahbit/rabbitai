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
