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
from typing import List, Dict, Any, Optional, Tuple, Callable
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


@dataclass
class PromptSet:
    """Per-source stage system prompts for GoldenGenerator.

    Inject a PromptSet to swap the JEE-specific persona (Stage 2) for NCERT,
    Teacher Agent, or M4 Feedback without touching stage logic.
    build_solver_user: optional callable(record) -> str for callers that build
    the user prompt programmatically; None means the caller passes the prompt
    string directly to generate_assembly_line.
    """
    solver_system: str
    tutor_system: str
    formatter_system_prefix: str  # prepended to the per-call schema instruction in stage 3
    build_solver_user: Optional[Callable[..., str]] = None


DEFAULT_PROMPT_SET = PromptSet(
    solver_system=(
        "You are a cold, calculating Math & Physics expert. Focus entirely on mathematical correctness. "
        "Parse the images, compute logic, dimensional analysis, and raw step-by-step logic. "
        "Do not worry about pedagogy or strict formatting beyond clear derivations. "
        "If textbook theory or context is provided, use it strictly to ground your calculations "
        "and prevent hallucination—never mathematically force or 'fudge' numbers simply to match an expected answer key. "
        "Return the raw textual derivations and final answer."
    ),
    tutor_system=(
        "You are a Master Teacher reviewing a TA's logic for an IIT-JEE student. "
        "Take the raw math derivations provided and translate them into a pedagogical, step-by-step tutorial. "
        "Inject helpful conceptual explanations and 'nudge_hints' (tips for where students get stuck). "
        "Validate that the logic flows correctly and fix any subtle math/physics errors. "
        "CRITICAL: NEVER skip algebraic substitutions or calculations. You MUST explicitly write out the final mathematical simplification step that bridges the formulas to the exact final answer option. "
        "CRITICAL RULE FOR HINTS: Your `nudge_hints` must be purely Socratic questions that guide the student to think. NEVER provide direct statements that quote the theory, and NEVER give away the exact next step or the answer. "
        "If the solver derivation quotes direct textbook theory or laws (e.g. Le Chatelier's), DO NOT write the rule as a direct statement in your hint. Instead, formulate a question asking the student how that specific law applies. "
        "Do not output JSON, just structure the pedagogical text clearly."
    ),
    formatter_system_prefix=(
        "You are a rigid Data Architect API Endpoint. "
        "Map the provided tutor's text perfectly into the required JSON schema output. "
        "Enforce all LaTeX/MathJax invariant syntax (e.g., proper inline `$` or `$$` blocking). "
        "Do NOT add, change, or evaluate the logic. Just format the text you are given into JSON. "
        "Here is the strict schema instruction:\n\n"
    ),
)


class GoldenGenerator:
    """Wrapper around GeminiClient to generate refined solutions via Critique Loop or Assembly Line."""

    def __init__(self, client: 'GeminiClient', config: 'PipelineConfig', prompts: 'PromptSet' = None):
        self.client = client
        self.config = config
        self.prompts = prompts if prompts is not None else DEFAULT_PROMPT_SET

    def _stage_1_expert_solver(self, question_text: str, image_urls: Optional[List[str]]) -> str:
        """Stage 1: Raw mathematical/physics solver."""
        logger.info("[GoldenGenerator] Assembly Stage 1: Expert Solver")
        response = self.client.generate(
            model_config=self.config.solver_model,
            prompt=question_text,
            system_instruction=self.prompts.solver_system,
            image_urls=image_urls,
        )
        return response.text

    def _stage_2_pedagogical_tutor(self, question_text: str, solver_derivation: str) -> str:
        """Stage 2: Pedagogical tutor and reviewer."""
        logger.info("[GoldenGenerator] Assembly Stage 2: Pedagogical Tutor")
        prompt = f"Question:\n{question_text}\n\nSolver Derivation:\n{solver_derivation}\n\nPlease generate a pedagogical step-by-step tutorial based on this."
        response = self.client.generate(
            model_config=self.config.tutor_model,
            prompt=prompt,
            system_instruction=self.prompts.tutor_system,
        )
        return response.text

    def _stage_3_json_formatter(self, tutor_tutorial: str, original_system_prompt: str) -> 'GeneratedContent':
        """Stage 3: JSON Formatter."""
        logger.info("[GoldenGenerator] Assembly Stage 3: JSON Formatter")
        system_instruction = self.prompts.formatter_system_prefix + original_system_prompt
        prompt = f"Please map the following tutorial into the strict JSON schema:\n\n{tutor_tutorial}"
        response = self.client.generate(
            model_config=self.config.formatter_model,
            prompt=prompt,
            system_instruction=system_instruction,
        )
        return response

    def generate_assembly_line(self, prompt: str, system_prompt: str, image_urls: Optional[List[str]] = None) -> 'GeneratedContent':
        """
        Three-pass generation: Solver -> Tutor -> JSON Formatter.
        """
        # 1. Expert Solver (context: question + images)
        solver_text = self._stage_1_expert_solver(prompt, image_urls)
        
        # 2. Pedagogical Tutor (context: question + solver derivations, no images)
        tutor_text = self._stage_2_pedagogical_tutor(prompt, solver_text)
        
        # 3. JSON Formatter (context: pure tutor text into strict schema)
        formatted_response = self._stage_3_json_formatter(tutor_text, system_prompt)
        
        return formatted_response

    def generate_with_feedback(self, prompt: str, system_prompt: str, feedback_text: str, image_urls: Optional[List[str]] = None) -> 'GeneratedContent':
        """
        Closed-loop generation: Augments the stage 1 prompt with critique feedback to avoid blind retries.
        """
        logger.info("[GoldenGenerator] Assembly Line - Retry with explicit Evaluator Feedback")
        augmented_prompt = (
            f"{prompt}\n\n"
            f"=== PRIOR ATTEMPT CRITICAL FEEDBACK ===\n"
            f"Your previous attempt failed review for this exact reason:\n\"{feedback_text}\"\n"
            f"You MUST explicitly correct this mistake in your logical derivation."
        )
        
        # Push augmented prompt into standard 3-pass assembly line
        return self.generate_assembly_line(augmented_prompt, system_prompt, image_urls)

    def generate_with_critique(self, prompt: str, system_prompt: str, image_urls: Optional[List[str]] = None) -> 'GeneratedContent':
        """
        Two-pass generation: initial draft, followed by self-critique.
        image_urls: Optional list of figure image URLs to inline on Pass 1.
        """
        model_config = self.config.solver_model
        
        logger.info("[GoldenGenerator] Pass 1: Zero-Shot Generation")
        initial_response = self.client.generate(
            model_config=model_config,
            prompt=prompt,
            system_instruction=system_prompt,
            image_urls=image_urls,  # Give the model visual context for figures
        )
        
        logger.info("[GoldenGenerator] Pass 2: Critique and Refine")
        critique_prompt = f"""
        You are a rigorous IIT-JEE/NCERT expert peer reviewer acting as the 'Devil's Advocate'.
        Critically review the following problem solution to catch subtle errors before they reach the students.

        Checklist for strict compliance:
        1. Mathematics: Verify all arithmetic calculation bounds. Catch any hallucinatory leaps from step A to B.
        2. Physics: Ensure all dimensional units are consistent throughout every single step, not just the final step.
        3. Chemistry: Verify stoichiometry balancing, state symbols (s, l, g, aq) are present, and bonding logic is sound.
        4. MathJax Formatting: Ensure inline equations are perfectly wrapped in LaTeX constraints without breaking JSON schema.
        5. Pedagogical Flow: If the solution reads like an AI instead of a teacher, inject missing explanatory text or definitions.
        
        If the initial solution makes an error (no matter how small), FIX it. If it is already flawless, pass it through exactly as generated.
        
        Initial Solution:
        {initial_response.text}
        
        Output the final, corrected solution in the exact same expected JSON schema. Preserve all JSON structure keys.
        """
        
        refined_response = self.client.generate(
            model_config=model_config,
            prompt=critique_prompt,
            system_instruction=system_prompt,
            # No image_urls on critique pass — model already saw them
        )
        
        return refined_response
        
    def _sanitize_json_escapes(self, text: str) -> str:
        r"""
        Sanitize JSON string by fixing common escape sequence errors from model output.
        """
        def fix_backslash(match):
            char_after = match.group(1)
            if char_after in '"\\bfnrt/':
                return match.group(0)
            return '\\\\' + char_after
        
        placeholder = "\x00DOUBLE_BACKSLASH\x00"
        text = text.replace('\\\\', placeholder)
        
        pattern = r'\\([^"\\bfnrtu/])'
        text = re.sub(pattern, fix_backslash, text)
        
        pattern_u = r'\\u([^0-9a-fA-F]|[0-9a-fA-F]{0,3}(?![0-9a-fA-F]))'
        def fix_invalid_unicode(match):
            return '\\\\u' + match.group(1)
        text = re.sub(pattern_u, fix_invalid_unicode, text)
        
        text = text.replace(placeholder, '\\\\')
        return text


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
        from db_client import DatabaseClient
        self.db_client = DatabaseClient()
        self.golden_generator = GoldenGenerator(self.client, self.config)
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
        use_smart_context: bool = False,
    ) -> SolverResponse:
        """
        Generate solutions for the requested questions.
        
        Args:
            request: SolverRequest with PDF path, questions, and metadata
            system_prompt: Filled system prompt (parameterized by client)
            use_cache: Whether to use content caching for the PDF
            use_smart_context: Use PgVector context & GoldenGenerator instead of passing Full PDF
            
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
        
        # Branch execution based on architecture configuration
        if use_smart_context:
            logger.info("Using Localized Smart Context & GoldenGenerator.")
            chapter_id = None
            if request.chapter_number:
                chapter_id = self.db_client.get_chapter_id(request.class_level, request.subject, request.chapter_number)

            # --- Category 1 fix: Fetch full question text + question figures from DB ---
            # Pass the full pipeline IDs (e.g., EXERCISE_3_1_Q1) directly.
            # The DB method re-encodes the exercise title in SQL, so cross-exercise
            # collisions (e.g., Maths EXERCISE_3_1_Q1 vs EXERCISE_3_2_Q1) are impossible.
            question_figure_urls = []
            rich_question_blocks = []

            if chapter_id:
                try:
                    q_data_rows = self.db_client.get_questions_data_by_refs(chapter_id, request.questions)
                    for row in q_data_rows:
                        pipeline_id = row.get("pipeline_id", "")   # e.g. "EXERCISES_Q8.1"
                        q_text = row.get("question_text") or ""
                        fig_url = row.get("figure_url")
                        # Use the full pipeline ID as the label so Gemini echoes it back
                        block = f"**{pipeline_id}**: {q_text}" if q_text else f"**{pipeline_id}**"
                        if fig_url:
                            block += f"\n[Figure attached as image for {pipeline_id}]"
                            question_figure_urls.append(fig_url)
                        rich_question_blocks.append(block)
                    logger.info(f"Fetched full text for {len(q_data_rows)} question(s) from DB.")
                except Exception as e:
                    logger.warning(f"Could not fetch question data from DB: {e}")

            # Build prompt using full question text if available, else fall back to IDs
            if rich_question_blocks:
                user_prompt = (
                    "Please solve the following exercises from the textbook chapter.\n\n"
                    + "\n\n".join(rich_question_blocks)
                )
            else:
                user_prompt = f"Please solve the following exercises from the attached chapter: {question_list}."

            # --- Category 2 fix: Retrieve wider concept context (top_k=10) ---
            context_snippets = []
            figure_urls = []
            if chapter_id:
                logger.info(f"Retrieving PgVector context for chapter_id={chapter_id}")
                # Use the richer combined question text for a better embedding signal
                embed_text = " ".join(rich_question_blocks) if rich_question_blocks else question_list
                try:
                    q_embed = self.client.embed_text(embed_text)
                    chunks = self.db_client.get_smart_context_for_question(chapter_id, q_embed, top_k=10)
                    context_snippets = [c.get("chunk_text") for c in chunks if c.get("chunk_text")]
                    # Collect any textbook concept figure URLs from the retrieved chunks
                    figure_urls = [c.get("figure_url") for c in chunks if c.get("figure_url")]
                    if figure_urls:
                        logger.info(f"Found {len(figure_urls)} figure(s) from retrieved context chunks.")
                except Exception as e:
                    logger.warning(f"PgVector context retrieval failed: {e}")

            # Enhance prompt with retrieved Context
            if context_snippets:
                joined_context = "\n\n---\n".join(context_snippets)
                user_prompt += f"\n\nHere is some localized textbook context that may be helpful:\n{joined_context}"

            # Combine question-level figures + concept-index figures for Pass 1
            all_image_urls = question_figure_urls + figure_urls

            # Three-pass generation using GoldenGenerator's Assembly Line
            result = self.golden_generator.generate_assembly_line(user_prompt, system_prompt, image_urls=all_image_urls)
            
        elif use_cache and "gemini-3-pro-image-preview" not in model_config.model_id:
            # Traditional Full-PDF method with CachedContent
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
        use_smart_context: bool = False,
    ) -> List[SolverResponse]:
        """
        Solve multiple requests in batch.
        
        Useful when processing questions from multiple chapters or
        when splitting large question sets across multiple API calls.
        """
        responses = []
        
        for i, request in enumerate(requests):
            logger.info(f"Processing request {i+1}/{len(requests)}")
            
            response = self.solve(request, system_prompt, use_cache, use_smart_context)
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
        
        # Try to parse all JSON blocks found in the output
        json_texts = self._extract_all_json(text)
        
        if json_texts:
            for json_text in json_texts:
                try:
                    parsed = json.loads(json_text)
                    
                    # Check for new exercise-grouped format
                    if isinstance(parsed, dict) and 'exercises' in parsed:
                        if not chapter_number:
                            chapter_number = parsed.get('chapter_number')
                        
                        for ex in parsed.get('exercises', []):
                            exercise_title = ex.get('exercise_title', 'EXERCISES')
                            ex_solutions = []
                            
                            for sol_dict in ex.get('solutions', []):
                                if not self._is_solution_dict(sol_dict):
                                    logger.debug("Skipping non-solution entry inside exercises[].solutions")
                                    continue
                                solution = self._dict_to_solution(sol_dict)
                                ex_solutions.append(solution)
                                solutions.append(solution)  # Also add to flat list
                            
                            if ex_solutions:
                                exercise_solutions.append(ExerciseSolutions(
                                    exercise_title=exercise_title,
                                    solutions=ex_solutions
                                ))
                    
                    # Legacy JSON format (flat solutions array)
                    elif isinstance(parsed, dict) and 'solutions' in parsed:
                        solution_dicts = parsed['solutions']
                        if not chapter_number:
                            chapter_number = parsed.get('chapter_number') or parsed.get('metadata', {}).get('chapter_number')
                        for sol_dict in solution_dicts:
                            if not self._is_solution_dict(sol_dict):
                                logger.debug("Skipping non-solution entry inside solutions[]")
                                continue
                            solution = self._dict_to_solution(sol_dict)
                            solutions.append(solution)
                    elif isinstance(parsed, list):
                        for sol_dict in parsed:
                            if not self._is_solution_dict(sol_dict):
                                logger.debug("Skipping non-solution dict from top-level list")
                                continue
                            solution = self._dict_to_solution(sol_dict)
                            solutions.append(solution)
                    else:
                        if self._is_solution_dict(parsed):
                            solution = self._dict_to_solution(parsed)
                            solutions.append(solution)
                        else:
                            logger.debug("Skipping parsed JSON object that does not look like a solution")
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse a JSON response block: {e}")
            
            logger.info(f"Parsed {len(solutions)} solutions in {len(exercise_solutions)} exercises from JSON")
        else:
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
        
        # Post-process: attempt to map LLM's returned question_ids back to the requested ones
        if request and hasattr(request, 'questions') and request.questions:
            available_req_ids = list(request.questions)
            
            # Fast pass: EXACT matches
            for sol in solutions:
                if sol.question_id in available_req_ids:
                    available_req_ids.remove(sol.question_id)
            
            # Second pass: suffix matches to fix stripped prepends like EXERCISE_2_1_Q
            for sol in solutions:
                raw_id = sol.question_id
                if raw_id not in request.questions:
                    # Normalise: strip "Question " prefix that Gemini returns when the
                    # new rich-text prompt is used (e.g. "Question 8.11" -> "8.11")
                    normalised_id = raw_id
                    if normalised_id.lower().startswith("question "):
                        normalised_id = normalised_id[9:].strip()
                    
                    best_match = None
                    for req_id in available_req_ids:
                        if (req_id.endswith(f"_{normalised_id}")
                                or req_id.endswith(f"Q{normalised_id}")
                                or req_id.endswith(normalised_id)):
                            best_match = req_id
                            break
                    if best_match:
                        sol.question_id = best_match
                        available_req_ids.remove(best_match)
                        logger.debug(f"Remapped returned question_id '{raw_id}' to requested '{best_match}'")

            # Keep only requested IDs to avoid polluting results with malformed fragments.
            requested_ids = set(request.questions)
            filtered = []
            seen_ids = set()
            for sol in solutions:
                if sol.question_id in requested_ids:
                    if sol.question_id not in seen_ids:
                        filtered.append(sol)
                        seen_ids.add(sol.question_id)
                else:
                    logger.warning(f"Dropping unexpected solution id from model output: {sol.question_id}")
            solutions = filtered
        
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
        r"""
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
    
    def _extract_all_json(self, text: str) -> List[str]:
        """Extract all valid JSON blocks from text that may contain markdown or other content."""
        valid_jsons = []
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # Markdown JSON code block
            r'```\s*([\s\S]*?)\s*```',       # Generic code block
        ]
        
        # Collect candidates
        candidates = []
        for pattern in patterns:
            candidates.extend(re.findall(pattern, text))
            
        if not candidates:
            # Fallback arrays
            candidates.extend(re.findall(r'(\[\s*\{[\s\S]*?\}\s*\])', text))
            # Fallback objects
            candidates.extend(re.findall(r'(\{[\s\S]*?\})', text))
            
        for candidate in candidates:
            candidate = candidate.strip()
            if candidate.startswith('[') or candidate.startswith('{'):
                try:
                    json.loads(candidate)
                    valid_jsons.append(candidate)
                    continue
                except json.JSONDecodeError:
                    sanitized = self._sanitize_json_escapes(candidate)
                    try:
                        json.loads(sanitized)
                        valid_jsons.append(sanitized)
                    except json.JSONDecodeError:
                        pass
        return valid_jsons
    
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

    def _is_solution_dict(self, value: Any) -> bool:
        """Return True only for dictionaries that look like solution payloads."""
        if not isinstance(value, dict):
            return False

        if "question_id" in value:
            return True

        # Allow minimal fallback shape for older/variant model outputs.
        has_content = any(key in value for key in ("question_text", "steps", "final_answer"))
        return has_content
    
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
