"""
Gemini API client with retry logic and model constants.
Extracted from function_app.py + validate_split.py patterns.
Migrated to google-genai SDK (google.generativeai is deprecated).
"""
import logging
import json
import time
from google import genai
from google.genai import types
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import os

# Model constants
MODEL_EVALUATION = "gemini-3-pro-image-preview"       # Evaluation with image output support
MODEL_BOUNDING_BOX = "gemini-3-pro-preview"            # Proven in experiment (validate_split.py)
MODEL_TEXT_PARSE = "gemini-2.5-flash-lite"              # Lightweight text parsing

# In-memory caches
_api_key_cache = None
_client_cache = None


def get_api_key() -> str:
    """
    Retrieve Google API key from Azure Key Vault with in-memory caching.
    """
    global _api_key_cache
    if _api_key_cache:
        return _api_key_cache

    vault_url = os.environ.get("KEY_VAULT_URL", "<KEY_VAULT_URL>")
    secret_name = os.environ.get("KEY_VAULT_SECRET_NAME", "<KEY_VAULT_SECRET_NAME>")

    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)
        secret = client.get_secret(secret_name)
        _api_key_cache = secret.value
        logging.info("API key retrieved from Key Vault and cached")
        return _api_key_cache
    except Exception as e:
        logging.error(f"Error retrieving API key from Key Vault: {e}")
        raise


def _get_client() -> genai.Client:
    """
    Return a cached google.genai Client instance.
    """
    global _client_cache
    if _client_cache is None:
        api_key = get_api_key()
        _client_cache = genai.Client(api_key=api_key)
        logging.info("google.genai Client created and cached")
    return _client_cache


def call_gemini(
    model_id: str,
    content_parts: list,
    response_json: bool = False,
    temperature: float = None,
    max_retries: int = 3,
    base_delay: int = 5,
    enrich: bool = True,
) -> str | dict:
    """
    Generic Gemini call with exponential backoff retry.
    
    Args:
        model_id: Gemini model identifier
        content_parts: List of content parts (strings, dicts with mime_type/data)
        response_json: If True, request JSON response and parse it
        temperature: Optional temperature override
        max_retries: Number of retry attempts for rate limiting
        base_delay: Base delay in seconds for exponential backoff
        enrich: If True, return enriched dict with model/token metadata;
                if False, return raw text/parsed JSON (legacy behavior)
    
    Returns:
        If enrich=True: {"parsed_result": ..., "raw_response_text": str, "model": str, "usage_metadata": dict|None}
        If enrich=False: Response text (str) or parsed JSON (dict) if response_json=True
    """
    client = _get_client()

    # Convert raw dict parts (old google-generativeai format) to google-genai types.Part
    converted_parts = []
    for part in content_parts:
        if isinstance(part, dict) and "mime_type" in part and "data" in part:
            converted_parts.append(
                types.Part.from_bytes(data=part["data"], mime_type=part["mime_type"])
            )
        else:
            converted_parts.append(part)

    # Build generation config
    config_kwargs = {}
    if response_json:
        config_kwargs["response_mime_type"] = "application/json"
    if temperature is not None:
        config_kwargs["temperature"] = temperature
    config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=converted_parts,
                config=config,
            )

            if not response.text:
                logging.error("Empty response text from Gemini")
                raise ValueError("Empty response from Gemini API")

            # Extract usage metadata if available
            usage = None
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                um = response.usage_metadata
                usage = {
                    "prompt_tokens": getattr(um, "prompt_token_count", None),
                    "completion_tokens": getattr(um, "candidates_token_count", None),
                    "total_tokens": getattr(um, "total_token_count", None),
                }

            if response_json:
                try:
                    parsed = json.loads(response.text)
                except json.JSONDecodeError as e:
                    logging.warning(f"JSON decode attempt 1 failed: {e}. Trying escape sanitisation...")
                    try:
                        sanitized = _sanitize_json_escapes(response.text)
                        parsed = json.loads(sanitized)
                        logging.info("JSON parsed successfully after escape sanitisation")
                    except json.JSONDecodeError as e2:
                        logging.error(f"JSON decode failed even after sanitisation: {e2}. Raw: {response.text[:500]}")
                        raise ValueError(f"Invalid JSON response from Gemini: {e2}")

                if enrich:
                    return {
                        "parsed_result": parsed,
                        "raw_response_text": response.text,
                        "model": model_id,
                        "usage_metadata": usage,
                    }
                return parsed

            if enrich:
                return {
                    "parsed_result": response.text,
                    "raw_response_text": response.text,
                    "model": model_id,
                    "usage_metadata": usage,
                }
            return response.text

        except Exception as e:
            error_str = str(e)
            is_retryable = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

            if is_retryable and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logging.warning(f"Rate limited. Retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                continue
            
            if is_retryable:
                logging.error(f"Gemini API rate limit exhausted after {max_retries} retries: {e}")
            else:
                logging.error(f"Gemini API error: {e}")
            raise
    
    raise RuntimeError("Unexpected: exhausted retries without raising")


# Escape characters we KEEP as valid JSON escapes.
# We intentionally omit  b  f  t  because Gemini almost always means
# \beta, \frac, \text (LaTeX) rather than backspace / form-feed / tab.
# We keep  "  \\  /  n  r  u  which are structurally used in JSON.
_VALID_JSON_ESCAPES = frozenset('"\\nru/')

def _sanitize_json_escapes(text: str) -> str:
    """
    Fix invalid JSON escape sequences produced by Gemini when it embeds LaTeX
    inside JSON string values (e.g. \\ce{}, \\sigma, \\frac, \\beta, \\text).

    Strategy: Walk through the string character-by-character, tracking whether
    we are inside a JSON string literal.  For every backslash inside a string
    that is NOT followed by a character we want to keep as a real JSON escape,
    we double it so json.loads() treats it as a literal backslash.
    """
    result = []
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        if not in_string:
            result.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        # Inside a JSON string
        if ch == '"':
            # End of string
            result.append(ch)
            in_string = False
            i += 1
            continue

        if ch == '\\':
            # Look at what follows the backslash
            if i + 1 < n:
                next_ch = text[i + 1]
                if next_ch in _VALID_JSON_ESCAPES:
                    # This is a valid JSON escape — keep as is
                    result.append(ch)
                    result.append(next_ch)
                    # If it's \u, also copy the 4 hex digits
                    if next_ch == 'u' and i + 5 < n:
                        result.append(text[i+2:i+6])
                        i += 6
                    else:
                        i += 2
                else:
                    # Invalid escape (LaTeX like \c, \s, \a, \f, \t, \b ...)
                    # Double the backslash so json.loads treats it as literal \
                    result.append('\\\\')
                    i += 1
            else:
                # Trailing backslash at end of text — double it
                result.append('\\\\')
                i += 1
            continue

        result.append(ch)
        i += 1

    return ''.join(result)
