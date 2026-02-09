"""
Stage 2: Solver Engine - Generates step-by-step tutorial solutions.

This module:
- Takes a PDF chapter and list of questions
- Uses parameterized prompts (filled by client)
- Generates pedagogical, step-by-step solutions
- Handles interleaved text/image output from Gemini 3
- Saves solutions as JSON with associated images

Designed for easy integration into the full pipeline.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
import logging

from config import PipelineConfig, GeminiModelConfig
from gemini_client import GeminiClient, GeneratedContent

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class VisualAsset:
    """Represents a visual asset in a solution step."""
    required: bool = False
    type: str = "none"  # image_generation | smiles_code | svg_code | latex_diagram | none
    data: str = ""
    caption: str = ""


@dataclass
class FormatBlock:
    """Represents an embedded format block (SVG, SMILES, code, etc.)"""
    block_type: str  # svg | smiles | latex | image_ref | code
    content: str
    caption: Optional[str] = None


@dataclass 
class SolutionStep:
    """Represents a single step in a solution."""
    step_number: int
    step_type: str  # conceptual | calculation | visual
    nudge_hint: str
    explanation: str
    latex_formula: Optional[str] = None
    visual_asset: VisualAsset = field(default_factory=VisualAsset)
    embedded_formats: List[FormatBlock] = field(default_factory=list)  # SVG, SMILES, etc.


@dataclass
class Solution:
    """Complete solution for a question."""
    question_id: str
    question_text: str
    steps: List[SolutionStep] = field(default_factory=list)
    final_answer: str = ""
    generated_images: List[str] = field(default_factory=list)  # Paths to saved images
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "question_id": self.question_id,
            "question_text": self.question_text,
            "steps": [
                {
                    "step_number": s.step_number,
                    "step_type": s.step_type,
                    "nudge_hint": s.nudge_hint,
                    "explanation": s.explanation,
                    "latex_formula": s.latex_formula,
                    "visual_asset": asdict(s.visual_asset),
                    "embedded_formats": [asdict(f) for f in s.embedded_formats],
                }
                for s in self.steps
            ],
            "final_answer": self.final_answer,
            "generated_images": self.generated_images,
        }


@dataclass
class SolverRequest:
    """Request to solve specific questions from a chapter."""
    pdf_path: Path
    questions: List[str]  # e.g., ["12.4", "12.7"] - flat list for backward compat
    class_level: str = "11th"
    board: str = "CBSE"
    subject: str = "Physics"
    chapter_name: Optional[str] = None
    chapter_number: Optional[str] = None  # NEW: Chapter number from extraction
    exercises: Optional[List[Dict]] = None  # NEW: Exercise-grouped questions structure


@dataclass
class ExerciseSolutions:
    """Solutions grouped by exercise."""
    exercise_title: str
    solutions: List[Solution]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "exercise_title": self.exercise_title,
            "solutions": [s.to_dict() for s in self.solutions],
        }

    
@dataclass
class SolverResponse:
    """Response containing all generated solutions."""
    request: SolverRequest
    solutions: List[Solution]  # Flat list for backward compat
    exercise_solutions: List[ExerciseSolutions] = field(default_factory=list)  # NEW: Grouped by exercise
    raw_response: str = ""  # Original response from model
    processing_time_seconds: float = 0.0
    model_used: str = ""
    chapter_number: Optional[str] = None  # NEW: Chapter number
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization with exercise grouping."""
        result = {
            "metadata": {
                "pdf_file": str(self.request.pdf_path.name),
                "chapter_number": self.chapter_number or self.request.chapter_number,
                "questions_requested": self.request.questions,
                "class": self.request.class_level,
                "board": self.request.board,
                "subject": self.request.subject,
                "chapter": self.request.chapter_name,
                "model": self.model_used,
                "processing_time_seconds": self.processing_time_seconds,
                "timestamp": self.timestamp,
            },
            "solutions": [s.to_dict() for s in self.solutions],  # Flat list
            "raw_response": self.raw_response,
        }
        
        # Add exercise-grouped solutions if available
        if self.exercise_solutions:
            result["exercises"] = [es.to_dict() for es in self.exercise_solutions]
        
        return result


class SolverEngine:
    """
    Stage 2 Solver Engine for generating step-by-step solutions.
    
    Usage:
        engine = SolverEngine(config)
        
        # Load and fill prompt template
        prompt = engine.load_prompt_template("tutor_prompt.md")
        filled_prompt = engine.fill_prompt(prompt, class_level="11th", ...)
        
        # Generate solutions
        response = engine.solve(
            pdf_path=Path("chapter.pdf"),
            questions=["12.4", "12.7"],
            system_prompt=filled_prompt,
        )
        
        # Save results
        engine.save_response(response, output_dir)
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initialize the solver engine."""
        self.config = config or PipelineConfig.from_env()
        self.client = GeminiClient(self.config)
        self._cached_document = None
        
        logger.info("SolverEngine initialized")
    
    def load_prompt_template(self, template_path: Path) -> str:
        """
        Load a prompt template from file.
        
        The template can contain placeholders like {{CLASS}}, {{BOARD}}, {{SUBJECT}}.
        """
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")
        
        return template_path.read_text(encoding="utf-8")
    
    def fill_prompt(
        self,
        template: str,
        class_level: str = "11th",
        board: str = "CBSE", 
        subject: str = "Physics",
        **kwargs
    ) -> str:
        """
        Fill placeholders in a prompt template.
        
        Standard placeholders:
            {{CLASS}} - Class level (e.g., "11th")
            {{BOARD}} - Education board (e.g., "CBSE")
            {{SUBJECT}} - Subject name (e.g., "Physics")
            
        Additional placeholders can be passed via kwargs.
        """
        filled = template
        
        # Standard replacements
        replacements = {
            "{{CLASS}}": class_level,
            "{{BOARD}}": board,
            "{{SUBJECT}}": subject,
        }
        
        # Add any additional kwargs
        for key, value in kwargs.items():
            replacements[f"{{{{{key}}}}}"] = str(value)
        
        for placeholder, value in replacements.items():
            filled = filled.replace(placeholder, value)
        
        return filled
    
    def solve(
        self,
        request: SolverRequest,
        system_prompt: str,
        use_cache: bool = True,
    ) -> SolverResponse:
        """
        Generate solutions for the requested questions.
        
        Args:
            request: SolverRequest with PDF path, questions, and metadata
            system_prompt: Filled system prompt (parameterized by client)
            use_cache: Whether to use content caching for the PDF
            
        Returns:
            SolverResponse with all generated solutions
        """
        start_time = datetime.now()
        
        logger.info(f"Solving {len(request.questions)} questions from {request.pdf_path.name}")
        
        # Build user prompt
        question_list = ", ".join(request.questions)
        user_prompt = f"Please solve the following exercises from the attached chapter: {question_list}."
        
        # Get model config
        model_config = self.config.solver_model
        
        # Generate with or without cache
        if use_cache:
            # Cache the PDF for this session
            if self._cached_document is None or self._cached_document.file_uri != str(request.pdf_path.resolve()):
                self._cached_document = self.client.cache_document(
                    document_path=request.pdf_path,
                    model_id=model_config.model_id,
                )
            
            result = self.client.generate_with_cache(
                model_config=model_config,
                prompt=user_prompt,
                cached_doc=self._cached_document,
                system_instruction=system_prompt,
            )
        else:
            result = self.client.generate(
                model_config=model_config,
                prompt=user_prompt,
                document_path=request.pdf_path,
                system_instruction=system_prompt,
            )
        
        # Parse solutions from response (now returns exercise grouping too)
        solutions, exercise_solutions, chapter_number = self._parse_solutions(result, request)
        
        # Associate generated images with solutions
        if result.images:
            self._associate_images(solutions, result.images)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return SolverResponse(
            request=request,
            solutions=solutions,
            exercise_solutions=exercise_solutions,
            raw_response=result.text,
            processing_time_seconds=processing_time,
            model_used=model_config.model_id,
            chapter_number=chapter_number or request.chapter_number,
        )
    
    def solve_batch(
        self,
        requests: List[SolverRequest],
        system_prompt: str,
        use_cache: bool = True,
    ) -> List[SolverResponse]:
        """
        Solve multiple requests in batch.
        
        Useful when processing questions from multiple chapters or
        when splitting large question sets across multiple API calls.
        """
        responses = []
        
        for i, request in enumerate(requests):
            logger.info(f"Processing request {i+1}/{len(requests)}")
            
            response = self.solve(request, system_prompt, use_cache)
            responses.append(response)
            
            # Delay between requests
            if i < len(requests) - 1:
                import time
                time.sleep(self.config.batch_delay_seconds)
        
        return responses
    
    def _parse_solutions(
        self,
        result: GeneratedContent,
        request: SolverRequest,
    ) -> Tuple[List[Solution], List[ExerciseSolutions], Optional[str]]:
        """
        Parse the model's response into Solution objects.
        
        Supports both new JSON format (exercise-grouped) and legacy markdown.
        
        Returns:
            Tuple of (flat solutions list, exercise-grouped solutions, chapter_number)
        """
        solutions = []
        exercise_solutions = []
        chapter_number = None
        text = result.text
        
        # First, try to parse as JSON (new format)
        json_text = self._extract_json(text)
        
        if json_text:
            try:
                parsed = json.loads(json_text)
                
                # Check for new exercise-grouped format
                if isinstance(parsed, dict) and 'exercises' in parsed:
                    chapter_number = parsed.get('chapter_number')
                    
                    for ex in parsed.get('exercises', []):
                        exercise_title = ex.get('exercise_title', 'EXERCISES')
                        ex_solutions = []
                        
                        for sol_dict in ex.get('solutions', []):
                            solution = self._dict_to_solution(sol_dict)
                            ex_solutions.append(solution)
                            solutions.append(solution)  # Also add to flat list
                        
                        if ex_solutions:
                            exercise_solutions.append(ExerciseSolutions(
                                exercise_title=exercise_title,
                                solutions=ex_solutions
                            ))
                    
                    logger.info(f"Parsed {len(solutions)} solutions in {len(exercise_solutions)} exercises from JSON")
                    return solutions, exercise_solutions, chapter_number
                
                # Legacy JSON format (flat solutions array)
                elif isinstance(parsed, dict) and 'solutions' in parsed:
                    solution_dicts = parsed['solutions']
                    chapter_number = parsed.get('chapter_number') or parsed.get('metadata', {}).get('chapter_number')
                elif isinstance(parsed, list):
                    solution_dicts = parsed
                else:
                    solution_dicts = [parsed]
                
                for sol_dict in solution_dicts:
                    solution = self._dict_to_solution(sol_dict)
                    solutions.append(solution)
                
                logger.info(f"Parsed {len(solutions)} solutions from JSON (legacy format)")
                return solutions, exercise_solutions, chapter_number
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response: {e}")
        
        # Fallback: try markdown parsing (legacy)
        parsed_solutions = self._parse_markdown_solutions(text)
        
        if parsed_solutions:
            solutions = parsed_solutions
            logger.info(f"Parsed {len(solutions)} solutions from markdown")
        else:
            # If all parsing fails, store raw text
            logger.warning("Could not parse structured response, storing raw text")
            solutions.append(Solution(
                question_id="raw_response",
                question_text=f"Questions: {', '.join(request.questions)}",
                final_answer=text,
            ))
        
        # Return solutions (images are associated by caller)
        return solutions, exercise_solutions, chapter_number
    
    def _parse_markdown_solutions(self, text: str) -> List[Solution]:
        """
        Parse markdown-formatted solutions.
        
        Expected format:
        ## QUESTION [question_number]
        **Question Text:** ...
        
        ### STEP 1 | [step_type]
        **Hint:** ...
        **Explanation:** ...
        **Formula:** ...
        
        ### FINAL ANSWER
        ...
        """
        solutions = []
        
        # Split by question headers
        # Pattern: ## QUESTION followed by question number
        question_pattern = r'##\s*QUESTION\s+(.+?)(?=##\s*QUESTION|\Z)'
        question_blocks = re.findall(question_pattern, text, re.DOTALL | re.IGNORECASE)
        
        if not question_blocks:
            # Try alternate pattern without "QUESTION" keyword
            question_pattern = r'---\s*\n##\s+(.+?)(?=---|\Z)'
            question_blocks = re.findall(question_pattern, text, re.DOTALL)
        
        for block in question_blocks:
            solution = self._parse_single_question_block(block)
            if solution:
                solutions.append(solution)
        
        return solutions
    
    def _parse_single_question_block(self, block: str) -> Optional[Solution]:
        """Parse a single question block from markdown."""
        try:
            # Extract question ID from first line
            lines = block.strip().split('\n')
            question_id = lines[0].strip() if lines else "unknown"
            
            # Extract question text
            question_text_match = re.search(
                r'\*\*Question\s*Text:\*\*\s*(.+?)(?=###|\Z)', 
                block, 
                re.DOTALL | re.IGNORECASE
            )
            question_text = question_text_match.group(1).strip() if question_text_match else ""
            
            # Extract steps
            steps = []
            step_pattern = r'###\s*STEP\s+(\d+)\s*\|\s*(\w+)\s*\n(.*?)(?=###|\Z)'
            step_matches = re.findall(step_pattern, block, re.DOTALL | re.IGNORECASE)
            
            for step_num, step_type, step_content in step_matches:
                step = self._parse_step_content(int(step_num), step_type.lower(), step_content)
                steps.append(step)
            
            # Extract final answer
            final_answer_match = re.search(
                r'###\s*FINAL\s*ANSWER\s*\n(.+?)(?=---|\Z)', 
                block, 
                re.DOTALL | re.IGNORECASE
            )
            final_answer = final_answer_match.group(1).strip() if final_answer_match else ""
            
            return Solution(
                question_id=question_id,
                question_text=question_text,
                steps=steps,
                final_answer=final_answer,
            )
            
        except Exception as e:
            logger.warning(f"Error parsing question block: {e}")
            return None
    
    def _parse_step_content(self, step_num: int, step_type: str, content: str) -> SolutionStep:
        """Parse the content of a single step, preserving LaTeX, SVG, SMILES, etc."""
        # Extract hint
        hint_match = re.search(r'\*\*Hint:\*\*\s*(.+?)(?=\*\*|\Z)', content, re.DOTALL | re.IGNORECASE)
        hint = hint_match.group(1).strip() if hint_match else ""
        
        # Extract explanation
        explanation_match = re.search(r'\*\*Explanation:\*\*\s*(.+?)(?=\*\*Formula|\*\*Visual|\Z)', content, re.DOTALL | re.IGNORECASE)
        explanation = explanation_match.group(1).strip() if explanation_match else ""
        
        # Extract formula (preserve LaTeX exactly)
        formula_match = re.search(r'\*\*Formula:\*\*\s*(.+?)(?=\*\*|\n\n|\Z)', content, re.DOTALL | re.IGNORECASE)
        formula = formula_match.group(1).strip() if formula_match else None
        
        # Extract embedded format blocks
        embedded_formats = self._extract_format_blocks(content)
        
        # Check for visual assets
        visual_asset = self._extract_visual_asset(content)
        
        return SolutionStep(
            step_number=step_num,
            step_type=step_type,
            nudge_hint=hint,
            explanation=explanation,
            latex_formula=formula,
            visual_asset=visual_asset,
            embedded_formats=embedded_formats,
        )
    
    def _extract_format_blocks(self, content: str) -> List[FormatBlock]:
        """Extract SVG, SMILES, and other format blocks from content."""
        blocks = []
        
        # Extract SVG blocks
        svg_pattern = r'```svg\s*(.*?)\s*```'
        for match in re.finditer(svg_pattern, content, re.DOTALL | re.IGNORECASE):
            blocks.append(FormatBlock(
                block_type="svg",
                content=match.group(1).strip(),
            ))
        
        # Also find inline SVG (without code fence)
        inline_svg_pattern = r'(<svg[^>]*>.*?</svg>)'
        for match in re.finditer(inline_svg_pattern, content, re.DOTALL | re.IGNORECASE):
            blocks.append(FormatBlock(
                block_type="svg",
                content=match.group(1).strip(),
            ))
        
        # Extract SMILES blocks
        smiles_pattern = r'```smiles\s*(.*?)\s*```'
        for match in re.finditer(smiles_pattern, content, re.DOTALL | re.IGNORECASE):
            smiles_content = match.group(1).strip()
            # Check for caption on next line
            blocks.append(FormatBlock(
                block_type="smiles",
                content=smiles_content,
            ))
        
        # Extract image references [IMAGE: description]
        image_ref_pattern = r'\[IMAGE:\s*([^\]]+)\]'
        for match in re.finditer(image_ref_pattern, content, re.IGNORECASE):
            blocks.append(FormatBlock(
                block_type="image_ref",
                content=match.group(1).strip(),
            ))
        
        # Extract display LaTeX blocks ($$...$$)
        display_latex_pattern = r'\$\$(.*?)\$\$'
        for match in re.finditer(display_latex_pattern, content, re.DOTALL):
            blocks.append(FormatBlock(
                block_type="latex_display",
                content=match.group(1).strip(),
            ))
        
        return blocks
    
    def _extract_visual_asset(self, content: str) -> VisualAsset:
        """Extract visual asset information from step content."""
        # Check for SVG
        if re.search(r'```svg|<svg', content, re.IGNORECASE):
            svg_match = re.search(r'```svg\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
            if not svg_match:
                svg_match = re.search(r'(<svg[^>]*>.*?</svg>)', content, re.DOTALL | re.IGNORECASE)
            if svg_match:
                return VisualAsset(
                    required=True,
                    type="svg_code",
                    data=svg_match.group(1).strip(),
                )
        
        # Check for SMILES
        smiles_match = re.search(r'```smiles\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
        if smiles_match:
            return VisualAsset(
                required=True,
                type="smiles_code",
                data=smiles_match.group(1).strip(),
            )
        
        # Check for image reference
        image_ref_match = re.search(r'\[IMAGE:\s*([^\]]+)\]', content, re.IGNORECASE)
        if image_ref_match:
            return VisualAsset(
                required=True,
                type="image_generation",
                caption=image_ref_match.group(1).strip(),
            )
        
        return VisualAsset()
    
    def _sanitize_json_escapes(self, text: str) -> str:
        """
        Sanitize JSON string by fixing common escape sequence errors from model output.
        
        Models sometimes output invalid escape sequences in JSON, especially in LaTeX:
        - Single backslash before letters (like \Delta instead of \\Delta)
        - Backslash-space (\ ) which is invalid
        - Other invalid escape sequences
        
        This function attempts to fix these without breaking valid JSON escapes.
        """
        # Valid JSON escape sequences: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
        # We need to double-escape any backslash NOT followed by these valid chars
        
        def fix_backslash(match):
            """Fix a single backslash that's not a valid escape."""
            char_after = match.group(1)
            # If it's a valid escape char, keep as-is (already escaped or special)
            if char_after in '"\\bfnrt/':
                return match.group(0)
            # If it's 'u' followed by 4 hex digits (unicode), keep as-is
            # This is handled by checking for \u separately
            # Otherwise, double the backslash
            return '\\\\' + char_after
        
        # First, normalize already doubled backslashes to a placeholder
        # This prevents quadruple-escaping when we fix singles
        placeholder = "\x00DOUBLE_BACKSLASH\x00"
        text = text.replace('\\\\', placeholder)
        
        # Now fix single backslashes that aren't followed by valid escape chars
        # Pattern: single backslash followed by non-escape character
        # Valid escape chars: " \ / b f n r t u
        # We need to be careful with 'u' - only valid if followed by 4 hex digits
        pattern = r'\\([^"\\bfnrtu/])'
        text = re.sub(pattern, fix_backslash, text)
        
        # Handle \u that's NOT followed by 4 hex digits (invalid unicode escape)
        pattern_u = r'\\u([^0-9a-fA-F]|[0-9a-fA-F]{0,3}(?![0-9a-fA-F]))'
        def fix_invalid_unicode(match):
            return '\\\\u' + match.group(1)
        text = re.sub(pattern_u, fix_invalid_unicode, text)
        
        # Restore doubled backslashes
        text = text.replace(placeholder, '\\\\')
        
        return text
    
    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from text that may contain markdown or other content."""
        # Try to find JSON array or object
        # Use findall to get ALL matches, then take the last valid one
        # (model often outputs thinking text before the final JSON)
        
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # Markdown JSON code block
            r'```\s*([\s\S]*?)\s*```',       # Generic code block
        ]
        
        # First, try to find all markdown code blocks and use the last valid JSON one
        for pattern in patterns:
            matches = re.findall(pattern, text)
            # Check matches in reverse order (last one is usually the final JSON)
            for candidate in reversed(matches):
                candidate = candidate.strip()
                if candidate.startswith('[') or candidate.startswith('{'):
                    # First try to parse as-is
                    try:
                        json.loads(candidate)
                        logger.info(f"Found valid JSON in code block ({len(candidate)} chars)")
                        return candidate
                    except json.JSONDecodeError as e:
                        # Try sanitizing escape sequences
                        logger.debug(f"JSON parse failed, attempting escape sanitization: {e}")
                        sanitized = self._sanitize_json_escapes(candidate)
                        try:
                            json.loads(sanitized)
                            logger.info(f"Found valid JSON after escape sanitization ({len(sanitized)} chars)")
                            return sanitized
                        except json.JSONDecodeError:
                            continue
        
        # Fallback: try to find raw JSON array or object (last occurrence)
        # Look for JSON array
        array_matches = re.findall(r'(\[\s*\{[\s\S]*?\}\s*\])', text)
        for candidate in reversed(array_matches):
            try:
                json.loads(candidate)
                logger.info(f"Found valid JSON array ({len(candidate)} chars)")
                return candidate
            except json.JSONDecodeError:
                # Try sanitizing
                sanitized = self._sanitize_json_escapes(candidate)
                try:
                    json.loads(sanitized)
                    logger.info(f"Found valid JSON array after sanitization ({len(sanitized)} chars)")
                    return sanitized
                except json.JSONDecodeError:
                    continue
        
        # Look for JSON object
        object_matches = re.findall(r'(\{[\s\S]*?\})', text)
        for candidate in reversed(object_matches):
            try:
                json.loads(candidate)
                logger.info(f"Found valid JSON object ({len(candidate)} chars)")
                return candidate
            except json.JSONDecodeError:
                # Try sanitizing
                sanitized = self._sanitize_json_escapes(candidate)
                try:
                    json.loads(sanitized)
                    logger.info(f"Found valid JSON object after sanitization ({len(sanitized)} chars)")
                    return sanitized
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _dict_to_solution(self, d: Dict[str, Any]) -> Solution:
        """Convert a dictionary to a Solution object."""
        steps = []
        for step_dict in d.get("steps", []):
            visual = step_dict.get("visual_asset", {})
            steps.append(SolutionStep(
                step_number=step_dict.get("step_number", 0),
                step_type=step_dict.get("step_type", "conceptual"),
                nudge_hint=step_dict.get("nudge_hint", ""),
                explanation=step_dict.get("explanation", ""),
                latex_formula=step_dict.get("latex_formula"),
                visual_asset=VisualAsset(
                    required=visual.get("required", False),
                    type=visual.get("type", "none"),
                    data=visual.get("data", ""),
                    caption=visual.get("caption", ""),
                ),
            ))
        
        return Solution(
            question_id=d.get("question_id", "unknown"),
            question_text=d.get("question_text", ""),
            steps=steps,
            final_answer=d.get("final_answer", ""),
        )
    
    def _associate_images(
        self,
        solutions: List[Solution],
        images: List[Dict[str, Any]],
    ):
        """Associate generated images with the appropriate solutions."""
        # For now, distribute images across solutions
        # In a more sophisticated version, we'd use image metadata/captions
        for i, img in enumerate(images):
            if solutions:
                sol_idx = i % len(solutions)
                solutions[sol_idx].generated_images.append(img["filename"])
    
    def save_response(
        self,
        response: SolverResponse,
        output_dir: Optional[Path] = None,
        save_images: bool = True,
    ) -> Path:
        """
        Save the solver response to disk.
        
        Creates:
        - solution_<timestamp>.json - The main solution file
        - images/ - Directory with any generated images
        
        Returns:
            Path to the saved JSON file
        """
        output_dir = output_dir or self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        subject = response.request.subject.lower()
        base_filename = f"solution_{subject}_{timestamp}"
        
        # Save JSON (structured data)
        json_path = output_dir / f"{base_filename}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(response.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved structured JSON to: {json_path}")
        
        # Save raw markdown (human-readable)
        md_path = output_dir / f"{base_filename}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Solutions for {response.request.subject}\n\n")
            f.write(f"**PDF:** {response.request.pdf_path.name}\n")
            f.write(f"**Questions:** {', '.join(response.request.questions)}\n")
            f.write(f"**Model:** {response.model_used}\n")
            f.write(f"**Generated:** {response.timestamp}\n\n")
            f.write("---\n\n")
            f.write("## Raw Model Response\n\n")
            f.write(response.raw_response)
        logger.info(f"Saved raw markdown to: {md_path}")
        
        # Save images if present
        if save_images and any(s.generated_images for s in response.solutions):
            images_dir = output_dir / self.config.image_subdir
            images_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Images directory: {images_dir}")
        
        return json_path
    
    def save_images(
        self,
        result: GeneratedContent,
        output_dir: Path,
        prefix: str = "solution",
    ) -> List[Path]:
        """
        Save generated images from a result.
        
        Returns list of saved image paths.
        """
        saved_paths = []
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for img in result.images:
            filename = f"{prefix}_{img['index']}.{img['mime_type'].split('/')[-1]}"
            path = output_dir / filename
            
            with open(path, "wb") as f:
                f.write(img["data"])
            
            saved_paths.append(path)
            logger.info(f"Saved image: {path}")
        
        return saved_paths
    
    def cleanup(self):
        """Clean up resources (caches, etc.)."""
        if self._cached_document:
            self.client.clear_cache(self._cached_document)
            self._cached_document = None
