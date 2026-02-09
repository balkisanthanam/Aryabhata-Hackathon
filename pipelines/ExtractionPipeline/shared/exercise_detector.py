"""
Shared Exercise Section Detector

Detects exercise sections in PDF files using:
1. Gemini model with PDF file upload (recommended - sees visual structure)
2. Pattern matching fallback (no API cost)

This module is used by:
- ImageBasedExtraction pipeline
- SchoolDataExtraction/MultiStep pipeline
"""

import json
import os
import re
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple
import google.generativeai as genai

logger = logging.getLogger(__name__)


@dataclass
class ExerciseSection:
    """Represents a detected exercise section in a PDF."""
    title: str
    start_page: int  # 0-indexed
    end_page: int    # 0-indexed
    confidence: float = 1.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary (1-indexed for display)."""
        return {
            "title": self.title,
            "start_page": self.start_page + 1,
            "end_page": self.end_page + 1,
            "confidence": self.confidence
        }


class ExerciseDetector:
    """
    Detects exercise sections in PDF files.
    
    Uses Gemini model with PDF file upload for accurate detection,
    with pattern matching as fallback.
    """
    
    # Common exercise section headers
    EXERCISE_PATTERNS = [
        r'(?i)^\s*EXERCISES?\s*$',
        r'(?i)^\s*ADDITIONAL\s+EXERCISES?\s*$',
        r'(?i)^\s*Miscellaneous\s+Exercise\s*$',
        r'(?i)^\s*Practice\s+Problems?\s*$',
        r'(?i)^\s*Questions?\s*$',
        r'(?i)^\s*Exercise\s+\d+',
    ]
    
    # Keywords that indicate end of exercises
    END_MARKERS = [
        r'(?i)^\s*ANSWERS?\s*$',
        r'(?i)^\s*SUMMARY\s*$',
        r'(?i)^\s*Chapter\s+\d+',
        r'(?i)^\s*APPENDIX',
    ]
    
    def __init__(
        self,
        model_id: str = "gemini-2.5-flash",
        api_key: Optional[str] = None,
        api_key_env: str = "GOOGLE_API_KEY",
        prompt_path: Optional[Path] = None,
        temperature: float = 0.0,
    ):
        """
        Initialize the exercise detector.
        
        Args:
            model_id: Gemini model to use for detection
            api_key: API key (if None, reads from environment)
            api_key_env: Environment variable name for API key
            prompt_path: Path to custom prompt template
            temperature: Model temperature (0.0 for deterministic)
        """
        self.model_id = model_id
        self.temperature = temperature
        
        # Configure API
        api_key = api_key or os.getenv(api_key_env)
        if api_key:
            genai.configure(api_key=api_key)
            self._api_configured = True
        else:
            logger.warning(f"No API key found. Set {api_key_env} for model-based detection.")
            self._api_configured = False
        
        # Load prompt template
        if prompt_path and prompt_path.exists():
            self._prompt_template = prompt_path.read_text(encoding='utf-8')
        else:
            # Use default prompt from shared/prompts
            default_path = Path(__file__).parent / "prompts" / "page_detection_prompt.txt"
            if default_path.exists():
                self._prompt_template = default_path.read_text(encoding='utf-8')
            else:
                self._prompt_template = self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """Return default prompt if file not found."""
        return """### Role
You are a precise Document Structure Analyzer for educational textbooks.

### Task
Identify exercise sections and their page ranges in the PDF.

### Output Format (JSON)
{
  "sections": [
    {"title": "EXERCISES", "start_page": 25, "end_page": 27}
  ],
  "confidence": 0.95
}
"""
    
    def detect(
        self,
        pdf_path: Path,
        method: str = "auto",
    ) -> List[ExerciseSection]:
        """
        Detect exercise sections in a PDF.
        
        Args:
            pdf_path: Path to PDF file
            method: Detection method - "gemini", "pattern", or "auto"
                    "auto" tries gemini first, falls back to pattern
        
        Returns:
            List of ExerciseSection objects
        """
        pdf_path = Path(pdf_path)
        
        if method == "auto":
            if self._api_configured:
                try:
                    sections = self._detect_with_gemini(pdf_path)
                    if sections:
                        return sections
                except Exception as e:
                    logger.warning(f"Gemini detection failed: {e}")
            return self._detect_with_pattern(pdf_path)
        
        elif method == "gemini":
            if not self._api_configured:
                raise ValueError("API key not configured for Gemini detection")
            return self._detect_with_gemini(pdf_path)
        
        elif method == "pattern":
            return self._detect_with_pattern(pdf_path)
        
        else:
            raise ValueError(f"Unknown method: {method}")
    
    def _detect_with_gemini(self, pdf_path: Path) -> List[ExerciseSection]:
        """
        Detect exercise sections using Gemini with PDF file upload.
        
        This method uploads the entire PDF to Gemini, allowing the model
        to see the visual structure and accurately identify exercise boundaries.
        """
        logger.info(f"Detecting exercise sections using Gemini ({self.model_id})...")
        
        # Configure model
        generation_config = {
            "temperature": self.temperature,
            "max_output_tokens": 8192,
            "top_p": 0.95,
        }
        
        model = genai.GenerativeModel(
            self.model_id,
            generation_config=generation_config
        )
        
        # Upload PDF to Gemini
        logger.info(f"  Uploading PDF: {pdf_path.name}")
        uploaded_file = genai.upload_file(pdf_path)
        
        try:
            # Send to Gemini
            logger.info("  Analyzing document structure...")
            response = model.generate_content([
                self._prompt_template,
                uploaded_file
            ])
            
            # Parse response
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0]
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0]
            
            result = json.loads(response_text.strip())
            
            sections_data = result.get("sections", [])
            confidence = result.get("confidence", 0.0)
            
            if not sections_data:
                logger.info("  No exercise sections found by model")
                return []
            
            # Convert to ExerciseSection objects
            sections = []
            for s in sections_data:
                section = ExerciseSection(
                    title=s.get("title", "Exercises"),
                    start_page=s.get("start_page", 1) - 1,  # Convert to 0-indexed
                    end_page=s.get("end_page", 1) - 1,      # Convert to 0-indexed
                    confidence=confidence,
                )
                sections.append(section)
                logger.info(f"  Found: '{section.title}' pages {section.start_page + 1}-{section.end_page + 1}")
            
            logger.info(f"  Confidence: {confidence:.2f}")
            return sections
            
        finally:
            # Clean up uploaded file
            try:
                genai.delete_file(uploaded_file.name)
                logger.debug("  Cleaned up uploaded file")
            except Exception as e:
                logger.warning(f"  Failed to delete uploaded file: {e}")
    
    def _detect_with_pattern(self, pdf_path: Path) -> List[ExerciseSection]:
        """
        Detect exercise sections using keyword pattern matching.
        
        This is a fallback method that doesn't require API access.
        Less accurate than Gemini but works offline.
        """
        import fitz  # PyMuPDF - import here to avoid dependency if not needed
        
        logger.info(f"Detecting exercise sections using pattern matching...")
        
        doc = fitz.open(pdf_path)
        sections = []
        combined_pattern = '|'.join(self.EXERCISE_PATTERNS)
        end_pattern = '|'.join(self.END_MARKERS)
        
        current_section = None
        
        for page_idx in range(len(doc)):
            page = doc.load_page(page_idx)
            text = page.get_text("text")
            
            # Check for exercise start
            if re.search(combined_pattern, text, re.MULTILINE):
                # Extract title from match
                for pattern in self.EXERCISE_PATTERNS:
                    match = re.search(pattern, text, re.MULTILINE)
                    if match:
                        title = match.group(0).strip()
                        
                        # Save previous section if exists
                        if current_section:
                            current_section.end_page = page_idx - 1
                            if current_section.end_page >= current_section.start_page:
                                sections.append(current_section)
                        
                        # Start new section
                        current_section = ExerciseSection(
                            title=title,
                            start_page=page_idx,
                            end_page=len(doc) - 1,  # Will be updated
                            confidence=0.7,  # Lower confidence for pattern matching
                        )
                        logger.info(f"  Found (pattern): '{title}' starting at page {page_idx + 1}")
                        break
            
            # Check for section end
            elif current_section and re.search(end_pattern, text, re.MULTILINE):
                current_section.end_page = page_idx - 1
                if current_section.end_page >= current_section.start_page:
                    sections.append(current_section)
                current_section = None
        
        # Add final section if still open
        if current_section:
            sections.append(current_section)
        
        doc.close()
        
        logger.info(f"  Found {len(sections)} exercise section(s) via pattern matching")
        return sections
    
    def get_page_list(self, sections: List[ExerciseSection]) -> List[int]:
        """
        Convert exercise sections to a flat list of page indices.
        
        Useful for pipelines that need individual page numbers.
        
        Args:
            sections: List of ExerciseSection objects
            
        Returns:
            List of 0-indexed page numbers
        """
        pages = []
        for section in sections:
            pages.extend(range(section.start_page, section.end_page + 1))
        return sorted(set(pages))  # Remove duplicates and sort


# Convenience function for quick detection
def detect_exercises(
    pdf_path: Path,
    model_id: str = "gemini-2.5-flash",
    method: str = "auto",
) -> List[ExerciseSection]:
    """
    Quick function to detect exercise sections in a PDF.
    
    Args:
        pdf_path: Path to PDF file
        model_id: Gemini model to use
        method: "auto", "gemini", or "pattern"
    
    Returns:
        List of ExerciseSection objects
    """
    detector = ExerciseDetector(model_id=model_id)
    return detector.detect(pdf_path, method=method)
