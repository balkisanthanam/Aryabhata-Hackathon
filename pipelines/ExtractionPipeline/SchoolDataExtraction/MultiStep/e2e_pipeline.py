"""
End-to-End Pipeline Orchestrator for AryaBhatta.

This module orchestrates the complete extraction-to-database pipeline:
1. Stage 1: Extract questions from PDF (two-pass)
2. Upload figure images to Azure Blob Storage
3. Ingest questions to PostgreSQL (ExerciseData, QuestionData)
4. Stage 2: Generate solutions for each question
5. Update solutions in PostgreSQL

Features:
- --local-only: Skip database and blob uploads, save to local JSON
- --force-rerun: Re-process even if data exists (uses UPSERT)
- Per-chapter resumability via state file
- Supports managed identity for Azure services

Usage:
    python e2e_pipeline.py --pdf chapter.pdf --book-id 1 --subject Physics
    python e2e_pipeline.py --pdf chapter.pdf --local-only
"""

import json
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime

from extraction_engine import ExtractionEngine, ExtractionRequest, ExtractionResponse, ExtractedQuestion, ExerciseSection, VisualMetadata
from solver_engine import SolverEngine, SolverRequest, SolverResponse
from config import PipelineConfig

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    """State tracking for resumable pipeline runs."""
    pdf_path: str
    chapter_number: Optional[str] = None
    
    # Stage tracking
    stage1_complete: bool = False
    stage2_complete: bool = False
    db_ingestion_complete: bool = False
    
    # IDs for resumability
    chapter_id: Optional[int] = None
    exercise_ids: Dict[str, int] = field(default_factory=dict)  # exercise_title -> ExerciseId
    question_ids: Dict[str, int] = field(default_factory=dict)  # question_ref -> QuestionId
    
    # Stage 2 incremental checkpointing
    solved_questions: List[str] = field(default_factory=list)  # question_ids that have been solved
    
    # Output paths
    extraction_json_path: Optional[str] = None
    solutions_json_path: Optional[str] = None
    
    # Timestamps
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    
    def save(self, path: Path):
        """Save state to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2)
        logger.debug(f"State saved to {path}")
    
    @classmethod
    def load(cls, path: Path) -> 'PipelineState':
        """Load state from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(**data)


def _reconstruct_extraction_response(extraction_data: dict, pdf_path: Path) -> ExtractionResponse:
    """
    Reconstruct an ExtractionResponse from saved JSON data.
    
    This enables resumption of DB ingestion when pipeline is interrupted
    after Stage 1 completes but before DB ingestion.
    """
    # Build ExtractionRequest (minimal, for compatibility)
    request = ExtractionRequest(
        pdf_path=pdf_path,
        class_level=extraction_data.get('metadata', {}).get('class', '11th'),
        board=extraction_data.get('metadata', {}).get('board', 'CBSE'),
        subject=extraction_data.get('metadata', {}).get('subject', 'Physics'),
        chapter_name=extraction_data.get('metadata', {}).get('chapter')
    )
    
    # Build ExtractedQuestion objects
    questions = []
    for q in extraction_data.get('questions', []):
        visual_data = VisualMetadata()
        if q.get('visual_data'):
            vd = q['visual_data']
            visual_data = VisualMetadata(
                type=vd.get('type', 'NONE'),
                description=vd.get('description', ''),
                box_2d=vd.get('box_2d'),
                visual_source=vd.get('visual_source'),
                smiles=vd.get('smiles'),
                cropped_image_path=vd.get('cropped_image_path')
            )
        
        questions.append(ExtractedQuestion(
            question_id=q['question_id'],
            question_text=q.get('question_text', ''),
            page_number=q.get('page_number', 0),
            visual_required=q.get('visual_required', False),
            visual_data=visual_data,
            figure_references=q.get('figure_references', [])
        ))
    
    # Build ExerciseSection objects
    exercise_sections = []
    for ex in extraction_data.get('exercises', []):
        ex_questions = []
        for q in ex.get('questions', []):
            visual_data = VisualMetadata()
            if q.get('visual_data'):
                vd = q['visual_data']
                visual_data = VisualMetadata(
                    type=vd.get('type', 'NONE'),
                    description=vd.get('description', ''),
                    box_2d=vd.get('box_2d'),
                    visual_source=vd.get('visual_source'),
                    smiles=vd.get('smiles'),
                    cropped_image_path=vd.get('cropped_image_path')
                )
            
            ex_questions.append(ExtractedQuestion(
                question_id=q['question_id'],
                question_text=q.get('question_text', ''),
                page_number=q.get('page_number', 0),
                visual_required=q.get('visual_required', False),
                visual_data=visual_data,
                figure_references=q.get('figure_references', [])
            ))
        
        exercise_sections.append(ExerciseSection(
            title=ex.get('exercise_title', 'EXERCISES'),
            start_page=ex.get('start_page', 0) - 1,  # Convert back to 0-indexed
            end_page=(ex.get('end_page', 0) or ex.get('start_page', 0)) - 1,
            total_questions=len(ex_questions),
            questions=ex_questions
        ))
    
    return ExtractionResponse(
        request=request,
        questions=questions,
        exercise_sections=exercise_sections,
        raw_responses=[],
        chapter_number=extraction_data.get('metadata', {}).get('chapter_number'),
        model_used=extraction_data.get('metadata', {}).get('model', ''),
        processing_time_seconds=extraction_data.get('metadata', {}).get('processing_time_seconds', 0)
    )


class E2EPipeline:
    """
    End-to-End Pipeline for question extraction and solution generation.
    
    Orchestrates:
    - Stage 1: Question extraction from PDF
    - Blob upload for figures
    - Database ingestion (exercises, questions)
    - Stage 2: Solution generation
    - Database update with solutions
    """
    
    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        use_managed_identity: bool = True,
        local_only: bool = False
    ):
        """
        Initialize pipeline.
        
        Args:
            config: Pipeline configuration
            use_managed_identity: Use Azure Managed Identity for DB/Blob
            local_only: Skip database and blob operations
        """
        self.config = config or PipelineConfig.from_env()
        self.use_managed_identity = use_managed_identity
        self.local_only = local_only
        
        # Initialize engines
        self.extraction_engine = ExtractionEngine(self.config)
        self.solver_engine = SolverEngine(self.config)
        
        # Initialize Azure clients (lazy, only if needed)
        self._db_client = None
        self._blob_client = None
        
        logger.info(f"E2EPipeline initialized: local_only={local_only}, managed_identity={use_managed_identity}")
    
    @property
    def db_client(self):
        """Lazy-load database client."""
        if self._db_client is None and not self.local_only:
            from db_client import get_db_client
            self._db_client = get_db_client(use_managed_identity=self.use_managed_identity)
        return self._db_client
    
    @property
    def blob_client(self):
        """Lazy-load blob client."""
        if self._blob_client is None and not self.local_only:
            from blob_client import get_blob_client
            self._blob_client = get_blob_client(use_managed_identity=self.use_managed_identity)
        return self._blob_client
    
    def run(
        self,
        pdf_path: Path,
        class_level: str = "11",
        board: str = "CBSE",
        subject: str = "Physics",
        chapter_name: Optional[str] = None,
        output_dir: Optional[Path] = None,
        force_rerun: bool = False,
        skip_solutions: bool = False,
        batch_size: int = 5,
    ) -> PipelineState:
        """
        Run the complete E2E pipeline.
        
        Args:
            pdf_path: Path to chapter PDF
            class_level: Class level (e.g., "11", "12")
            board: Education board (e.g., "CBSE")
            subject: Subject name (e.g., "Physics", "Maths")
            chapter_name: Optional chapter name
            output_dir: Output directory for JSON files
            force_rerun: Re-process even if data exists
            skip_solutions: Skip Stage 2 (solution generation)
            batch_size: Questions per batch for Stage 2
            
        Returns:
            PipelineState with results and IDs
        """
        output_dir = output_dir or self.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize or load state
        state_path = output_dir / f"{pdf_path.stem}_pipeline_state.json"
        
        if state_path.exists() and not force_rerun:
            state = PipelineState.load(state_path)
            logger.info(f"Resuming from existing state: {state_path}")
        else:
            state = PipelineState(
                pdf_path=str(pdf_path)
            )
        
        try:
            # ===== STAGE 1: Extraction =====
            if not state.stage1_complete or force_rerun:
                logger.info("=" * 60)
                logger.info("STAGE 1: Question Extraction")
                logger.info("=" * 60)
                
                extraction_result = self._run_stage1(
                    pdf_path=pdf_path,
                    class_level=class_level,
                    board=board,
                    subject=subject,
                    chapter_name=chapter_name,
                    output_dir=output_dir
                )
                
                state.chapter_number = extraction_result.chapter_number
                state.extraction_json_path = str(output_dir / f"{pdf_path.stem}_extraction.json")
                state.stage1_complete = True
                state.save(state_path)
                
                logger.info(f"Stage 1 complete: {len(extraction_result.questions)} questions extracted")
            else:
                # Load existing extraction
                logger.info("Stage 1 already complete, loading existing extraction")
                extraction_path = Path(state.extraction_json_path)
                if extraction_path.exists():
                    with open(extraction_path, 'r', encoding='utf-8') as f:
                        extraction_data = json.load(f)
                    # Reconstruct ExtractionResponse from saved JSON
                    extraction_result = _reconstruct_extraction_response(extraction_data, pdf_path)
                    logger.info(f"Loaded {len(extraction_result.questions)} questions from {extraction_path.name}")
                else:
                    raise FileNotFoundError(f"Extraction file not found: {extraction_path}")
            
            # ===== UPLOAD & INGEST =====
            if not self.local_only and (not state.db_ingestion_complete or force_rerun):
                logger.info("=" * 60)
                logger.info("INGESTION: Upload figures & Ingest to Database")
                logger.info("=" * 60)
                
                if extraction_result:
                    self._run_ingestion(
                        extraction_result=extraction_result,
                        class_level=class_level,
                        subject=subject,
                        state=state,
                        output_dir=output_dir
                    )
                    
                    state.db_ingestion_complete = True
                    state.save(state_path)
                else:
                    logger.warning("Skipping ingestion - no extraction result available")
            
            # ===== STAGE 2: Solution Generation =====
            if not skip_solutions and (not state.stage2_complete or force_rerun):
                logger.info("=" * 60)
                logger.info("STAGE 2: Solution Generation")
                logger.info("=" * 60)
                
                # Get all questions to solve
                if extraction_result:
                    all_questions = [q.question_id for q in extraction_result.questions]
                elif state.extraction_json_path:
                    with open(state.extraction_json_path, 'r', encoding='utf-8') as f:
                        extraction_data = json.load(f)
                    all_questions = [q['question_id'] for q in extraction_data.get('questions', [])]
                else:
                    all_questions = []
                
                # Filter out already-solved questions (for resume)
                already_solved = set(state.solved_questions or [])
                questions_to_solve = [q for q in all_questions if q not in already_solved]
                
                if already_solved:
                    logger.info(f"Resuming Stage 2: {len(already_solved)} questions already solved, {len(questions_to_solve)} remaining")
                
                if questions_to_solve:
                    solver_result = self._run_stage2_incremental(
                        pdf_path=pdf_path,
                        questions=questions_to_solve,
                        class_level=class_level,
                        board=board,
                        subject=subject,
                        chapter_name=chapter_name,
                        chapter_number=state.chapter_number,
                        output_dir=output_dir,
                        batch_size=batch_size,
                        state=state,
                        state_path=state_path
                    )
                    
                    state.solutions_json_path = str(output_dir / f"{pdf_path.stem}_solutions.json")
                    state.stage2_complete = True
                    state.save(state_path)
                    
                    # Update solutions in database
                    if not self.local_only:
                        self._update_solutions_in_db(solver_result, state)
                    
                    logger.info(f"Stage 2 complete: {len(solver_result.solutions)} solutions generated")
                elif already_solved:
                    # All questions already solved (interrupted after batches completed but before final save)
                    logger.info("All questions already solved, loading solutions for DB ingestion")
                    state.solutions_json_path = str(output_dir / f"{pdf_path.stem}_solutions.json")
                    state.stage2_complete = True
                    state.save(state_path)
                    
                    # Load solutions from JSON and update DB (may have been skipped on previous run)
                    if not self.local_only:
                        solutions_path = output_dir / f"{pdf_path.stem}_solutions.json"
                        if solutions_path.exists():
                            with open(solutions_path, 'r', encoding='utf-8') as f:
                                solutions_data = json.load(f)
                            # Update DB directly from JSON data
                            self._update_solutions_from_json(solutions_data, state)
                            logger.info(f"DB ingestion complete for solutions")
                else:
                    logger.warning("No questions to solve")
            
            # ===== PUSH SOLUTIONS TO DB (if skipped earlier) =====
            # This handles the case where stage2 completed but solutions weren't written to DB
            if not self.local_only and state.stage2_complete and state.question_ids:
                solutions_path = output_dir / f"{pdf_path.stem}_solutions.json"
                if solutions_path.exists():
                    # Check if any solutions are missing in DB by looking at solved_questions
                    if state.solved_questions:
                        logger.info("Ensuring solutions are in database...")
                        with open(solutions_path, 'r', encoding='utf-8') as f:
                            solutions_data = json.load(f)
                        self._update_solutions_from_json(solutions_data, state)
                        logger.info(f"Solutions sync complete")
            
            # ===== COMPLETE =====
            state.completed_at = datetime.now().isoformat()
            state.save(state_path)
            
            logger.info("=" * 60)
            logger.info("PIPELINE COMPLETE")
            logger.info(f"  Chapter: {state.chapter_number}")
            logger.info(f"  Extraction: {state.extraction_json_path}")
            logger.info(f"  Solutions: {state.solutions_json_path}")
            if not self.local_only:
                logger.info(f"  Database: ChapterId={state.chapter_id}, Exercises={len(state.exercise_ids)}")
            logger.info("=" * 60)
            
            return state
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            state.save(state_path)
            raise
    
    def _run_stage1(
        self,
        pdf_path: Path,
        class_level: str,
        board: str,
        subject: str,
        chapter_name: Optional[str],
        output_dir: Path
    ) -> ExtractionResponse:
        """Run Stage 1 extraction."""
        # Create extraction request
        request = ExtractionRequest(
            pdf_path=pdf_path,
            class_level=class_level,
            board=board,
            subject=subject,
            chapter_name=chapter_name
        )
        
        # Load prompt templates
        prompts_dir = Path(__file__).parent / "prompts"
        
        # Run two-pass extraction
        response = self.extraction_engine.extract_two_pass(
            request=request,
            pass1_prompt_path=prompts_dir / "pass1_text_extraction.md",
            pass2_prompt_path=prompts_dir / "pass2_box_extraction.md"
        )
        
        # Save extraction result
        output_path = output_dir / f"{pdf_path.stem}_extraction.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(response.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Extraction saved to: {output_path}")
        return response
    
    def _run_ingestion(
        self,
        extraction_result: ExtractionResponse,
        class_level: str,
        subject: str,
        state: PipelineState,
        output_dir: Path
    ):
        """Upload figures and ingest to database."""
        if not class_level or not subject:
            raise ValueError("class_level and subject required for database ingestion")
        
        # Get chapter ID
        chapter_number = extraction_result.chapter_number
        if not chapter_number:
            raise ValueError("chapter_number not found in extraction result")
        
        chapter_id = self.db_client.get_chapter_id(class_level, subject, chapter_number)
        if not chapter_id:
            raise ValueError(f"Chapter not found: class={class_level}, subject={subject}, chapter_number={chapter_number}")
        
        state.chapter_id = chapter_id
        logger.info(f"Found ChapterId={chapter_id} for Chapter {chapter_number}")
        
        # Process each exercise
        for exercise in extraction_result.exercise_sections:
            logger.info(f"Processing exercise: {exercise.title}")
            
            # Build exercise data for OtherData JSONB
            exercise_data = {
                "title": exercise.title,
                "start_page": exercise.start_page,
                "end_page": exercise.end_page,
                "question_ids": [q.question_id for q in exercise.questions]
            }
            
            # Use model's total_questions (fallback to len if None)
            total_questions = exercise.total_questions or len(exercise.questions)
            
            # Upsert exercise
            exercise_id = self.db_client.upsert_exercise(
                chapter_id=chapter_id,
                exercise_title=exercise.title,
                total_questions=total_questions,
                other_data=exercise_data
            )
            state.exercise_ids[exercise.title] = exercise_id
            
            # Process questions in this exercise
            for question in exercise.questions:
                # Upload figure if needed and build figure_info
                figure_info = []
                if question.visual_required and question.visual_data.cropped_image_path:
                    # cropped_image_path is relative to output_dir (e.g., "cropped_images/keph204/q11_8_fig.png")
                    local_path = output_dir / question.visual_data.cropped_image_path
                    if local_path.exists():
                        from blob_client import generate_blob_path
                        blob_path = generate_blob_path(
                            class_level=class_level,
                            subject=subject,
                            chapter_number=chapter_number,
                            question_ref=question.question_id
                        )
                        figure_url = self.blob_client.upload_image(local_path, blob_path)
                        figure_info.append({
                            "url": figure_url,
                            "description": question.visual_data.description,
                            "type": question.visual_data.type,
                            "local_path": str(local_path)
                        })
                    else:
                        logger.warning(f"Figure not found for {question.question_id}: {local_path}")
                
                # Build Content JSONB from ExtractedQuestion
                content = {
                    "question_text": question.question_text,
                    "page_number": question.page_number,
                    "has_figure": question.visual_required,
                    "figure_info": figure_info if figure_info else None,
                    "figure_references": question.figure_references if question.figure_references else None,
                    "visual_data": question.visual_data.to_dict() if question.visual_required else None,
                }
                # Remove None values
                content = {k: v for k, v in content.items() if v is not None}
                
                # Add sub_questions if present
                if question.sub_questions:
                    content["sub_questions"] = [
                        {"sub_id": sq.sub_id, "text": sq.text}
                        for sq in question.sub_questions
                    ]
                
                # Upsert question with Content JSONB
                question_id = self.db_client.upsert_question(
                    exercise_id=exercise_id,
                    question_ref=question.question_id,
                    content=content
                )
                state.question_ids[question.question_id] = question_id
        
        logger.info(f"Ingested {len(state.exercise_ids)} exercises, {len(state.question_ids)} questions")
    
    def _run_stage2(
        self,
        pdf_path: Path,
        questions: List[str],
        class_level: str,
        board: str,
        subject: str,
        chapter_name: Optional[str],
        chapter_number: Optional[str],
        output_dir: Path,
        batch_size: int
    ) -> SolverResponse:
        """Run Stage 2 solution generation."""
        # Load prompt template
        prompt_path = Path(__file__).parent / "tutor_prompt.md"
        prompt_template = self.solver_engine.load_prompt_template(prompt_path)
        filled_prompt = self.solver_engine.fill_prompt(
            prompt_template,
            class_level=class_level,
            board=board,
            subject=subject
        )
        
        # Create request
        request = SolverRequest(
            pdf_path=pdf_path,
            questions=questions,
            class_level=class_level,
            board=board,
            subject=subject,
            chapter_name=chapter_name,
            chapter_number=chapter_number
        )
        
        # Generate solutions (with batching)
        if batch_size > 0 and len(questions) > batch_size:
            from main import run_stage2_solver
            response = run_stage2_solver(
                pdf_path=pdf_path,
                questions=questions,
                class_level=class_level,
                board=board,
                subject=subject,
                chapter_name=chapter_name,
                prompt_template_path=prompt_path,
                output_dir=output_dir,
                batch_size=batch_size
            )
        else:
            response = self.solver_engine.solve(
                request=request,
                system_prompt=filled_prompt
            )
        
        # Save solutions
        output_path = output_dir / f"{pdf_path.stem}_solutions.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(response.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Solutions saved to: {output_path}")
        return response
    
    def _run_stage2_incremental(
        self,
        pdf_path: Path,
        questions: List[str],
        class_level: str,
        board: str,
        subject: str,
        chapter_name: Optional[str],
        chapter_number: Optional[str],
        output_dir: Path,
        batch_size: int,
        state: PipelineState,
        state_path: Path
    ) -> SolverResponse:
        """
        Run Stage 2 with incremental checkpointing.
        
        Saves solutions after each batch and updates state, allowing resume
        if the process is interrupted.
        """
        from solver_engine import SolverRequest, SolverResponse
        
        # Load prompt template
        prompt_path = Path(__file__).parent / "tutor_prompt.md"
        prompt_template = self.solver_engine.load_prompt_template(prompt_path)
        filled_prompt = self.solver_engine.fill_prompt(
            prompt_template,
            class_level=class_level,
            board=board,
            subject=subject
        )
        
        # Output path for solutions
        output_path = output_dir / f"{pdf_path.stem}_solutions.json"
        
        # Load existing solutions if any (for merging) - keep as dicts for JSON compatibility
        existing_solutions_dicts = []
        existing_raw_response = ""
        if output_path.exists():
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                existing_solutions_dicts = existing_data.get('solutions', [])
                existing_raw_response = existing_data.get('raw_response', '')
                logger.info(f"Loaded {len(existing_solutions_dicts)} existing solutions for merging")
            except Exception as e:
                logger.warning(f"Could not load existing solutions: {e}")
        
        # Split into batches
        if batch_size > 0 and len(questions) > batch_size:
            batches = [questions[i:i + batch_size] for i in range(0, len(questions), batch_size)]
        else:
            batches = [questions]  # Single batch
        
        logger.info(f"Processing {len(questions)} questions in {len(batches)} batch(es)")
        
        # Track new solutions as Solution objects (for DB update)
        new_solutions = []
        all_raw_responses = [existing_raw_response] if existing_raw_response else []
        total_time = 0.0
        model_used = None
        
        for batch_idx, batch_questions in enumerate(batches):
            batch_num = batch_idx + 1
            logger.info(f"\n{'='*40}")
            logger.info(f"Processing Batch {batch_num}/{len(batches)}: {batch_questions}")
            logger.info(f"{'='*40}")
            
            try:
                # Create request for this batch
                batch_request = SolverRequest(
                    pdf_path=pdf_path,
                    questions=batch_questions,
                    class_level=class_level,
                    board=board,
                    subject=subject,
                    chapter_name=chapter_name,
                    chapter_number=chapter_number
                )
                
                batch_response = self.solver_engine.solve(batch_request, filled_prompt, use_cache=True)
                
                # Collect results
                new_solutions.extend(batch_response.solutions)
                all_raw_responses.append(f"\n\n# === BATCH {batch_num} ({', '.join(batch_questions)}) ===\n\n{batch_response.raw_response}")
                total_time += batch_response.processing_time_seconds
                model_used = batch_response.model_used
                
                # Update solved questions in state
                for sol in batch_response.solutions:
                    if sol.question_id not in state.solved_questions:
                        state.solved_questions.append(sol.question_id)
                
                # Save solutions incrementally - merge existing dicts with new solution dicts
                all_solutions_dicts = existing_solutions_dicts + [s.to_dict() for s in new_solutions]
                save_data = {
                    "metadata": {
                        "pdf_file": str(pdf_path.name),
                        "chapter_number": chapter_number,
                        "questions_requested": list(set(state.solved_questions)),
                        "class": class_level,
                        "board": board,
                        "subject": subject,
                        "chapter": chapter_name,
                        "model": model_used,
                        "processing_time_seconds": total_time,
                        "timestamp": datetime.now().isoformat(),
                    },
                    "solutions": all_solutions_dicts,
                    "raw_response": "".join(all_raw_responses),
                }
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, indent=2, ensure_ascii=False)
                
                # Save state checkpoint
                state.save(state_path)
                
                logger.info(f"✓ Batch {batch_num} complete: {len(batch_response.solutions)} solutions")
                logger.info(f"  Checkpoint saved: {len(all_solutions_dicts)} total solutions, {len(state.solved_questions)} questions solved")
                
            except Exception as e:
                logger.error(f"Batch {batch_num} failed: {e}")
                logger.info(f"Progress saved: {len(existing_solutions_dicts) + len(new_solutions)} solutions from previous batches")
                logger.info(f"Resume by re-running the same command")
                raise
        
        # Build final merged response (for DB update, needs Solution objects)
        # Combine existing solutions (can be skipped for DB since they were already updated)
        # and new solutions
        final_request = SolverRequest(
            pdf_path=pdf_path,
            questions=questions,
            class_level=class_level,
            board=board,
            subject=subject,
            chapter_name=chapter_name,
            chapter_number=chapter_number
        )
        
        final_response = SolverResponse(
            request=final_request,
            solutions=new_solutions,  # Only new solutions for DB update
            raw_response="".join(all_raw_responses),
            processing_time_seconds=total_time,
            model_used=model_used or "unknown"
        )
        
        # Final save already done in last batch iteration
        
        logger.info(f"\n{'='*40}")
        logger.info(f"All batches complete: {len(existing_solutions_dicts) + len(new_solutions)} total solutions in {total_time:.2f}s")
        logger.info(f"Solutions saved to: {output_path}")
        
        return final_response
    
    def _extract_parent_question_id(self, question_id: str) -> tuple[str, str | None]:
        """
        Extract parent question ID and sub-part from a question reference.
        
        Examples:
            "8.6" -> ("8.6", None)
            "8.6.a" -> ("8.6", "a")
            "8.6.b" -> ("8.6", "b")
            "8.8.i" -> ("8.8", "i")
            "8.8.ii" -> ("8.8", "ii")
            "10.2.a" -> ("10.2", "a")
        """
        import re
        # Pattern: number.number followed by optional .subpart (letter or roman numeral)
        match = re.match(r'^(\d+\.\d+)\.([a-z]+|[ivxlc]+)$', question_id, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2).lower()
        return question_id, None
    
    def _update_solutions_in_db(self, solver_result: SolverResponse, state: PipelineState):
        """Update database with generated solutions, consolidating sub-parts."""
        from collections import defaultdict
        
        # Group solutions by parent question ID
        parent_solutions = defaultdict(list)
        
        for solution in solver_result.solutions:
            parent_id, sub_part = self._extract_parent_question_id(solution.question_id)
            parent_solutions[parent_id].append((sub_part, solution))
        
        updated_count = 0
        
        for parent_id, parts in parent_solutions.items():
            question_id = state.question_ids.get(parent_id)
            
            if not question_id:
                logger.warning(f"Question not found in state: {parent_id}")
                continue
            
            # Check if this is a multi-part question or single question
            has_sub_parts = any(sub_part is not None for sub_part, _ in parts)
            
            if has_sub_parts:
                # Multi-part question: consolidate into sub_parts structure
                sub_parts_dict = {}
                all_steps = []
                combined_question_text = ""
                combined_final_answer = []
                
                # Sort parts by sub-part identifier
                sorted_parts = sorted(parts, key=lambda x: (x[0] or "", x[1].question_id))
                
                for sub_part, solution in sorted_parts:
                    part_key = sub_part or "main"
                    sub_parts_dict[part_key] = {
                        "question_text": solution.question_text,
                        "steps": [
                            {
                                "step_number": step.step_number,
                                "step_type": step.step_type,
                                "nudge_hint": step.nudge_hint,
                                "explanation": step.explanation,
                                "latex_formula": step.latex_formula
                            }
                            for step in solution.steps
                        ],
                        "final_answer": solution.final_answer
                    }
                    # Combine final answers with part labels
                    if sub_part:
                        combined_final_answer.append(f"({sub_part}) {solution.final_answer}")
                    else:
                        combined_final_answer.append(solution.final_answer)
                    
                    if not combined_question_text:
                        combined_question_text = solution.question_text
                
                solution_dict = {
                    "question_id": parent_id,
                    "question_text": combined_question_text,
                    "has_sub_parts": True,
                    "sub_parts": sub_parts_dict,
                    "final_answer": "\n".join(combined_final_answer),
                    "rendered_text": self._render_multipart_solution(parent_id, sub_parts_dict)
                }
            else:
                # Single question (no sub-parts)
                _, solution = parts[0]
                solution_dict = {
                    "question_id": solution.question_id,
                    "question_text": solution.question_text,
                    "has_sub_parts": False,
                    "steps": [
                        {
                            "step_number": step.step_number,
                            "step_type": step.step_type,
                            "nudge_hint": step.nudge_hint,
                            "explanation": step.explanation,
                            "latex_formula": step.latex_formula
                        }
                        for step in solution.steps
                    ],
                    "final_answer": solution.final_answer,
                    "rendered_text": self._render_solution_text(solution)
                }
            
            self.db_client.update_question_solution(
                question_id=question_id,
                solution=solution_dict
            )
            updated_count += 1
        
        logger.info(f"Updated {updated_count} solutions in database (from {len(solver_result.solutions)} individual solutions)")
    
    def _render_multipart_solution(self, parent_id: str, sub_parts: dict) -> str:
        """Render a multi-part solution to markdown text."""
        lines = []
        lines.append(f"## Question {parent_id}")
        
        for part_key in sorted(sub_parts.keys()):
            part = sub_parts[part_key]
            lines.append(f"\n### Part ({part_key})")
            lines.append(f"\n{part.get('question_text', '')}\n")
            
            for step in part.get('steps', []):
                lines.append(f"\n#### Step {step['step_number']} ({step['step_type']})")
                lines.append(f"**Hint:** {step['nudge_hint']}")
                lines.append(f"\n{step['explanation']}")
                if step.get('latex_formula'):
                    lines.append(f"\n**Formula:** {step['latex_formula']}")
            
            lines.append(f"\n**Answer ({part_key}):** {part.get('final_answer', '')}")
        
        return "\n".join(lines)
    
    def _render_solution_text(self, solution) -> str:
        """Render a Solution object to markdown text."""
        lines = []
        lines.append(f"## Question {solution.question_id}")
        lines.append(f"\n{solution.question_text}\n")
        
        for step in solution.steps:
            lines.append(f"\n### Step {step.step_number} ({step.step_type})")
            lines.append(f"**Hint:** {step.nudge_hint}")
            lines.append(f"\n{step.explanation}")
            if step.latex_formula:
                lines.append(f"\n**Formula:** {step.latex_formula}")
        
        lines.append(f"\n### Final Answer")
        lines.append(solution.final_answer)
        
        return "\n".join(lines)
    
    def _update_solutions_from_json(self, solutions_data: dict, state: PipelineState):
        """
        Update database with solutions loaded directly from JSON file.
        Handles sub-part consolidation like _update_solutions_in_db.
        """
        from collections import defaultdict
        
        solutions = solutions_data.get("solutions", [])
        
        # Group solutions by parent question ID
        parent_solutions = defaultdict(list)
        
        for solution in solutions:
            question_id = solution.get("question_id", "unknown")
            parent_id, sub_part = self._extract_parent_question_id(question_id)
            parent_solutions[parent_id].append((sub_part, solution))
        
        updated_count = 0
        
        for parent_id, parts in parent_solutions.items():
            question_id = state.question_ids.get(parent_id)
            
            if not question_id:
                logger.warning(f"Question not found in state: {parent_id}")
                continue
            
            # Check if this is a multi-part question or single question
            has_sub_parts = any(sub_part is not None for sub_part, _ in parts)
            
            if has_sub_parts:
                # Multi-part question: consolidate into sub_parts structure
                sub_parts_dict = {}
                combined_final_answer = []
                combined_question_text = ""
                
                sorted_parts = sorted(parts, key=lambda x: (x[0] or "", x[1].get("question_id", "")))
                
                for sub_part, solution in sorted_parts:
                    part_key = sub_part or "main"
                    sub_parts_dict[part_key] = {
                        "question_text": solution.get("question_text", ""),
                        "steps": solution.get("steps", []),
                        "final_answer": solution.get("final_answer", "")
                    }
                    if sub_part:
                        combined_final_answer.append(f"({sub_part}) {solution.get('final_answer', '')}")
                    else:
                        combined_final_answer.append(solution.get("final_answer", ""))
                    
                    if not combined_question_text:
                        combined_question_text = solution.get("question_text", "")
                
                solution_dict = {
                    "question_id": parent_id,
                    "question_text": combined_question_text,
                    "has_sub_parts": True,
                    "sub_parts": sub_parts_dict,
                    "final_answer": "\n".join(combined_final_answer),
                    "rendered_text": self._render_multipart_solution(parent_id, sub_parts_dict)
                }
            else:
                # Single question (no sub-parts)
                _, solution = parts[0]
                solution_dict = {
                    "question_id": solution.get("question_id", ""),
                    "question_text": solution.get("question_text", ""),
                    "has_sub_parts": False,
                    "steps": solution.get("steps", []),
                    "final_answer": solution.get("final_answer", ""),
                    "rendered_text": self._render_solution_dict(solution)
                }
            
            self.db_client.update_question_solution(
                question_id=question_id,
                solution=solution_dict
            )
            updated_count += 1
        
        logger.info(f"Updated {updated_count} solutions in database from JSON")
    
    def _render_solution_dict(self, solution: dict) -> str:
        """Render a solution dictionary to markdown text."""
        lines = []
        lines.append(f"## Question {solution.get('question_id', '')}")
        lines.append(f"\n{solution.get('question_text', '')}\n")
        
        for step in solution.get('steps', []):
            step_num = step.get('step_number', 0)
            step_type = step.get('step_type', '')
            lines.append(f"\n### Step {step_num} ({step_type})")
            lines.append(f"**Hint:** {step.get('nudge_hint', '')}")
            lines.append(f"\n{step.get('explanation', '')}")
            if step.get('latex_formula'):
                lines.append(f"\n**Formula:** {step['latex_formula']}")
        
        lines.append(f"\n### Final Answer")
        lines.append(solution.get('final_answer', ''))
        
        return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run E2E pipeline: Extract questions and generate solutions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline with database ingestion
  python e2e_pipeline.py --pdf chapter.pdf --book-id 1 --subject Physics
  
  # Local only (no database, no blob upload)
  python e2e_pipeline.py --pdf chapter.pdf --local-only
  
  # Force rerun (re-process everything)
  python e2e_pipeline.py --pdf chapter.pdf --book-id 1 --force-rerun
  
  # Skip solution generation
  python e2e_pipeline.py --pdf chapter.pdf --book-id 1 --skip-solutions
        """
    )
    
    # Required arguments
    parser.add_argument("--pdf", type=Path, required=True, help="Path to chapter PDF")
    
    # Database/Azure arguments
    parser.add_argument("--local-only", action="store_true", help="Skip database and blob operations")
    parser.add_argument("--no-managed-identity", action="store_true", help="Don't use Azure Managed Identity")
    
    # Metadata arguments
    parser.add_argument("--class", dest="class_level", default="11", help="Class level (default: 11)")
    parser.add_argument("--board", default="CBSE", help="Education board (default: CBSE)")
    parser.add_argument("--subject", default="Physics", help="Subject (default: Physics)")
    parser.add_argument("--chapter-name", help="Chapter name for metadata")
    
    # Pipeline control
    parser.add_argument("--force-rerun", action="store_true", help="Re-process even if data exists")
    parser.add_argument("--skip-solutions", action="store_true", help="Skip Stage 2 (solution generation)")
    parser.add_argument("--batch-size", type=int, default=5, help="Questions per batch for Stage 2")
    parser.add_argument("--output-dir", type=Path, help="Output directory")
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.pdf.exists():
        parser.error(f"PDF file not found: {args.pdf}")
    
    # Set output directory
    output_dir = args.output_dir or Path(__file__).parent / "Output"
    
    # Run pipeline
    pipeline = E2EPipeline(
        use_managed_identity=not args.no_managed_identity,
        local_only=args.local_only
    )
    
    state = pipeline.run(
        pdf_path=args.pdf,
        class_level=args.class_level,
        board=args.board,
        subject=args.subject,
        chapter_name=args.chapter_name,
        output_dir=output_dir,
        force_rerun=args.force_rerun,
        skip_solutions=args.skip_solutions,
        batch_size=args.batch_size
    )
    
    print(f"\nPipeline complete!")
    print(f"  Extraction: {state.extraction_json_path}")
    print(f"  Solutions: {state.solutions_json_path}")


if __name__ == "__main__":
    main()
