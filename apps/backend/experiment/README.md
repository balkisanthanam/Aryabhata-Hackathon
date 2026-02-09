# Gemini Validation Tool

This tool helps iterate on the `Student_HW_Split.md` prompt using `gemini-3-pro-preview` via Vertex AI.

## Prerequisites

1. **Environment**: Ensure you are in the `Karma` environment (or one with `google-genai` installed).
2. **Authentication**: This tool uses Vertex AI and requires Google Cloud authentication.

### Login Step

Run the following command to authenticate with the Google Cloud project (`animated-rope-453904-j7`):

```bash
gcloud auth application-default login
```

Follow the browser prompts to sign in.

## Usage

Use the `validate_split.py` script to process folders of student homework images.
The tool iterates through **sub-folders** in the input directory.

### Command Syntax

```bash
python validate_split.py --input <path_to_input_folder> --output <path_to_output_folder>
```

### Example

```bash
python validate_split.py --input input/HandWritten --output output/HandWritten
```

## Features

- **Batch Processing**: Automatically iterates through all sub-folders in `input`.
- **Skip Logic**: Skips any sub-folder if its corresponding `output` folder already exists. Delete the output folder to re-process.
- **Rate Limiting**: Includes retry logic for `429` errors and a 10-second delay between folders.
- **Stitching**: Stitches multi-part solutions (e.g., `Q13_part1`, `Q13_part2`) vertically.

---

# Experiment Viewer

A local web tool to visualize comparison between output versions.

## Setup

Install Flask:

```bash
pip install flask
```

## Running

```bash
python experiment_viewer.py
```

Open **<http://localhost:5001>** in your browser.

## Features

- **Dropdown**: Select any subfolder input.
- **Gallery**: View original input images.
- **Comparison**: Side-by-side view of cropped results. Select any two versions (V1, V2...) to compare.
