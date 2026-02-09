# Quick Start Guide

## 🚀 Running the Pipeline

### Single PDF Extraction

**Windows (Batch file):**
```batch
run_extraction.bat input\chemistry_textbook.pdf
```

**Command Line:**
```bash
python main_extraction_pipeline.py --input input/chemistry_textbook.pdf
```

**Clean Start (Delete Previous Results):**
```bash
# Use --flush to delete all intermediate results before running
python main_extraction_pipeline.py --input input/chemistry_textbook.pdf --flush

# Or with batch file
run_extraction.bat input\chemistry_textbook.pdf --flush
```

### Batch Processing (Multiple PDFs)

```bash
python main_extraction_pipeline.py --input-folder input/ --output output/batch_run/
```

### Custom Configuration

```bash
python main_extraction_pipeline.py --input sample.pdf --config custom_config.json
```

## 📁 Expected Output Structure

After running the pipeline on `chemistry_ch8.pdf`:

```
output/chemistry_ch8/
├── chemistry_ch8_exercise_pages.json    # Step 1: Detected page numbers
├── bounding_boxes.json                   # Step 3: Question coordinates
├── pipeline_results.json                 # Final summary
├── page_images/                          # Step 2: Full page images
│   ├── page_0045.png
│   ├── page_0046.png
│   └── conversion_metadata.json
└── questions/                            # Step 4: Individual questions
    ├── q_0045_8_1.png
    ├── q_0045_8_2.png
    ├── q_0046_8_3.png
    └── cropping_metadata.json
```

## 🔧 Running Individual Steps

Sometimes you may want to re-run specific steps without starting from scratch:

### Re-run Step 3 & 4 Only (Skip page detection and conversion)

```bash
python main_extraction_pipeline.py --input sample.pdf --skip step1 step2
```

### Clean Start with Flush Option

When you need to delete all previous intermediate results (useful after fixing bugs or changing config):

```bash
# Delete all previous results and start fresh
python main_extraction_pipeline.py --input sample.pdf --flush

# Combine with other options
python main_extraction_pipeline.py --input sample.pdf --output custom_output/ --flush
```

### Run Only Step 1 (Find Exercise Pages)

```bash
python step1_find_exercise_pages.py --pdf input/sample.pdf --config config.json
```

### Run Only Step 4 (Re-crop with Different Padding)

1. Edit `config.json` - change `padding_pixels`
2. Run:
```bash
python step4_crop_questions.py \
  --images-dir output/sample/page_images \
  --boxes-json output/sample/bounding_boxes.json
```

## 🎯 Common Use Cases

### Use Case 1: Extract from NCERT Textbook
```bash
run_extraction.bat input\NCERT_Class12_Chemistry.pdf output\NCERT_extraction
```

### Use Case 2: Process JEE Practice Papers
```bash
python main_extraction_pipeline.py --input-folder input/JEE_papers/ --output output/JEE/
```

### Use Case 3: Extract with AI-Based Page Detection
Edit `config.json`:
```json
"step1_page_detection": {
  "method": "gemini"
}
```
Then run normally.

### Use Case 4: High-Resolution Extraction (for printing)
Edit `config.json`:
```json
"step2_page_conversion": {
  "dpi": 600
}
```

## 📊 Checking Results

### View Summary
```bash
# View pipeline results
python -m json.tool output/chemistry_ch8/pipeline_results.json

# View detected questions
python -m json.tool output/chemistry_ch8/bounding_boxes.json
```

### Verify Question Images
Just open the `output/<pdf_name>/questions/` folder and review the PNG files.

## ⚡ Tips for Best Results

1. **Use AI detection for complex layouts**: Set `"method": "gemini"` in step 1
2. **Adjust DPI based on content**:
   - Math/Chemistry formulas: 300 DPI
   - Diagrams: 400+ DPI
   - Simple text: 200 DPI
3. **Check intermediate results**: Review page images before running step 3
4. **Adjust padding if crops are too tight**: Increase `padding_pixels` in config

## 🐛 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| No pages detected | Check keywords in config or use `"method": "gemini"` |
| Blurry question images | Increase DPI in step 2 config |
| Questions cut off | Increase `padding_pixels` in step 4 config |
| API rate limit errors | Increase `rate_limit_delay` in config |
| Out of memory | Reduce DPI or process fewer pages at once |
| Stale/incorrect results | Run with `--flush` to delete old intermediate files |

## 📖 Next Steps

- Review `README.md` for pipeline architecture
- See `SETUP.md` for detailed installation
- Check `config.json` for all available options
- Modify prompts in `prompts/` folder for better detection
