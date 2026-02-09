"""
Shared Figure Extraction Module

Detects and crops figures/diagrams from PDF page images.
Used by:
- SchoolDataExtraction/MultiStep (Pass 2 figure extraction)
- ImageBasedExtraction (optional figure-only extraction)

Components:
- figure_detector.py: Gemini-based figure detection (one page at a time)
- figure_cropper.py: PIL-based figure cropping
- figure_matcher.py: Match detected figures to questions (handles cross-page)
"""

from .figure_detector import FigureDetector
from .figure_cropper import FigureCropper
from .figure_matcher import FigureMatcher

__all__ = ['FigureDetector', 'FigureCropper', 'FigureMatcher']
