"""
Step 3: Detect Question Bounding Boxes using Gemini

Uses Gemini 2.5 Pro to analyze page images and extract bounding box coordinates
for each question.
"""

import json
import os
import time
from pathlib import Path
from typing import List, Dict, Optional
import google.generativeai as genai
from PIL import Image
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BoundingBoxDetector:
    """Detects question bounding boxes using Gemini vision model."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.max_retries = config['step3_bounding_box']['max_retries']
        self.rate_limit_delay = config['gemini']['rate_limit_delay']
        self.top_buffer = config['step3_bounding_box'].get('top_buffer', 15)
        self.bottom_buffer = config['step3_bounding_box'].get('bottom_buffer', 5)
        self.left_buffer = config['step3_bounding_box'].get('left_buffer', 5)
        self.right_buffer = config['step3_bounding_box'].get('right_buffer', 5)
        
        # Initialize Gemini
        api_key = os.getenv(config['gemini']['api_key_env'])
        if not api_key:
            raise ValueError(f"API key not found: {config['gemini']['api_key_env']}")
        
        genai.configure(api_key=api_key)
        
        # Configure generation parameters to match AI Studio defaults
        generation_config = {
            "temperature": config['gemini'].get('temperature', 0.0),
            "max_output_tokens": config['gemini'].get('max_tokens', 8192),
            "top_p": config['gemini'].get('top_p', 0.95),
        }
        
        self.model = genai.GenerativeModel(
            config['step3_bounding_box']['gemini_model'],
            generation_config=generation_config
        )
        
        # Load prompt template
        prompt_file = Path(config['step3_bounding_box']['prompt_template'])
        with open(prompt_file, 'r', encoding='utf-8') as f:
            self.prompt_template = f.read()
    
    def apply_safety_buffer(self, questions: List[Dict], img_height_norm: int = 1000, img_width_norm: int = 1000) -> List[Dict]:
        """
        Expands bounding boxes slightly in normalized space to prevent cutting off question numbers/text.
        
        This is applied BEFORE converting to pixels, so buffers scale proportionally with image size.
        
        Args:
            questions: List of question objects with bbox in [ymin, xmin, ymax, xmax] format
            img_height_norm: Normalized height scale (default 1000)
            img_width_norm: Normalized width scale (default 1000)
        
        Returns:
            Modified questions list with expanded bounding boxes
        """
        for q in questions:
            bbox = q['bbox']  # [ymin, xmin, ymax, xmax]
            
            # Expand upwards (reduce ymin) - catches question numbers at top
            bbox[0] = max(0, bbox[0] - self.top_buffer)
            
            # Expand left (reduce xmin)
            bbox[1] = max(0, bbox[1] - self.left_buffer)
            
            # Expand downwards (increase ymax) - ensures descenders aren't cut
            bbox[2] = min(img_height_norm, bbox[2] + self.bottom_buffer)
            
            # Expand right (increase xmax)
            bbox[3] = min(img_width_norm, bbox[3] + self.right_buffer)
        
        logger.debug(f"Applied safety buffer: top={self.top_buffer}, bottom={self.bottom_buffer}, left={self.left_buffer}, right={self.right_buffer}")
        return questions
    
    def detect_boxes_for_image(self, image_path: Path, page_number: int) -> Optional[Dict]:
        """Detect bounding boxes for a single page image."""
        logger.info(f"Detecting bounding boxes for page {page_number}: {image_path.name}")
        
        # Load image
        img = Image.open(image_path)
        
        for attempt in range(self.max_retries):
            try:
                # Send to Gemini
                response = self.model.generate_content([
                    self.prompt_template,
                    img
                ])
                
                # Parse JSON response
                response_text = response.text.strip()
                # Remove markdown code blocks if present
                if '```json' in response_text:
                    response_text = response_text.split('```json')[1].split('```')[0]
                elif '```' in response_text:
                    response_text = response_text.split('```')[1].split('```')[0]
                
                result = json.loads(response_text)
                
                # Validate structure
                if 'questions' not in result:
                    raise ValueError("Response missing 'questions' key")
                
                # Apply safety buffer to bounding boxes (in normalized space)
                result['questions'] = self.apply_safety_buffer(result['questions'])
                
                # Add page info to each question
                for q in result['questions']:
                    q['page_number'] = page_number
                    q['source_image'] = str(image_path.name)
                
                logger.info(f"  Found {len(result['questions'])} questions on page {page_number}")
                
                # Rate limiting
                time.sleep(self.rate_limit_delay)
                
                return result
                
            except Exception as e:
                logger.warning(f"  Attempt {attempt + 1}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"  Failed to detect boxes for page {page_number} after {self.max_retries} attempts")
                    return None
    
    def detect_boxes_batch(self, image_dir: Path, page_numbers: List[int]) -> List[Dict]:
        """Detect bounding boxes for all page images."""
        all_questions = []
        
        for page_num in page_numbers:
            # Find corresponding image file
            image_file = image_dir / f"page_{page_num + 1:04d}.png"
            if not image_file.exists():
                # Try other formats
                for ext in ['jpg', 'jpeg', 'PNG', 'JPG']:
                    alt_file = image_dir / f"page_{page_num + 1:04d}.{ext}"
                    if alt_file.exists():
                        image_file = alt_file
                        break
            
            if not image_file.exists():
                logger.warning(f"Image file not found for page {page_num + 1}")
                continue
            
            # Detect boxes
            result = self.detect_boxes_for_image(image_file, page_num + 1)
            if result and 'questions' in result:
                all_questions.extend(result['questions'])
        
        return all_questions
    
    def stitch_continuations(self, questions: List[Dict]) -> List[Dict]:
        """
        Merges 'continuation' blocks into the last question from the previous page.
        
        When a question spans multiple pages, the continuation block from page N
        is merged with the last question from page N-1, combining their bboxes
        so Step 4 can create a single vertically-stitched image.
        
        Args:
            questions: List of all questions (from all pages)
        
        Returns:
            Cleaned list with continuations merged
        """
        if not questions:
            return questions
        
        # Group questions by page
        pages_dict = {}
        for q in questions:
            page_num = q['page_number']
            if page_num not in pages_dict:
                pages_dict[page_num] = []
            pages_dict[page_num].append(q)
        
        # Sort by page number
        sorted_pages = sorted(pages_dict.keys())
        
        # Process each page
        cleaned_questions = []
        for i, page_num in enumerate(sorted_pages):
            page_questions = pages_dict[page_num]
            
            # Check if first question is a continuation
            if page_questions and page_questions[0]['question_number'] == 'continuation':
                continuation = page_questions.pop(0)
                
                # Find the last question from the previous page
                if cleaned_questions:
                    last_q = cleaned_questions[-1]
                    
                    # Mark as multi-page question
                    last_q['has_continuation'] = True
                    last_q['continuation_page'] = page_num
                    last_q['continuation_bbox'] = continuation['bbox']
                    last_q['continuation_source_image'] = continuation.get('source_image')
                    
                    logger.info(f"  Stitched continuation from page {page_num} to Q{last_q['question_number']} (page {last_q['page_number']})")
                else:
                    # Orphaned continuation at the start - shouldn't happen but handle gracefully
                    logger.warning(f"  Found orphaned continuation on page {page_num} with no previous question")
            
            # Add remaining questions from this page
            cleaned_questions.extend(page_questions)
        
        logger.info(f"Stitching complete: {len(questions)} → {len(cleaned_questions)} questions")
        return cleaned_questions
    
    def save_results(self, questions: List[Dict], output_dir: Path, pdf_name: str):
        """Save detected bounding boxes to JSON."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        result = {
            "pdf_name": pdf_name,
            "total_questions": len(questions),
            "questions": questions
        }
        
        output_file = output_dir / "bounding_boxes.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        
        logger.info(f"Saved bounding boxes to: {output_file}")
        return output_file


def main():
    """Main execution for step 3."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Step 3: Detect question bounding boxes')
    parser.add_argument('--images-dir', type=Path, required=True, help='Directory with page images')
    parser.add_argument('--pages-json', type=Path, required=True, help='JSON file with page numbers')
    parser.add_argument('--config', type=Path, default=Path('config.json'), help='Config file')
    parser.add_argument('--output', type=Path, help='Output directory for results')
    parser.add_argument('--pdf-name', type=str, help='Name of source PDF')
    
    args = parser.parse_args()
    
    # Load config
    with open(args.config, 'r') as f:
        config = json.load(f)
    
    # Load page numbers
    with open(args.pages_json, 'r') as f:
        pages_data = json.load(f)
        page_numbers = pages_data['exercise_pages']
        pdf_name = args.pdf_name or pages_data.get('pdf_file', 'unknown')
    
    # Determine output directory
    output_dir = args.output or args.images_dir.parent
    
    # Detect bounding boxes
    detector = BoundingBoxDetector(config)
    questions = detector.detect_boxes_batch(args.images_dir, page_numbers)
    
    # Stitch continuations
    questions = detector.stitch_continuations(questions)
    
    # Save results
    detector.save_results(questions, output_dir, pdf_name)
    
    print(f"\n✓ Detected {len(questions)} questions across {len(page_numbers)} pages")


if __name__ == "__main__":
    main()
