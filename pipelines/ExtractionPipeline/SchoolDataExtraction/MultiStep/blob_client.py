"""
Azure Blob Storage Client for AryaBhatta E2E Pipeline.

This module provides Azure Blob Storage operations with:
- Azure Managed Identity authentication (DefaultAzureCredential)
- Connection string fallback for local development
- Upload images and return public URLs

Storage Account: stevaluationstorage
Container: onlineresources
"""

import os
import logging
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """Result of a blob upload operation."""
    local_path: str
    blob_name: str
    url: str
    success: bool
    error: Optional[str] = None


class BlobClient:
    """
    Azure Blob Storage client with Managed Identity support.
    
    Authentication priority:
    1. Azure Managed Identity (DefaultAzureCredential)
    2. Connection string from environment variable
    
    Usage:
        # With managed identity (production)
        client = BlobClient(use_managed_identity=True)
        
        # With connection string (local dev)
        client = BlobClient(connection_string="...")
        
        # Upload image
        url = client.upload_image(local_path, blob_path)
    """
    
    # Default configuration
    DEFAULT_ACCOUNT = "stevaluationstorage"
    DEFAULT_CONTAINER = "onlineresources"
    
    def __init__(
        self,
        account_name: Optional[str] = None,
        container_name: Optional[str] = None,
        connection_string: Optional[str] = None,
        use_managed_identity: bool = True
    ):
        """
        Initialize blob client.
        
        Args:
            account_name: Storage account name
            container_name: Container name
            connection_string: Full connection string (overrides other params)
            use_managed_identity: Use Azure DefaultAzureCredential for auth
        """
        self.account_name = account_name or os.environ.get("AZURE_STORAGE_ACCOUNT", self.DEFAULT_ACCOUNT)
        self.container_name = container_name or os.environ.get("AZURE_STORAGE_CONTAINER", self.DEFAULT_CONTAINER)
        self.connection_string = connection_string or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        self.use_managed_identity = use_managed_identity
        
        self._container_client = None
        
        logger.info(f"BlobClient initialized: account={self.account_name}, container={self.container_name}, "
                    f"managed_identity={use_managed_identity}")
    
    def _get_container_client(self):
        """Get or create container client."""
        if self._container_client:
            return self._container_client
        
        try:
            from azure.storage.blob import BlobServiceClient, ContainerClient
            
            if self.connection_string:
                logger.info("Connecting to blob storage using connection string")
                service_client = BlobServiceClient.from_connection_string(self.connection_string)
                self._container_client = service_client.get_container_client(self.container_name)
            
            elif self.use_managed_identity:
                logger.info("Connecting to blob storage using Managed Identity")
                from azure.identity import DefaultAzureCredential
                
                credential = DefaultAzureCredential()
                account_url = f"https://{self.account_name}.blob.core.windows.net"
                service_client = BlobServiceClient(account_url=account_url, credential=credential)
                self._container_client = service_client.get_container_client(self.container_name)
            
            else:
                raise ValueError("Either connection_string or use_managed_identity must be provided")
            
            logger.info(f"Connected to container: {self.container_name}")
            return self._container_client
            
        except Exception as e:
            logger.error(f"Failed to connect to blob storage: {e}")
            raise
    
    def download_blob(self, blob_path: str, local_path: str) -> bool:
        try:
            container_client = self._get_container_client()
            blob_client = container_client.get_blob_client(blob_path)
            with open(local_path, 'wb') as f:
                f.write(blob_client.download_blob().readall())
            return True
        except Exception as e:
            logger.error(f"Failed to download blob {blob_path}: {e}")
            return False

    def upload_image(
        self,
        local_path: Path,
        blob_path: str,
        content_type: str = "image/png",
        overwrite: bool = True
    ) -> str:
        """
        Upload an image to blob storage.
        
        Args:
            local_path: Local file path
            blob_path: Path in blob container (e.g., "questions/ch10/fig_10_15.png")
            content_type: MIME type of the file
            overwrite: Whether to overwrite existing blob
            
        Returns:
            Public URL of the uploaded blob
        """
        from azure.storage.blob import ContentSettings
        
        container_client = self._get_container_client()
        
        try:
            with open(local_path, "rb") as data:
                blob_client = container_client.get_blob_client(blob_path)
                
                blob_client.upload_blob(
                    data,
                    overwrite=overwrite,
                    content_settings=ContentSettings(content_type=content_type)
                )
            
            url = f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{blob_path}"
            logger.info(f"Uploaded: {local_path} -> {blob_path}")
            return url
            
        except Exception as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            raise
    
    def download_blob(self, blob_path: str, local_path: str) -> bool:
        try:
            container_client = self._get_container_client()
            blob_client = container_client.get_blob_client(blob_path)
            with open(local_path, 'wb') as f:
                f.write(blob_client.download_blob().readall())
            return True
        except Exception as e:
            logger.error(f"Failed to download blob {blob_path}: {e}")
            return False

    def upload_images_batch(
        self,
        uploads: List[tuple],  # List of (local_path, blob_path) tuples
        content_type: str = "image/png",
        overwrite: bool = True
    ) -> List[UploadResult]:
        """
        Upload multiple images in batch.
        
        Args:
            uploads: List of (local_path, blob_path) tuples
            content_type: MIME type for all files
            overwrite: Whether to overwrite existing blobs
            
        Returns:
            List of UploadResult objects
        """
        results = []
        
        for local_path, blob_path in uploads:
            try:
                url = self.upload_image(
                    Path(local_path),
                    blob_path,
                    content_type=content_type,
                    overwrite=overwrite
                )
                results.append(UploadResult(
                    local_path=str(local_path),
                    blob_name=blob_path,
                    url=url,
                    success=True
                ))
            except Exception as e:
                results.append(UploadResult(
                    local_path=str(local_path),
                    blob_name=blob_path,
                    url="",
                    success=False,
                    error=str(e)
                ))
        
        success_count = sum(1 for r in results if r.success)
        logger.info(f"Batch upload complete: {success_count}/{len(results)} successful")
        return results
    
    def blob_exists(self, blob_path: str) -> bool:
        """
        Check if a blob exists.
        
        Args:
            blob_path: Path in blob container
            
        Returns:
            True if blob exists, False otherwise
        """
        container_client = self._get_container_client()
        blob_client = container_client.get_blob_client(blob_path)
        return blob_client.exists()
    
    def get_blob_url(self, blob_path: str) -> str:
        """
        Get the URL for a blob (whether it exists or not).
        
        Args:
            blob_path: Path in blob container
            
        Returns:
            Blob URL
        """
        return f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{blob_path}"
    
    def delete_blob(self, blob_path: str) -> bool:
        """
        Delete a blob.
        
        Args:
            blob_path: Path in blob container
            
        Returns:
            True if deleted, False if not found
        """
        container_client = self._get_container_client()
        blob_client = container_client.get_blob_client(blob_path)
        
        try:
            blob_client.delete_blob()
            logger.info(f"Deleted blob: {blob_path}")
            return True
        except Exception as e:
            if "BlobNotFound" in str(e):
                logger.warning(f"Blob not found: {blob_path}")
                return False
            raise


# =============================================================================
# Helper Functions
# =============================================================================

def generate_blob_path(
    class_level: str,
    subject: str,
    chapter_number: str,
    question_ref: str,
    file_type: str = "figure"
) -> str:
    """
    Generate a standardized blob path for a question figure.
    
    Format: questions/{class}/{subject}/ch_{chapter_number}/{file_type}_{question_ref}.png
    
    Args:
        class_level: Class (e.g., '11', '12')
        subject: Subject name (e.g., 'Maths', 'Physics')
        chapter_number: Chapter number (e.g., '10', 'VII')
        question_ref: Question reference (e.g., '10.15')
        file_type: Type of file (figure, solution_diagram, etc.)
        
    Returns:
        Standardized blob path
    """
    # Sanitize for filename
    safe_ref = question_ref.replace(".", "_").replace(" ", "_")
    safe_chapter = chapter_number.replace(".", "_").replace(" ", "_")
    safe_subject = subject.replace(" ", "_")
    
    return f"questions/{class_level}/{safe_subject}/ch_{safe_chapter}/{file_type}_{safe_ref}.png"


def get_blob_client(use_managed_identity: bool = True) -> BlobClient:
    """
    Factory function to create blob client.
    
    Checks for connection string first, then falls back to managed identity.
    
    Args:
        use_managed_identity: Whether to use managed identity if no connection string
        
    Returns:
        Configured BlobClient
    """
    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    
    if connection_string:
        logger.info("Using storage connection string from environment")
        return BlobClient(connection_string=connection_string, use_managed_identity=False)
    
    elif use_managed_identity:
        logger.info("Using Azure Managed Identity for storage")
        return BlobClient(use_managed_identity=True)
    
    else:
        raise ValueError(
            "Blob storage not configured. Set AZURE_STORAGE_CONNECTION_STRING "
            "or use managed identity."
        )


# =============================================================================
# CLI for Testing
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test blob storage connectivity")
    parser.add_argument("--connection-string", help="Storage connection string")
    parser.add_argument("--upload", help="Path to file to upload")
    parser.add_argument("--blob-path", help="Destination blob path")
    parser.add_argument("--list", action="store_true", help="List blobs in container")
    args = parser.parse_args()
    
    client = BlobClient(
        connection_string=args.connection_string,
        use_managed_identity=not args.connection_string
    )
    
    try:
        if args.upload and args.blob_path:
            url = client.upload_image(Path(args.upload), args.blob_path)
            print(f"Uploaded: {url}")
        elif args.list:
            container = client._get_container_client()
            blobs = list(container.list_blobs(name_starts_with="questions/"))[:10]
            print(f"First 10 blobs in 'questions/':")
            for blob in blobs:
                print(f"  - {blob.name}")
        else:
            # Test connection
            client._get_container_client()
            print("Connection successful!")
    except Exception as e:
        print(f"Error: {e}")
        exit(1)

