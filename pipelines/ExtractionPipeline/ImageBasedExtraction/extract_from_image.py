"""
Standalone script to extract questions from a single page image.

This script runs steps 3 (bounding box detection) and 4 (cropping) on a single image,
without needing a PDF or page detection step.

Usage:
    python extract_from_image.py --image "page_image.png" --output "output_folder"
"""

import json
import argparse
from pathlib import Path
from step3_detect_question_boxes import BoundingBoxDetector
from step4_crop_questions import QuestionCropper
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def extract_from_single_image(image_path: Path, output_dir: Path, config_path: Path, page_number: int = 1):
    """
    Extract questions from a single page image.
    
    Args:
        image_path: Path to the page image
        output_dir: Directory to save cropped questions
        config_path: Path to config.json
        page_number: Page number to assign (default: 1)
    """
    
    # Load config
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    logger.info(f"Processing image: {image_path.name}")
    
    # Step 3: Detect bounding boxes
    logger.info("Step 3: Detecting question bounding boxes...")
    detector = BoundingBoxDetector(config)
    result = detector.detect_boxes_for_image(image_path, page_number)
    
    if not result or 'questions' not in result:
        logger.error("Failed to detect bounding boxes")
        return
    
    questions = result['questions']
    logger.info(f"  Found {len(questions)} questions")
    
    # Create temporary directory structure for cropping
    temp_images_dir = output_dir / "temp_images"
    temp_images_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy/link the image to temp directory with expected naming
    import shutil
    temp_image_path = temp_images_dir / f"page_{page_number:04d}{image_path.suffix}"
    shutil.copy2(image_path, temp_image_path)
    
    # Step 4: Crop questions
    logger.info("Step 4: Cropping individual questions...")
    questions_dir = output_dir / "questions"
    questions_dir.mkdir(parents=True, exist_ok=True)
    
    cropper = QuestionCropper(config)
    cropped_files, errors = cropper.crop_all_questions(questions, temp_images_dir, questions_dir)
    
    # Save metadata
    metadata = {
        'source_image': str(image_path.name),
        'page_number': page_number,
        'total_questions': len(questions),
        'successful_crops': len(cropped_files),
        'failed_crops': len(errors),
        'questions': cropped_files,
        'bounding_boxes': questions,
        'errors': errors
    }
    
    metadata_file = output_dir / 'extraction_metadata.json'
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    # Clean up temp directory
    shutil.rmtree(temp_images_dir)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"✓ Extraction Complete!")
    print(f"{'='*60}")
    print(f"  Source image: {image_path.name}")
    print(f"  Questions found: {len(questions)}")
    print(f"  Successfully cropped: {len(cropped_files)}")
    if errors:
        print(f"  ⚠ Failed: {len(errors)}")
    print(f"  Output directory: {questions_dir}")
    print(f"  Metadata: {metadata_file}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Extract questions from a single page image',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python extract_from_image.py --image "page_001.png" --output "output/test1"
  python extract_from_image.py --image "my_page.jpg" --output "results" --page-number 5
  python extract_from_image.py --image "page.png" --output "out" --config "custom_config.json"
        """
    )
    
    parser.add_argument('--image', type=Path, required=True,
                       help='Path to the page image to process')
    parser.add_argument('--output', type=Path, required=True,
                       help='Output directory for cropped questions')
    parser.add_argument('--config', type=Path, default=Path('config.json'),
                       help='Path to config file (default: config.json)')
    parser.add_argument('--page-number', type=int, default=1,
                       help='Page number to assign (default: 1)')
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.image.exists():
        print(f"Error: Image file not found: {args.image}")
        return
    
    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}")
        return
    
    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)
    
    # Extract questions
    extract_from_single_image(args.image, args.output, args.config, args.page_number)


if __name__ == "__main__":
    main()
