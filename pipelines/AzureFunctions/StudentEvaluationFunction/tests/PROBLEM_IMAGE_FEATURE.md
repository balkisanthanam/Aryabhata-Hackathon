# Problem as Image Feature

## Overview

The Azure Function now supports receiving the **problem statement as an image** in addition to text. This enhancement enables evaluation of problems containing:
- Diagrams and figures (Physics, Geometry)
- Chemical structures and equations (Chemistry)
- Complex mathematical notation
- Graphs and charts
- Circuit diagrams
- Any visual content difficult to express in text

## API Changes

### New Request Parameters

The `/api/evaluate` endpoint now accepts:

```json
{
  "image_bytes": "base64_student_answer",
  "problem": "Text description (OPTIONAL if problem_image_bytes provided)",
  "problem_image_bytes": "base64_problem_image (OPTIONAL if problem provided)",
  "class": "11",
  "subject": "Physics",
  "reference_answer": "Expected answer",
  "pdf_blob_url": "https://..." (optional)
}
```

### Supported Combinations

| Problem Text | Problem Image | Valid? | Use Case |
|-------------|---------------|--------|----------|
| ✓ | ✗ | ✅ Yes | Simple text-based problems |
| ✗ | ✓ | ✅ Yes | Problems with complex diagrams |
| ✓ | ✓ | ✅ Yes | Diagram + explanatory text |
| ✗ | ✗ | ❌ No | At least one required |

## Usage Examples

### Example 1: Problem as Text Only (Current Method)

```python
payload = {
    "image_bytes": student_answer_base64,
    "problem": "Calculate the force on a 5kg object accelerating at 2 m/s²",
    "class": "9",
    "subject": "Physics",
    "reference_answer": "10 N",
    "pdf_blob_url": "https://..."
}
```

### Example 2: Problem as Image Only

```python
payload = {
    "image_bytes": student_answer_base64,
    "problem_image_bytes": problem_image_base64,
    "class": "11",
    "subject": "Physics",
    "reference_answer": "934 J",
    "pdf_blob_url": "https://..."
}
```

### Example 3: Both Text and Image

```python
payload = {
    "image_bytes": student_answer_base64,
    "problem": "The circuit shown in the diagram has three resistors...",
    "problem_image_bytes": circuit_diagram_base64,
    "class": "12",
    "subject": "Physics",
    "reference_answer": "5.2 Ω",
    "pdf_blob_url": "https://..."
}
```

## Testing

### Test Script: `test_with_problem_image.py`

New dedicated test script for the multimodal capability:

```powershell
# Test with problem as text
python tests\test_with_problem_image.py

# Test with custom images
python tests\test_with_problem_image.py student_answer.jpg problem_diagram.jpg
```

### Using curl

Create payload with problem image:

```powershell
# Use the updated create_curl_payload.py (needs enhancement)
python create_curl_payload.py student.jpg pdf_url problem_image.jpg
```

## Prompt Optimization

The evaluation prompt has been optimized for Gemini's multimodal understanding:

### Key Enhancements

1. **Clear Image Labeling**: Each image is labeled for Gemini's context
   - `[PROBLEM IMAGE]`
   - `[STUDENT'S ANSWER IMAGE]`
   - `[REFERENCE MATERIAL PDF]`

2. **Multimodal Instructions**: Specific guidance for:
   - Diagram interpretation (Physics diagrams, chemical structures)
   - Handwriting recognition tolerance
   - Mathematical notation in images
   - Graph and chart analysis

3. **Subject-Specific Hints**:
   - Physics: Free body diagrams, vectors, circuits
   - Chemistry: Molecular structures, reaction mechanisms
   - Mathematics: Geometric constructions, coordinate systems

4. **Ordering**: Problem image comes before student answer for better context

## Implementation Details

### Function Flow

```
1. Receive HTTP request
2. Validate: At least problem OR problem_image required
3. Decode student answer image (required)
4. Decode problem image (if provided)
5. Fetch PDF reference (if provided)
6. Fetch prompt template from blob
7. Fill prompt with text values
8. Build content array:
   - Prompt text
   - [PROBLEM IMAGE] + problem image (if provided)
   - [STUDENT'S ANSWER IMAGE] + student answer
   - [REFERENCE MATERIAL PDF] + PDF (if provided)
9. Call Gemini 2.5 Pro
10. Return evaluation JSON
```

### Code Changes

**Files Modified:**
- `function_app.py`: 
  - Updated `evaluate_with_gemini()` to accept problem image
  - Updated `evaluate_student_answer()` endpoint logic
  - Added validation for problem text/image requirement
  
- `Feedback\Prompt\Evaluation.txt`:
  - Rewritten for multimodal understanding
  - Added image interpretation instructions
  - Enhanced JSON response structure

**Files Created:**
- `tests\test_with_problem_image.py`: Comprehensive test script
- `tests\PROBLEM_IMAGE_FEATURE.md`: This documentation

## Best Practices

### When to Use Problem as Image

✅ **Use image when:**
- Problem contains diagrams, figures, or graphs
- Complex mathematical notation (matrices, integrals, special symbols)
- Chemical structures or reaction mechanisms
- Circuit diagrams or engineering drawings
- Geometric constructions
- Any visual element that adds context

✅ **Use text when:**
- Simple word problems
- Straightforward equations
- Problems without visual components

✅ **Use both when:**
- Diagram needs textual explanation
- Figure references specific points discussed in text
- Additional context helps interpret the diagram

### Image Quality Guidelines

- **Resolution**: Minimum 800x600, recommended 1200x900 or higher
- **Format**: JPEG or PNG (JPEG recommended for photos)
- **Clarity**: Ensure text in diagram is readable
- **Lighting**: Avoid shadows, glare, or poor lighting
- **Cropping**: Crop to relevant problem area only
- **File Size**: Keep under 5MB for faster processing

## Error Handling

### Common Errors

| Error Message | Cause | Solution |
|--------------|-------|----------|
| `Either 'problem' (text) or 'problem_image_bytes' must be provided` | Neither problem text nor image provided | Provide at least one |
| `Error decoding base64 image` | Invalid base64 encoding | Verify image encoding |
| `Image file not found` | Invalid file path | Check file path exists |

## Future Enhancements

Potential improvements:
- [ ] Support multiple problem images (multi-part questions)
- [ ] OCR fallback for problem image text extraction
- [ ] Automatic image quality assessment
- [ ] Support for problem image URLs (like PDF URLs)
- [ ] Diagram annotation in feedback

## Deployment

### Redeploy to Azure

After making these changes:

```powershell
cd C:\Bala\Coding\AryaBhatta\AzureFunctions\StudentEvaluationFunction
func azure functionapp publish <YOUR_FUNCTION_APP>
```

### Verify Deployment

```powershell
# Test with problem as text
python tests\test_prod.py student.jpg pdf_url problem.txt

# Test with problem as image
python tests\test_with_problem_image.py student.jpg problem.jpg
```

## Security Considerations

- Problem images are treated the same as student answer images
- Base64 encoding in transit
- No persistent storage of images
- Gemini API handles image data securely
- Same authentication (function key) applies

## Performance Impact

- **Latency**: +1-2 seconds per problem image (additional encoding/processing)
- **Bandwidth**: Larger payload size (typical problem image: 200KB-1MB base64)
- **Gemini API**: Multimodal requests may have slightly longer processing time
- **Recommendation**: Use image only when necessary for visual context

## Cost Impact

- Gemini API charges may differ for multimodal requests
- Monitor usage if heavily using problem images
- Compression recommended for problem images before encoding

## Support

For issues or questions:
1. Check error logs: `az functionapp log tail --name <YOUR_FUNCTION_APP> --resource-group rg-student-evaluation`
2. Verify prompt template: Check `feedback` blob container for `Evaluation.txt`
3. Test locally first: `func start` in StudentEvaluationFunction directory
