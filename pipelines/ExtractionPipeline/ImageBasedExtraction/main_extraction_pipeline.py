"""
Main Extraction Pipeline - Orchestrates all steps

Runs the complete image-based question extraction pipeline:
1. Find exercise pages
2. Convert pages to high-res images
3. Detect question bounding boxes
4. Crop individual questions
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
import logging
import sys

# Import step modules
from step1_find_exercise_pages import ExercisePageDetector
from step2_convert_pages_to_images import PageConverter
from step3_detect_question_boxes import BoundingBoxDetector
from step4_crop_questions import QuestionCropper

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('extraction.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class ExtractionPipeline:
    """Complete image-based question extraction pipeline."""
    
    def __init__(self, config_path: Path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.start_time = datetime.now()
        logger.info("=" * 80)
        logger.info("IMAGE-BASED QUESTION EXTRACTION PIPELINE")
        logger.info("=" * 80)
    
    def flush_output(self, output_base: Path):
        """Delete all intermediate and final results for a clean start."""
        import shutil
        
        if output_base.exists():
            logger.warning(f"FLUSHING: Deleting all contents in {output_base}")
            shutil.rmtree(output_base)
            logger.info(f"  Deleted: {output_base}")
        else:
            logger.info(f"  Nothing to flush: {output_base} does not exist")
    
    def run(self, pdf_path: Path, output_base: Path = None, skip_steps: list = None, flush: bool = False):
        """Run the complete pipeline."""
        skip_steps = skip_steps or []
        
        # Setup output directories
        if output_base is None:
            output_base = Path(self.config['output']['base_folder']) / pdf_path.stem
        
        # Flush if requested
        if flush:
            self.flush_output(output_base)
        
        output_base.mkdir(parents=True, exist_ok=True)
        logger.info(f"Processing: {pdf_path}")
        logger.info(f"Output directory: {output_base}")
        
        results = {
            'pdf_file': str(pdf_path),
            'start_time': self.start_time.isoformat(),
            'steps_completed': []
        }
        
        # Step 1: Find exercise pages
        if 'step1' not in skip_steps:
            logger.info("\n" + "=" * 80)
            logger.info("STEP 1: Finding Exercise Pages")
            logger.info("=" * 80)
            
            detector = ExercisePageDetector(self.config)
            exercise_pages = detector.detect_pages(pdf_path)
            pages_json = detector.save_results(pdf_path, exercise_pages, output_base)
            
            results['step1'] = {
                'exercise_pages': exercise_pages,
                'output_file': str(pages_json)
            }
            results['steps_completed'].append('step1')
            
            if not exercise_pages:
                logger.error("No exercise pages found. Aborting pipeline.")
                return results
        else:
            # Load from existing file
            pages_json = output_base / f"{pdf_path.stem}_exercise_pages.json"
            with open(pages_json, 'r') as f:
                data = json.load(f)
                exercise_pages = data['exercise_pages']
        
        # Step 2: Convert pages to images
        if 'step2' not in skip_steps:
            logger.info("\n" + "=" * 80)
            logger.info("STEP 2: Converting Pages to Images")
            logger.info("=" * 80)
            
            images_dir = output_base / self.config['output']['page_images_folder']
            converter = PageConverter(self.config)
            image_files = converter.convert_pages(pdf_path, exercise_pages, images_dir)
            converter.save_metadata(pdf_path, exercise_pages, image_files, images_dir)
            
            results['step2'] = {
                'images_dir': str(images_dir),
                'total_images': len(image_files)
            }
            results['steps_completed'].append('step2')
        else:
            images_dir = output_base / self.config['output']['page_images_folder']
        
        # Step 3: Detect question bounding boxes
        if 'step3' not in skip_steps:
            logger.info("\n" + "=" * 80)
            logger.info("STEP 3: Detecting Question Bounding Boxes")
            logger.info("=" * 80)
            
            detector = BoundingBoxDetector(self.config)
            questions = detector.detect_boxes_batch(images_dir, exercise_pages)
            
            # Stitch continuations (merges questions spanning multiple pages)
            questions = detector.stitch_continuations(questions)
            
            boxes_json = detector.save_results(questions, output_base, pdf_path.name)
            
            results['step3'] = {
                'total_questions': len(questions),
                'output_file': str(boxes_json)
            }
            results['steps_completed'].append('step3')
            
            if not questions:
                logger.error("No questions detected. Aborting pipeline.")
                return results
        else:
            # Load from existing file
            boxes_json = output_base / "bounding_boxes.json"
            with open(boxes_json, 'r') as f:
                data = json.load(f)
                questions = data['questions']
        
        # Step 4: Crop individual questions
        if 'step4' not in skip_steps:
            logger.info("\n" + "=" * 80)
            logger.info("STEP 4: Cropping Individual Questions")
            logger.info("=" * 80)
            
            questions_dir = output_base / self.config['output']['questions_folder']
            cropper = QuestionCropper(self.config)
            cropped_files, errors = cropper.crop_all_questions(questions, images_dir, questions_dir)
            cropper.save_metadata(cropped_files, errors, questions_dir, pdf_path.name)
            
            results['step4'] = {
                'successful_crops': len(cropped_files),
                'failed_crops': len(errors),
                'output_dir': str(questions_dir)
            }
            results['steps_completed'].append('step4')
        
        # Save final pipeline results
        end_time = datetime.now()
        results['end_time'] = end_time.isoformat()
        results['duration_seconds'] = (end_time - self.start_time).total_seconds()
        
        results_file = output_base / "pipeline_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        logger.info("\n" + "=" * 80)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Duration: {results['duration_seconds']:.2f} seconds")
        logger.info(f"Results saved to: {results_file}")
        
        return results


def main():
    parser = argparse.ArgumentParser(
        description='Image-Based Question Extraction Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run complete pipeline
  python main_extraction_pipeline.py --input sample.pdf

  # Custom output location
  python main_extraction_pipeline.py --input sample.pdf --output output/my_extraction/

  # Skip certain steps (use existing intermediate results)
  python main_extraction_pipeline.py --input sample.pdf --skip step1 step2

  # Process specific folder
  python main_extraction_pipeline.py --input-folder input/pdfs/ --output output/batch/
        """
    )
    
    parser.add_argument(
        '--input',
        type=Path,
        help='Input PDF file'
    )
    
    parser.add_argument(
        '--input-folder',
        type=Path,
        help='Process all PDFs in this folder'
    )
    
    parser.add_argument(
        '--output',
        type=Path,
        help='Base output directory (default: from config)'
    )
    
    parser.add_argument(
        '--config',
        type=Path,
        default=Path('config.json'),
        help='Configuration file (default: config.json)'
    )
    
    parser.add_argument(
        '--skip',
        nargs='+',
        choices=['step1', 'step2', 'step3', 'step4'],
        help='Skip specific steps (uses existing intermediate results)'
    )
    
    parser.add_argument(
        '--flush',
        action='store_true',
        help='Delete all intermediate results before running (clean start)'
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.input and not args.input_folder:
        parser.error("Either --input or --input-folder must be specified")
    
    # Initialize pipeline
    pipeline = ExtractionPipeline(args.config)
    
    # Process single file or folder
    if args.input:
        pdf_files = [args.input]
    else:
        pdf_files = list(args.input_folder.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files in {args.input_folder}")
    
    # Flush once before processing all files (if requested and using default output structure)
    if args.flush and args.output:
        # If custom output specified, flush that entire directory once
        output_base = Path(args.output)
        if output_base.exists():
            pipeline.flush_output(output_base)
    
    # Process each PDF
    for pdf_file in pdf_files:
        if not pdf_file.exists():
            logger.error(f"File not found: {pdf_file}")
            continue
        
        try:
            # Only flush per-file if using default output (each PDF gets its own folder)
            flush_this_file = args.flush if not args.output else False
            results = pipeline.run(pdf_file, args.output, args.skip, flush_this_file)
            
            print(f"\n{'=' * 80}")
            print(f"SUMMARY FOR: {pdf_file.name}")
            print(f"{'=' * 80}")
            
            if 'step1' in results:
                print(f"  Exercise pages found: {len(results['step1']['exercise_pages'])}")
            if 'step3' in results:
                print(f"  Questions detected: {results['step3']['total_questions']}")
            if 'step4' in results:
                print(f"  Questions extracted: {results['step4']['successful_crops']}")
                if results['step4']['failed_crops'] > 0:
                    print(f"  Failed crops: {results['step4']['failed_crops']}")
            
            print(f"  Duration: {results['duration_seconds']:.2f}s")
            print(f"{'=' * 80}\n")
            
        except Exception as e:
            logger.error(f"Error processing {pdf_file.name}: {e}", exc_info=True)
            continue
    
    logger.info("All processing complete!")


if __name__ == "__main__":
    main()
