"""
Helper script to test the Azure Function with actual files
This script reads an image and PDF from disk and creates a proper test request
"""

import base64
import json
import requests
import sys
from pathlib import Path


def encode_file_to_base64(file_path: str) -> str:
    """
    Read a file and encode it to base64 string
    """
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
        base64_encoded = base64.b64encode(file_bytes).decode('utf-8')
        return base64_encoded


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


def read_problem_and_answer_simple(problem_file_path: str) -> tuple:
    """
    Simple format: Read problem and reference answer from a text file
    
    Expected format - last line is the answer, everything else is the problem:
    ----------------
    Problem line 1
    Problem line 2
    ...
    Reference Answer (last line)
    ----------------
    
    Returns:
        tuple: (problem, reference_answer)
    """
    with open(problem_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if len(lines) < 2:
        raise ValueError("Problem file must have at least 2 lines (problem and answer)")
    
    # Last line is the answer, everything else is the problem
    problem = ''.join(lines[:-1]).strip()
    reference_answer = lines[-1].strip()
    
    return problem, reference_answer


def test_function_local(image_path: str, pdf_path: str = None, pdf_url: str = None,
                        problem_file: str = None, problem_image: str = None,
                        class_value: str = "10", subject: str = "Mathematics"):
    """
    Test the Azure Function running locally
    
    Args:
        image_path: Path to student's answer image
        pdf_path: Path to chapter PDF (optional if pdf_url provided)
        pdf_url: Azure Blob URL of chapter PDF (optional if pdf_path provided)
        problem_file: Path to text file containing problem and reference answer (optional)
        problem_image: Path to problem image (optional)
        class_value: Student's class (default "10")
        subject: Subject name (default "Mathematics")
        
    Note: Either problem_file OR problem_image (or both) must be provided
    """
    
    # Validate inputs
    if not Path(image_path).exists():
        print(f"Error: Image file not found: {image_path}")
        return
    
    # Validate that at least problem text OR problem image is provided
    if not problem_file and not problem_image:
        print("Error: Either problem_file or problem_image must be provided")
        return
    
    # Only check if pdf_path is provided AND it's not a URL
    if pdf_path:
        # Check if it's a URL or a file path
        if not (pdf_path.startswith('http://') or pdf_path.startswith('https://')):
            # It's a file path, so check if it exists
            if not Path(pdf_path).exists():
                print(f"Error: PDF file not found: {pdf_path}")
                return
        else:
            # It's a URL, treat it as pdf_url instead
            pdf_url = pdf_path
            pdf_path = None
    
    print("Encoding student answer image...")
    image_base64 = encode_file_to_base64(image_path)
    
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
    
    # Encode problem image if provided
    problem_image_base64 = None
    if problem_image:
        if Path(problem_image).exists():
            print(f"Encoding problem image: {problem_image}")
            problem_image_base64 = encode_file_to_base64(problem_image)
            print(f"Problem image encoded ({len(problem_image_base64)} chars)")
        else:
            print(f"Warning: Problem image not found: {problem_image}")
            if not problem_text:
                print("Error: Neither problem text nor problem image available")
                return
    
    # Use defaults if nothing provided (shouldn't happen due to earlier validation)
    if not problem_text and not problem_image_base64:
        print("Using default problem (fallback)...")
        problem_text = "Solve the equation: 2x + 5 = 15. Show all steps."
    
    # Set default reference answer if not provided
    if not reference_answer:
        reference_answer = "Not provided"
        print("No reference answer provided - Gemini will derive it from the problem")
    
    # Prepare payload
    payload = {
        "image_bytes": image_base64,
        "class": class_value,
        "subject": subject,
        "reference_answer": reference_answer
    }
    
    # Add problem text if provided
    if problem_text:
        payload["problem"] = problem_text
    
    # Add problem image if provided
    if problem_image_base64:
        payload["problem_image_bytes"] = problem_image_base64
    
    # Add PDF
    if pdf_path:
        print("Encoding PDF...")
        pdf_base64 = encode_file_to_base64(pdf_path)
        payload["pdf_bytes"] = pdf_base64
    else:
        payload["pdf_blob_url"] = pdf_url
    
    # Save payload to file for reference
    with open("test_request_generated.json", "w") as f:
        # Save without the large base64 strings for readability
        payload_summary = payload.copy()
        if "pdf_bytes" in payload_summary:
            payload_summary["pdf_bytes"] = f"<base64 data: {len(payload['pdf_bytes'])} chars>"
        payload_summary["image_bytes"] = f"<base64 data: {len(payload['image_bytes'])} chars>"
        json.dump(payload_summary, f, indent=2)
    
    print("Payload created. Summary saved to test_request_generated.json")
    
    # Send request to local function
    function_url = "http://localhost:7071/api/evaluate"
    
    print(f"\nSending request to {function_url}...")
    print("Make sure your function is running with: func start")
    
    try:
        response = requests.post(
            function_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=300  # 5 minutes timeout
        )
        
        print(f"\nResponse Status Code: {response.status_code}")
        print("\nResponse Body:")
        
        try:
            response_json = response.json()
            print(json.dumps(response_json, indent=2))
            
            # Save full response
            with open("test_response.json", "w") as f:
                json.dump(response_json, f, indent=2)
            print("\nFull response saved to test_response.json")
            
        except json.JSONDecodeError:
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("\nError: Could not connect to function.")
        print("Make sure the function is running locally with: func start")
    except requests.exceptions.Timeout:
        print("\nError: Request timed out. The function may be processing a large file.")
    except Exception as e:
        print(f"\nError: {str(e)}")


def test_function_azure(image_path: str, function_url: str, function_key: str, 
                        pdf_path: str = None, pdf_url: str = None,
                        problem_file: str = None, problem_image: str = None,
                        class_value: str = "10", subject: str = "Mathematics"):
    """
    Test the Azure Function deployed to Azure
    
    Args:
        image_path: Path to student's answer image
        function_url: Full Azure Function URL
        function_key: Function access key
        pdf_path: Path to chapter PDF (optional if pdf_url provided)
        pdf_url: Azure Blob URL of chapter PDF (optional if pdf_path provided)
        problem_file: Path to text file containing problem and reference answer (optional)
        problem_image: Path to problem image (optional, used instead of or with problem_file)
        class_value: Student's class (default "10")
        subject: Subject name (default "Mathematics")
    """
    
    # Validate inputs
    if not Path(image_path).exists():
        print(f"Error: Image file not found: {image_path}")
        return
    
    # Either problem_file OR problem_image must be provided (or both)
    if not problem_file and not problem_image:
        print("Error: Either problem_file or problem_image must be provided")
        return
    
    # Validate problem image if provided
    if problem_image and not Path(problem_image).exists():
        print(f"Error: Problem image file not found: {problem_image}")
        return
    
    # Encode files
    image_base64 = encode_file_to_base64(image_path)
    
    # Encode problem image if provided
    problem_image_base64 = None
    if problem_image:
        problem_image_base64 = encode_file_to_base64(problem_image)
        print(f"Problem image: {problem_image}")
    
    # Read problem and reference answer from file if provided
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
    
    # Set default reference answer if not provided
    if not reference_answer:
        reference_answer = "Not provided"
        print("No reference answer provided - Gemini will derive it from the problem")
    
    # Build payload
    payload = {
        "image_bytes": image_base64,
        "class": class_value,
        "subject": subject,
        "reference_answer": reference_answer
    }
    
    # Add problem text if available
    if problem_text:
        payload["problem"] = problem_text
    
    # Add problem image if available
    if problem_image_base64:
        payload["problem_image_bytes"] = problem_image_base64
    
    # Handle PDF - check if it's a URL or file path
    if pdf_path:
        if pdf_path.startswith('http://') or pdf_path.startswith('https://'):
            # It's a URL, use blob URL
            payload["pdf_blob_url"] = pdf_path
        else:
            # It's a file path, encode it
            pdf_base64 = encode_file_to_base64(pdf_path)
            payload["pdf_bytes"] = pdf_base64
    elif pdf_url:
        payload["pdf_blob_url"] = pdf_url
    
    # Add function key to URL
    if "?" in function_url:
        request_url = f"{function_url}&code={function_key}"
    else:
        request_url = f"{function_url}?code={function_key}"
    
    print(f"Sending request to Azure Function...")
    
    try:
        response = requests.post(
            request_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=300
        )
        
        print(f"\nResponse Status Code: {response.status_code}")
        response_json = response.json()
        print(json.dumps(response_json, indent=2))
        
        with open("test_response_azure.json", "w") as f:
            json.dump(response_json, f, indent=2)
        
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    
    print("Azure Function Test Helper")
    print("==========================\n")
    
    # Check for --prod flag
    use_production = "--prod" in sys.argv
    if use_production:
        sys.argv.remove("--prod")
    
    # Parse command line arguments
    test_image_path = None
    test_pdf_path = None
    test_problem_file = None
    test_problem_image = None
    test_pdf_url = "https://<YOUR_STORAGE_ACCOUNT>.blob.core.windows.net/feedback/sample-chapter.pdf"
    
    if len(sys.argv) > 1:
        test_image_path = sys.argv[1]
    
    if len(sys.argv) > 2:
        test_pdf_path = sys.argv[2]
    
    if len(sys.argv) > 3:
        test_problem_file = sys.argv[3]
    
    if len(sys.argv) > 4:
        test_problem_image = sys.argv[4]
    
    # Show usage if no image provided
    if not test_image_path or not Path(test_image_path).exists():
        print("Usage:")
        print("  python test_helper.py [--prod] <student_image> [pdf_file] [problem_file] [problem_image]")
        print("\nFlags:")
        print("  --prod    Test against production (Azure). Without this flag, tests locally.")
        print("\nExamples:")
        print("  Local testing (default):")
        print("    python test_helper.py student_answer.jpg chapter.pdf problem.txt")
        print("\n  Production testing:")
        print("    python test_helper.py --prod student_answer.jpg chapter.pdf problem.txt")
        print("\n  Problem image only:")
        print("    python test_helper.py student_answer.jpg chapter.pdf \"\" problem_image.jpg")
        print("\n  Both text and image:")
        print("    python test_helper.py student_answer.jpg chapter.pdf problem.txt problem_image.jpg")
        print("\nProblem file format (problem.txt):")
        print("  Problem:")
        print("  Solve the equation: x^2 + 5x + 6 = 0")
        print("  Show all your work.")
        print("  ")
        print("  Reference Answer:")
        print("  x = -2 or x = -3")
        sys.exit(1)
    
    print(f"Testing: {'PRODUCTION (Azure)' if use_production else 'LOCAL'}")
    print(f"Image: {test_image_path}")
    print(f"PDF: {test_pdf_path if test_pdf_path else test_pdf_url}")
    print(f"Problem file: {test_problem_file if test_problem_file else 'None'}")
    print(f"Problem image: {test_problem_image if test_problem_image else 'None'}")
    print()
    
    if use_production:
        # Production configuration
        FUNCTION_URL = "https://<YOUR_FUNCTION_APP>.azurewebsites.net/api/evaluate"
        FUNCTION_KEY = "<YOUR_FUNCTION_KEY>"
        
        test_function_azure(
            image_path=test_image_path,
            function_url=FUNCTION_URL,
            function_key=FUNCTION_KEY,
            pdf_path=test_pdf_path,
            pdf_url=test_pdf_url if not test_pdf_path else None,
            problem_file=test_problem_file,
            problem_image=test_problem_image
        )
    else:
        test_function_local(
            image_path=test_image_path,
            pdf_path=test_pdf_path,
            pdf_url=test_pdf_url if not test_pdf_path else None,
            problem_file=test_problem_file,
            problem_image=test_problem_image
        )
