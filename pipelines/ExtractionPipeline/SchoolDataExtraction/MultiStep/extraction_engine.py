"""
Stage 1: Question Extraction Engine - Extracts questions from textbook PDFs.

This module:
- Uses sliding window (Page N + Page N+1) to handle text/figure spill-overs
- Page N is PRIMARY: extract questions that START here
- Page N+1 is for SPILL-OVER only: complete questions, don't start new ones
- Extracts questions with LaTeX formulas, chemical equations, tables
- Captures figure bounding boxes with page tracking
- Crops and saves visual assets using PyMuPDF

Key Features:
- Auto-detects EXERCISES sections in PDFs using Gemini model
- Handles questions that spill across page boundaries
- Supports multiple exercise sections per chapter
- Outputs Question.json + cropped images
- Deduplicates questions by ID

Model: gemini-3-pro-image-preview (300 DPI, 1000x1000 coordinate system)
"""

import json
import re
import io
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
import logging

import fitz  # PyMuPDF
from PIL import Image

# Add path to shared module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from exercise_detector import ExerciseDetector, ExerciseSection as SharedExerciseSection

# Import shared FigureExtraction module for Pass 2
from FigureExtraction import FigureDetector, FigureCropper, FigureMatcher
from FigureExtraction.figure_detector import FigureDetectorConfig

from config import PipelineConfig, GeminiModelConfig
from gemini_client import GeminiClient, GeneratedContent

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class VisualMetadata:
    """Metadata for a visual asset (diagram, graph, chemical structure)."""
    type: str = "NONE"  # DIAGRAM | CHEM_STRUCTURE | GRAPH | NONE
    description: str = ""
    box_2d: Optional[List[int]] = None  # [ymin, xmin, ymax, xmax] on 0-1000 scale
    visual_source: Optional[str] = None  # "current_page" | "next_page"
    smiles: Optional[str] = None  # For chemical structures
    cropped_image_path: Optional[str] = None  # Path to saved cropped image
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SubQuestion:
    """Represents a sub-question (e.g., 9.15(a), 9.15(b))."""
    sub_id: str  # e.g., "a", "b", "i", "ii"
    text: str
    visual_data: Optional[VisualMetadata] = None


@dataclass
class ExtractedQuestion:
    """A fully extracted question with all metadata."""
    question_id: str  # e.g., "9.15", "12.4"
    question_text: str  # Full text with LaTeX and Markdown tables
    page_number: int  # Page where question starts
    visual_required: bool = False
    visual_data: VisualMetadata = field(default_factory=VisualMetadata)
    sub_questions: List[SubQuestion] = field(default_factory=list)
    figure_references: List[str] = field(default_factory=list)  # ["Fig 10.3", "Table 10.1"]
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "question_id": self.question_id,
            "question_text": self.question_text,
            "page_number": self.page_number,
            "visual_required": self.visual_required,
            "visual_data": self.visual_data.to_dict() if self.visual_required else None,
            "figure_references": self.figure_references if self.figure_references else None,
        }
        if self.sub_questions:
            result["sub_questions"] = [
                {
                    "sub_id": sq.sub_id,
                    "text": sq.text,
                    "visual_data": sq.visual_data.to_dict() if sq.visual_data else None,
                }
                for sq in self.sub_questions
            ]
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class ExerciseSection:
    """Represents an exercise section found in the PDF."""
    title: str  # e.g., "EXERCISES", "ADDITIONAL EXERCISES"
    start_page: int  # 0-indexed
    end_page: Optional[int] = None  # 0-indexed, None if unknown
    total_questions: Optional[int] = None  # From model or computed
    questions: List[ExtractedQuestion] = field(default_factory=list)  # Questions in this exercise


@dataclass
class ExtractionRequest:
    """Request to extract questions from a PDF."""
    pdf_path: Path
    page_range: Optional[Tuple[int, int]] = None  # (start, end) 0-indexed, None for auto-detect
    class_level: str = "11th"
    board: str = "CBSE"
    subject: str = "Physics"
    chapter_name: Optional[str] = None


@dataclass
class ExtractionResponse:
    """Response containing all extracted questions grouped by exercise."""
    request: ExtractionRequest
    questions: List[ExtractedQuestion]  # Flat list (for backward compat)
    exercise_sections: List[ExerciseSection]  # Now contains questions grouped by exercise
    raw_responses: List[str]  # Raw JSON from each page pair
    chapter_number: Optional[str] = None  # NEW: Chapter number extracted from PDF
    cropped_images_dir: Optional[Path] = None
    processing_time_seconds: float = 0.0
    model_used: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with exercise-grouped structure."""
        return {
            "metadata": {
                "pdf_file": str(self.request.pdf_path.name),
                "chapter_number": self.chapter_number,
                "class": self.request.class_level,
                "board": self.request.board,
                "subject": self.request.subject,
                "chapter": self.request.chapter_name,
                "total_questions": len(self.questions),
                "model": self.model_used,
                "processing_time_seconds": self.processing_time_seconds,
                "timestamp": self.timestamp,
            },
            "exercises": [
                {
                    "exercise_title": es.title,
                    "start_page": es.start_page + 1,
                    "end_page": (es.end_page or es.start_page) + 1,
                    "questions": [q.to_dict() for q in es.questions],
                }
                for es in self.exercise_sections
            ]
        }


# =============================================================================
# Extraction Engine
# =============================================================================

class ExtractionEngine:
    """
    Stage 1 Extraction Engine for extracting questions from PDF textbooks.
    
    Usage:
        engine = ExtractionEngine(config)
        
        # Extract from PDF (auto-detect exercise pages)
        response = engine.extract_from_pdf(
            pdf_path=Path("chapter.pdf"),
            subject="Physics"
        )
        
        # Extract from specific pages
        response = engine.extract_from_pdf(
            pdf_path=Path("chapter.pdf"),
            page_range=(20, 25),
            subject="Physics"
        )
        
        # Save results
        engine.save_questions(response, output_dir)
    """
    
    # Patterns for figure references in question text
    FIGURE_REF_PATTERNS = [
        r'Fig\.?\s*(\d+\.?\d*)',
        r'Figure\s*(\d+\.?\d*)',
        r'Table\s*(\d+\.?\d*)',
        r'diagram\s+(?:below|above|shown)',
        r'graph\s+(?:below|above|shown)',
    ]
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initialize the extraction engine."""
        self.config = config or PipelineConfig.from_env()
        self.client = GeminiClient(self.config)
        self._prompt_template: Optional[str] = None
        
        logger.info("ExtractionEngine initialized")
    
    def load_prompt_template(self, template_path: Path) -> str:
        """Load the extraction prompt template."""
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")
        
        self._prompt_template = template_path.read_text(encoding="utf-8")
        return self._prompt_template
    
    def extract_from_pdf(
        self,
        request: ExtractionRequest,
        prompt_template: Optional[str] = None,
    ) -> ExtractionResponse:
        """
        Extract questions from a PDF using sliding window approach.
        
        Args:
            request: ExtractionRequest with PDF path and options
            prompt_template: Optional prompt template (uses default if not provided)
            
        Returns:
            ExtractionResponse with all extracted questions
        """
        start_time = datetime.now()
        
        logger.info(f"Starting extraction from {request.pdf_path.name}")
        
        # Open PDF
        doc = fitz.open(request.pdf_path)
        total_pages = len(doc)
        logger.info(f"PDF has {total_pages} pages")
        
        # Determine page range
        if request.page_range:
            start_page, end_page = request.page_range
            page_indices = list(range(start_page, end_page + 1))
        else:
            # Auto-detect exercise sections using shared detector (PDF upload)
            exercise_sections = self._detect_exercise_sections(request.pdf_path)
            if exercise_sections:
                page_indices = sorted(
                    {
                        page_num
                        for section in exercise_sections
                        for page_num in range(section.start_page, (section.end_page or section.start_page) + 1)
                    }
                )
                start_page = page_indices[0]
                end_page = page_indices[-1]
                logger.info(
                    "Auto-detected exercise pages: %s",
                    ", ".join(str(page_num + 1) for page_num in page_indices),
                )
            else:
                logger.warning("No exercise sections detected, processing all pages")
                start_page = 0
                end_page = total_pages - 1
                page_indices = list(range(start_page, end_page + 1))
                exercise_sections = []
        
        # Store exercise sections for response
        if not request.page_range:
            detected_sections = exercise_sections
        else:
            detected_sections = [ExerciseSection(
                title="Manual Range",
                start_page=start_page,
                end_page=end_page,
            )]
        
        # Load prompt template
        prompt = prompt_template or self._prompt_template
        if not prompt:
            default_prompt_path = Path(__file__).parent / "extraction_prompt.md"
            if default_prompt_path.exists():
                prompt = self.load_prompt_template(default_prompt_path)
            else:
                raise ValueError("No prompt template provided or found")
        
        # Process pages with sliding window
        all_questions: List[ExtractedQuestion] = []
        raw_responses: List[str] = []
        seen_question_ids: Set[str] = set()
        
        for page_idx in page_indices:
            logger.info(f"Processing page {page_idx + 1}/{total_pages}")
            current_section = self._find_exercise_section_for_page(page_idx, detected_sections)
            
            # Render current page and next page (if exists)
            images = self._render_pages(doc, page_idx)
            
            # Call extraction model
            try:
                result = self._call_extraction_model(
                    images=images,
                    page_number=page_idx + 1,  # 1-indexed for display
                    has_next_page=(page_idx + 1 <= end_page),
                    prompt_template=prompt,
                )
                
                raw_responses.append(result.text)
                
                # Parse response
                questions = self._parse_extraction_response(
                    result.text,
                    page_number=page_idx + 1,
                    seen_ids=seen_question_ids,
                )
                
                # Add new questions (skip duplicates from previous page's look-ahead)
                for q in questions:
                    scoped_question_id = self._build_scoped_question_id(q.question_id, page_idx, current_section)
                    if scoped_question_id not in seen_question_ids:
                        if current_section:
                            q._exercise_title = current_section.title
                        all_questions.append(q)
                        seen_question_ids.add(scoped_question_id)
                        logger.info(f"  Extracted: {q.question_id}")
                
            except Exception as e:
                logger.error(f"Error processing page {page_idx + 1}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                continue
        
        doc.close()
        
        # Crop visuals
        cropped_dir = None
        if any(q.visual_required for q in all_questions):
            cropped_dir = self._crop_all_visuals(request.pdf_path, all_questions)
        
        processing_time = (datetime.now() - start_time).total_seconds()

        exercise_sections_with_questions = self._assign_questions_to_sections(
            detected_sections,
            all_questions,
        )
        
        return ExtractionResponse(
            request=request,
            questions=all_questions,
            exercise_sections=exercise_sections_with_questions,
            raw_responses=raw_responses,
            cropped_images_dir=cropped_dir,
            processing_time_seconds=processing_time,
            model_used=self.config.extraction_model.model_id,
        )

    # =========================================================================
    # Two-Pass Extraction (New Approach)
    # =========================================================================
    
    def extract_two_pass(
        self,
        request: ExtractionRequest,
        pass1_prompt_path: Optional[Path] = None,
        pass2_prompt_path: Optional[Path] = None,
    ) -> ExtractionResponse:
        """
        Extract questions using a two-pass approach for better reliability.
        
        Pass 1: Upload PDF → Extract text + LaTeX + flag figures (no bounding boxes)
        Pass 2: Send page images → Extract bounding boxes only for flagged questions
        Merge: Combine Pass 1 text with Pass 2 bounding boxes
        
        This approach:
        - Separates text extraction from visual detection
        - More reliable for complex content (chemistry structures)
        - Uses PDF upload for better context in Pass 1
        
        Args:
            request: ExtractionRequest with PDF path and metadata
            pass1_prompt_path: Optional path to Pass 1 prompt template
            pass2_prompt_path: Optional path to Pass 2 prompt template
            
        Returns:
            ExtractionResponse with all questions and cropped images
        """
        start_time = datetime.now()
        logger.info(f"=== Two-Pass Extraction: {request.pdf_path.name} ===")
        
        # Load prompts
        default_prompts_dir = Path(__file__).parent / "prompts"
        
        pass1_filename = "pass1_text_extraction.md"
        if request.subject and request.subject.lower() in ["maths", "mathematics", "math"]:
            pass1_filename = "pass1_text_extraction_math.md"
            
        pass1_prompt = self._load_prompt(
            pass1_prompt_path or default_prompts_dir / pass1_filename,
            request
        )
        pass2_prompt = self._load_prompt(
            pass2_prompt_path or default_prompts_dir / "pass2_box_extraction.md",
            request
        )
        
        # Open PDF to detect exercise pages
        doc = fitz.open(request.pdf_path)
        total_pages = len(doc)
        logger.info(f"PDF has {total_pages} pages")
        
        # Detect exercise sections
        if request.page_range:
            start_page, end_page = request.page_range
            page_indices = list(range(start_page, end_page + 1))
            exercise_sections = [ExerciseSection(
                title="Manual Range",
                start_page=start_page,
                end_page=end_page,
            )]
        else:
            exercise_sections = self._detect_exercise_sections(request.pdf_path)
            if not exercise_sections:
                logger.warning("No exercise sections detected")
                doc.close()
                return ExtractionResponse(
                    request=request,
                    questions=[],
                    exercise_sections=[],
                    raw_responses=["No exercise sections found"],
                    processing_time_seconds=(datetime.now() - start_time).total_seconds(),
                    model_used=self.config.extraction_model.model_id,
                )
            page_indices = sorted(
                {
                    page_num
                    for section in exercise_sections
                    for page_num in range(section.start_page, (section.end_page or section.start_page) + 1)
                }
            )
            start_page = page_indices[0]
            end_page = page_indices[-1]
        
        logger.info(
            "Processing exercise pages: %s",
            ", ".join(str(page_num + 1) for page_num in page_indices),
        )
        
        # Create temporary PDF with just exercise pages
        exercise_pdf_path = self._extract_exercise_pages_to_pdf(
            request.pdf_path, page_indices
        )
        
        # Pass 1: Extract text + figure flags from PDF
        logger.info("=== PASS 1: Text + Figure Flag Extraction ===")
        pass1_result = self._pass1_extract_text(
            exercise_pdf_path,
            pass1_prompt,
            request
        )
        
        # Parse Pass 1 results (new: returns exercise structure and chapter_number)
        pass1_questions, pass1_exercises, chapter_number, pass1_raw = self._parse_pass1_response(pass1_result.text)
        logger.info(f"Pass 1 extracted {len(pass1_questions)} questions in {len(pass1_exercises)} exercises, chapter={chapter_number}")
        logger.info(f"  Questions with figures: {sum(1 for q in pass1_questions if q.get('has_figure'))}")
        
        # Filter questions that need bounding boxes
        questions_with_figures = [q for q in pass1_questions if q.get('has_figure', False)]
        
        # Pass 2: Detect figures and match to questions using shared FigureExtraction
        pass2_raw = ""
        figure_boxes = {}
        detected_figures = []
        
        if questions_with_figures:
            logger.info(f"=== PASS 2: Figure Detection for {len(questions_with_figures)} questions ===")
            
            # Render all exercise pages as images
            exercise_images = self._render_page_list(doc, page_indices)
            
            # Call Pass 2 using shared FigureExtraction module (single-page-at-a-time)
            detected_figures, figure_boxes = self._pass2_extract_figures(
                exercise_images,
                questions_with_figures,
                page_indices
            )
            pass2_raw = json.dumps({"figures": detected_figures}, indent=2)
            
            logger.info(f"Pass 2 matched boxes for {len(figure_boxes)} questions")
        
        doc.close()
        
        # Clean up temporary PDF
        if exercise_pdf_path != request.pdf_path and exercise_pdf_path.exists():
            exercise_pdf_path.unlink()
        
        # Merge Pass 1 + Pass 2 into ExtractedQuestion objects
        all_questions = self._merge_passes(
            pass1_questions,
            figure_boxes,
            page_indices
        )
        logger.info(f"Merged: {len(all_questions)} total questions")
        
        # Build exercise_sections with nested questions
        exercise_sections_with_questions = self._build_exercise_sections(
            pass1_exercises,
            all_questions,
            start_page,
            end_page,
            detected_sections=exercise_sections  # Pass the Stage 0 bounds down
        )
        
        # Crop visuals
        cropped_dir = None
        if any(q.visual_required for q in all_questions):
            cropped_dir = self._crop_all_visuals(request.pdf_path, all_questions)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return ExtractionResponse(
            request=request,
            questions=all_questions,
            exercise_sections=exercise_sections_with_questions,
            raw_responses=[pass1_raw, pass2_raw] if pass2_raw else [pass1_raw],
            chapter_number=chapter_number,
            cropped_images_dir=cropped_dir,
            processing_time_seconds=processing_time,
            model_used=f"Pass1:{self.config.extraction_model.model_id}, Pass2:{self.config.extraction_model.model_id}",
        )
    
    def _load_prompt(self, prompt_path: Path, request: ExtractionRequest) -> str:
        """Load and parameterize a prompt template."""
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt not found: {prompt_path}")
        
        template = prompt_path.read_text(encoding='utf-8')
        
        # Substitute placeholders
        template = template.replace("{{BOARD}}", request.board)
        template = template.replace("{{CLASS}}", request.class_level)
        template = template.replace("{{SUBJECT}}", request.subject)
        
        return template
    
    def _extract_exercise_pages_to_pdf(
        self,
        pdf_path: Path,
        page_numbers: List[int]
    ) -> Path:
        """
        Extract specific pages from PDF to a new temporary PDF.
        
        Args:
            pdf_path: Original PDF path
            page_numbers: Page numbers to extract (0-indexed)
            
        Returns:
            Path to temporary PDF with just the exercise pages
        """
        output_dir = Path(__file__).parent / "Output"
        output_dir.mkdir(exist_ok=True)
        temp_pdf_path = output_dir / f"_temp_exercise_{pdf_path.stem}.pdf"
        
        doc = fitz.open(pdf_path)
        new_doc = fitz.open()
        
        for page_num in page_numbers:
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        
        new_doc.save(temp_pdf_path)
        new_doc.close()
        doc.close()
        
        logger.info(
            "Created temp PDF with pages %s: %s",
            ", ".join(str(page_num + 1) for page_num in page_numbers),
            temp_pdf_path.name,
        )
        return temp_pdf_path
    
    def _pass1_extract_text(
        self,
        pdf_path: Path,
        prompt: str,
        request: ExtractionRequest
    ) -> GeneratedContent:
        """
        Pass 1: Extract text and figure flags from PDF.
        
        Uses PDF file upload for full document context.
        Note: gemini-3-pro-image-preview doesn't support response_mime_type with PDF,
        so we don't enforce JSON output - we parse it from the response instead.
        """
        # gemini-3-pro-image-preview max output tokens is 8192.
        max_tokens = self.config.extraction_model.max_output_tokens or 8192
        
        model_config = GeminiModelConfig(
            model_id=self.config.extraction_model.model_id,
            temperature=0.2,
            max_output_tokens=max_tokens,
            # Note: NOT setting response_mime_type - it causes errors with PDF input
        )
        
        return self.client.generate(
            model_config=model_config,
            prompt=prompt,
            document_path=pdf_path,
        )
    
    def _render_page_range(
        self,
        doc: fitz.Document,
        start_page: int,
        end_page: int,
        dpi: int = 300
    ) -> List[Image.Image]:
        """Render a range of pages as PIL Images."""
        images = []
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        
        for page_num in range(start_page, end_page + 1):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
            logger.debug(f"Rendered page {page_num + 1}: {img.size[0]}x{img.size[1]}")
        
        return images

    def _render_page_list(
        self,
        doc: fitz.Document,
        page_numbers: List[int],
        dpi: int = 300
    ) -> List[Image.Image]:
        """Render an arbitrary list of pages as PIL Images."""
        images = []
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        for page_num in page_numbers:
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
            logger.debug(f"Rendered page {page_num + 1}: {img.size[0]}x{img.size[1]}")

        return images
    
    def _pass2_extract_figures(
        self,
        images: List[Image.Image],
        questions_with_figures: List[Dict],
        page_numbers: List[int]
    ) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
        """
        Pass 2: Detect figures on page images and match to questions.
        
        Uses the shared FigureExtraction module which processes ONE PAGE AT A TIME
        for more accurate bounding box detection (proven pattern from ImageBasedExtraction).
        
        Args:
            images: List of PIL Images for exercise pages
            questions_with_figures: Questions from Pass 1 that have figures
            page_numbers: Original PDF page numbers for each image (0-indexed)
            
        Returns:
            Tuple of:
            - List of all detected figures (raw)
            - Dict mapping question_id -> list of figure boxes
        """
        logger.info(f"Pass 2: Detecting figures on {len(images)} pages using shared FigureExtraction")
        
        # Initialize the shared figure detector with GeminiClient (Vertex AI)
        # This allows using gemini-3-pro-preview or other Vertex AI models
        detector_config = FigureDetectorConfig(
            model_id=self.config.extraction_model.model_id,  # Use configured model
            temperature=0.1,
            max_retries=3,
            rate_limit_delay=2.0,
        )
        detector = FigureDetector(
            config=detector_config,
            gemini_client=self.client  # Pass the GeminiClient for Vertex AI support
        )
        
        # Detect figures on each page (one at a time for accuracy)
        all_figures = detector.detect_figures_batch(
            images=images,
            start_page=1
        )

        for figure in all_figures:
            if 0 <= figure.page_index < len(page_numbers):
                figure.page_number = page_numbers[figure.page_index] + 1
        
        logger.info(f"  Detected {len(all_figures)} figures across all pages")
        
        # Convert DetectedFigure objects to dicts for matching
        figures_as_dicts = [f.to_dict() for f in all_figures]
        
        # Prepare questions for matching
        # Add source_page info based on Pass 1 hints
        default_source_page = page_numbers[0] + 1 if page_numbers else 1
        default_next_page = page_numbers[1] + 1 if len(page_numbers) > 1 else default_source_page
        for q in questions_with_figures:
            fig_info = q.get('figure_info', {}) or {}
            if fig_info.get('page') == 'next':
                # Figure is on next page relative to question
                q['source_page'] = default_next_page
            else:
                q['source_page'] = default_source_page
        
        # Use the shared FigureMatcher to match figures to questions
        matcher = FigureMatcher()
        matched_questions = matcher.match_figures_to_questions(
            questions=questions_with_figures,
            figures=figures_as_dicts,
            exercise_start_page=default_source_page
        )
        
        # Build the figure_boxes mapping from match results
        figure_boxes = {}
        for q in matched_questions:
            if 'figure_match' in q:
                match = q['figure_match']
                q_id = q.get('question_id', '')
                figure_boxes[q_id] = [{
                    'box_2d': match.get('box_2d', []),
                    'page_index': match.get('page_index', 0),
                    'type': match.get('figure_type', 'DIAGRAM'),
                    'label': match.get('figure_label', ''),
                }]
        
        # Log matching summary
        summary = matcher.get_match_summary(matched_questions)
        logger.info(f"  Matching summary: {summary['figures_matched']}/{summary['questions_needing_figures']} matched")
        if summary.get('match_breakdown'):
            for reason, count in summary['match_breakdown'].items():
                logger.info(f"    - {reason}: {count}")
        
        return figures_as_dicts, figure_boxes
    
    def _parse_pass1_response(self, response_text: str) -> Tuple[List[Dict], List[Dict], Optional[str], str]:
        """
        Parse Pass 1 response to extract questions with figure flags.
        
        Supports both new exercise-grouped format and legacy flat format.
        
        Returns:
            Tuple of (flat question list, exercise list with questions, chapter_number, raw response)
        """
        json_text = self._extract_json(response_text)
        if not json_text:
            logger.warning("No valid JSON in Pass 1 response")
            return [], [], None, response_text
        
        try:
            data = json.loads(json_text)
            
            # Extract chapter_number (new field)
            chapter_number = data.get('chapter_number')
            
            # Check for new exercise-grouped format
            if 'exercises' in data:
                # New format: exercises array with nested questions
                exercises = data.get('exercises', [])
                all_questions = []
                
                for exercise in exercises:
                    exercise_title = exercise.get('exercise_title', 'EXERCISES')
                    exercise_questions = exercise.get('questions', [])
                    
                    # Add exercise_title to each question for tracking
                    for q in exercise_questions:
                        q['exercise_title'] = exercise_title
                        all_questions.append(q)
                
                logger.info(f"Parsed {len(exercises)} exercises, {len(all_questions)} total questions, chapter={chapter_number}")
                return all_questions, exercises, chapter_number, response_text
            
            else:
                # Legacy format: flat questions array
                questions = data.get('questions', [])
                
                # Check for chapter_info (old format)
                chapter_info = data.get('chapter_info', {})
                if not chapter_number and chapter_info:
                    chapter_number = chapter_info.get('chapter_number')
                
                # Create a synthetic exercise from legacy format
                exercise_title = chapter_info.get('exercise_title', 'EXERCISES') if chapter_info else 'EXERCISES'
                for q in questions:
                    q['exercise_title'] = exercise_title
                
                synthetic_exercises = [{
                    'exercise_title': exercise_title,
                    'questions': questions
                }] if questions else []
                
                logger.info(f"Parsed legacy format: {len(questions)} questions, chapter={chapter_number}")
                return questions, synthetic_exercises, chapter_number, response_text
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in Pass 1: {e}")
            return [], [], None, response_text
    
    def _parse_pass2_response(self, response_text: str) -> Dict[str, List[Dict]]:
        """
        Parse Pass 2 response to extract bounding boxes.
        
        Returns:
            Dict mapping question_id -> list of bounding box dicts
        """
        json_text = self._extract_json(response_text)
        if not json_text:
            logger.warning("No valid JSON in Pass 2 response")
            return {}
        
        try:
            data = json.loads(json_text)
            figures = data.get('figures', [])
            
            # Build mapping: question_id -> boxes
            result = {}
            for fig in figures:
                q_id = fig.get('question_id')
                if q_id:
                    result[q_id] = fig.get('boxes', [])
            
            return result
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in Pass 2: {e}")
            return {}
    
    def _merge_passes(
        self,
        pass1_questions: List[Dict],
        figure_boxes: Dict[str, List[Dict]],
        page_numbers: List[int]
    ) -> List[ExtractedQuestion]:
        """
        Merge Pass 1 text with Pass 2 bounding boxes.
        
        Args:
            pass1_questions: Questions from Pass 1 with text and figure flags
            figure_boxes: Mapping of question_id -> bounding boxes from Pass 2
            page_numbers: Original PDF page numbers for exercise pages (0-indexed)
            
        Returns:
            List of fully populated ExtractedQuestion objects
        """
        merged = []
        
        for q in pass1_questions:
            q_id = q.get('question_id', 'unknown')
            has_figure = q.get('has_figure', False)
            
            # Basic question data
            visual_data = VisualMetadata()
            visual_required = False
            figure_page_number = None  # Track the actual page where the figure is
            
            if has_figure and q_id in figure_boxes:
                boxes = figure_boxes[q_id]
                if boxes:
                    # Take the first box for visual_data
                    first_box = boxes[0]
                    visual_required = True
                    visual_data = VisualMetadata(
                        type=first_box.get('type', 'DIAGRAM'),
                        description=q.get('figure_info', {}).get('description', '') if q.get('figure_info') else '',
                        box_2d=first_box.get('box_2d'),
                        visual_source="current_page",  # Will be adjusted based on page_index
                    )
                    
                    # Calculate actual page number from page_index
                    page_index = first_box.get('page_index', 0)
                    if 0 <= page_index < len(page_numbers):
                        figure_page_number = page_numbers[page_index] + 1
                    elif page_numbers:
                        figure_page_number = page_numbers[0] + 1
                    logger.debug(f"Q{q_id}: figure on page_index={page_index}, actual_page={figure_page_number}")
            
            # Determine page number for the question
            # Pass 1 doesn't give us exact page numbers, so we estimate from figure info
            fig_info = q.get('figure_info', {}) or {}
            if fig_info.get('page') == 'next':
                # Question on current, figure on next - needs special handling
                visual_data.visual_source = "next_page"
            
            # Use the figure's page number if we detected one, otherwise default to first page
            question_page = figure_page_number if figure_page_number else (page_numbers[0] + 1 if page_numbers else 1)
            
            question = ExtractedQuestion(
                question_id=q_id,
                question_text=q.get('question_text', ''),
                page_number=question_page,  # Use actual page from figure detection
                visual_required=visual_required,
                visual_data=visual_data,
                figure_references=[fig_info.get('reference')] if fig_info.get('reference') else [],
            )
            
            # Store exercise_title in question for later grouping
            question._exercise_title = q.get('exercise_title', 'EXERCISES')
            
            merged.append(question)
        
        return merged
    
    def _build_exercise_sections(
        self,
        pass1_exercises: List[Dict],
        all_questions: List[ExtractedQuestion],
        start_page: int,
        end_page: int,
        detected_sections: Optional[List[ExerciseSection]] = None
    ) -> List[ExerciseSection]:
        """
        Build ExerciseSection objects with questions grouped by exercise.
        
        Args:
            pass1_exercises: Exercise structure from Pass 1 JSON
            all_questions: List of ExtractedQuestion objects from merge
            start_page: Global starting page for fallback (0-indexed)
            end_page: Global ending page for fallback (0-indexed)
            detected_sections: Original sections from Stage 0 with accurate bounds
            
        Returns:
            List of ExerciseSection objects with nested questions
        """
        # Build a map keyed by exercise title + question id because numbering restarts per exercise.
        question_map = {
            (getattr(q, '_exercise_title', 'EXERCISES'), q.question_id): q
            for q in all_questions
        }
        
        sections = []
        for idx, ex in enumerate(pass1_exercises):
            title = ex.get('exercise_title', f'Exercise {idx + 1}')
            
            # Get total_questions from model (fallback to counting)
            model_total = ex.get('total_questions')
            
            # Get questions for this exercise
            exercise_questions = []
            for q_dict in ex.get('questions', []):
                q_id = q_dict.get('question_id', '')
                question_key = (title, q_id)
                if question_key in question_map:
                    exercise_questions.append(question_map[question_key])
            
            # Use model's total if available, else count
            total_questions = model_total if model_total is not None else len(exercise_questions)
            
            # Estimate page range for this exercise based on Stage 0 detection first
            ex_start_page = start_page
            ex_end_page = end_page
            
            # Map back to Stage 0 accurate detector bounds if available
            if detected_sections:
                import re
                from difflib import SequenceMatcher
                
                # Try exact title match first
                matched_sec = next((s for s in detected_sections if s.title.lower() == title.lower()), None)
                
                # Then try fuzzy match (e.g. "EXERCISE 3.1" matches "EXERCISE 3")
                if not matched_sec:
                    # Clean title e.g. "EXERCISE 3.1" -> "EXERCISE 3"
                    base_title = re.sub(r'\.\d+$', '', title)
                    matched_sec = next((s for s in detected_sections if s.title.lower() == base_title.lower() 
                                        or SequenceMatcher(None, s.title.lower(), title.lower()).ratio() > 0.8), None)
                
                if matched_sec:
                    ex_start_page = matched_sec.start_page
                    ex_end_page = matched_sec.end_page or end_page

            # Pass 1 does not include exact page numbers for non-figure questions.
            # When no figure-based page was inferred, assign the exercise start page
            # so later consumers do not inherit the global first page for every exercise.
            for question in exercise_questions:
                if question.page_number == start_page + 1:
                    question.page_number = ex_start_page + 1
            
            # If there was no Stage 0 section match, fall back to question start pages.
            # Do not shrink detector-provided bounds to the last question start page,
            # because an exercise can span additional pages without new question starts.
            if exercise_questions and not detected_sections:
                # Question.page_number is 1-indexed in saved output; convert back to
                # 0-indexed PDF pages before refining exercise bounds.
                page_nums = [
                    q.page_number - 1
                    for q in exercise_questions
                    if hasattr(q, 'page_number') and q.page_number is not None and (q.page_number - 1) != start_page
                ]
                if page_nums:
                    ex_start_page = max(ex_start_page, min(page_nums))
                    ex_end_page = min(ex_end_page, max(page_nums))

            section = ExerciseSection(
                title=title,
                start_page=ex_start_page,
                end_page=ex_end_page,
                total_questions=total_questions,
                questions=exercise_questions
            )
            sections.append(section)
            
            logger.info(f"  Exercise '{title}': {len(exercise_questions)} questions (model reported: {model_total})")
        
        return sections

    def _detect_exercise_sections(self, pdf_path: Path) -> List[ExerciseSection]:
        """
        Auto-detect exercise sections using the shared ExerciseDetector.
        
        Uses PDF file upload to Gemini for accurate visual-based detection,
        with pattern matching fallback.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of ExerciseSection objects
        """
        logger.info("Detecting exercise sections using shared ExerciseDetector...")
        
        # Use the shared detector with PDF upload (more accurate)
        detector = ExerciseDetector(
            model_id=self.config.detection_model.model_id,
        )
        
        shared_sections = detector.detect(pdf_path, method="auto")
        
        # Convert shared ExerciseSection to local ExerciseSection
        sections = []
        for ss in shared_sections:
            section = ExerciseSection(
                title=ss.title,
                start_page=ss.start_page,
                end_page=ss.end_page,
            )
            sections.append(section)
            logger.info(f"  Found: '{section.title}' pages {section.start_page + 1}-{section.end_page + 1}")
        
        return sections

    def _find_exercise_section_for_page(
        self,
        page_idx: int,
        sections: List[ExerciseSection],
    ) -> Optional[ExerciseSection]:
        """Return the detected exercise section covering the given 0-indexed page."""
        for section in sections:
            section_end = section.end_page if section.end_page is not None else section.start_page
            if section.start_page <= page_idx <= section_end:
                return section
        return None

    def _build_scoped_question_id(
        self,
        question_id: str,
        page_idx: int,
        section: Optional[ExerciseSection],
    ) -> str:
        """Build a dedupe key that avoids collisions across exercises with repeated numbering."""
        if section:
            section_end = section.end_page if section.end_page is not None else section.start_page
            return f"{section.title}:{section.start_page}:{section_end}:{question_id}"
        return f"page:{page_idx}:{question_id}"

    def _assign_questions_to_sections(
        self,
        detected_sections: List[ExerciseSection],
        questions: List[ExtractedQuestion],
    ) -> List[ExerciseSection]:
        """Attach extracted questions to their detected exercise sections for serialization."""
        if not detected_sections:
            return []

        section_copies = [
            ExerciseSection(
                title=section.title,
                start_page=section.start_page,
                end_page=section.end_page,
                total_questions=section.total_questions,
                questions=[],
            )
            for section in detected_sections
        ]

        for question in questions:
            question_page_idx = max((question.page_number or 1) - 1, 0)
            matched_section = self._find_exercise_section_for_page(question_page_idx, section_copies)
            if matched_section:
                matched_section.questions.append(question)

        for section in section_copies:
            if section.questions:
                section.total_questions = len(section.questions)

        return section_copies
    
    def _render_pages(
        self,
        doc: fitz.Document,
        page_idx: int,
        dpi: int = 300,
    ) -> List[Image.Image]:
        """
        Render current page and optionally next page as PIL Images.
        
        The sliding window approach:
        - Current page: PRIMARY - extract questions that START here
        - Next page: For spill-over completion only (text/figures that continue)
        
        Args:
            doc: PyMuPDF document
            page_idx: Current page index (0-based)
            dpi: Resolution for rendering
            
        Returns:
            List of 1-2 PIL Images (current, and next if exists)
        """
        images = []
        
        # Render current page (PRIMARY)
        page = doc.load_page(page_idx)
        mat = fitz.Matrix(dpi / 72, dpi / 72)  # 72 is default PDF DPI
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        images.append(img)
        
        # Render next page if exists (for spill-over)
        if page_idx + 1 < len(doc):
            next_page = doc.load_page(page_idx + 1)
            next_pix = next_page.get_pixmap(matrix=mat)
            next_img = Image.open(io.BytesIO(next_pix.tobytes("png")))
            images.append(next_img)
        
        return images
    
    def _call_extraction_model(
        self,
        images: List[Image.Image],
        page_number: int,
        has_next_page: bool,
        prompt_template: str,
    ) -> GeneratedContent:
        """
        Call Gemini model with page images for extraction.
        
        Args:
            images: List of PIL Images (current page, optional next page)
            page_number: Current page number (1-indexed)
            has_next_page: Whether a next page image is included
            prompt_template: The extraction prompt
            
        Returns:
            GeneratedContent from model
        """
        # Build the prompt with page context
        # Sliding window: Page N (primary) + Page N+1 (spill-over only)
        if len(images) == 2:
            context_note = f"""
**Current Processing Context:**
- **Image 1 = Page {page_number}** (PRIMARY PAGE)
  - Extract ALL questions whose question number/ID STARTS on this page
  - Record page_number as {page_number} for these questions
  
- **Image 2 = Page {page_number + 1}** (SPILL-OVER REFERENCE ONLY)
  - Use this ONLY to complete questions that started on Page {page_number} but spill over
  - If a question's text or figure continues onto Page {page_number + 1}, include that content
  - DO NOT extract questions that START on Page {page_number + 1} - they will be extracted in the next iteration

**Important:** Only extract questions where the question NUMBER first appears on Page {page_number}.
"""
        else:
            context_note = f"""
**Current Processing Context:**
- **Image 1 = Page {page_number}** (FINAL PAGE - no next page available)
  - Extract ALL questions visible on this page
  - Record page_number as {page_number} for these questions
"""
        
        full_prompt = f"{prompt_template}\n\n{context_note}"
        
        # Prepare content parts for the API
        # The Gemini client expects images + prompt
        model_config = self.config.extraction_model
        
        # Use generate method with images
        result = self.client.generate_with_images(
            model_config=model_config,
            prompt=full_prompt,
            images=images,
        )
        
        return result
    
    def _parse_extraction_response(
        self,
        response_text: str,
        page_number: int,
        seen_ids: Set[str],
    ) -> List[ExtractedQuestion]:
        """
        Parse the JSON response from the extraction model.
        
        Args:
            response_text: Raw response text (should be JSON)
            page_number: Page number for context
            seen_ids: Set of question IDs already processed
            
        Returns:
            List of ExtractedQuestion objects
        """
        questions = []
        
        # Extract JSON from response
        json_text = self._extract_json(response_text)
        if not json_text:
            logger.warning(f"No valid JSON found in response for page {page_number}")
            return questions
        
        try:
            data = json.loads(json_text)
            
            # Handle different response formats
            exercises = []
            if isinstance(data, dict):
                exercises = data.get("exercises", data.get("questions", []))
                if not exercises and "question_id" in data:
                    exercises = [data]
            elif isinstance(data, list):
                exercises = data
            
            for ex in exercises:
                q_id = ex.get("question_id", "unknown")
                
                # Skip if already seen (from previous page's look-ahead)
                if q_id in seen_ids:
                    continue
                
                # Parse visual data
                visual_data = VisualMetadata()
                visual_required = ex.get("visual_required", False)
                
                if visual_required and "visual_data" in ex:
                    vd = ex["visual_data"]
                    visual_data = VisualMetadata(
                        type=vd.get("type", "DIAGRAM"),
                        description=vd.get("description", ""),
                        box_2d=vd.get("box_2d"),
                        visual_source=vd.get("visual_source", vd.get("source", "current_page")),
                        smiles=vd.get("smiles"),
                    )
                
                # Extract figure references from text
                fig_refs = self._extract_figure_references(ex.get("question_text", ""))
                
                # Parse sub-questions if present
                sub_questions = []
                if "sub_questions" in ex:
                    for sq in ex["sub_questions"]:
                        sub_questions.append(SubQuestion(
                            sub_id=sq.get("sub_id", ""),
                            text=sq.get("text", ""),
                            visual_data=VisualMetadata(**sq["visual_data"]) if sq.get("visual_data") else None,
                        ))
                
                question = ExtractedQuestion(
                    question_id=q_id,
                    question_text=ex.get("question_text", ex.get("text", "")),
                    page_number=page_number,
                    visual_required=visual_required,
                    visual_data=visual_data,
                    sub_questions=sub_questions,
                    figure_references=fig_refs,
                )
                
                questions.append(question)
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for page {page_number}: {e}")
        
        return questions
    
    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from text that may contain markdown or other content."""
        # Helper to fix single unescaped backslashes in LaTeX generated by the model
        def _clean_json_latex(json_str: str) -> str:
            return re.sub(r'(?<!\\)\\([^"\\/bfnrtu])', r'\\\\\1', json_str)

        # Try markdown code blocks first
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for candidate in reversed(matches):
                candidate = candidate.strip()
                if candidate.startswith('{') or candidate.startswith('['):
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        # Attempt to heal invalid LaTeX JSON escapes
                        try:
                            patched = _clean_json_latex(candidate)
                            json.loads(patched)
                            return patched
                        except json.JSONDecodeError:
                            continue
        
        # Try raw JSON
        if text.strip().startswith('{') or text.strip().startswith('['):
            try:
                json.loads(text.strip())
                return text.strip()
            except json.JSONDecodeError:
                # Attempt to heal invalid LaTeX JSON escapes
                try:
                    patched = _clean_json_latex(text.strip())
                    json.loads(patched)
                    return patched
                except json.JSONDecodeError:
                    pass
        
        # Try to find JSON object/array in text
        json_patterns = [
            r'(\{[\s\S]*"exercises"[\s\S]*\})',
            r'(\{[\s\S]*"questions"[\s\S]*\})',
            r'(\[[\s\S]*"question_id"[\s\S]*\])',
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    json.loads(match.group(1))
                    return match.group(1)
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _extract_figure_references(self, text: str) -> List[str]:
        """Extract figure/table references from question text."""
        refs = []
        for pattern in self.FIGURE_REF_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, str) and match:
                    refs.append(f"Fig {match}" if not match.startswith(('Fig', 'Table')) else match)
        return list(set(refs))
    
    def _crop_all_visuals(
        self,
        pdf_path: Path,
        questions: List[ExtractedQuestion],
    ) -> Path:
        """
        Crop all visual assets from the PDF.
        
        Args:
            pdf_path: Path to the PDF
            questions: List of questions with visual metadata
            
        Returns:
            Path to the directory containing cropped images
        """
        output_dir = self.config.output_dir / "cropped_images" / pdf_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)
        
        doc = fitz.open(pdf_path)
        
        for q in questions:
            if not q.visual_required or not q.visual_data.box_2d:
                continue
            
            # Determine which page to crop from
            page_idx = q.page_number - 1  # Convert to 0-indexed
            if q.visual_data.visual_source == "next_page":
                page_idx += 1
            
            if page_idx >= len(doc):
                logger.warning(f"Page {page_idx + 1} out of range for question {q.question_id}")
                continue
            
            try:
                # Crop the image
                cropped_path = self._crop_visual(
                    doc=doc,
                    page_idx=page_idx,
                    box_2d=q.visual_data.box_2d,
                    output_dir=output_dir,
                    question_id=q.question_id,
                )
                
                q.visual_data.cropped_image_path = str(cropped_path.relative_to(self.config.output_dir))
                logger.info(f"  Cropped visual for {q.question_id}: {cropped_path.name}")
                
            except Exception as e:
                logger.error(f"Error cropping visual for {q.question_id}: {e}")
        
        doc.close()
        return output_dir
    
    def _crop_visual(
        self,
        doc: fitz.Document,
        page_idx: int,
        box_2d: List[int],
        output_dir: Path,
        question_id: str,
    ) -> Path:
        """
        Crop a specific region from a PDF page.
        
        Args:
            doc: PyMuPDF document
            page_idx: Page index (0-based)
            box_2d: Bounding box [ymin, xmin, ymax, xmax] on 0-1000 scale
            output_dir: Directory to save cropped image
            question_id: Question ID for filename
            
        Returns:
            Path to the cropped image
        """
        page = doc.load_page(page_idx)
        page_rect = page.rect
        
        # Convert 0-1000 scale to actual page coordinates
        ymin, xmin, ymax, xmax = box_2d
        
        x0 = page_rect.width * (xmin / 1000)
        y0 = page_rect.height * (ymin / 1000)
        x1 = page_rect.width * (xmax / 1000)
        y1 = page_rect.height * (ymax / 1000)
        
        # Create clip rectangle
        clip_rect = fitz.Rect(x0, y0, x1, y1)
        
        # Render at high DPI
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat, clip=clip_rect)
        
        # Save as PNG
        safe_id = question_id.replace(".", "_").replace(" ", "_")
        output_path = output_dir / f"q{safe_id}_fig.png"
        pix.save(str(output_path))
        
        return output_path
    
    def save_questions(
        self,
        response: ExtractionResponse,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """
        Save extracted questions to JSON file.
        
        Args:
            response: ExtractionResponse to save
            output_dir: Output directory (uses config default if not provided)
            
        Returns:
            Path to the saved JSON file
        """
        output_dir = output_dir or self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        subject = response.request.subject.lower()
        pdf_stem = response.request.pdf_path.stem
        
        json_path = output_dir / f"questions_{subject}_{pdf_stem}_{timestamp}.json"
        
        # Save JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(response.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved questions to: {json_path}")
        
        # Also save raw responses for debugging
        raw_path = output_dir / f"questions_{subject}_{pdf_stem}_{timestamp}_raw.md"
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write(f"# Raw Extraction Responses\n\n")
            f.write(f"**PDF:** {response.request.pdf_path.name}\n")
            f.write(f"**Timestamp:** {response.timestamp}\n\n")
            for i, raw in enumerate(response.raw_responses):
                f.write(f"---\n\n## Page {i + 1} Response\n\n")
                f.write(raw)
                f.write("\n\n")
        
        return json_path
    
    def cleanup(self):
        """Cleanup any resources."""
        pass


# =============================================================================
# Standalone Testing
# =============================================================================

def test_extraction():
    """Quick test of the extraction engine."""
    from config import PipelineConfig
    
    config = PipelineConfig.from_env()
    engine = ExtractionEngine(config)
    
    # Test with a sample PDF
    pdf_path = Path(__file__).parent / "Input" / "keph203.pdf"
    
    if pdf_path.exists():
        request = ExtractionRequest(
            pdf_path=pdf_path,
            subject="Physics",
        )
        
        prompt_path = Path(__file__).parent / "extraction_prompt.md"
        prompt = engine.load_prompt_template(prompt_path)
        
        response = engine.extract_from_pdf(request, prompt)
        
        print(f"\nExtracted {len(response.questions)} questions:")
        for q in response.questions:
            print(f"  - {q.question_id}: {q.question_text[:50]}...")
        
        output_path = engine.save_questions(response)
        print(f"\nSaved to: {output_path}")
    else:
        print(f"Test PDF not found: {pdf_path}")


if __name__ == "__main__":
    test_extraction()
