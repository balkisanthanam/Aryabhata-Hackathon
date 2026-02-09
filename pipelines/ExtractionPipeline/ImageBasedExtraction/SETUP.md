# Installation & Setup Guide

## Prerequisites

- Python 3.8 or higher
- Gemini API key
- Poppler (for pdf2image on Windows)

## Step 1: Install Python Dependencies

From the `ImageBasedExtraction` folder:

```bash
# Install base dependencies (shared with other pipelines)
pip install -r ../requirements.txt

# Install image-specific dependencies
pip install -r requirements.txt
```

This installs:
- `google-generativeai` - Gemini API
- `PyMuPDF` - PDF processing
- `pdf2image` - High-quality PDF to image conversion
- `Pillow` - Image manipulation

## Step 2: Install Poppler (Windows)

`pdf2image` requires Poppler for PDF rendering:

1. Download Poppler for Windows:
   - https://github.com/oschwartz10612/poppler-windows/releases/
   - Download the latest release (e.g., `Release-XX.XX.X-0.zip`)

2. Extract to a permanent location (e.g., `C:\Program Files\poppler-xx.xx.x\`)

3. Update `config.json`:
   ```json
   "step2_page_conversion": {
     "poppler_path": "C:/Program Files/poppler-xx.xx.x/Library/bin"
   }
   ```

**Alternative**: Use PyMuPDF fallback (already installed, no Poppler needed)
   - Set in `config.json`: `"library": "pymupdf"`

## Step 3: Configure Gemini API Key

Set your Gemini API key as an environment variable:

**Windows (PowerShell):**
```powershell
$env:GEMINI_API_KEY = "your-api-key-here"
```

**Windows (Command Prompt):**
```cmd
set GEMINI_API_KEY=your-api-key-here
```

**Permanent (Windows):**
1. Search "Environment Variables" in Start menu
2. Add new system variable:
   - Name: `GEMINI_API_KEY`
   - Value: `your-api-key-here`

**Linux/Mac:**
```bash
export GEMINI_API_KEY="your-api-key-here"
```

Add to `~/.bashrc` or `~/.zshrc` for persistence.

## Step 4: Configure Pipeline

Edit `config.json` to customize:

### Detection Method
```json
"step1_page_detection": {
  "method": "pattern",  // or "gemini" for AI-based detection
  "keywords": ["Exercise", "Questions", "Problems"]
}
```

### Image Quality
```json
"step2_page_conversion": {
  "dpi": 300,  // Higher = better quality, larger files
  "format": "PNG"
}
```

### Gemini Models
```json
"step1_page_detection": {
  "gemini_model": "gemini-2.0-flash-lite"  // Fast, cheap
},
"step3_bounding_box": {
  "gemini_model": "gemini-2.0-flash-thinking-exp"  // More accurate
}
```

## Step 5: Test Installation

Run a quick test:

```bash
# Test with a sample PDF
python main_extraction_pipeline.py --input path/to/sample.pdf

# Or use the batch file (Windows)
run_extraction.bat path\to\sample.pdf
```

## Troubleshooting

### Error: "pdf2image not available"
- Install: `pip install pdf2image`
- Or use PyMuPDF fallback: set `"library": "pymupdf"` in config

### Error: "Poppler not found"
- Install Poppler (see Step 2)
- Or set `"poppler_path"` in config.json
- Or use PyMuPDF fallback

### Error: "API key not found"
- Set `GEMINI_API_KEY` environment variable
- Restart terminal/IDE after setting

### Low detection accuracy
- Use `"method": "gemini"` for page detection
- Increase DPI: `"dpi": 400` or higher
- Adjust keywords in config

### Images too large
- Reduce DPI: `"dpi": 200`
- Use JPEG: `"format": "JPG", "quality": 85`

## Next Steps

See `README.md` for usage examples and pipeline details.
