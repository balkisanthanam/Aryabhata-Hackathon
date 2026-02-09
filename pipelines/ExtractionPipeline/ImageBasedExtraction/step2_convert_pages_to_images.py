"""
Step 2: Convert PDF Pages to High-Resolution Images

Converts identified exercise pages to high-quality images using pdf2image.
"""

import json
from pathlib import Path
from typing import List, Dict
import logging

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    print("Warning: pdf2image not available. Install with: pip install pdf2image")

import fitz  # PyMuPDF fallback

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PageConverter:
    """Converts PDF pages to high-resolution images."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.dpi = config['step2_page_conversion']['dpi']
        self.format = config['step2_page_conversion']['format'].lower()
        self.poppler_path = config['step2_page_conversion'].get('poppler_path')
        self.library = config['step2_page_conversion']['library']
    
    def convert_with_pdf2image(self, pdf_path: Path, page_numbers: List[int], output_dir: Path) -> List[Path]:
        """Convert pages using pdf2image (highest quality)."""
        if not PDF2IMAGE_AVAILABLE:
            raise ImportError("pdf2image library not available")
        
        logger.info(f"Converting {len(page_numbers)} pages using pdf2image at {self.dpi} DPI")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_images = []
        
        # Convert pages (pdf2image uses 1-indexed pages)
        first_page = min(page_numbers) + 1
        last_page = max(page_numbers) + 1
        
        images = convert_from_path(
            pdf_path,
            dpi=self.dpi,
            first_page=first_page,
            last_page=last_page,
            fmt=self.format,
            poppler_path=self.poppler_path
        )
        
        # Save each page
        page_indices = [p for p in page_numbers if first_page - 1 <= p <= last_page - 1]
        for idx, (page_num, image) in enumerate(zip(sorted(page_indices), images)):
            output_file = output_dir / f"page_{page_num + 1:04d}.{self.format}"
            image.save(output_file, self.format.upper())
            saved_images.append(output_file)
            logger.info(f"  Saved page {page_num + 1} -> {output_file.name}")
        
        return saved_images
    
    def convert_with_pymupdf(self, pdf_path: Path, page_numbers: List[int], output_dir: Path) -> List[Path]:
        """Convert pages using PyMuPDF (fallback, good quality)."""
        logger.info(f"Converting {len(page_numbers)} pages using PyMuPDF at {self.dpi} DPI")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_images = []
        
        doc = fitz.open(pdf_path)
        
        for page_num in sorted(page_numbers):
            page = doc[page_num]
            
            # Calculate zoom factor from DPI (72 is default PDF DPI)
            zoom = self.dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            
            # Render page
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Save image
            output_file = output_dir / f"page_{page_num + 1:04d}.{self.format}"
            pix.save(output_file)
            saved_images.append(output_file)
            logger.info(f"  Saved page {page_num + 1} -> {output_file.name}")
        
        doc.close()
        return saved_images
    
    def convert_pages(self, pdf_path: Path, page_numbers: List[int], output_dir: Path) -> List[Path]:
        """Convert pages using configured library."""
        if self.library == 'pdf2image' and PDF2IMAGE_AVAILABLE:
            return self.convert_with_pdf2image(pdf_path, page_numbers, output_dir)
        else:
            if self.library == 'pdf2image':
                logger.warning("pdf2image not available, falling back to PyMuPDF")
            return self.convert_with_pymupdf(pdf_path, page_numbers, output_dir)
    
    def save_metadata(self, pdf_path: Path, page_numbers: List[int], image_files: List[Path], output_dir: Path):
        """Save conversion metadata."""
        metadata = {
            "pdf_file": str(pdf_path.name),
            "total_pages_converted": len(page_numbers),
            "dpi": self.dpi,
            "format": self.format,
            "library": self.library,
            "pages": [
                {
                    "page_number": page_num + 1,
                    "image_file": str(img.name)
                }
                for page_num, img in zip(sorted(page_numbers), image_files)
            ]
        }
        
        output_file = output_dir / "conversion_metadata.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Saved metadata to: {output_file}")


def main():
    """Main execution for step 2."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Step 2: Convert PDF pages to images')
    parser.add_argument('--pdf', type=Path, required=True, help='Path to input PDF')
    parser.add_argument('--pages-json', type=Path, required=True, help='JSON file with page numbers from step 1')
    parser.add_argument('--config', type=Path, default=Path('config.json'), help='Config file')
    parser.add_argument('--output', type=Path, help='Output directory for images')
    
    args = parser.parse_args()
    
    # Load config
    with open(args.config, 'r') as f:
        config = json.load(f)
    
    # Load page numbers
    with open(args.pages_json, 'r') as f:
        pages_data = json.load(f)
        page_numbers = pages_data['exercise_pages']
    
    # Determine output directory
    if args.output:
        output_dir = args.output
    else:
        base_output = Path(config['output']['base_folder']) / args.pdf.stem
        output_dir = base_output / config['output']['page_images_folder']
    
    # Convert pages
    converter = PageConverter(config)
    image_files = converter.convert_pages(args.pdf, page_numbers, output_dir)
    
    # Save metadata
    converter.save_metadata(args.pdf, page_numbers, image_files, output_dir)
    
    print(f"\n✓ Converted {len(image_files)} pages to images")
    print(f"  Output directory: {output_dir}")


if __name__ == "__main__":
    main()
