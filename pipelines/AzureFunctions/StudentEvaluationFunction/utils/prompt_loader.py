"""
Prompt loading and template filling utilities.
Prompts are loaded from blob storage using environment-configured base URL and container.
"""
import logging
import os
from .blob_storage import fetch_blob_content

# In-memory prompt cache
_prompt_cache: dict = {}


def load_prompt(prompt_name: str) -> str:
    """
    Load a prompt template from blob storage with in-memory caching.
    
    Args:
        prompt_name: Prompt file name (e.g. "Evaluation.txt", "Student_HW_Split.md")
    
    Returns:
        Prompt template string
    """
    if prompt_name in _prompt_cache:
        return _prompt_cache[prompt_name]

    blob_base = os.environ.get("BLOB_STORAGE_URL", "<BLOB_STORAGE_URL>")
    container = os.environ.get("PROMPTS_CONTAINER", "<PROMPTS_CONTAINER>")
    blob_url = f"{blob_base}/{container}/{prompt_name}"

    logging.info(f"Loading prompt from blob: {blob_url}")
    content = fetch_blob_content(blob_url, as_text=True)
    _prompt_cache[prompt_name] = content
    logging.info(f"Prompt '{prompt_name}' loaded and cached ({len(content)} chars)")
    return content


def fill_template(template: str, **kwargs) -> str:
    """
    Fill a prompt template with provided key-value pairs.
    Supports both {key} and {{key}} style placeholders.
    
    Args:
        template: The prompt template string
        **kwargs: Key-value pairs for placeholder substitution
    
    Returns:
        Filled template string
    """
    filled = template
    for key, value in kwargs.items():
        # Handle {{key}} style (e.g., Text_ParsingPrompt uses {{user_input}})
        filled = filled.replace(f"{{{{{key}}}}}", str(value))
        # Handle {key} style (e.g., Evaluation.txt uses {class}, {Subject})
        filled = filled.replace(f"{{{key}}}", str(value))
    return filled
