"""
Test the deployed Azure Function
"""
import os
from test_helper import test_function_azure
from pathlib import Path
import sys

# Azure Function details
FUNCTION_URL = os.getenv("AZURE_FUNCTION_URL", "<FUNCTION_URL>")
FUNCTION_KEY = os.getenv("AZURE_FUNCTION_KEY", "<FUNCTION_KEY>")

# Default test files (update these values or pass arguments explicitly)
IMAGE_PATH = os.getenv("TEST_IMAGE_PATH", "<IMAGE_PATH>")
PDF_INPUT_DEFAULT = os.getenv("TEST_PDF_PATH_OR_URL", "")
PROBLEM_FILE = os.getenv("TEST_PROBLEM_FILE", "") or None

if __name__ == "__main__":
    print("Testing Azure Function (Production)")
    print("=" * 50)
    print()
    
    # Parse command-line arguments
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help', 'help']:
        print("Usage:")
        print("  python test_prod.py [image_path] [pdf_path_or_url] [problem_file]")
        print()
        print("Arguments:")
        print("  image_path       : Path to student answer image (required)")
        print("  pdf_path_or_url  : Path to PDF file OR blob URL (optional)")
        print("  problem_file     : Path to problem text file (optional)")
        print()
        print("Examples:")
        print("  python test_prod.py student.jpg")
        print("  python test_prod.py student.jpg chapter.pdf")
        print("  python test_prod.py student.jpg chapter.pdf problem.txt")
        print('  python test_prod.py student.jpg "<PDF_URL>"')
        print('  python test_prod.py student.jpg "<PDF_URL>" problem.txt')
        sys.exit(0)
    
    # Allow command-line overrides
    image_path = sys.argv[1] if len(sys.argv) > 1 else IMAGE_PATH
    pdf_input = sys.argv[2] if len(sys.argv) > 2 else PDF_INPUT_DEFAULT
    problem_file = sys.argv[3] if len(sys.argv) > 3 else PROBLEM_FILE

    if FUNCTION_URL == "<FUNCTION_URL>" or FUNCTION_KEY == "<FUNCTION_KEY>":
        print("Set AZURE_FUNCTION_URL and AZURE_FUNCTION_KEY before running this script.")
        sys.exit(1)

    if image_path == "<IMAGE_PATH>":
        print("Provide an image path as an argument or set TEST_IMAGE_PATH.")
        sys.exit(1)
    
    # Determine if pdf_input is a URL or file path
    pdf_path = None
    pdf_url = None
    
    if pdf_input:
        if pdf_input.startswith('http://') or pdf_input.startswith('https://'):
            # It's a URL
            pdf_url = pdf_input
        else:
            # It's a file path
            if Path(pdf_input).exists():
                pdf_path = pdf_input
            else:
                print(f"Warning: PDF file not found: {pdf_input}")
                print("Continuing without PDF...")
    
    print(f"Function URL: {FUNCTION_URL}")
    print(f"Image: {image_path}")
    if pdf_path:
        print(f"PDF (file): {pdf_path}")
    elif pdf_url:
        print(f"PDF (URL): {pdf_url}")
    else:
        print("PDF: None")
    print(f"Problem file: {problem_file if problem_file else 'Using default'}")
    print()
    
    test_function_azure(
        image_path=image_path,
        function_url=FUNCTION_URL,
        function_key=FUNCTION_KEY,
        pdf_path=pdf_path,
        pdf_url=pdf_url,
        problem_file=problem_file
    )
    
    print("\nTest complete!")
