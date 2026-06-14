"""
Local test script for OnDemand Image Extraction Azure Function
"""
import json
import os
from datetime import datetime
import io

import requests
from PIL import Image

# Local function URL
FUNCTION_URL = "http://localhost:7071/api/extract_image"
TEST_PDF_BLOB_URL = os.getenv("TEST_PDF_BLOB_URL", "<PDF_BLOB_URL>")

# Test data
test_payload = {
    "pdf_blob_url": TEST_PDF_BLOB_URL,
    "exercise_name": "EXERCISES",
    "problem_number": "11.8"
}

def test_extraction():
    """Test the image extraction endpoint"""
    if TEST_PDF_BLOB_URL == "<PDF_BLOB_URL>":
        raise SystemExit("Set TEST_PDF_BLOB_URL before running this script.")

    print("=" * 60)
    print("Testing OnDemand Image Extraction Function")
    print("=" * 60)
    print(f"\nRequest URL: {FUNCTION_URL}")
    print(f"Payload: {json.dumps(test_payload, indent=2)}")
    print("\nSending request...")
    
    try:
        response = requests.post(
            FUNCTION_URL,
            json=test_payload,
            timeout=200  # 200 second timeout (3+ minutes for Gemini Pro)
        )
        
        print(f"\nResponse Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            # Save the image
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"test_output_problem_{test_payload['problem_number']}_{timestamp}.png"
            
            with open(output_filename, "wb") as f:
                f.write(response.content)
            
            print(f"\n✓ SUCCESS!")
            print(f"Image saved to: {output_filename}")
            print(f"Image size: {len(response.content):,} bytes")
            
            # Display the image on screen
            try:
                img = Image.open(io.BytesIO(response.content))
                print(f"Image dimensions: {img.width} x {img.height} pixels")
                print(f"Image mode: {img.mode}")
                print("\nDisplaying image... (close the image window to continue)")
                img.show()
            except Exception as e:
                print(f"\nWarning: Could not display image: {str(e)}")
                print("Image was saved successfully though!")
        else:
            # Print error response
            print(f"\n✗ ERROR!")
            try:
                error_data = response.json()
                print(f"Error details: {json.dumps(error_data, indent=2)}")
            except:
                print(f"Response text: {response.text}")
    
    except requests.exceptions.ConnectionError:
        print("\n✗ CONNECTION ERROR!")
        print("Make sure the Azure Function is running locally.")
        print("Run: func start")
    except requests.exceptions.Timeout:
        print("\n✗ TIMEOUT ERROR!")
        print("Request took longer than 60 seconds.")
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR!")
        print(f"Error: {str(e)}")

def test_missing_fields():
    """Test error handling for missing required fields"""
    print("\n" + "=" * 60)
    print("Testing Error Handling - Missing Fields")
    print("=" * 60)
    
    invalid_payload = {
        "pdf_blob_url": TEST_PDF_BLOB_URL
        # Missing exercise_name and problem_number
    }
    
    print(f"Payload: {json.dumps(invalid_payload, indent=2)}")
    
    try:
        response = requests.post(FUNCTION_URL, json=invalid_payload, timeout=10)
        print(f"\nResponse Status Code: {response.status_code}")
        
        if response.status_code == 400:
            print("✓ Correctly returned 400 Bad Request")
            print(f"Error message: {response.json()}")
        else:
            print(f"Unexpected status code: {response.status_code}")
    
    except Exception as e:
        print(f"Error: {str(e)}")

def test_invalid_pdf():
    """Test error handling for invalid PDF URL"""
    print("\n" + "=" * 60)
    print("Testing Error Handling - Invalid PDF URL")
    print("=" * 60)
    
    invalid_payload = {
        "pdf_blob_url": "https://invalid-url.com/nonexistent.pdf",
        "exercise_name": "Exercise 1.1",
        "problem_number": "1"
    }
    
    print(f"Payload: {json.dumps(invalid_payload, indent=2)}")
    
    try:
        response = requests.post(FUNCTION_URL, json=invalid_payload, timeout=30)
        print(f"\nResponse Status Code: {response.status_code}")
        
        if response.status_code == 500:
            print("✓ Correctly returned 500 Internal Server Error")
            print(f"Error message: {response.json()}")
        else:
            print(f"Response: {response.json() if response.headers.get('content-type') == 'application/json' else response.text}")
    
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    print("\n" + "🚀 " * 20)
    print("LOCAL TESTING SCRIPT")
    print("🚀 " * 20)
    
    # Run tests
    test_extraction()
    
    # Optional: uncomment to test error handling
    # test_missing_fields()
    # test_invalid_pdf()
    
    print("\n" + "=" * 60)
    print("Testing Complete!")
    print("=" * 60 + "\n")
