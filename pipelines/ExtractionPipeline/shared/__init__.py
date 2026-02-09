"""
Shared utilities for the Extraction Pipeline.

This module contains reusable components used across:
- ImageBasedExtraction
- SchoolDataExtraction/MultiStep
- Other extraction pipelines
"""

from .exercise_detector import ExerciseDetector, ExerciseSection

__all__ = ['ExerciseDetector', 'ExerciseSection']
