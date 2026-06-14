"""
Test script for deployed Azure Function (Production)
"""
import json
import os
from datetime import datetime

import requests

# =============================================================================
# CONFIGURATION - Your deployed function URL (with code parameter)
# =============================================================================
FUNCTION_URL = os.getenv("ONDEMAND_EXTRACTION_FUNCTION_URL", "<FUNCTION_URL>")
FUNCTION_KEY = os.getenv("ONDEMAND_EXTRACTION_FUNCTION_KEY", "<FUNCTION_KEY>")

# Test data
test_payload = {
    "pdf_blob_url": os.getenv("TEST_PDF_BLOB_URL", "<PDF_BLOB_URL>"),
    "exercise_name": "EXERCISES",
    "problem_number": "5.17"
}

if FUNCTION_URL == "<FUNCTION_URL>" or FUNCTION_KEY == "<FUNCTION_KEY>":
    raise SystemExit("Set ONDEMAND_EXTRACTION_FUNCTION_URL and ONDEMAND_EXTRACTION_FUNCTION_KEY before running this script.")

if test_payload["pdf_blob_url"] == "<PDF_BLOB_URL>":
    raise SystemExit("Set TEST_PDF_BLOB_URL before running this script.")

print("=" * 70)
print("PRODUCTION TEST: OnDemand Image Extraction")
print("=" * 70)
print(f"\nFunction URL: {FUNCTION_URL}")
print(f"Request payload:")
print(json.dumps(test_payload, indent=2))
print("\nSending request...")

try:
    response = requests.post(
        FUNCTION_URL,
        json=test_payload,
        headers={"Content-Type": "application/json"},
        params={"code": FUNCTION_KEY},  # Function key for authentication
        timeout=200  # 3+ minutes for Gemini Pro
    )
    
    print(f"\n✓ Response Status: {response.status_code}")
    print(f"✓ Content-Type: {response.headers.get('content-type')}")
    print(f"✓ Content-Length: {response.headers.get('content-length')} bytes")
    
    if response.status_code == 200:
        # Save the image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"prod_test_problem_{test_payload['problem_number']}_{timestamp}.png"
        
        with open(output_filename, "wb") as f:
            f.write(response.content)
        
        print(f"\n✓ SUCCESS!")
        print(f"Image saved to: {output_filename}")
        print(f"Image size: {len(response.content):,} bytes")
        
    else:
        print(f"\n✗ ERROR!")
        try:
            error_data = response.json()
            print(json.dumps(error_data, indent=2))
        except:
            print(response.text)

except requests.exceptions.Timeout:
    print("\n✗ TIMEOUT ERROR")
    print("Request took longer than 200 seconds")
except Exception as e:
    print(f"\n✗ ERROR: {str(e)}")

print("\n" + "=" * 70)
print("Test complete")
print("=" * 70)
