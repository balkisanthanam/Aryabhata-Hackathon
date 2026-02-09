"""
Figure Matcher - Matches detected figures to questions.

Handles the critical task of associating figures with the correct questions,
including cross-page scenarios where a figure appears at the top of the next page.

Usage:
    matcher = FigureMatcher()
    matched = matcher.match_figures_to_questions(questions, figures)
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of matching a figure to a question."""
    question_id: str
    figure_label: str
    figure_type: str
    box_2d: List[int]
    page_number: int
    page_index: int
    match_confidence: float
    match_reason: str
    
    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "figure_label": self.figure_label,
            "figure_type": self.figure_type,
            "box_2d": self.box_2d,
            "page_number": self.page_number,
            "page_index": self.page_index,
            "match_confidence": self.match_confidence,
            "match_reason": self.match_reason
        }


class FigureMatcher:
    """
    Matches detected figures to questions based on labels, position, and page context.
    
    Matching strategies:
    1. Label match: Figure label matches question's figure_reference
    2. Same-page proximity: Figure on same page as question with has_figure=True
    3. Cross-page: top_of_page figure matches previous page's unresolved question
    """
    
    def __init__(self):
        """Initialize the figure matcher."""
        pass
    
    def _normalize_label(self, label: str) -> str:
        """Normalize a label for comparison."""
        if not label:
            return ""
        # Lowercase, remove extra spaces, normalize common patterns
        normalized = label.lower().strip()
        normalized = re.sub(r'\s+', ' ', normalized)
        # Normalize "Fig." variations
        normalized = re.sub(r'fig\.?\s*', 'fig ', normalized)
        # Normalize structure references
        normalized = re.sub(r'structures?\s*', 'struct ', normalized)
        return normalized
    
    def _extract_figure_ref(self, figure_info: Dict) -> str:
        """Extract the figure reference from question's figure_info."""
        if not figure_info:
            return ""
        ref = figure_info.get('reference', '') or figure_info.get('label', '')
        return self._normalize_label(ref)
    
    def _labels_match(self, fig_label: str, question_ref: str) -> Tuple[bool, float]:
        """
        Check if a figure label matches a question's figure reference.
        
        Returns:
            Tuple of (is_match, confidence)
        """
        norm_fig = self._normalize_label(fig_label)
        norm_ref = self._normalize_label(question_ref)
        
        if not norm_fig or not norm_ref:
            return False, 0.0
        
        # Exact match
        if norm_fig == norm_ref:
            return True, 1.0
        
        # One contains the other
        if norm_fig in norm_ref or norm_ref in norm_fig:
            return True, 0.8
        
        # Check for letter/number patterns like "(a)-(f)" matching "a-f"
        fig_chars = set(re.findall(r'[a-z0-9]', norm_fig))
        ref_chars = set(re.findall(r'[a-z0-9]', norm_ref))
        if fig_chars and ref_chars:
            overlap = len(fig_chars & ref_chars) / max(len(fig_chars), len(ref_chars))
            if overlap > 0.5:
                return True, 0.6
        
        return False, 0.0
    
    def _find_questions_needing_figures(self, questions: List[Dict]) -> List[Dict]:
        """Filter questions that have has_figure=True but no figure assigned yet."""
        return [
            q for q in questions 
            if q.get('has_figure') or q.get('figure_info')
        ]
    
    def match_figures_to_questions(
        self,
        questions: List[Dict],
        figures: List[Dict],
        exercise_start_page: int = 1
    ) -> List[Dict]:
        """
        Match detected figures to questions.
        
        Args:
            questions: List of questions from Pass 1 with:
                - question_id
                - source_page (1-indexed)
                - has_figure (bool)
                - figure_info: {reference, description}
            figures: List of detected figures with:
                - label
                - type
                - box_2d
                - page_number (1-indexed)
                - page_index (0-indexed)
                - position
            exercise_start_page: 1-indexed start page of exercise section
                
        Returns:
            Updated questions list with figure_match data added
        """
        logger.info(f"Matching {len(figures)} figures to {len(questions)} questions")
        
        # Track which figures have been matched
        matched_figure_indices = set()
        
        # Get questions needing figures
        questions_needing_figures = self._find_questions_needing_figures(questions)
        logger.info(f"  {len(questions_needing_figures)} questions need figures")
        
        # First pass: Match by label OR question_id
        for q in questions_needing_figures:
            q_id = q.get('question_id', '')
            q_page = q.get('source_page', 0)
            fig_info = q.get('figure_info', {}) or {}
            fig_ref = self._extract_figure_ref(fig_info)
            
            best_match = None
            best_confidence = 0.0
            best_idx = -1
            best_reason = 'label_match'
            
            for idx, fig in enumerate(figures):
                if idx in matched_figure_indices:
                    continue
                
                fig_label = fig.get('label', '')
                
                # Strategy 1: Match figure label to question's figure_reference
                is_match, confidence = self._labels_match(fig_label, fig_ref)
                
                if is_match and confidence > best_confidence:
                    best_match = fig
                    best_confidence = confidence
                    best_idx = idx
                    best_reason = 'label_match'
                
                # Strategy 2: Match figure label to question_id directly
                # This handles cases where figure is labeled "8.15" and question_id is "8.15"
                if fig_label and q_id:
                    norm_fig_label = self._normalize_label(fig_label)
                    norm_q_id = self._normalize_label(q_id)
                    
                    # Check if figure label matches question ID (e.g., "8.15" == "8.15")
                    if norm_fig_label == norm_q_id:
                        if 0.95 > best_confidence:  # High confidence for direct ID match
                            best_match = fig
                            best_confidence = 0.95
                            best_idx = idx
                            best_reason = 'question_id_match'
                    # Also check partial match (e.g., "fig 8.15" contains "8.15")
                    elif q_id in fig_label or norm_q_id in norm_fig_label:
                        if 0.85 > best_confidence:
                            best_match = fig
                            best_confidence = 0.85
                            best_idx = idx
                            best_reason = 'question_id_match'
            
            if best_match:
                q['figure_match'] = MatchResult(
                    question_id=q_id,
                    figure_label=best_match.get('label', ''),
                    figure_type=best_match.get('type', 'OTHER'),
                    box_2d=best_match.get('box_2d', []),
                    page_number=best_match.get('page_number', 0),
                    page_index=best_match.get('page_index', 0),
                    match_confidence=best_confidence,
                    match_reason=best_reason
                ).to_dict()
                matched_figure_indices.add(best_idx)
                logger.info(f"  Matched Q{q_id} -> {best_match.get('label')} ({best_reason}, conf={best_confidence:.2f})")
        
        # Second pass: Match top_of_page figures to previous page's unresolved questions
        top_of_page_figures = [
            (idx, fig) for idx, fig in enumerate(figures)
            if idx not in matched_figure_indices 
            and fig.get('position') == 'top_of_page'
        ]
        
        for idx, fig in top_of_page_figures:
            fig_page = fig.get('page_number', 0)
            
            # Find questions on the PREVIOUS page that still need figures
            prev_page = fig_page - 1
            candidates = [
                q for q in questions_needing_figures
                if q.get('source_page') == prev_page
                and 'figure_match' not in q
            ]
            
            if candidates:
                # Take the last question on the previous page
                last_q = candidates[-1]
                q_id = last_q.get('question_id', '')
                
                last_q['figure_match'] = MatchResult(
                    question_id=q_id,
                    figure_label=fig.get('label', ''),
                    figure_type=fig.get('type', 'OTHER'),
                    box_2d=fig.get('box_2d', []),
                    page_number=fig_page,
                    page_index=fig.get('page_index', 0),
                    match_confidence=0.7,
                    match_reason='cross_page_top_of_page'
                ).to_dict()
                matched_figure_indices.add(idx)
                logger.info(f"  Matched Q{q_id} (page {prev_page}) -> figure on page {fig_page} (cross-page)")
        
        # Third pass: Proximity match - same page, nearest position
        for q in questions_needing_figures:
            if 'figure_match' in q:
                continue
            
            q_id = q.get('question_id', '')
            q_page = q.get('source_page', 0)
            
            # Find unmatched figures on the same page
            same_page_figs = [
                (idx, fig) for idx, fig in enumerate(figures)
                if idx not in matched_figure_indices
                and fig.get('page_number') == q_page
            ]
            
            if same_page_figs:
                # Take the first available figure on that page
                idx, fig = same_page_figs[0]
                
                q['figure_match'] = MatchResult(
                    question_id=q_id,
                    figure_label=fig.get('label', ''),
                    figure_type=fig.get('type', 'OTHER'),
                    box_2d=fig.get('box_2d', []),
                    page_number=q_page,
                    page_index=fig.get('page_index', 0),
                    match_confidence=0.5,
                    match_reason='same_page_proximity'
                ).to_dict()
                matched_figure_indices.add(idx)
                logger.info(f"  Matched Q{q_id} -> {fig.get('label')} (same page proximity)")
        
        # Log unmatched
        unmatched_questions = [q for q in questions_needing_figures if 'figure_match' not in q]
        unmatched_figures = [fig for idx, fig in enumerate(figures) if idx not in matched_figure_indices]
        
        if unmatched_questions:
            logger.warning(f"  {len(unmatched_questions)} questions still need figures: {[q.get('question_id') for q in unmatched_questions]}")
        if unmatched_figures:
            logger.warning(f"  {len(unmatched_figures)} figures unmatched: {[f.get('label') for f in unmatched_figures]}")
        
        return questions
    
    def get_match_summary(self, questions: List[Dict]) -> Dict:
        """Generate a summary of matching results."""
        total_with_figures = len([q for q in questions if q.get('has_figure') or q.get('figure_info')])
        matched = len([q for q in questions if 'figure_match' in q])
        
        match_reasons = {}
        for q in questions:
            if 'figure_match' in q:
                reason = q['figure_match'].get('match_reason', 'unknown')
                match_reasons[reason] = match_reasons.get(reason, 0) + 1
        
        return {
            "questions_needing_figures": total_with_figures,
            "figures_matched": matched,
            "unmatched": total_with_figures - matched,
            "match_breakdown": match_reasons
        }
