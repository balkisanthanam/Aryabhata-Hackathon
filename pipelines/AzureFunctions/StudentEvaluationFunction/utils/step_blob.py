"""
Blob storage helpers for pipeline artifact persistence.
Saves large artifacts (images, PDFs, raw responses) to blob storage
so pipeline_steps JSONB stays lean.
"""
import logging
import os
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from utils.blob_storage import fetch_blob_content


# Storage settings come from the environment for public-safe configuration.
_STORAGE_ACCOUNT = os.environ.get("ARTIFACT_STORAGE_ACCOUNT", "<ARTIFACT_STORAGE_ACCOUNT>")
_CONTAINER = os.environ.get("ARTIFACT_CONTAINER", "<ARTIFACT_CONTAINER>")
_ARTIFACT_PREFIX = "pipeline-artifacts"

_blob_service_cache = None


def _get_blob_service() -> BlobServiceClient:
    """Get a cached BlobServiceClient with Managed Identity auth."""
    global _blob_service_cache
    if _blob_service_cache is None:
        account_url = f"https://{_STORAGE_ACCOUNT}.blob.core.windows.net"
        credential = DefaultAzureCredential()
        _blob_service_cache = BlobServiceClient(account_url, credential=credential)
        logging.info(f"BlobServiceClient created for {account_url}")
    return _blob_service_cache


def save_artifact(
    job_id: str,
    step_name: str,
    filename: str,
    data_bytes: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """
    Upload an artifact to blob storage under a structured path.

    Path: {container}/{prefix}/{job_id}/{step_name}/{filename}
    Example: feedback/pipeline-artifacts/abc-123/split_student_hw/solution_0.jpg

    Args:
        job_id: UUID of the evaluation
        step_name: Pipeline step name
        filename: Artifact filename (e.g. "solution_0.jpg", "raw_response.json")
        data_bytes: Raw bytes to upload
        content_type: MIME type for the blob

    Returns:
        Full blob URL string
    """
    blob_path = f"{_ARTIFACT_PREFIX}/{job_id}/{step_name}/{filename}"

    service = _get_blob_service()
    container_client = service.get_container_client(_CONTAINER)
    blob_client = container_client.get_blob_client(blob_path)

    blob_client.upload_blob(
        data_bytes,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )

    blob_url = blob_client.url
    logging.info(f"Artifact saved: {blob_path} ({len(data_bytes)} bytes)")
    return blob_url


def load_artifact(blob_url: str) -> bytes:
    """
    Fetch artifact bytes from blob storage.
    Delegates to the existing fetch_blob_content utility.

    Args:
        blob_url: Full blob URL

    Returns:
        Raw bytes
    """
    return fetch_blob_content(blob_url, as_text=False)
