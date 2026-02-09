"""
Debug test script - shows raw Gemini response without extraction
"""
import requests
import json
from datetime import datetime

# Local function URL
FUNCTION_URL = "http://localhost:7071/api/extract_image"

# Test data
test_payload = {
    "pdf_blob_url": "https://<YOUR_STORAGE>.blob.core.windows.net/feedback/11/Maths/kemh108.pdf",
    "exercise_name": "Exercise 8.1",
    "problem_number": "12"
}

print("=" * 70)
print("DEBUG MODE: Testing OnDemand Image Extraction")
print("=" * 70)
print(f"\nRequest:")
print(json.dumps(test_payload, indent=2))
print("\nSending request to function...")
print("(Check the Azure Function terminal for detailed logs)")
print("=" * 70)

try:
    response = requests.post(
        FUNCTION_URL,
        json=test_payload,
        timeout=200  # 200 seconds (3+ minutes) to accommodate Gemini Pro timeout
    )
    
    print(f"\n✓ Response Status: {response.status_code}")
    print(f"✓ Content-Type: {response.headers.get('content-type')}")
    print(f"✓ Content-Length: {response.headers.get('content-length')} bytes")
    
    if response.status_code == 200:
        # Image returned successfully
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"debug_output_{timestamp}.png"
        
        with open(output_filename, "wb") as f:
            f.write(response.content)
        
        print(f"\n✓ Image saved to: {output_filename}")
        print("\n" + "=" * 70)
        print("SUCCESS - Image extracted")
        print("=" * 70)
        print("\nCheck the Azure Function logs to see:")
        print("  1. What Gemini returned as coordinates")
        print("  2. What page/bbox was used for extraction")
        
    elif response.status_code == 422:
        # Gemini response validation failed
        error_data = response.json()
        print(f"\n✗ ERROR: Validation failed")
        print(f"\nGemini's raw response:")
        print(json.dumps(error_data.get('raw_response', {}), indent=2))
        print(f"\nError message: {error_data.get('error')}")
        
    else:
        # Other error
        print(f"\n✗ ERROR: {response.status_code}")
        try:
            error_data = response.json()
            print(json.dumps(error_data, indent=2))
        except:
            print(response.text)
    
except requests.exceptions.ConnectionError:
    print("\n✗ CONNECTION ERROR")
    print("Make sure Azure Function is running: func start")
except requests.exceptions.Timeout:
    print("\n✗ TIMEOUT ERROR")
    print("Request took longer than 200 seconds (3+ minutes)")
except Exception as e:
    print(f"\n✗ ERROR: {str(e)}")

print("\n" + "=" * 70)
print("Debug complete")
print("=" * 70)
