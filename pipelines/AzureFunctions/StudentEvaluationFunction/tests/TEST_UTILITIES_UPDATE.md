# Test Utilities Update - Problem Image Support

## Overview
All test utilities have been updated to support the new problem image feature, maintaining consistency with the enhanced Azure Function API.

## Updated Files

### 1. test_helper.py ✅
**Main test utility for local and Azure testing**

#### Changes to `test_function_local()`:
- Added `problem_image` parameter (optional)
- Updated validation: Either `problem_file` OR `problem_image` must be provided (or both)
- Added problem image file validation and base64 encoding
- Updated payload construction to conditionally include:
  - `"problem"` field (only if problem text exists)
  - `"problem_image_bytes"` field (only if problem image exists)
  - `"reference_answer"` field (only if available from problem file)

#### Changes to `test_function_azure()`:
- Added `problem_image` parameter (optional)
- Same validation and payload logic as local version
- Consistent behavior between local and production testing

#### Command-Line Usage:
```bash
# Text problem only
python test_helper.py student_answer.jpg chapter.pdf problem.txt

# Problem image only
python test_helper.py student_answer.jpg chapter.pdf "" problem_image.jpg

# Both text and image
python test_helper.py student_answer.jpg chapter.pdf problem.txt problem_image.jpg
```

### 2. create_curl_payload.py ✅
**Payload generator for curl testing**

#### Changes:
- Added `problem_image` parameter to `create_payload()` function
- Added validation: Either `problem_file` OR `problem_image` required (or both)
- Added problem image validation and base64 encoding
- Updated payload construction to match Azure Function API:
  - Conditionally adds `"problem"` field
  - Conditionally adds `"problem_image_bytes"` field
  - Conditionally adds `"reference_answer"` field

#### Command-Line Usage:
```bash
# Text problem only
python create_curl_payload.py student.jpg chapter.pdf problem.txt

# Problem image only
python create_curl_payload.py student.jpg chapter.pdf "" problem.jpg

# Both text and image
python create_curl_payload.py student.jpg chapter.pdf problem.txt problem.jpg

# With custom output file
python create_curl_payload.py student.jpg chapter.pdf problem.txt problem.jpg my_payload.json
```

### 3. test_with_problem_image.py ✅
**Already created with full problem image support**

This dedicated test script was created specifically for testing the multimodal feature with three scenarios:
- Text only
- Image only  
- Both text and image

## API Consistency

All test utilities now match the Azure Function API exactly:

### Request Payload Structure:
```json
{
  "image_bytes": "base64_string",
  "class": "10",
  "subject": "Mathematics",
  "problem": "optional_text_problem",
  "problem_image_bytes": "optional_base64_image",
  "reference_answer": "optional_reference",
  "pdf_blob_url": "optional_blob_url",
  "pdf_bytes": "optional_base64_pdf"
}
```

### Validation Rules:
- ✅ Student answer image (`image_bytes`) is always required
- ✅ Either `problem` (text) OR `problem_image_bytes` must be provided
- ✅ Both `problem` and `problem_image_bytes` can be provided together
- ✅ Reference answer is optional (defaults to "Not provided")
- ✅ PDF can be provided as URL or base64-encoded bytes

## Testing Workflow

### Local Testing (Recommended First)
1. Start local function:
   ```bash
   cd C:\Bala\Coding\AryaBhatta\AzureFunctions\StudentEvaluationFunction
   conda activate AzureFunc
   func start
   ```

2. Test with problem text:
   ```bash
   cd tests
   python test_helper.py student.jpg chapter.pdf problem.txt
   ```

3. Test with problem image:
   ```bash
   python test_helper.py student.jpg chapter.pdf "" problem_image.jpg
   ```

4. Test with both:
   ```bash
   python test_helper.py student.jpg chapter.pdf problem.txt problem_image.jpg
   ```

### Production Testing (After Deployment)
Same commands work for production testing - the utilities automatically detect if the function is running locally or on Azure.

## Backward Compatibility

✅ **Fully backward compatible** - Existing clients using only text problems continue to work without any changes.

Old usage still works:
```bash
python test_helper.py student.jpg chapter.pdf problem.txt
```

## Next Steps

1. **Local Testing** - Test all three problem input combinations locally
2. **Upload Updated Prompt** - Deploy new Evaluation.txt to blob storage
3. **Deploy Function** - Publish enhanced function to Azure
4. **Production Testing** - Verify in production environment

## Related Documentation

- `PROBLEM_IMAGE_FEATURE.md` - Complete feature documentation
- `ENHANCEMENT_SUMMARY.md` - Summary of all changes
- `DEPLOYMENT_CHECKLIST.md` - Deployment guide
