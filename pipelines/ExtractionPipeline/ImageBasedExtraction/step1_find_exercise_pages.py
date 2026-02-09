"""
Step 1: Find Exercise Pages in PDF

Identifies pages containing exercises using either:
1. Pattern matching (fast, rule-based)
2. Gemini 2.5 Flash Lite (intelligent, ML-based)
"""

import fitz  # PyMuPDF
import json
import os
from pathlib import Path
from typing import List, Dict, Tuple
import google.generativeai as genai
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ExercisePageDetector:
    """Detects pages containing exercises in PDF files."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.keywords = config['step1_page_detection']['keywords']
        self.method = config['step1_page_detection']['method']
        
        if self.method == 'gemini':
            api_key = os.getenv(config['gemini']['api_key_env'])
            if not api_key:
                raise ValueError(f"API key not found in environment variable: {config['gemini']['api_key_env']}")
            genai.configure(api_key=api_key)
            
            # Configure generation parameters to match AI Studio defaults
            generation_config = {
                "temperature": config['gemini'].get('temperature', 0.0),
                "max_output_tokens": config['gemini'].get('max_tokens', 8192),
                "top_p": config['gemini'].get('top_p', 0.95),
            }
            
            self.model = genai.GenerativeModel(
                config['step1_page_detection']['gemini_model'],
                generation_config=generation_config
            )
            
            # Load prompt template
            prompt_file = Path(config['step1_page_detection'].get('prompt_template', 'prompts/page_detection_prompt.txt'))
            with open(prompt_file, 'r', encoding='utf-8') as f:
                self.prompt_template = f.read()
    
    def detect_pages_pattern(self, pdf_path: Path) -> List[int]:
        """Detect exercise pages using keyword pattern matching."""
        logger.info(f"Detecting exercise pages using pattern matching in: {pdf_path.name}")
        
        exercise_pages = []
        doc = fitz.open(pdf_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            
            # Check for exercise keywords
            for keyword in self.keywords:
                if keyword.lower() in text.lower():
                    exercise_pages.append(page_num)
                    logger.info(f"  Found keyword '{keyword}' on page {page_num + 1}")
                    break
        
        doc.close()
        logger.info(f"Detected {len(exercise_pages)} exercise pages using patterns")
        return exercise_pages
    
    def detect_pages_gemini(self, pdf_path: Path) -> List[int]:
        """Detect exercise pages using Gemini - single API call for entire PDF.
        
        This is more efficient than page-by-page detection:
        - 1 API call instead of N calls (where N = total pages)
        - Faster execution (no per-page overhead)
        - Better context understanding (Gemini sees whole document structure)
        - Lower cost (fewer API requests)
        """
        logger.info(f"Detecting exercise pages using Gemini in: {pdf_path.name}")
        
        try:
            # Upload PDF to Gemini
            logger.info("  Uploading PDF to Gemini...")
            uploaded_file = genai.upload_file(pdf_path)
            logger.info(f"  Upload complete. Processing with {self.config['step1_page_detection']['gemini_model']}...")
            
            # Send to Gemini with uploaded PDF
            response = self.model.generate_content([
                self.prompt_template,
                uploaded_file
            ])
            
            # Parse response
            response_text = response.text.strip()
            # Remove markdown code blocks if present
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0]
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0]
            
            result = json.loads(response_text.strip())
            
            # Parse page ranges into individual page numbers (0-indexed for internal use)
            page_ranges = result.get('page_ranges', [])
            exercise_numbers = result.get('exercise_number', [])
            confidence = result.get('confidence', 0.0)
            
            # Convert page ranges to list of page numbers
            exercise_pages = []
            for page_range in page_ranges:
                if '-' in str(page_range):
                    # It's a range like "6-7"
                    start, end = map(int, str(page_range).split('-'))
                    exercise_pages.extend(range(start - 1, end))  # Convert to 0-indexed
                else:
                    # Single page
                    exercise_pages.append(int(page_range) - 1)  # Convert to 0-indexed
            
            logger.info(f"  Detected {len(exercise_pages)} exercise pages")
            logger.info(f"  Page ranges: {', '.join(map(str, page_ranges))}")
            if exercise_numbers:
                logger.info(f"  Exercise numbers: {', '.join(map(str, exercise_numbers))}")
            logger.info(f"  Confidence: {confidence:.2f}")
            
            # Clean up uploaded file
            genai.delete_file(uploaded_file.name)
            
            return exercise_pages
            
        except Exception as e:
            logger.error(f"  Error processing PDF with Gemini: {e}")
            logger.warning("  Falling back to pattern matching...")
            # Fallback to pattern matching if Gemini fails
            return self.detect_pages_pattern(pdf_path)
    
    def detect_pages(self, pdf_path: Path) -> List[int]:
        """Detect exercise pages using configured method."""
        if self.method == 'pattern':
            return self.detect_pages_pattern(pdf_path)
        elif self.method == 'gemini':
            return self.detect_pages_gemini(pdf_path)
        else:
            raise ValueError(f"Unknown detection method: {self.method}")
    
    def save_results(self, pdf_path: Path, page_numbers: List[int], output_dir: Path):
        """Save detection results to JSON."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        result = {
            "pdf_file": str(pdf_path.name),
            "total_pages": len(page_numbers),
            "exercise_pages": page_numbers,
            "method": self.method
        }
        
        output_file = output_dir / f"{pdf_path.stem}_exercise_pages.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        
        logger.info(f"Saved results to: {output_file}")
        return output_file


def main():
    """Main execution for step 1."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Step 1: Find exercise pages in PDF')
    parser.add_argument('--pdf', type=Path, required=True, help='Path to input PDF')
    parser.add_argument('--config', type=Path, default=Path('config.json'), help='Config file')
    parser.add_argument('--output', type=Path, help='Output directory for results')
    
    args = parser.parse_args()
    
    # Load config
    with open(args.config, 'r') as f:
        config = json.load(f)
    
    # Determine output directory
    output_dir = args.output or Path(config['output']['base_folder']) / args.pdf.stem
    
    # Detect pages
    detector = ExercisePageDetector(config)
    exercise_pages = detector.detect_pages(args.pdf)
    
    # Save results
    detector.save_results(args.pdf, exercise_pages, output_dir)
    
    print(f"\n✓ Found {len(exercise_pages)} exercise pages")
    print(f"  Pages: {[p+1 for p in exercise_pages]}")


if __name__ == "__main__":
    main()
