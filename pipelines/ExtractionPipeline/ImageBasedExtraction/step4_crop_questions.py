"""
Step 4: Crop Individual Questions from Page Images

Uses bounding box coordinates to physically crop individual question images
from full page images.
"""

import json
from pathlib import Path
from typing import List, Dict
from PIL import Image
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class QuestionCropper:
    """Crops individual questions from page images using bounding boxes."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.padding = config['step4_cropping']['padding_pixels']
        self.output_format = config['step4_cropping']['output_format'].lower()
        self.quality = config['step4_cropping']['quality']
        self.naming_convention = config['step4_cropping']['naming_convention']
    
    def crop_bbox_from_image(self, img: Image, bbox: List[float]) -> Image:
        """
        Crop a bounding box region from an image.
        
        Args:
            img: PIL Image object
            bbox: Bounding box as [ymin, xmin, ymax, xmax] in normalized 0-1000 coordinates
        
        Returns:
            Cropped PIL Image
        """
        width, height = img.size
        
        # Extract bbox coordinates - Gemini returns [ymin, xmin, ymax, xmax] in normalized 0-1000 scale
        ymin_norm, xmin_norm, ymax_norm, xmax_norm = bbox
        
        # Convert from normalized coordinates (0-1000) to actual pixels
        ymin_px = int((ymin_norm / 1000) * height)
        xmin_px = int((xmin_norm / 1000) * width)
        ymax_px = int((ymax_norm / 1000) * height)
        xmax_px = int((xmax_norm / 1000) * width)
        
        # Add padding
        xmin_px = max(0, xmin_px - self.padding)
        ymin_px = max(0, ymin_px - self.padding)
        xmax_px = min(width, xmax_px + self.padding)
        ymax_px = min(height, ymax_px + self.padding)
        
        # Crop using PIL format: (left, upper, right, lower)
        return img.crop((xmin_px, ymin_px, xmax_px, ymax_px))
    
    def crop_question(self, page_image_path: Path, bbox: List[float], 
                     question_number: str, page_number: int, 
                     output_dir: Path, continuation_data: Dict = None) -> Path:
        """Crop a single question from page image, with optional continuation stitching.
        
        Args:
            page_image_path: Path to the full page image
            bbox: Bounding box as [ymin, xmin, ymax, xmax] in normalized 0-1000 coordinates
            question_number: Question identifier
            page_number: Page number
            output_dir: Directory to save cropped image
            continuation_data: Optional dict with continuation_page, continuation_bbox, continuation_source_image
        """
        
        # Load main page image
        img = Image.open(page_image_path)
        
        logger.debug(f"  Q{question_number}: Normalized bbox {bbox}")
        
        # Crop main part
        cropped_main = self.crop_bbox_from_image(img, bbox)
        
        # If there's a continuation, stitch vertically
        if continuation_data:
            continuation_bbox = continuation_data.get('continuation_bbox')
            continuation_source = continuation_data.get('continuation_source_image')
            
            if continuation_bbox and continuation_source:
                # Find continuation image
                cont_image_path = page_image_path.parent / continuation_source
                
                if cont_image_path.exists():
                    # Load continuation page
                    img_cont = Image.open(cont_image_path)
                    
                    # Crop continuation part
                    cropped_cont = self.crop_bbox_from_image(img_cont, continuation_bbox)
                    
                    # Vertically stitch: main on top, continuation below
                    total_height = cropped_main.height + cropped_cont.height
                    max_width = max(cropped_main.width, cropped_cont.width)
                    
                    stitched = Image.new('RGB', (max_width, total_height), color='white')
                    stitched.paste(cropped_main, (0, 0))
                    stitched.paste(cropped_cont, (0, cropped_main.height))
                    
                    cropped = stitched
                    logger.info(f"  Q{question_number}: Stitched with continuation from page {continuation_data.get('continuation_page')}")
                else:
                    logger.warning(f"  Q{question_number}: Continuation image not found: {cont_image_path}")
                    cropped = cropped_main
            else:
                cropped = cropped_main
        else:
            cropped = cropped_main
        
        # Generate output filename
        safe_q_num = question_number.replace('.', '_').replace(' ', '_')
        filename = self.naming_convention.format(
            page=f"{page_number:04d}",
            number=safe_q_num
        )
        
        output_path = output_dir / filename
        
        # Save with high quality
        if self.output_format == 'png':
            cropped.save(output_path, 'PNG', optimize=True)
        elif self.output_format in ['jpg', 'jpeg']:
            cropped.save(output_path, 'JPEG', quality=self.quality, optimize=True)
        else:
            cropped.save(output_path)
        
        logger.info(f"  Cropped Q{question_number} (page {page_number}) -> {filename}")
        return output_path
    
    def crop_all_questions(self, questions: List[Dict], images_dir: Path, 
                          output_dir: Path) -> List[Dict]:
        """Crop all questions from their respective page images."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        cropped_files = []
        errors = []
        
        for i, question in enumerate(questions, 1):
            try:
                # Find source page image
                page_num = question['page_number']
                source_image = question.get('source_image')
                
                # Try to find the image file
                if source_image:
                    page_image_path = images_dir / source_image
                else:
                    page_image_path = images_dir / f"page_{page_num:04d}.png"
                
                # Check alternative formats if not found
                if not page_image_path.exists():
                    for ext in ['jpg', 'jpeg', 'PNG', 'JPG']:
                        alt_path = images_dir / f"page_{page_num:04d}.{ext}"
                        if alt_path.exists():
                            page_image_path = alt_path
                            break
                
                if not page_image_path.exists():
                    raise FileNotFoundError(f"Page image not found: {page_image_path}")
                
                # Prepare continuation data if present
                continuation_data = None
                if question.get('has_continuation'):
                    continuation_data = {
                        'continuation_page': question.get('continuation_page'),
                        'continuation_bbox': question.get('continuation_bbox'),
                        'continuation_source_image': question.get('continuation_source_image')
                    }
                
                # Crop question (with stitching if needed)
                output_path = self.crop_question(
                    page_image_path,
                    question['bbox'],
                    question['question_number'],
                    page_num,
                    output_dir,
                    continuation_data
                )
                
                cropped_files.append({
                    'question_number': question['question_number'],
                    'page_number': page_num,
                    'output_file': str(output_path.name),
                    'bbox': question['bbox'],
                    'description': question.get('description', ''),
                    'has_figures': question.get('has_figures', False),
                    'has_formulas': question.get('has_formulas', False),
                    'has_continuation': question.get('has_continuation', False),
                    'continuation_page': question.get('continuation_page')
                })
                
            except Exception as e:
                logger.error(f"  Error cropping question {i}: {e}")
                errors.append({
                    'question_index': i,
                    'question_number': question.get('question_number', 'unknown'),
                    'error': str(e)
                })
        
        logger.info(f"Successfully cropped {len(cropped_files)} questions")
        if errors:
            logger.warning(f"Failed to crop {len(errors)} questions")
        
        return cropped_files, errors
    
    def save_metadata(self, cropped_files: List[Dict], errors: List[Dict], 
                     output_dir: Path, pdf_name: str):
        """Save cropping metadata and results."""
        metadata = {
            'pdf_name': pdf_name,
            'total_questions': len(cropped_files),
            'successful_crops': len(cropped_files),
            'failed_crops': len(errors),
            'questions': cropped_files,
            'errors': errors
        }
        
        output_file = output_dir / 'cropping_metadata.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Saved metadata to: {output_file}")


def main():
    """Main execution for step 4."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Step 4: Crop individual questions')
    parser.add_argument('--images-dir', type=Path, required=True, help='Directory with page images')
    parser.add_argument('--boxes-json', type=Path, required=True, help='JSON with bounding boxes')
    parser.add_argument('--config', type=Path, default=Path('config.json'), help='Config file')
    parser.add_argument('--output', type=Path, help='Output directory for cropped images')
    
    args = parser.parse_args()
    
    # Load config
    with open(args.config, 'r') as f:
        config = json.load(f)
    
    # Load bounding boxes
    with open(args.boxes_json, 'r') as f:
        boxes_data = json.load(f)
        questions = boxes_data['questions']
        pdf_name = boxes_data.get('pdf_name', 'unknown')
    
    # Determine output directory
    if args.output:
        output_dir = args.output
    else:
        base_output = args.images_dir.parent
        output_dir = base_output / config['output']['questions_folder']
    
    # Crop questions
    cropper = QuestionCropper(config)
    cropped_files, errors = cropper.crop_all_questions(questions, args.images_dir, output_dir)
    
    # Save metadata
    cropper.save_metadata(cropped_files, errors, output_dir, pdf_name)
    
    print(f"\n✓ Successfully cropped {len(cropped_files)} questions")
    if errors:
        print(f"  ⚠ Failed to crop {len(errors)} questions")
    print(f"  Output directory: {output_dir}")


if __name__ == "__main__":
    main()
