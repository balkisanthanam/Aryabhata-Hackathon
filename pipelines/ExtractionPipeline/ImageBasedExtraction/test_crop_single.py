"""
Test/Debug Script - Quick Bounding Box Cropping

Test different bounding box coordinates on a single image to help refine prompts.
Usage: python test_crop_single.py --image page_0001.png --bbox 100 50 500 400
"""

import argparse
from pathlib import Path
from PIL import Image
import json


def crop_and_display(image_path: Path, bbox: list, padding: int = 10, output_path: Path = None, normalized: bool = True):
    """Crop a single image with given bounding box and optionally save it.
    
    Args:
        image_path: Path to the image file
        bbox: Bounding box as [ymin, xmin, ymax, xmax] in normalized coordinates (0-1000)
        padding: Padding in pixels to add around the bbox
        output_path: Optional custom output path
        normalized: If True, bbox is in normalized 0-1000 scale; if False, bbox is in actual pixels
    """
    
    # Load image
    img = Image.open(image_path)
    width, height = img.size
    
    print(f"Image size: {width}x{height} pixels")
    print(f"Input bbox (normalized 0-1000): {bbox}")
    
    # Extract coordinates - Gemini returns [ymin, xmin, ymax, xmax]
    ymin_norm, xmin_norm, ymax_norm, xmax_norm = bbox
    
    if normalized:
        # Convert from normalized coordinates (0-1000) to actual pixels
        # Formula: pixel = (normalized / 1000) × image_dimension
        ymin_px = int((ymin_norm / 1000) * height)
        xmin_px = int((xmin_norm / 1000) * width)
        ymax_px = int((ymax_norm / 1000) * height)
        xmax_px = int((xmax_norm / 1000) * width)
        
        print(f"Converted to pixels:")
        print(f"  ymin: {ymin_norm}/1000 × {height} = {ymin_px} px")
        print(f"  xmin: {xmin_norm}/1000 × {width} = {xmin_px} px")
        print(f"  ymax: {ymax_norm}/1000 × {height} = {ymax_px} px")
        print(f"  xmax: {xmax_norm}/1000 × {width} = {xmax_px} px")
    else:
        # Already in pixels
        ymin_px = int(ymin_norm)
        xmin_px = int(xmin_norm)
        ymax_px = int(ymax_norm)
        xmax_px = int(xmax_norm)
        print(f"Using bbox as-is (already in pixels)")
    
    # Add padding
    xmin_px = max(0, xmin_px - padding)
    ymin_px = max(0, ymin_px - padding)
    xmax_px = min(width, xmax_px + padding)
    ymax_px = min(height, ymax_px + padding)
    
    print(f"After padding ({padding}px): left={xmin_px}, top={ymin_px}, right={xmax_px}, bottom={ymax_px}")
    print(f"Crop dimensions: {xmax_px-xmin_px}x{ymax_px-ymin_px} pixels")
    
    # Crop using PIL format: (left, upper, right, lower) which is (x1, y1, x2, y2)
    # Note: PIL uses (x, y) coordinate system where x=horizontal, y=vertical
    cropped = img.crop((xmin_px, ymin_px, xmax_px, ymax_px))
    
    # Save or display
    if output_path:
        cropped.save(output_path)
        print(f"\n✓ Saved cropped image to: {output_path}")
    else:
        # Auto-generate output name
        output_path = image_path.parent / f"{image_path.stem}_cropped.png"
        cropped.save(output_path)
        print(f"\n✓ Saved cropped image to: {output_path}")
    
    # Show info for verification
    print(f"\nTo verify, open the cropped image and check if:")
    print("  - Question number is included")
    print("  - All text is visible (not cut off)")
    print("  - Figures/diagrams are complete")
    print("  - Not too much extra whitespace")
    
    return cropped


def main():
    parser = argparse.ArgumentParser(
        description='Test bounding box cropping on a single image',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with coordinates
  python test_crop_single.py --image output/sample/page_images/page_0037.png --bbox 100 50 800 400
  
  # With custom padding
  python test_crop_single.py --image page_0037.png --bbox 100 50 800 400 --padding 20
  
  # Load bbox from JSON (from step 3 output)
  python test_crop_single.py --image page_0037.png --json output/sample/bounding_boxes.json --question-index 0
  
  # Save to custom location
  python test_crop_single.py --image page_0037.png --bbox 100 50 800 400 --output test_crop.png
        """
    )
    
    parser.add_argument('--image', type=Path, required=True, help='Path to page image')
    
    parser.add_argument(
        '--bbox',
        type=float,
        nargs=4,
        metavar=('YMIN', 'XMIN', 'YMAX', 'XMAX'),
        help='Bounding box coordinates: ymin xmin ymax xmax (in normalized 0-1000 scale by default)'
    )
    
    parser.add_argument(
        '--pixels',
        action='store_true',
        help='Treat bbox as actual pixels instead of normalized 0-1000 coordinates'
    )
    
    parser.add_argument(
        '--json',
        type=Path,
        help='Load bbox from bounding_boxes.json file (from step 3)'
    )
    
    parser.add_argument(
        '--question-index',
        type=int,
        default=0,
        help='Question index to use from JSON file (default: 0)'
    )
    
    parser.add_argument(
        '--padding',
        type=int,
        default=10,
        help='Padding pixels around bbox (default: 10)'
    )
    
    parser.add_argument(
        '--output',
        type=Path,
        help='Output path for cropped image (default: auto-generated)'
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.image.exists():
        print(f"Error: Image file not found: {args.image}")
        return 1
    
    # Get bounding box
    if args.bbox:
        bbox = args.bbox
        print(f"Using provided bbox: {bbox}")
    elif args.json:
        if not args.json.exists():
            print(f"Error: JSON file not found: {args.json}")
            return 1
        
        with open(args.json, 'r') as f:
            data = json.load(f)
            questions = data.get('questions', [])
            
            if not questions:
                print("Error: No questions found in JSON file")
                return 1
            
            if args.question_index >= len(questions):
                print(f"Error: Question index {args.question_index} out of range (0-{len(questions)-1})")
                return 1
            
            question = questions[args.question_index]
            bbox = question['bbox']
            print(f"Loaded question #{args.question_index}: {question.get('question_number', 'N/A')}")
            print(f"  Source: {question.get('source_image', 'N/A')}")
            print(f"  bbox: {bbox}")
    else:
        print("Error: Must provide either --bbox or --json")
        parser.print_help()
        return 1
    
    # Crop and display
    normalized = not args.pixels  # If --pixels flag is set, bbox is already in pixels
    crop_and_display(args.image, bbox, args.padding, args.output, normalized)
    
    return 0


if __name__ == "__main__":
    exit(main())
