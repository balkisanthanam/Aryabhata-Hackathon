# JSON-Based Extraction Evaluation Tool

## Overview

This tool evaluates the output from `run_json_extraction.py` by comparing it against manually verified model outputs. It performs deep structural and content comparison of JSON files and can optionally compare extracted figure images.

## Features

- **Deep JSON Comparison**: Recursively compares all fields in the JSON structure
- **Flexible Matching**: Handles whitespace normalization and case sensitivity options
- **Similarity Scoring**: Calculates similarity percentages for text fields
- **Image Comparison**: Uses perceptual hashing to compare extracted figures
- **Detailed Reports**: Generates both human-readable text reports and machine-readable JSON reports
- **Batch Processing**: Can evaluate multiple test files at once

## Installation

1. Install required dependencies:
```bash
pip install -r evaluate_requirements.txt
```

Note: Image comparison requires `Pillow` and `imagehash`. If these are not installed, the tool will skip image comparison.

## Usage

### Basic Usage

Compare a test run against the model reference:

```bash
python evaluate_extraction.py --test-dir output/JEEMain/backup/Run1 --model-dir output/JEEMain/backup/ModelRun
```

### Using the Batch File (Windows)

For convenience, use the provided batch file:

```batch
run_evaluation.bat output\JEEMain\backup\Run1
```

This will automatically use the default model directory.

### Advanced Options

```bash
# Skip image comparison
python evaluate_extraction.py --test-dir output/JEEMain/backup/Run2 --no-images

# Custom output location
python evaluate_extraction.py --test-dir output/JEEMain/backup/Run3 --output results/my_eval.txt

# Enable case-sensitive comparison
python evaluate_extraction.py --test-dir output/JEEMain/backup/Run1 --case-sensitive

# Strict whitespace matching (don't normalize spaces)
python evaluate_extraction.py --test-dir output/JEEMain/backup/Run1 --strict-whitespace
```

## Command-Line Arguments

| Argument | Description | Required | Default |
|----------|-------------|----------|---------|
| `--test-dir` | Directory containing test run output with *_with_images.json files | Yes | - |
| `--model-dir` | Directory containing model/reference output | No | `output/JEEMain/backup/ModelRun` |
| `--output` | Output path for evaluation report | No | Auto-generated in test-dir |
| `--no-images` | Skip image comparison | No | False |
| `--case-sensitive` | Enable case-sensitive text comparison | No | False |
| `--strict-whitespace` | Do not normalize whitespace in text comparison | No | False |

## Understanding the Output

The tool generates two types of reports:

### 1. Text Report (*.txt)

A human-readable report containing:
- **Summary Statistics**: Total fields, matching fields, differences, etc.
- **Match Percentage**: Overall percentage of matching fields
- **Detailed Differences**: Grouped by type (value mismatches, missing fields, etc.)
- **Image Comparison**: Results of image similarity checks

### 2. JSON Report (*.json)

A machine-readable report for programmatic access containing:
- Metadata (timestamps, file paths)
- Full comparison statistics
- Complete list of all differences with paths
- Image comparison results

## Example Output

```
================================================================================
JSON-BASED EXTRACTION EVALUATION REPORT
================================================================================

Generated: 2025-11-08 10:30:45
Model File: output/JEEMain/backup/ModelRun/Paper_20200509203411_with_images.json
Test File: output/JEEMain/backup/Run1/Paper_20200509203411_with_images.json

--------------------------------------------------------------------------------
JSON COMPARISON SUMMARY
--------------------------------------------------------------------------------

Total Fields Compared: 2547
Matching Fields: 2489
Different Fields: 58
Missing in Test: 0
Extra in Test: 0
Overall Match: 97.72%

--------------------------------------------------------------------------------
IMAGE COMPARISON SUMMARY
--------------------------------------------------------------------------------

Total Images Compared: 45
Matching Images: 43
Different Images: 2
Match Rate: 95.56%
```

## Folder Structure Compatibility

The tool automatically handles both old and new folder structures:

- **Old structure** (ModelRun): Images in the same directory as JSON
- **New structure** (Recent runs): Images in a subdirectory called `images/`

## Troubleshooting

### No matching model file found

Ensure the model directory contains a file with the same base name as your test file. The tool looks for `*_with_images.json` files.

### Image comparison skipped

Install the required libraries:
```bash
pip install Pillow imagehash
```

### High number of differences

Check these common issues:
- Whitespace differences: Use default settings (whitespace normalization is on by default)
- Case differences: Don't use `--case-sensitive` unless needed
- Model extraction changes: Some variation is expected with LLM-based extraction

## Integration with CI/CD

The tool returns exit code 0 on success, making it suitable for automated testing:

```bash
python evaluate_extraction.py --test-dir output/JEEMain/backup/Run1 && echo "Evaluation passed"
```

## Tips

1. **First Run**: Always check the text report first to understand the types of differences
2. **Similarity Threshold**: Text fields with >90% similarity are usually acceptable
3. **Image Comparison**: Perceptual hashing is tolerant to minor compression differences
4. **Batch Evaluation**: Process all runs in a loop for comprehensive testing

## Future Enhancements

Potential improvements:
- HTML report generation with visual diff
- Configurable similarity thresholds
- Statistical analysis across multiple runs
- Image diff visualization
- Auto-acceptance of minor differences
