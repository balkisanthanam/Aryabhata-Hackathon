"""
Main Entry Point for the Multi-Step Pipeline.

Supports:
1. Stage 1: Question Extraction from PDF pages
2. Stage 2: Solution Generation (Solver Engine)
3. Stage 3: End-to-End Pipeline (Extract → Ingest → Solve → Ingest)

Usage:
    # Stage 1 - Extract questions from PDF
    python main.py --stage 1 --pdf "Input/keph203.pdf"
    python main.py --stage 1 --pdf "Input/keph203.pdf" --pages "20-25"
    
    # Stage 2 - Generate solutions (existing)
    python main.py --stage 2 --pdf "Input/keph205.pdf" --questions "12.4,12.7"
    python main.py --questions "12.4"  # defaults to stage 2
    
    # Stage 3 - End-to-End Pipeline
    python main.py --stage 3 --pdf "Input/keph205.pdf" --class 11 --subject Physics
    python main.py --stage 3 --pdf "Input/keph205.pdf" --local-only
    
    # As a module
    from main import run_stage1_extraction, run_stage2_solver
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple
import logging

from config import PipelineConfig
from solver_engine import SolverEngine, SolverRequest, SolverResponse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_stage2_solver(
    pdf_path: Path,
    questions: List[str],
    class_level: str = "11th",
    board: str = "CBSE",
    subject: str = "Physics",
    chapter_name: Optional[str] = None,
    prompt_template_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    use_cache: bool = True,
    config: Optional[PipelineConfig] = None,
    batch_size: int = 5,
) -> SolverResponse:
    """
    Run Stage 2 Solver Engine to generate step-by-step solutions.
    
    This is the main entry point for programmatic use.
    
    Args:
        pdf_path: Path to the chapter PDF
        questions: List of question IDs to solve (e.g., ["12.4", "12.7"])
        class_level: Class/grade level (default: "11th")
        board: Education board (default: "CBSE")
        subject: Subject name (default: "Physics")
        chapter_name: Optional chapter name for metadata
        prompt_template_path: Path to prompt template (default: tutor_prompt.md)
        output_dir: Where to save results
        use_cache: Whether to use Gemini content caching
        config: Optional custom PipelineConfig
        batch_size: Number of questions per batch (default: 5). Set to 0 for no batching.
        
    Returns:
        SolverResponse with generated solutions (merged if batched)
        
    Example:
        response = run_stage2_solver(
            pdf_path=Path("Input/keph205.pdf"),
            questions=["12.4", "12.7"],
            subject="Physics",
        )
        print(f"Generated {len(response.solutions)} solutions")
    """
    # Initialize config
    config = config or PipelineConfig.from_env()
    
    # Set output directory if provided
    if output_dir:
        config.output_dir = output_dir
    
    # Initialize engine
    engine = SolverEngine(config)
    
    # Load and fill prompt template
    template_path = prompt_template_path or Path(__file__).parent / "tutor_prompt.md"
    
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    
    prompt_template = engine.load_prompt_template(template_path)
    filled_prompt = engine.fill_prompt(
        prompt_template,
        class_level=class_level,
        board=board,
        subject=subject,
    )
    
    # Create request
    request = SolverRequest(
        pdf_path=pdf_path,
        questions=questions,
        class_level=class_level,
        board=board,
        subject=subject,
        chapter_name=chapter_name,
    )
    
    # Generate solutions
    logger.info(f"Starting Stage 2 Solver for {len(questions)} questions")
    logger.info(f"PDF: {pdf_path.name}")
    logger.info(f"Subject: {subject}, Class: {class_level}, Board: {board}")
    
    try:
        # Determine if batching is needed
        if batch_size > 0 and len(questions) > batch_size:
            # Split questions into batches
            batches = [questions[i:i + batch_size] for i in range(0, len(questions), batch_size)]
            logger.info(f"Batching {len(questions)} questions into {len(batches)} batches (size={batch_size})")
            
            all_solutions = []
            all_raw_responses = []
            total_time = 0.0
            
            for batch_idx, batch_questions in enumerate(batches):
                batch_num = batch_idx + 1
                logger.info(f"\n{'='*40}")
                logger.info(f"Processing Batch {batch_num}/{len(batches)}: {batch_questions}")
                logger.info(f"{'='*40}")
                
                # Create request for this batch
                batch_request = SolverRequest(
                    pdf_path=pdf_path,
                    questions=batch_questions,
                    class_level=class_level,
                    board=board,
                    subject=subject,
                    chapter_name=chapter_name,
                )
                
                batch_response = engine.solve(batch_request, filled_prompt, use_cache=use_cache)
                
                all_solutions.extend(batch_response.solutions)
                all_raw_responses.append(f"\n\n# === BATCH {batch_num} ({', '.join(batch_questions)}) ===\n\n{batch_response.raw_response}")
                total_time += batch_response.processing_time_seconds
                
                logger.info(f"✓ Batch {batch_num} completed: {len(batch_response.solutions)} solutions in {batch_response.processing_time_seconds:.2f}s")
            
            # Create merged response
            merged_request = SolverRequest(
                pdf_path=pdf_path,
                questions=questions,  # All questions
                class_level=class_level,
                board=board,
                subject=subject,
                chapter_name=chapter_name,
            )
            
            response = SolverResponse(
                request=merged_request,
                solutions=all_solutions,
                raw_response="".join(all_raw_responses),
                processing_time_seconds=total_time,
                model_used=batch_response.model_used,
            )
            
            logger.info(f"\n{'='*40}")
            logger.info(f"All batches complete: {len(all_solutions)} total solutions in {total_time:.2f}s")
        else:
            # Single request (no batching needed)
            response = engine.solve(request, filled_prompt, use_cache=use_cache)
        
        # Save results
        output_path = engine.save_response(response)
        
        logger.info(f"✓ Completed in {response.processing_time_seconds:.2f}s")
        logger.info(f"✓ Generated {len(response.solutions)} solutions")
        logger.info(f"✓ Saved to: {output_path}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error during solution generation: {e}")
        raise
    finally:
        # Cleanup
        engine.cleanup()


# =============================================================================
# Stage 1: Question Extraction
# =============================================================================

def run_stage1_extraction(
    pdf_path: Path,
    class_level: str = "11th",
    board: str = "CBSE",
    subject: str = "Physics",
    chapter_name: Optional[str] = None,
    page_range: Optional[Tuple[int, int]] = None,
    prompt_template_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    config: Optional[PipelineConfig] = None,
):
    """
    Run Stage 1 Extraction Engine to extract questions from PDF.
    
    Args:
        pdf_path: Path to the chapter PDF
        class_level: Class/grade level (default: "11th")
        board: Education board (default: "CBSE")
        subject: Subject name (default: "Physics")
        chapter_name: Optional chapter name for metadata
        page_range: Optional (start, end) page range (1-indexed), None for auto-detect
        prompt_template_path: Path to prompt template (default: extraction_prompt.md)
        output_dir: Where to save results
        config: Optional custom PipelineConfig
        
    Returns:
        ExtractionResponse with extracted questions
    """
    # Import here to avoid circular imports
    from extraction_engine import ExtractionEngine, ExtractionRequest
    
    # Initialize config
    config = config or PipelineConfig.from_env()
    
    # Set output directory if provided
    if output_dir:
        config.output_dir = output_dir
    
    # Initialize engine
    engine = ExtractionEngine(config)
    
    # Load prompt template
    template_path = prompt_template_path or Path(__file__).parent / "extraction_prompt.md"
    
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    
    prompt_template = engine.load_prompt_template(template_path)
    
    # Fill template placeholders
    prompt_template = prompt_template.replace("{{CLASS}}", class_level)
    prompt_template = prompt_template.replace("{{BOARD}}", board)
    prompt_template = prompt_template.replace("{{SUBJECT}}", subject)
    
    # Convert page range from 1-indexed to 0-indexed
    page_range_0idx = None
    if page_range:
        page_range_0idx = (page_range[0] - 1, page_range[1] - 1)
    
    # Create request
    request = ExtractionRequest(
        pdf_path=pdf_path,
        page_range=page_range_0idx,
        class_level=class_level,
        board=board,
        subject=subject,
        chapter_name=chapter_name,
    )
    
    # Extract questions
    logger.info(f"Starting Stage 1 Extraction from {pdf_path.name}")
    logger.info(f"Subject: {subject}, Class: {class_level}, Board: {board}")
    if page_range:
        logger.info(f"Page range: {page_range[0]} to {page_range[1]}")
    else:
        logger.info("Page range: Auto-detect exercise sections")
    
    try:
        response = engine.extract_from_pdf(request, prompt_template)
        
        # Save results
        output_path = engine.save_questions(response)
        
        logger.info(f"✓ Completed in {response.processing_time_seconds:.2f}s")
        logger.info(f"✓ Extracted {len(response.questions)} questions")
        logger.info(f"✓ Saved to: {output_path}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error during extraction: {e}")
        raise
    finally:
        engine.cleanup()


def run_stage1_extraction_two_pass(
    pdf_path: Path,
    class_level: str = "11th",
    board: str = "CBSE",
    subject: str = "Physics",
    chapter_name: Optional[str] = None,
    page_range: Optional[Tuple[int, int]] = None,
    output_dir: Optional[Path] = None,
    config: Optional[PipelineConfig] = None,
):
    """
    Run Stage 1 Extraction using Two-Pass approach.
    
    Pass 1: PDF upload → Extract text + LaTeX + flag figures
    Pass 2: Page images → Extract bounding boxes for flagged figures
    
    This approach is more reliable for complex content like Chemistry.
    
    Args:
        pdf_path: Path to the chapter PDF
        class_level: Class/grade level (default: "11th")
        board: Education board (default: "CBSE")
        subject: Subject name (default: "Physics")
        chapter_name: Optional chapter name for metadata
        page_range: Optional (start, end) page range (1-indexed), None for auto-detect
        output_dir: Where to save results
        config: Optional custom PipelineConfig
        
    Returns:
        ExtractionResponse with extracted questions
    """
    # Import here to avoid circular imports
    from extraction_engine import ExtractionEngine, ExtractionRequest
    
    # Initialize config
    config = config or PipelineConfig.from_env()
    
    # Set output directory if provided
    if output_dir:
        config.output_dir = output_dir
    
    # Initialize engine
    engine = ExtractionEngine(config)
    
    # Convert page range from 1-indexed to 0-indexed
    page_range_0idx = None
    if page_range:
        page_range_0idx = (page_range[0] - 1, page_range[1] - 1)
    
    # Create request
    request = ExtractionRequest(
        pdf_path=pdf_path,
        page_range=page_range_0idx,
        class_level=class_level,
        board=board,
        subject=subject,
        chapter_name=chapter_name,
    )
    
    # Extract questions using two-pass method
    logger.info(f"Starting Stage 1 Two-Pass Extraction from {pdf_path.name}")
    logger.info(f"Subject: {subject}, Class: {class_level}, Board: {board}")
    if page_range:
        logger.info(f"Page range: {page_range[0]} to {page_range[1]}")
    else:
        logger.info("Page range: Auto-detect exercise sections")
    
    try:
        response = engine.extract_two_pass(request)
        
        # Save results
        output_path = engine.save_questions(response)
        
        logger.info(f"✓ Completed in {response.processing_time_seconds:.2f}s")
        logger.info(f"✓ Extracted {len(response.questions)} questions")
        logger.info(f"✓ Saved to: {output_path}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error during two-pass extraction: {e}")
        raise
    finally:
        engine.cleanup()


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """Command-line interface for Multi-Step Pipeline."""
    
    # Default values (defined once to avoid hardcoding in multiple places)
    DEFAULT_PDF = "Input/keph205.pdf"
    DEFAULT_SUBJECT = "Physics"
    
    parser = argparse.ArgumentParser(
        description="Multi-Step Education Pipeline - Extract questions & generate solutions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Stage 1 - Extract questions (auto-detect exercise pages)
    python main.py --stage 1 --pdf "Input/keph203.pdf"
    
    # Stage 1 - Extract from specific pages
    python main.py --stage 1 --pdf "Input/keph203.pdf" --pages "20-25"
    
    # Stage 1 - Two-pass extraction (for Chemistry)
    python main.py --stage 1 --pdf "Input/kech202.pdf" --subject "Chemistry" --two-pass
    
    # Stage 2 - Generate solutions for specific questions
    python main.py --stage 2 --pdf "Input/keph205.pdf" --questions "12.4,12.7"
    
    # Stage 2 - Solve ALL questions from a previous extraction
    python main.py --stage 2 --from-extraction "Output/questions_physics_keph102_*.json" --questions all
    
    # Stage 2 - Solve specific non-contiguous questions (will be batched)
    python main.py --stage 2 --pdf "Input/keph205.pdf" --questions "5.14,5.21,5.25,5.40"
    
    # Stage 2 - Custom batch size (3 questions per batch)
    python main.py --stage 2 --from-extraction "Output/questions_*.json" --questions all --batch-size 3
    
    # Stage 2 - Disable batching (all questions in one API call)
    python main.py --stage 2 --from-extraction "Output/questions_*.json" --questions all --batch-size 0
    
    # Stage 2 - Auto-use extraction (PDF and subject inferred from extraction)
    python main.py --stage 2 --from-extraction "Output/questions_physics_keph102_*.json"
    
    # Stage 3 - End-to-End Pipeline (with database ingestion)
    python main.py --stage 3 --pdf "Input/keph205.pdf" --class 11 --subject Physics
    
    # Stage 3 - Local only (no database, no blob upload)
    python main.py --stage 3 --pdf "Input/keph205.pdf" --local-only
    
    # Stage 3 - Force rerun (re-process everything)
    python main.py --stage 3 --pdf "Input/keph205.pdf" --class 11 --subject Physics --force-rerun
    
    # Cleanup - Remove exercise/question data + local files (keeps ChapterData)
    python main.py --cleanup --pdf "Input/keph205.pdf" --chapter-id 24
    
    # Cleanup - By class/subject/chapter-number
    python main.py --cleanup --pdf "Input/keph205.pdf" --class 11 --subject Physics --chapter-number 10
    
    # Cleanup - Local files only (no DB, e.g., after aborted Stage 1)
    python main.py --cleanup --pdf "Input/kech102.pdf"
    
    # Cleanup - Dry run (preview without deleting)
    python main.py --cleanup --pdf "Input/keph205.pdf" --chapter-id 24 --dry-run
    
    # Different subject
    python main.py --stage 1 --pdf "chemistry.pdf" --subject "Chemistry"
        """
    )
    
    # Stage selection
    parser.add_argument(
        "--stage",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Pipeline stage: 1=Extraction, 2=Solver, 3=E2E Pipeline (default: 2 if --questions provided, else 1)"
    )
    
    # Common arguments
    parser.add_argument(
        "--pdf",
        type=str,
        default=DEFAULT_PDF,
        help="Path to the chapter PDF"
    )
    
    parser.add_argument(
        "--subject",
        type=str,
        default=DEFAULT_SUBJECT,
        help="Subject name (default: Physics)"
    )
    
    parser.add_argument(
        "--class",
        dest="class_level",
        type=str,
        default="11th",
        help="Class level (default: 11th)"
    )
    
    parser.add_argument(
        "--board",
        type=str,
        default="CBSE",
        help="Education board (default: CBSE)"
    )
    
    parser.add_argument(
        "--chapter",
        type=str,
        default=None,
        help="Chapter name (optional)"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory (default: Output/)"
    )
    
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Path to custom prompt template"
    )
    
    # Stage 1 specific
    parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="[Stage 1] Page range to extract (e.g., '20-25'). Omit for auto-detect."
    )
    
    parser.add_argument(
        "--two-pass",
        action="store_true",
        help="[Stage 1] Use two-pass extraction (more reliable for complex content like Chemistry)"
    )
    
    # Stage 2 specific
    parser.add_argument(
        "--questions",
        type=str,
        default=None,
        help="[Stage 2] Comma-separated list of question IDs (e.g., '12.4,12.7') or 'all' to solve all from --from-extraction"
    )
    
    parser.add_argument(
        "--from-extraction",
        type=str,
        default=None,
        help="[Stage 2] Path to Stage 1 extraction JSON to get questions from (supports glob patterns like 'Output/questions_*.json')"
    )
    
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="[Stage 2] Disable content caching"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="[Stage 2/3] Number of questions per batch (default: 5). Set to 0 to disable batching."
    )
    
    # Stage 3 (E2E Pipeline) specific
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="[Stage 3] Skip database and blob storage operations (save to local JSON only)"
    )
    
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="[Stage 3] Re-process even if data exists (uses UPSERT for database)"
    )
    
    parser.add_argument(
        "--skip-solutions",
        action="store_true",
        help="[Stage 3] Skip Stage 2 solution generation (extraction only)"
    )
    
    parser.add_argument(
        "--no-managed-identity",
        action="store_true",
        help="[Stage 3] Don't use Azure Managed Identity (use connection strings instead)"
    )
    
    # Cleanup arguments
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="[Cleanup] Delete ExerciseData and QuestionData for a chapter, plus local state/output files (keeps ChapterData)"  
    )
    
    parser.add_argument(
        "--chapter-id",
        type=int,
        default=None,
        help="[Cleanup] ChapterId to clean up (alternative to --class/--subject/--chapter-number)"
    )
    
    parser.add_argument(
        "--chapter-number",
        type=str,
        default=None,
        help="[Cleanup] Chapter number (used with --class and --subject to find ChapterId)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="[Cleanup] Preview what would be deleted without actually deleting"
    )
    
    args = parser.parse_args()
    
    # ==========================================================================
    # Cleanup Mode
    # ==========================================================================
    if args.cleanup:
        print("\n" + "="*60)
        print("CLEANUP MODE")
        print("="*60)
        
        # PDF is required for cleanup to identify local files
        # Note: We accept any --pdf value including the default, since user may want to cleanup that file
        if not args.pdf:
            logger.error("--pdf is required for cleanup to identify local state/output files")
            sys.exit(1)
        
        # Resolve PDF path for file cleanup
        script_dir = Path(__file__).parent
        cleanup_pdf_path = Path(args.pdf)
        if not cleanup_pdf_path.is_absolute():
            cleanup_pdf_path = script_dir / cleanup_pdf_path
        
        pdf_stem = cleanup_pdf_path.stem
        output_dir = Path(args.output) if args.output else script_dir / "Output"
        
        # Determine if we have DB info to clean
        has_db_info = args.chapter_id or args.chapter_number
        
        print(f"  PDF: {cleanup_pdf_path.name}")
        print(f"  Dry Run: {'Yes' if args.dry_run else 'No'}")
        
        try:
            # ============================================================
            # Database cleanup (only if chapter info provided)
            # ============================================================
            if has_db_info:
                from db_client import DatabaseClient
                db_client = DatabaseClient(use_managed_identity=not args.no_managed_identity)
                
                # Determine chapter_id
                chapter_id = args.chapter_id
                
                if not chapter_id:
                    # Look up by class/subject/chapter_number
                    chapter_id = db_client.get_chapter_id(
                        class_level=args.class_level.replace("th", ""),  # "11th" -> "11"
                        subject=args.subject,
                        chapter_number=args.chapter_number
                    )
                    
                    if not chapter_id:
                        logger.error(f"Chapter not found: class={args.class_level}, subject={args.subject}, chapter={args.chapter_number}")
                        sys.exit(1)
                
                # Get chapter info for display
                chapter_info = db_client.get_chapter_info(chapter_id)
                if chapter_info:
                    print(f"  Chapter ID: {chapter_id}")
                    print(f"  Class: {chapter_info['class']}")
                    print(f"  Subject: {chapter_info['subject']}")
                    print(f"  Chapter Number: {chapter_info['chapter_number']}")
                    print(f"  Chapter Name: {chapter_info['chapter_name']}")
                else:
                    print(f"  Chapter ID: {chapter_id}")
                    logger.warning("Could not retrieve chapter info from ChapterData")
                
                print("="*60 + "\n")
                
                # Perform DB cleanup
                result = db_client.cleanup_chapter_data(chapter_id, dry_run=args.dry_run)
                
                if args.dry_run:
                    print("[DRY RUN] Would delete from database:")
                else:
                    print("✓ Database cleanup complete:")
                
                print(f"  Exercises: {result['exercises_deleted']}")
                print(f"  Questions: {result['questions_deleted']}")
                print("  ChapterData: NOT touched")
                
                db_client.close()
            else:
                print("  (No chapter info provided - skipping database cleanup)")
                print("="*60 + "\n")
            
            # ============================================================
            # Local file cleanup (always runs)
            # ============================================================
            local_files_to_delete = [
                output_dir / f"{pdf_stem}_pipeline_state.json",
                output_dir / f"{pdf_stem}_extraction.json",
                output_dir / f"{pdf_stem}_solutions.json",
            ]
            
            print("\nLocal files:")
            files_deleted = 0
            for file_path in local_files_to_delete:
                if file_path.exists():
                    if args.dry_run:
                        print(f"  Would delete: {file_path.name}")
                    else:
                        file_path.unlink()
                        print(f"  ✓ Deleted: {file_path.name}")
                    files_deleted += 1
                else:
                    print(f"  (not found: {file_path.name})")
            
            if files_deleted == 0:
                print("  (no local files found)")
            
            print("\n" + "="*60 + "\n")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        sys.exit(0)
    
    # Determine stage
    if args.stage:
        stage = args.stage
    elif args.questions:
        stage = 2  # Questions provided → solver
    else:
        stage = 1  # Default to extraction
    
    # Resolve paths
    script_dir = Path(__file__).parent
    
    pdf_path = Path(args.pdf)
    if not pdf_path.is_absolute():
        pdf_path = script_dir / pdf_path
    
    if not pdf_path.exists():
        logger.error(f"PDF not found: {pdf_path}")
        sys.exit(1)
    
    output_dir = Path(args.output) if args.output else script_dir / "Output"
    prompt_path = Path(args.prompt) if args.prompt else None
    
    # ==========================================================================
    # Stage 1: Question Extraction
    # ==========================================================================
    if stage == 1:
        # Parse page range
        page_range = None
        if args.pages:
            try:
                parts = args.pages.split("-")
                page_range = (int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                logger.error(f"Invalid page range format: {args.pages}. Use 'start-end' (e.g., '20-25')")
                sys.exit(1)
        
        print("\n" + "="*60)
        print("Stage 1: Question Extraction")
        print("="*60)
        print(f"PDF: {pdf_path.name}")
        print(f"Subject: {args.subject}")
        print(f"Class: {args.class_level}")
        print(f"Board: {args.board}")
        print(f"Pages: {f'{page_range[0]}-{page_range[1]}' if page_range else 'Auto-detect'}")
        print(f"Mode: {'Two-Pass' if args.two_pass else 'Single-Pass (sliding window)'}")
        print("="*60 + "\n")
        
        try:
            if args.two_pass:
                response = run_stage1_extraction_two_pass(
                    pdf_path=pdf_path,
                    class_level=args.class_level,
                    board=args.board,
                    subject=args.subject,
                    chapter_name=args.chapter,
                    page_range=page_range,
                    output_dir=output_dir,
                )
            else:
                response = run_stage1_extraction(
                    pdf_path=pdf_path,
                    class_level=args.class_level,
                    board=args.board,
                    subject=args.subject,
                    chapter_name=args.chapter,
                    page_range=page_range,
                    prompt_template_path=prompt_path,
                    output_dir=output_dir,
                )
            
            # Print summary
            print("\n" + "="*60)
            print("✓ EXTRACTION COMPLETE")
            print("="*60)
            print(f"  Questions extracted: {len(response.questions)}")
            print(f"  Exercise sections: {len(response.exercise_sections)}")
            print(f"  Processing time: {response.processing_time_seconds:.2f}s")
            print(f"  Model used: {response.model_used}")
            
            if response.questions:
                print(f"\n  Extracted Questions:")
                for q in response.questions[:10]:  # Show first 10
                    visual_indicator = "📊" if q.visual_required else "  "
                    text_preview = q.question_text[:60].replace('\n', ' ')
                    print(f"    {visual_indicator} {q.question_id}: {text_preview}...")
                
                if len(response.questions) > 10:
                    print(f"    ... and {len(response.questions) - 10} more")
            
            print("="*60 + "\n")
            
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    # ==========================================================================
    # Stage 2: Solution Generation
    # ==========================================================================
    elif stage == 2:
        # Load questions from extraction JSON if provided
        questions = []
        extraction_data = None
        
        if args.from_extraction:
            import glob
            import json
            
            # Handle glob patterns
            extraction_path = args.from_extraction
            if '*' in extraction_path:
                matches = sorted(glob.glob(extraction_path))
                if not matches:
                    logger.error(f"No files match pattern: {extraction_path}")
                    sys.exit(1)
                extraction_path = matches[-1]  # Use most recent
                logger.info(f"Using extraction file: {extraction_path}")
            
            # Load extraction JSON
            try:
                with open(extraction_path, 'r', encoding='utf-8') as f:
                    extraction_data = json.load(f)
                
                all_question_ids = [q['question_id'] for q in extraction_data.get('questions', [])]
                logger.info(f"Found {len(all_question_ids)} questions in extraction: {all_question_ids}")
                
                # Get PDF path from extraction metadata if not provided
                if args.pdf == DEFAULT_PDF:  # Default value, try to use from extraction
                    extracted_pdf = extraction_data.get('metadata', {}).get('pdf_file')
                    if extracted_pdf:
                        pdf_path = script_dir / "Input" / extracted_pdf
                        logger.info(f"Using PDF from extraction: {pdf_path}")
                
                # Get subject from extraction metadata
                if args.subject == DEFAULT_SUBJECT:  # Default value
                    extracted_subject = extraction_data.get('metadata', {}).get('subject')
                    if extracted_subject:
                        args.subject = extracted_subject
                        logger.info(f"Using subject from extraction: {args.subject}")
                
            except Exception as e:
                logger.error(f"Failed to load extraction JSON: {e}")
                sys.exit(1)
        
        # Determine which questions to solve
        if args.questions:
            if args.questions.lower() == 'all':
                if extraction_data:
                    questions = [q['question_id'] for q in extraction_data.get('questions', [])]
                else:
                    logger.error("--questions all requires --from-extraction to specify which extraction file to use")
                    sys.exit(1)
            else:
                questions = [q.strip() for q in args.questions.split(",")]
        elif extraction_data:
            # Default to all questions from extraction
            questions = [q['question_id'] for q in extraction_data.get('questions', [])]
        else:
            logger.error("Stage 2 requires --questions argument or --from-extraction")
            sys.exit(1)
        
        if not questions:
            logger.error("No questions to solve")
            sys.exit(1)
        
        print("\n" + "="*60)
        print("Stage 2: Solver Engine")
        print("="*60)
        print(f"PDF: {pdf_path.name}")
        print(f"Questions: {questions}")
        print(f"Subject: {args.subject}")
        print(f"Class: {args.class_level}")
        print(f"Board: {args.board}")
        print(f"Cache: {'Disabled' if args.no_cache else 'Enabled'}")
        print(f"Batch Size: {args.batch_size} {'(disabled)' if args.batch_size == 0 else ''}")
        print("="*60 + "\n")
        
        try:
            response = run_stage2_solver(
                pdf_path=pdf_path,
                questions=questions,
                class_level=args.class_level,
                board=args.board,
                subject=args.subject,
                chapter_name=args.chapter,
                prompt_template_path=prompt_path,
                output_dir=output_dir,
                use_cache=not args.no_cache,
                batch_size=args.batch_size,
            )
            
            # Print summary
            print("\n" + "="*60)
            print("✓ SOLUTION GENERATION COMPLETE")
            print("="*60)
            print(f"  Solutions generated: {len(response.solutions)}")
            print(f"  Processing time: {response.processing_time_seconds:.2f}s")
            print(f"  Model used: {response.model_used}")
            
            for sol in response.solutions:
                print(f"\n  Question {sol.question_id}:")
                print(f"    Steps: {len(sol.steps)}")
                answer_preview = sol.final_answer[:100] if len(sol.final_answer) > 100 else sol.final_answer
                print(f"    Answer: {answer_preview}...")
            
            print("="*60 + "\n")
            
        except Exception as e:
            logger.error(f"Solution generation failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    # ==========================================================================
    # Stage 3: End-to-End Pipeline
    # ==========================================================================
    elif stage == 3:
        print("\n" + "="*60)
        print("Stage 3: End-to-End Pipeline")
        print("="*60)
        print(f"PDF: {pdf_path.name}")
        print(f"Subject: {args.subject}")
        print(f"Class: {args.class_level}")
        print(f"Board: {args.board}")
        print(f"Mode: {'Local Only' if args.local_only else 'Full (DB + Blob)'}")
        print(f"Force Rerun: {args.force_rerun}")
        print(f"Skip Solutions: {args.skip_solutions}")
        print(f"Managed Identity: {'No' if args.no_managed_identity else 'Yes'}")
        print("="*60 + "\n")
        
        try:
            from e2e_pipeline import E2EPipeline
            
            pipeline = E2EPipeline(
                use_managed_identity=not args.no_managed_identity,
                local_only=args.local_only
            )
            
            state = pipeline.run(
                pdf_path=pdf_path,
                class_level=args.class_level,
                board=args.board,
                subject=args.subject,
                chapter_name=args.chapter,
                output_dir=output_dir,
                force_rerun=args.force_rerun,
                skip_solutions=args.skip_solutions,
                batch_size=args.batch_size
            )
            
            # Print summary
            print("\n" + "="*60)
            print("✓ E2E PIPELINE COMPLETE")
            print("="*60)
            print(f"  Chapter Number: {state.chapter_number}")
            print(f"  Extraction JSON: {state.extraction_json_path}")
            print(f"  Solutions JSON: {state.solutions_json_path}")
            if not args.local_only:
                print(f"  Chapter ID: {state.chapter_id}")
                print(f"  Exercises: {len(state.exercise_ids)}")
                print(f"  Questions: {len(state.question_ids)}")
            print(f"  Completed at: {state.completed_at}")
            print("="*60 + "\n")
            
        except Exception as e:
            logger.error(f"E2E Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
