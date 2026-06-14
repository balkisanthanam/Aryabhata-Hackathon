"""
Gemini Client Module - Modular interface for Google's Gemini API via Vertex AI.

Features:
- Vertex AI authentication (OAuth2) for gemini-3-pro models
- Content caching for large documents (PDFs)
- Batch processing with rate limiting
- Support for multimodal responses (text + images)
- Parameterized prompts passed from client
- Designed for reuse across all 3 pipeline stages
- Exponential backoff for rate limit handling (429 errors)
"""

import time
import random
import base64
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Generator, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from google import genai
from google.genai import types
from google.genai.errors import ClientError
import httpx

from config import PipelineConfig, GeminiModelConfig, CacheConfig

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Exponential backoff configuration
MAX_RETRIES = 5
INITIAL_DELAY_SECONDS = 10
MAX_DELAY_SECONDS = 300  # 5 minutes max
BACKOFF_MULTIPLIER = 2
JITTER_FACTOR = 0.1  # Add 10% random jitter


@dataclass
class GeneratedContent:
    """Container for generated content including text and images."""
    text: str
    images: List[Dict[str, Any]] = None  # [{filename, data, mime_type, caption}]
    
    def __post_init__(self):
        if self.images is None:
            self.images = []


@dataclass
class CachedDocument:
    """Represents a cached document in Gemini."""
    cache_name: str
    display_name: str
    file_uri: str
    created_at: datetime
    expires_at: datetime
    
    @property
    def is_expired(self) -> bool:
        return datetime.now() >= self.expires_at


class GeminiClient:
    """
    Modular Gemini API client with Vertex AI authentication, caching, and batch support.
    
    Uses Vertex AI for gemini-3-pro models which require OAuth2 authentication.
    Requires: gcloud auth application-default login
    
    Usage:
        client = GeminiClient(config)
        
        # Simple generation
        result = client.generate(model_config, prompt, pdf_path)
        
        # With caching (for repeated calls on same document)
        cache = client.cache_document(pdf_path)
        result = client.generate_with_cache(model_config, prompt, cache)
        
        # Batch processing
        results = client.generate_batch(model_config, prompts, pdf_path)
    """
    
    def __init__(self, config: PipelineConfig):
        """Initialize the client with Vertex AI configuration."""
        self.config = config
        
        # Configure HTTP options with timeout
        http_options = types.HttpOptions(
            timeout=config.api_timeout_seconds * 1000,  # Convert to milliseconds
        )
        
        # Initialize client with Vertex AI (project + location)
        # This uses Application Default Credentials (ADC)
        # Run: gcloud auth application-default login
        self._client = genai.Client(
            vertexai=True,
            project=config.project_id,
            location=config.location,
            http_options=http_options,
        )
        self._document_cache: Dict[str, CachedDocument] = {}
        self._uploaded_files: Dict[str, str] = {}  # path -> file_uri
        
        # text-embedding-004 requires a regional Vertex AI endpoint (not 'global').
        # We build a dedicated embed client to be independent of the generation client.
        import os
        embed_location = os.environ.get("VERTEX_EMBED_LOCATION", "us-central1")
        self._embed_client = genai.Client(
            vertexai=True,
            project=config.project_id,
            location=embed_location,
            http_options=http_options,
        )
        
        logger.info(f"GeminiClient initialized with Vertex AI (project={config.project_id}, location={config.location}, timeout={config.api_timeout_seconds}s)")
    
    def _should_retry(self, error: Exception) -> bool:
        """Check if the error is retryable (rate limit or transient)."""
        if isinstance(error, ClientError):
            # 429 = Rate limited, 503 = Service unavailable, 500 = Internal error
            # 499 = CANCELLED - transient server-side load shedding, safe to retry
            return error.code in (429, 499, 503, 500)
        # Network-level timeouts and connection resets are transient; retry them.
        if isinstance(error, (httpx.ReadTimeout, httpx.ConnectTimeout,
                               httpx.RemoteProtocolError, httpx.ConnectError)):
            return True
        return False

    def _get_error_code(self, error: Exception) -> Optional[int]:
        """Extract an API error code when available."""
        if isinstance(error, ClientError):
            return error.code
        return getattr(error, "code", None)
    
    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate backoff delay with exponential growth and jitter."""
        delay = min(
            INITIAL_DELAY_SECONDS * (BACKOFF_MULTIPLIER ** attempt),
            MAX_DELAY_SECONDS
        )
        # Add jitter to prevent thundering herd
        jitter = delay * JITTER_FACTOR * random.random()
        return delay + jitter
    
    def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Execute a function with exponential backoff on retryable errors.
        
        Args:
            func: The function to execute
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            The result of the function call
            
        Raises:
            The last exception if all retries are exhausted
        """
        last_exception = None
        
        for attempt in range(MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if not self._should_retry(e):
                    # Non-retryable error, raise immediately
                    raise
                
                if attempt == MAX_RETRIES:
                    # Last attempt failed
                    logger.error(f"All {MAX_RETRIES} retries exhausted. Last error: {e}")
                    raise
                
                # Calculate backoff with minimum cool-downs for quota/load shedding.
                delay = self._calculate_backoff(attempt)
                error_code = self._get_error_code(e)
                if error_code == 429:
                    delay = max(delay, self.config.quota_cooldown_seconds)
                elif error_code == 499:
                    delay = max(delay, self.config.cancellation_cooldown_seconds)
                
                logger.warning(
                    f"Retryable error (attempt {attempt + 1}/{MAX_RETRIES + 1}): {type(e).__name__}"
                )
                logger.info(f"Waiting {delay:.1f}s before retry...")
                time.sleep(delay)
        
        # Should never reach here, but just in case
        raise last_exception
    
    def _upload_file(self, file_path: Path, mime_type: str = "application/pdf") -> str:
        """
        Upload a file to Gemini and return its URI.
        Caches uploads to avoid re-uploading the same file.
        """
        path_key = str(file_path.resolve())
        
        if path_key in self._uploaded_files:
            logger.info(f"Using cached upload for: {file_path.name}")
            return self._uploaded_files[path_key]
        
        logger.info(f"Uploading file: {file_path.name}")
        
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        
        # For the new SDK, we pass bytes directly
        # The file_uri is managed internally by the API
        self._uploaded_files[path_key] = path_key  # Track that we've "uploaded"
        
        return path_key
    
    def _read_file_bytes(self, file_path: Path) -> bytes:
        """Read file as bytes."""
        with open(file_path, "rb") as f:
            return f.read()
            
    def _fetch_image_bytes(self, url: str) -> tuple[bytes, str]:
        """
        Fetch image bytes and mime type from URL.
        Falls back to authenticated Azure Blob download if public access is blocked.
        Returns: (image_bytes, mime_type)
        """
        try:
            # First try unauthenticated request
            img_response = httpx.get(url, timeout=15.0)
            img_response.raise_for_status()
            
            content_type = img_response.headers.get("content-type", "image/png")
            if ";" in content_type:
                content_type = content_type.split(";")[0].strip()
            return img_response.content, content_type
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409 and "blob.core.windows.net" in url:
                logger.info(f"Public access blocked (409) for {url}, attempting authenticated blob download...")
                try:
                    from azure.identity import DefaultAzureCredential
                    from azure.storage.blob import BlobClient
                    
                    credential = DefaultAzureCredential()
                    blob_client = BlobClient.from_blob_url(url, credential=credential)
                    
                    download_stream = blob_client.download_blob()
                    content = download_stream.readall()
                    
                    # Try to get mime type from blob properties, default to png
                    properties = blob_client.get_blob_properties()
                    content_type = properties.content_settings.content_type if properties.content_settings else "image/png"
                    if not content_type:
                        content_type = "image/png"
                        
                    return content, content_type
                except Exception as auth_err:
                    logger.error(f"Authenticated blob download failed: {auth_err}")
                    raise
            raise
    
    def generate(
        self,
        model_config: GeminiModelConfig,
        prompt: str,
        document_path: Optional[Path] = None,
        system_instruction: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
    ) -> GeneratedContent:
        """
        Generate content using Gemini.
        
        Args:
            model_config: Configuration for the model to use
            prompt: The user prompt (already parameterized by client)
            document_path: Optional PDF or image to include
            system_instruction: Optional system instruction
            
        Returns:
            GeneratedContent with text and any generated images
        """
        logger.info(f"Generating with model: {model_config.model_id}")
        
        # Build content parts
        contents = []
        
        if document_path:
            file_bytes = self._read_file_bytes(document_path)
            mime_type = self._get_mime_type(document_path)
            contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime_type))
        
        # Inline any figure images from Azure Blob storage
        if image_urls:
            fetched = 0
            for url in image_urls:
                if not url:
                    continue
                try:
                    img_bytes, content_type = self._fetch_image_bytes(url)
                    contents.append(types.Part.from_bytes(data=img_bytes, mime_type=content_type))
                    fetched += 1
                    logger.info(f"Inlined figure image: {url[:80]}")
                except Exception as img_err:
                    logger.warning(f"Could not fetch figure image {url[:80]}: {img_err}")
            if fetched:
                logger.info(f"Attached {fetched} textbook figure(s) for visual context.")
        
        contents.append(types.Part.from_text(text=prompt))
        
        # Build generation config
        gen_config = types.GenerateContentConfig(
            temperature=model_config.temperature,
            top_p=model_config.top_p,
            response_modalities=model_config.response_modalities,
        )
        
        if system_instruction:
            gen_config.system_instruction = system_instruction
        
        if model_config.max_output_tokens:
            gen_config.max_output_tokens = model_config.max_output_tokens
            
        if model_config.response_mime_type:
            gen_config.response_mime_type = model_config.response_mime_type

        # Vertex JSON-mode schema — forces field presence + types in model output.
        # Particularly useful with tuned models that revert to base-model bias on schema.
        if getattr(model_config, "response_schema", None):
            gen_config.response_schema = model_config.response_schema

        # Cap deliberation on mechanical tasks (Gemini 3 thinking models default high).
        if getattr(model_config, "thinking_level", None):
            gen_config.thinking_config = types.ThinkingConfig(thinking_level=model_config.thinking_level)

        # Make the API call with exponential backoff for rate limits
        def _make_api_call():
            return self._client.models.generate_content(
                model=model_config.model_id,
                contents=contents,
                config=gen_config,
            )
        
        response = self._retry_with_backoff(_make_api_call)
        
        # Parse response
        return self._parse_response(response)
    
    def generate_batch(
        self,
        model_config: GeminiModelConfig,
        prompts: List[str],
        document_path: Optional[Path] = None,
        system_instruction: Optional[str] = None,
        batch_size: Optional[int] = None,
        delay_seconds: Optional[float] = None,
    ) -> List[GeneratedContent]:
        """
        Generate content for multiple prompts in batches.
        
        Args:
            model_config: Configuration for the model
            prompts: List of prompts to process
            document_path: Optional document to include with each request
            system_instruction: Optional system instruction
            batch_size: Override default batch size
            delay_seconds: Override default delay between batches
            
        Returns:
            List of GeneratedContent, one per prompt
        """
        batch_size = batch_size or self.config.batch_size
        delay = delay_seconds or self.config.batch_delay_seconds
        
        results = []
        total_batches = (len(prompts) + batch_size - 1) // batch_size
        
        for batch_idx in range(0, len(prompts), batch_size):
            batch = prompts[batch_idx:batch_idx + batch_size]
            current_batch = batch_idx // batch_size + 1
            
            logger.info(f"Processing batch {current_batch}/{total_batches} ({len(batch)} prompts)")
            
            for prompt in batch:
                try:
                    result = self.generate(
                        model_config=model_config,
                        prompt=prompt,
                        document_path=document_path,
                        system_instruction=system_instruction,
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error generating content: {e}")
                    results.append(GeneratedContent(text=f"ERROR: {str(e)}", images=[]))
            
            # Delay between batches to avoid rate limits
            if current_batch < total_batches:
                logger.info(f"Waiting {delay}s before next batch...")
                time.sleep(delay)
        
        return results
    
    def _parse_response(self, response) -> GeneratedContent:
        """Parse Gemini response into GeneratedContent."""
        text_buffer = ""
        images = []
        image_counter = 1
        
        if not response.candidates:
            logger.warning("No candidates in response")
            return GeneratedContent(text="", images=[])

        candidate = response.candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) if content is not None else None
        if not parts:
            # Thinking models can return a candidate with no output parts when the
            # token budget is exhausted mid-reasoning (MAX_TOKENS) or the response is
            # blocked (SAFETY/RECITATION). Surface the reason instead of crashing.
            logger.warning(f"Candidate has no output parts (finish_reason={finish_reason})")
            return GeneratedContent(text="", images=[])

        for part in parts:
            if hasattr(part, 'text') and part.text:
                text_buffer += part.text
                
            if hasattr(part, 'inline_data') and part.inline_data:
                mime_type = part.inline_data.mime_type
                image_data = part.inline_data.data
                
                ext = mime_type.split("/")[-1] if "/" in mime_type else "png"
                filename = f"generated_image_{image_counter}.{ext}"
                
                images.append({
                    "filename": filename,
                    "data": image_data,
                    "mime_type": mime_type,
                    "index": image_counter,
                })
                
                logger.info(f"Extracted generated image: {filename}")
                image_counter += 1
        
        return GeneratedContent(text=text_buffer, images=images)
    
    def _get_mime_type(self, file_path: Path) -> str:
        """Determine MIME type from file extension."""
        ext = file_path.suffix.lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_types.get(ext, "application/octet-stream")
    
    # =========================================================================
    # Caching Support (for Stage 2 optimization with large PDFs)
    # =========================================================================
    
    def cache_document(
        self,
        document_path: Path,
        model_id: str,
        ttl_seconds: Optional[int] = None,
        display_name: Optional[str] = None,
    ) -> CachedDocument:
        """
        Cache a document for repeated use with the same model.
        
        Note: Content caching is model-specific in Gemini.
        This is useful for Stage 2 where we query the same chapter multiple times.
        
        Args:
            document_path: Path to the document to cache
            model_id: Model to cache for
            ttl_seconds: Time-to-live in seconds
            display_name: Optional display name for the cache
            
        Returns:
            CachedDocument with cache metadata
        """
        ttl = ttl_seconds or self.config.cache.ttl_seconds
        name = display_name or f"{self.config.cache.display_name_prefix}_{document_path.stem}"
        
        path_key = str(document_path.resolve())
        
        # Check if we already have a valid cache
        if path_key in self._document_cache:
            cached = self._document_cache[path_key]
            if not cached.is_expired:
                logger.info(f"Using existing cache: {cached.display_name}")
                return cached
        
        logger.info(f"Creating cache for: {document_path.name} (TTL: {ttl}s)")
        
        # Read file
        file_bytes = self._read_file_bytes(document_path)
        mime_type = self._get_mime_type(document_path)
        
        # Create cached content using the caching API
        try:
            cached_content = self._client.caches.create(
                model=model_id,
                config=types.CreateCachedContentConfig(
                    contents=[
                        types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
                    ],
                    display_name=name,
                    ttl=f"{ttl}s",
                ),
            )
            
            created_at = datetime.now()
            expires_at = created_at + timedelta(seconds=ttl)
            
            cached_doc = CachedDocument(
                cache_name=cached_content.name,
                display_name=name,
                file_uri=path_key,
                created_at=created_at,
                expires_at=expires_at,
            )
            
            self._document_cache[path_key] = cached_doc
            logger.info(f"Cache created: {cached_content.name}")
            
            return cached_doc
            
        except Exception as e:
            logger.warning(f"Caching not available or failed: {e}")
            logger.info("Falling back to direct file upload")
            # Return a "fake" cache that will trigger direct upload
            return CachedDocument(
                cache_name="",
                display_name=name,
                file_uri=path_key,
                created_at=datetime.now(),
                expires_at=datetime.now(),  # Immediately expired = use direct upload
            )
    
    def generate_with_cache(
        self,
        model_config: GeminiModelConfig,
        prompt: str,
        cached_doc: CachedDocument,
        system_instruction: Optional[str] = None,
    ) -> GeneratedContent:
        """
        Generate content using a cached document.
        
        If cache is expired or invalid, falls back to direct upload.
        """
        # If cache is expired or invalid, use direct generation
        if cached_doc.is_expired or not cached_doc.cache_name:
            logger.info("Cache expired/invalid, using direct generation")
            return self.generate(
                model_config=model_config,
                prompt=prompt,
                document_path=Path(cached_doc.file_uri),
                system_instruction=system_instruction,
            )
        
        logger.info(f"Generating with cache: {cached_doc.display_name}")
        
        # Build generation config
        gen_config = types.GenerateContentConfig(
            temperature=model_config.temperature,
            top_p=model_config.top_p,
            response_modalities=model_config.response_modalities,
            cached_content=cached_doc.cache_name,
        )
        
        if system_instruction:
            # Vertex AI caching prohibits 'system_instruction' in generate_content
            # requests using cached content. We prepend it to the prompt instead.
            prompt = f"System Instructions:\n{system_instruction}\n\nUser Request:\n{prompt}"
            
        if model_config.max_output_tokens:
            gen_config.max_output_tokens = model_config.max_output_tokens
            
        if model_config.response_mime_type:
            gen_config.response_mime_type = model_config.response_mime_type
        
        # Make API call with cache (with backoff for rate limits)
        def _make_api_call():
            return self._client.models.generate_content(
                model=model_config.model_id,
                contents=[types.Part.from_text(text=prompt)],
                config=gen_config,
            )

        try:
            response = self._retry_with_backoff(_make_api_call)
        except (ClientError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            # Server-side cache expiry (400) or request timeout — re-create the
            # cache and retry once. We evict the stale local entry first so
            # cache_document creates a fresh one rather than returning the expired ref.
            is_cache_expired = isinstance(e, ClientError) and e.code == 400 and "expired" in str(e).lower()
            is_timeout = isinstance(e, (httpx.ReadTimeout, httpx.ConnectTimeout))
            if not (is_cache_expired or is_timeout):
                raise
            logger.warning(
                f"{'Cache expired server-side' if is_cache_expired else 'Request timed out'}; "
                "re-creating cache and retrying once."
            )
            path_key = str(Path(cached_doc.file_uri).resolve())
            self._document_cache.pop(path_key, None)  # evict stale local entry
            new_cached_doc = self.cache_document(
                document_path=Path(cached_doc.file_uri),
                model_id=model_config.model_id,
            )
            gen_config.cached_content = new_cached_doc.cache_name
            response = self._retry_with_backoff(_make_api_call)

        return self._parse_response(response)
    
    def clear_cache(self, cached_doc: Optional[CachedDocument] = None):
        """Clear a specific cache or all caches."""
        if cached_doc:
            if cached_doc.cache_name:
                try:
                    self._client.caches.delete(name=cached_doc.cache_name)
                    logger.info(f"Deleted cache: {cached_doc.cache_name}")
                except Exception as e:
                    logger.warning(f"Failed to delete cache: {e}")
            
            # Remove from local tracking
            if cached_doc.file_uri in self._document_cache:
                del self._document_cache[cached_doc.file_uri]
        else:
            # Clear all caches
            for doc in list(self._document_cache.values()):
                self.clear_cache(doc)
            self._document_cache.clear()
            logger.info("Cleared all caches")
    
    # =========================================================================
    # Image-based Generation (for Stage 1 - Question Extraction)
    # =========================================================================
    
    def generate_with_images(
        self,
        model_config: GeminiModelConfig,
        prompt: str,
        images: List["Image.Image"],  # PIL Images
        system_instruction: Optional[str] = None,
    ) -> GeneratedContent:
        """
        Generate content with one or more images as input.
        
        Used by Stage 1 for extracting questions from page images.
        Supports the sliding window approach (current + next page).
        
        Args:
            model_config: Configuration for the model
            prompt: The extraction prompt
            images: List of PIL Image objects (typically 1-2 pages)
            system_instruction: Optional system instruction
            
        Returns:
            GeneratedContent with extracted text (JSON)
        """
        import io
        
        logger.info(f"Generating with {len(images)} images using model: {model_config.model_id}")
        
        # Build content parts - images first, then prompt
        contents = []
        
        for idx, img in enumerate(images):
            # Convert PIL Image to bytes
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="PNG")
            img_bytes = img_buffer.getvalue()
            
            contents.append(types.Part.from_bytes(
                data=img_bytes,
                mime_type="image/png"
            ))
            logger.debug(f"Added image {idx + 1}: {img.size[0]}x{img.size[1]}")
        
        # Add prompt after images
        contents.append(types.Part.from_text(text=prompt))
        
        # Build generation config
        gen_config = types.GenerateContentConfig(
            temperature=model_config.temperature,
            top_p=model_config.top_p,
        )
        
        if system_instruction:
            gen_config.system_instruction = system_instruction
        
        if model_config.max_output_tokens:
            gen_config.max_output_tokens = model_config.max_output_tokens
            
        if model_config.response_mime_type:
            gen_config.response_mime_type = model_config.response_mime_type
        
        # Make the API call (with backoff for rate limits)
        def _make_api_call():
            return self._client.models.generate_content(
                model=model_config.model_id,
                contents=contents,
                config=gen_config,
            )
        
        response = self._retry_with_backoff(_make_api_call)
        
        return self._parse_response(response)
    
    # =========================================================================
    # Embedding (for Smart Context Retrieval)
    # =========================================================================
    
    def embed_text(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
        output_dimensionality: int = 768,
        model_id: str = "text-embedding-004",
    ) -> List[float]:
        """
        Create a 768-dim embedding for text.
        Used for PgVector similarity search in Smart Context querying.
        """
        def _api_call():
            return self._embed_client.models.embed_content(
                model=model_id,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=output_dimensionality,
                ),
            )

        response = self._retry_with_backoff(_api_call)
        
        # Extract values depending on SDK structure
        val = None
        if hasattr(response, "embeddings") and response.embeddings:
            first = response.embeddings[0]
            if hasattr(first, "values"): val = list(first.values)
            elif isinstance(first, dict) and "values" in first: val = list(first["values"])
        elif hasattr(response, "embedding") and response.embedding:
            emb = response.embedding
            if hasattr(emb, "values"): val = list(emb.values)
            elif isinstance(emb, dict) and "values" in emb: val = list(emb["values"])
            
        if not val or len(val) != output_dimensionality:
            raise ValueError(f"Could not extract valid {output_dimensionality}-dim embedding from response")
            
        return val

