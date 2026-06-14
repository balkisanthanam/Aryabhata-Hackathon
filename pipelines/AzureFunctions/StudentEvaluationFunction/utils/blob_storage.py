"""
Azure Blob Storage access with Managed Identity + public fallback.
Extracted from function_app.py.
"""
import logging
import requests
from azure.identity import DefaultAzureCredential
from typing import Union


def fetch_blob_content(blob_url: str, as_text: bool = True) -> Union[str, bytes]:
    """
    Fetch content from Azure Blob Storage using Managed Identity with fallback to public access.
    
    Args:
        blob_url: The full blob URL
        as_text: If True, decode as UTF-8 text; if False, return raw bytes
    
    Returns:
        Text string or bytes depending on as_text parameter
    """
    try:
        # Try using Managed Identity first (for production)
        if "blob.core.windows.net" in blob_url:
            try:
                from azure.storage.blob import BlobClient
                credential = DefaultAzureCredential()
                blob_client = BlobClient.from_blob_url(blob_url, credential=credential)
                content = blob_client.download_blob().readall()
                return content.decode("utf-8") if as_text else content
            except Exception as auth_error:
                logging.warning(
                    f"Managed Identity auth failed for {blob_url}, trying public access: {auth_error}"
                )

        # Fall back to public access
        response = requests.get(blob_url, timeout=30)
        response.raise_for_status()
        return response.text if as_text else response.content
    except Exception as e:
        logging.error(f"Error fetching blob from {blob_url}: {e}")
        raise


def fetch_image_from_url(image_url: str) -> bytes:
    """
    Fetch image bytes from a URL (blob storage or public URL).
    
    Args:
        image_url: URL to the image
    
    Returns:
        Raw image bytes
    """
    return fetch_blob_content(image_url, as_text=False)
