"""
Figure Detector - Detects figures/diagrams on PDF page images using Gemini.

Processes ONE page at a time for accuracy (following the proven pattern
from ImageBasedExtraction/step3_detect_question_boxes.py).

Usage:
    # Option 1: With GeminiClient (Vertex AI - supports gemini-3-pro-preview)
    from gemini_client import GeminiClient
    client = GeminiClient(config)
    detector = FigureDetector(gemini_client=client, model_id="gemini-3-pro-preview")
    
    # Option 2: With API key (supports gemini-2.5-flash, gemini-2.0-flash-exp)
    detector = FigureDetector(model_id="gemini-2.5-flash")
    
    figures = detector.detect_figures_on_page(image, page_number=1)
    all_figures = detector.detect_figures_batch(images, start_page=37)
"""

import json
import os
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Union, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from PIL import Image

# Type hint for GeminiClient without importing (avoids circular imports)
if TYPE_CHECKING:
    from gemini_client import GeminiClient

logger = logging.getLogger(__name__)


@dataclass
class DetectedFigure:
    """Represents a detected figure or question block on a page."""
    box_2d: List[int]  # [ymin, xmin, ymax, xmax] in 0-1000 scale
    label: str  # Figure label OR question_id for question blocks
    figure_type: str  # Figure type OR visual_type for question blocks
    position: str  # top, middle, bottom, top_of_page, OR 'question_block'
    page_number: int  # 1-indexed for display
    page_index: int   # 0-indexed for array access
    associated_text: str = ""  # Associated text OR sub_parts for question blocks
    # Question block specific fields
    continues_to_next: bool = False  # Block continues to next page
    continued_from_previous: bool = False  # Block started on previous page
    
    def to_dict(self) -> dict:
        result = {
            "box_2d": self.box_2d,
            "label": self.label,
            "type": self.figure_type,
            "position": self.position,
            "page_number": self.page_number,
            "page_index": self.page_index,
            "associated_text": self.associated_text
        }
        # Include continuation fields if set (for question blocks)
        if self.continues_to_next:
            result["continues_to_next"] = True
        if self.continued_from_previous:
            result["continued_from_previous"] = True
        return result


@dataclass 
class FigureDetectorConfig:
    """Configuration for FigureDetector."""
    model_id: str = "gemini-2.5-flash"  # Default to API-key compatible model
    temperature: float = 0.1
    max_output_tokens: int = 8192
    max_retries: int = 3
    rate_limit_delay: float = 2.0
    api_key_env: str = "GOOGLE_API_KEY"
    
    # Safety buffer in normalized space (0-1000)
    top_buffer: int = 10
    bottom_buffer: int = 15  # Larger bottom buffer to capture full content
    left_buffer: int = 5
    right_buffer: int = 5
    
    # Detection mode: "figure_only" or "question_block"
    detection_mode: str = "question_block"


class FigureDetector:
    """
    Detects figures and diagrams on PDF page images using Gemini vision model.
    
    Processes one page at a time for maximum accuracy.
    
    Supports two modes:
    1. GeminiClient mode (Vertex AI) - For models like gemini-3-pro-preview
    2. API key mode - For models like gemini-2.5-flash
    """
    
    def __init__(
        self, 
        config: Optional[FigureDetectorConfig] = None,
        gemini_client: Optional["GeminiClient"] = None,
        model_id: Optional[str] = None
    ):
        """
        Initialize the figure detector.
        
        Args:
            config: Configuration options. If None, uses defaults.
            gemini_client: Optional GeminiClient for Vertex AI mode.
                          If provided, uses Vertex AI authentication.
            model_id: Override model_id (takes precedence over config)
        """
        self.config = config or FigureDetectorConfig()
        self._gemini_client = gemini_client
        self._api_model = None
        self._prompt = None
        
        # Override model_id if provided
        if model_id:
            self.config.model_id = model_id
            
        # Log which mode we're using
        if self._gemini_client:
            logger.info(f"FigureDetector using Vertex AI mode with model: {self.config.model_id}")
        else:
            logger.info(f"FigureDetector using API key mode with model: {self.config.model_id}")
        
    def _get_api_model(self):
        """Lazy-load Gemini model for API key mode."""
        if self._api_model is None:
            import google.generativeai as genai
            
            api_key = os.getenv(self.config.api_key_env)
            if not api_key:
                raise ValueError(f"API key not found in env: {self.config.api_key_env}")
            
            genai.configure(api_key=api_key)
            
            generation_config = {
                "temperature": self.config.temperature,
                "max_output_tokens": self.config.max_output_tokens,
                "response_mime_type": "application/json",
            }
            
            self._api_model = genai.GenerativeModel(
                self.config.model_id,
                generation_config=generation_config
            )
            logger.info(f"Initialized Gemini API model: {self.config.model_id}")
            
        return self._api_model
            
        return self._model
    
    def _get_prompt(self) -> str:
        """Load the appropriate detection prompt based on mode."""
        if self._prompt is None:
            # Choose prompt based on detection mode
            if self.config.detection_mode == "question_block":
                prompt_file = "question_block_detection_prompt.md"
            else:
                prompt_file = "figure_detection_prompt.md"
            
            prompt_path = Path(__file__).parent / "prompts" / prompt_file
            if prompt_path.exists():
                self._prompt = prompt_path.read_text(encoding='utf-8')
                logger.info(f"Loaded prompt: {prompt_file}")
            else:
                # Fallback minimal prompt for question blocks
                self._prompt = """
                Analyze this page image and find FULL QUESTION BLOCKS that contain visual elements.
                
                For each question with figures/diagrams, output:
                - question_id: The question number (e.g., "8.4")
                - box_2d: [ymin, xmin, ymax, xmax] in 0-1000 normalized scale
                  - Start from the question NUMBER
                  - Include ALL text and figures for that question
                  - Stop before the next question starts
                - visual_type: CHEM_STRUCTURE, DIAGRAM, GRAPH, CIRCUIT, TABLE, FREE_BODY, or OTHER
                - sub_parts: Label range like "(a)-(f)" if applicable
                - continues_to_next: true if question continues to next page
                - continued_from_previous: true if this is a continuation
                
                Output JSON: {"question_blocks": [...]}
                """
        return self._prompt
    
    def _apply_safety_buffer(self, figures: List[Dict]) -> List[Dict]:
        """
        Expand bounding boxes slightly to prevent cutting off edges.
        Applied in normalized space (0-1000).
        """
        for fig in figures:
            bbox = fig.get('box_2d', [])
            if len(bbox) == 4:
                ymin, xmin, ymax, xmax = bbox
                
                # Expand with buffer
                ymin = max(0, ymin - self.config.top_buffer)
                xmin = max(0, xmin - self.config.left_buffer)
                ymax = min(1000, ymax + self.config.bottom_buffer)
                xmax = min(1000, xmax + self.config.right_buffer)
                
                fig['box_2d'] = [ymin, xmin, ymax, xmax]
        
        return figures
    
    def _parse_response(self, response_text: str) -> Dict:
        """Parse JSON response from Gemini."""
        text = response_text.strip()
        
        # Remove markdown code blocks if present
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            text = text.split('```')[1].split('```')[0]
        
        return json.loads(text)
    
    def _call_model(self, prompt: str, image: Image.Image) -> str:
        """
        Call the Gemini model with prompt and image.
        
        Uses GeminiClient (Vertex AI) if available, otherwise falls back to API key.
        
        Returns:
            Response text from the model
        """
        if self._gemini_client:
            # Vertex AI mode - use GeminiClient
            # Import here to get the model config class
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent.parent / "SchoolDataExtraction" / "MultiStep"))
            from gemini_client import GeminiModelConfig
            
            model_config = GeminiModelConfig(
                model_id=self.config.model_id,
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_output_tokens,
                response_mime_type="application/json",
            )
            
            result = self._gemini_client.generate_with_images(
                model_config=model_config,
                prompt=prompt,
                images=[image],
            )
            return result.text
        else:
            # API key mode
            model = self._get_api_model()
            response = model.generate_content([prompt, image])
            return response.text
    
    def detect_figures_on_page(
        self, 
        image: Union[Image.Image, Path, str],
        page_number: int,
        page_index: int = 0
    ) -> List[DetectedFigure]:
        """
        Detect figures or question blocks on a single page image.
        
        Args:
            image: PIL Image, or path to image file
            page_number: 1-indexed page number (for display/logging)
            page_index: 0-indexed position in the batch (for array access)
            
        Returns:
            List of DetectedFigure objects
        """
        mode = self.config.detection_mode
        logger.info(f"Detecting {mode} on page {page_number}")
        
        # Load image if path provided
        if isinstance(image, (str, Path)):
            image = Image.open(image)
        
        prompt = self._get_prompt()
        
        for attempt in range(self.config.max_retries):
            try:
                response_text = self._call_model(prompt, image)
                result = self._parse_response(response_text)
                
                # Extract data based on detection mode
                if mode == "question_block":
                    # New format: question_blocks
                    blocks_data = result.get('question_blocks', [])
                    blocks_data = self._apply_safety_buffer(blocks_data)
                    
                    figures = []
                    for block in blocks_data:
                        detected = DetectedFigure(
                            box_2d=block.get('box_2d', [0, 0, 0, 0]),
                            label=block.get('question_id', 'unknown'),
                            figure_type=block.get('visual_type', 'OTHER'),
                            position='question_block',
                            page_number=page_number,
                            page_index=page_index,
                            associated_text=block.get('sub_parts', '')
                        )
                        # Store additional fields for question blocks
                        detected.continues_to_next = block.get('continues_to_next', False)
                        detected.continued_from_previous = block.get('continued_from_previous', False)
                        figures.append(detected)
                else:
                    # Original format: figures
                    figures_data = result.get('figures', [])
                    figures_data = self._apply_safety_buffer(figures_data)
                    
                    figures = []
                    for fig in figures_data:
                        detected = DetectedFigure(
                            box_2d=fig.get('box_2d', [0, 0, 0, 0]),
                            label=fig.get('label', 'unlabeled'),
                            figure_type=fig.get('type', 'OTHER'),
                            position=fig.get('position', 'middle'),
                            page_number=page_number,
                            page_index=page_index,
                            associated_text=fig.get('associated_text', '')
                        )
                        figures.append(detected)
                
                logger.info(f"  Found {len(figures)} {mode}s on page {page_number}")
                
                # Rate limiting
                time.sleep(self.config.rate_limit_delay)
                
                return figures
                
            except json.JSONDecodeError as e:
                logger.warning(f"  Attempt {attempt + 1}: JSON parse error: {e}")
            except Exception as e:
                logger.warning(f"  Attempt {attempt + 1} failed: {e}")
            
            if attempt < self.config.max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
        
        logger.error(f"Failed to detect {mode} on page {page_number} after {self.config.max_retries} attempts")
        return []
    
    def detect_figures_batch(
        self,
        images: List[Union[Image.Image, Path, str]],
        start_page: int = 1
    ) -> List[DetectedFigure]:
        """
        Detect figures on multiple page images.
        
        Processes one page at a time for accuracy.
        
        Args:
            images: List of PIL Images or paths
            start_page: 1-indexed starting page number
            
        Returns:
            Combined list of all detected figures
        """
        all_figures = []
        
        for idx, image in enumerate(images):
            page_number = start_page + idx
            page_figures = self.detect_figures_on_page(
                image=image,
                page_number=page_number,
                page_index=idx
            )
            all_figures.extend(page_figures)
        
        logger.info(f"Total figures detected: {len(all_figures)} across {len(images)} pages")
        return all_figures
    
    def to_json(self, figures: List[DetectedFigure]) -> Dict:
        """Convert list of DetectedFigure to JSON-serializable dict."""
        return {
            "total_figures": len(figures),
            "figures": [f.to_dict() for f in figures]
        }
