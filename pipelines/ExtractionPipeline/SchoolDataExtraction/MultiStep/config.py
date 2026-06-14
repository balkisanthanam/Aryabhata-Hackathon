"""
Configuration management for the Multi-Step Pipeline.

Handles:
- Vertex AI authentication (for gemini-3-pro models)
- Model configurations for all 3 stages
- File paths and output settings
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path


# =============================================================================
# VERTEX AI CONFIGURATION - Set these before running
# =============================================================================
# Option 1: Set environment variables
#   set GOOGLE_CLOUD_PROJECT=your-project-id
#   set GOOGLE_CLOUD_LOCATION=us-central1
#
# Option 2: Set directly here
GOOGLE_CLOUD_PROJECT = "animated-rope-453904-j7"  # e.g., "my-gcp-project-123"
GOOGLE_CLOUD_LOCATION = "global"  # or your preferred region
# =============================================================================


@dataclass
class GeminiModelConfig:
    """Configuration for a specific Gemini model."""
    model_id: str
    temperature: float = 0.4
    max_output_tokens: Optional[int] = None
    top_p: float = 0.95
    top_k: Optional[int] = None
    response_modalities: list = field(default_factory=lambda: ["TEXT"])
    response_mime_type: Optional[str] = None  # "application/json" for structured output
    thinking_level: Optional[str] = None  # Gemini 3: "MINIMAL"|"LOW"|"MEDIUM"|"HIGH" — cap deliberation on mechanical tasks
    response_schema: Optional[Dict[str, Any]] = None  # Vertex JSON-mode schema — enforces field presence + types at generation time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API calls, excluding None values."""
        result = {
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        if self.max_output_tokens:
            result["max_output_tokens"] = self.max_output_tokens
        if self.top_k:
            result["top_k"] = self.top_k
        if self.response_mime_type:
            result["response_mime_type"] = self.response_mime_type
        return result


@dataclass
class CacheConfig:
    """Configuration for content caching."""
    enabled: bool = True
    ttl_seconds: int = 3600  # 1 hour default
    display_name_prefix: str = "multistep_pipeline"


@dataclass 
class PipelineConfig:
    """Main configuration for the Multi-Step Pipeline."""
    
    # Vertex AI Configuration (required for gemini-3-pro models)
    project_id: str = field(default_factory=lambda: GOOGLE_CLOUD_PROJECT or os.environ.get("GOOGLE_CLOUD_PROJECT", ""))
    location: str = field(default_factory=lambda: GOOGLE_CLOUD_LOCATION or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
    
    # Stage 2 - Solver Engine
    solver_model: GeminiModelConfig = field(default_factory=lambda: GeminiModelConfig(
        model_id="gemini-3.1-pro-preview",
        temperature=0.4,
    ))
    
    tutor_model: GeminiModelConfig = field(default_factory=lambda: GeminiModelConfig(
        model_id="gemini-3.1-pro-preview",
        temperature=0.6,
    ))
    
    formatter_model: GeminiModelConfig = field(default_factory=lambda: GeminiModelConfig(
        model_id="gemini-3-flash-preview",
        temperature=0.1,
        response_mime_type="application/json",
        thinking_level="LOW",  # Formatting is mechanical — cap thinking so Flash stays fast.
    ))
    
    # Stage 1 - Extraction Engine
    extraction_model: GeminiModelConfig = field(default_factory=lambda: GeminiModelConfig(
        model_id="gemini-3.1-pro-preview", 
        temperature=0.2,  # Low temp for consistent extraction
        response_mime_type="application/json",
        max_output_tokens=32768,  # Allow for long JSON + reasoning thoughts
    ))
    
    # Stage 1.5 - Detection Model (for exercise section detection - fast + cheap)
    detection_model: GeminiModelConfig = field(default_factory=lambda: GeminiModelConfig(
        model_id="gemini-3-flash-preview",  # Fast model for structure detection
        temperature=0.1,
        response_mime_type="application/json",
    ))
    
    # Stage 3 - Verification Engine (for future use)  
    verification_model: GeminiModelConfig = field(default_factory=lambda: GeminiModelConfig(
        model_id="gemini-2.0-flash",
        temperature=0.1,
        response_mime_type="application/json",
    ))
    
    # Caching
    cache: CacheConfig = field(default_factory=CacheConfig)
    
    # Batch Processing
    batch_size: int = 5  # Questions per batch
    batch_delay_seconds: float = 15.0  # Delay between Stage 2 batches to reduce rate-limit pressure
    quota_cooldown_seconds: float = 90.0  # Minimum cooldown after 429 responses
    cancellation_cooldown_seconds: float = 45.0  # Minimum cooldown after repeated 499 cancellations
    
    # Timeouts (in seconds)
    api_timeout_seconds: int = 600  # 10 minutes default for API calls
    
    # Output
    output_dir: Path = field(default_factory=lambda: Path(__file__).parent / "Output")
    save_images: bool = True
    image_subdir: str = "images"
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.project_id:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT not set. "
                "Set it in config.py or as environment variable."
            )
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """Create configuration from environment variables."""
        return cls()
    
    @classmethod
    def for_testing(cls, project_id: Optional[str] = None) -> "PipelineConfig":
        """Create a test configuration with relaxed settings."""
        return cls(
            project_id=project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project"),
            batch_size=2,
            batch_delay_seconds=1.0,
            quota_cooldown_seconds=5.0,
            cancellation_cooldown_seconds=3.0,
        )


# Convenience function for quick access
def get_config() -> PipelineConfig:
    """Get the default pipeline configuration."""
    return PipelineConfig.from_env()


def flash_assembly_config() -> PipelineConfig:
    """Flash Assembly Line config — solver+tutor on gemini-3-flash-preview.

    Formatter is already gemini-3-flash-preview (thinking=LOW) in the default
    PipelineConfig; only solver and tutor differ from the Pro default.
    Lifted verbatim from batch_evaluator.py A3.5 block so all consumers share
    one definition.
    """
    cfg = PipelineConfig()
    cfg.solver_model = GeminiModelConfig(model_id="gemini-3-flash-preview", temperature=0.4, max_output_tokens=32768)
    cfg.tutor_model  = GeminiModelConfig(model_id="gemini-3-flash-preview", temperature=0.6, max_output_tokens=32768)
    # formatter_model stays as configured (already gemini-3-flash-preview, thinking=LOW)
    return cfg
