"""
Generate a JSON payload file for curl testing
"""
import base64
import json
import os
import sys
from pathlib import Path


def read_problem_and_answer(problem_file_path: str) -> tuple:
    """
    Read problem and reference answer from a text file
    
    Expected format:
    ----------------
    Problem:
    <problem text here, can be multiple lines>
    
    Reference Answer:
    <reference answer here, can be multiple lines>
    ----------------
    
    Returns:
        tuple: (problem, reference_answer)
    """
    with open(problem_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by "Reference Answer:" marker
    if "Reference Answer:" in content:
        parts = content.split("Reference Answer:")
        problem_part = parts[0].strip()
        answer_part = parts[1].strip() if len(parts) > 1 else ""
        
        # Remove "Problem:" prefix if it exists
        if problem_part.startswith("Problem:"):
            problem_part = problem_part[8:].strip()
        
        return problem_part, answer_part
    else:
        raise ValueError("Problem file must contain 'Reference Answer:' marker")


def create_payload(image_path: str, pdf_url: str, output_file: str = "payload.json",
                   problem_file: str = None, problem_image: str = None,
                   class_value: str = "10", subject: str = "Mathematics"):
    """
    Create a JSON payload file for testing with curl
    
    Args:
        image_path: Path to student answer image
        pdf_url: URL to PDF on Azure Blob Storage or local file path
        output_file: Output JSON file name
        problem_file: Path to text file containing problem and reference answer (optional)
        problem_image: Path to problem image file (optional)
        class_value: Student's class (default "10")
        subject: Subject name (default "Mathematics")
    """
    
    if not Path(image_path).exists():
        print(f"Error: Image file not found: {image_path}")
        return
    
    # Either problem_file OR problem_image must be provided (or both)
    if not problem_file and not problem_image:
        print("Error: Either problem_file or problem_image must be provided")
        return
    
    if problem_image and not Path(problem_image).exists():
        print(f"Error: Problem image file not found: {problem_image}")
        return
    
    # Encode student answer image to base64
    print(f"Reading student answer image: {image_path}")
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    
    print(f"Student answer image encoded: {len(image_base64)} characters")
    
    # Read problem text and reference answer from file if provided
    problem_text = None
    reference_answer = None
    
    if problem_file and Path(problem_file).exists():
        print(f"Reading problem from: {problem_file}")
        try:
            problem_text, reference_answer = read_problem_and_answer(problem_file)
            print(f"Problem text loaded ({len(problem_text)} chars)")
            print(f"Reference answer loaded ({len(reference_answer)} chars)")
        except ValueError as e:
            print(f"Error reading problem file: {e}")
            return
    elif problem_file:
        print(f"Warning: Problem file not found: {problem_file}")
    
    # Encode problem image if provided
    problem_image_base64 = None
    if problem_image:
        print(f"Reading problem image: {problem_image}")
        with open(problem_image, 'rb') as f:
            problem_image_bytes = f.read()
            problem_image_base64 = base64.b64encode(problem_image_bytes).decode('utf-8')
        print(f"Problem image encoded: {len(problem_image_base64)} characters")
    
    # Build payload
    payload = {
        "image_bytes": image_base64,
        "class": class_value,
        "subject": subject
    }
    
    # Add problem text if available
    if problem_text:
        payload["problem"] = problem_text
    
    # Add problem image if available
    if problem_image_base64:
        payload["problem_image_bytes"] = problem_image_base64
    
    # Add reference answer if available
    if reference_answer:
        payload["reference_answer"] = reference_answer
    
    # Handle PDF - either URL or file path
    if pdf_url.startswith('http://') or pdf_url.startswith('https://'):
        payload["pdf_blob_url"] = pdf_url
        print(f"PDF URL: {pdf_url}")
    else:
        # It's a file path, encode it
        if Path(pdf_url).exists():
            print(f"Encoding PDF file: {pdf_url}")
            with open(pdf_url, 'rb') as f:
                pdf_bytes = f.read()
                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
            payload["pdf_bytes"] = pdf_base64
            print(f"PDF encoded: {len(pdf_base64)} characters")
        else:
            print(f"Warning: PDF file not found: {pdf_url}")
            print("Continuing without PDF...")
    
    # Save to file
    with open(output_file, 'w') as f:
        json.dump(payload, f)
    
    print(f"\nPayload saved to: {output_file}")
    print(f"File size: {Path(output_file).stat().st_size / 1024:.2f} KB")
    print("\nYou can now use this file with curl:")
    print(f'  curl -X POST "<FUNCTION_URL>?code=<FUNCTION_KEY>" \\')
    print(f'       -H "Content-Type: application/json" \\')
    print(f'       -d @{output_file}')


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ['-h', '--help', 'help']:
        print("Usage: python create_curl_payload.py <image_path> [pdf_path_or_url] [problem_file] [problem_image] [output_file]")
        print("\nArguments:")
        print("  image_path       : Path to student answer image (required)")
        print("  pdf_path_or_url  : Path to PDF file OR blob URL (optional)")
        print("  problem_file     : Path to problem text file (optional)")
        print("  problem_image    : Path to problem image file (optional)")
        print("  output_file      : Output JSON file name (default: payload.json)")
        print("\nNote: Either problem_file OR problem_image must be provided (or both)")
        print("\nExamples:")
        print("  Text problem only:")
        print("    python create_curl_payload.py student.jpg chapter.pdf problem.txt")
        print("\n  Problem image only:")
        print('    python create_curl_payload.py student.jpg chapter.pdf "" problem.jpg')
        print("\n  Both text and image:")
        print("    python create_curl_payload.py student.jpg chapter.pdf problem.txt problem.jpg")
        print("\n  With custom output file:")
        print("    python create_curl_payload.py student.jpg chapter.pdf problem.txt problem.jpg my_payload.json")
        print("\nProblem file format:")
        print("  Problem:")
        print("  What is the derivative of f(x) = x^2 + 3x?")
        print("  ")
        print("  Reference Answer:")
        print("  f'(x) = 2x + 3")
        sys.exit(0 if len(sys.argv) > 1 else 1)
    
    image_path = sys.argv[1]
    pdf_url = sys.argv[2] if len(sys.argv) > 2 else os.getenv("TEST_PDF_BLOB_URL", "<PDF_BLOB_URL>")
    problem_file = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
    problem_image = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
    output_file = sys.argv[5] if len(sys.argv) > 5 else "payload.json"
    
    create_payload(image_path, pdf_url, output_file, problem_file, problem_image)
