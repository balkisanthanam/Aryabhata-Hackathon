# ExtractionPipeline

This folder contains Python scripts for extracting structured data from PDF documents using the Google Generative AI (Gemini) API.

---

## JSON-Based Question Extraction (`JSONBasedExtraction/run_json_extraction.py`)

This script is designed to extract question and answer data from PDF documents (JEE Main question papers, CBSE textbooks, and other educational materials).

### Files

- `run_json_extraction.py` — The main script to run the extraction.
- `Prompts/JEEMainQuestionPaper_NTA.txt` — The prompt instructing the model on how to parse the JEE paper.
- `input/` — **(You must create this folder)** Place the PDF files you want to process here.
- `output/` — The script will create this folder to store the resulting JSON files.

### Setup

1. Python 3.11+ recommended
1. Install deps
   ```powershell
   python -m pip install -r .\ExtractionPipeline\requirements.txt
   ```
1. Set up your API key. The script reads the key from an environment variable.
   ```powershell
   $env:GOOGLE_API_KEY = "YOUR_API_KEY_HERE"
   ```
1. Create an `input` folder inside `ExtractionPipeline` and place your PDF files there.

### Run

```powershell
python .\ExtractionPipeline\JSONBasedExtraction\run_json_extraction.py
```

### Performance Note
1. Total e2e time taken, iteration 1 - 3726.77 seconds (with bugs)
   Config - Gemini 2.5 flash lite for header, flash for PDF and flash lite for image classification as figure.
2. Time taken for image classification as Figures with Gemini 2.5 Flash 182.03 seconds (in batch mode)
3. Time taken for image classification as Figures with Gemini 2.5 Pro 335.06 seconds (batch mode)
4. Time taken for e2e full run flash lite for header, pro for PDF and Pro for image classification - 605.86 
seconds
5. Total time for full PDF by pro in one go: 731.37 seconds
6. 

---

## CBSE Exercise Extraction (`run_extraction.py`)

This script invokes Gemini to extract Q&A JSON from a unit PDF and an answer PDF, typically from GCS, based on a configuration file.

### Setup

```powershell
python -m pip install -r .\ExtractionPipeline\requirements.txt
```

1. Auth to Google Cloud and ensure GCS object access:
	- `gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS`

## Run

```powershell
python .\ExtractionPipeline\run_extraction.py
```

Use a different config:

```powershell
$env:AB_EXTRACTION_CONFIG = "g:\\My Drive\\Karma\\AryaBhatta\\ExtractionPipeline\\my_config.json"; python .\ExtractionPipeline\run_extraction.py
```

Outputs are saved as `output/<input-stem>_<timestamp>.json`.
