# Stage 2: Solver Engine - Multi-Step Pipeline

Generates **pedagogical, step-by-step tutorial solutions** for textbook exercises using Gemini 3.

## Architecture Overview

```
MultiStep/
├── config.py           # Configuration management (API keys, models, settings)
├── gemini_client.py    # Modular Gemini API client (caching, batch, multimodal)
├── solver_engine.py    # Stage 2 implementation (solution generation)
├── main.py             # Entry point (CLI + programmatic)
├── tutor_prompt.md     # Parameterized prompt template
├── requirements.txt    # Dependencies
├── run_test.bat        # Quick test script
├── Input/              # Input PDF files
│   └── keph205.pdf     # Sample Physics chapter
└── Output/             # Generated solutions (JSON + images)
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set API Key
```bash
# Windows CMD
set GOOGLE_API_KEY=your_api_key_here

# Windows PowerShell
$env:GOOGLE_API_KEY="your_api_key_here"

# Linux/Mac
export GOOGLE_API_KEY=your_api_key_here
```

### 3. Run Test
```bash
# Quick test (uses defaults)
python main.py

# Specific questions
python main.py --questions "12.4,12.7,12.8"

# Different subject
python main.py --pdf "chemistry_ch5.pdf" --subject "Chemistry" --questions "5.1,5.2"
```

## Programmatic Usage

```python
from pathlib import Path
from main import run_stage2_solver

# Basic usage
response = run_stage2_solver(
    pdf_path=Path("Input/keph205.pdf"),
    questions=["12.4", "12.7"],
    subject="Physics",
)

# Access solutions
for solution in response.solutions:
    print(f"Question {solution.question_id}: {solution.final_answer}")
    for step in solution.steps:
        print(f"  Step {step.step_number}: {step.nudge_hint}")
```

## Modular Design

### GeminiClient (gemini_client.py)

A reusable Gemini API wrapper with:

- **Content Caching**: Cache large PDFs to reduce latency/cost on repeated calls
- **Batch Processing**: Process multiple prompts with rate limiting
- **Multimodal Support**: Handle text + image responses (Gemini 3)
- **Parameterized Prompts**: Client provides filled prompts for flexibility

```python
from config import PipelineConfig
from gemini_client import GeminiClient

client = GeminiClient(PipelineConfig.from_env())

# Simple generation
result = client.generate(
    model_config=config.solver_model,
    prompt="Solve this problem...",
    document_path=Path("chapter.pdf"),
    system_instruction="You are a tutor...",
)

# With caching (for multiple queries on same document)
cache = client.cache_document(Path("chapter.pdf"), model_config.model_id)
result = client.generate_with_cache(model_config, prompt, cache)

# Batch processing
results = client.generate_batch(model_config, prompts, document_path)
```

### SolverEngine (solver_engine.py)

Stage 2 specific logic:

- Load and fill prompt templates
- Parse JSON solutions from model output
- Handle interleaved text/image responses
- Save solutions with metadata

```python
from solver_engine import SolverEngine, SolverRequest

engine = SolverEngine()

# Load and customize prompt
prompt = engine.load_prompt_template(Path("tutor_prompt.md"))
filled = engine.fill_prompt(prompt, class_level="11th", board="CBSE", subject="Physics")

# Generate solutions
request = SolverRequest(
    pdf_path=Path("Input/keph205.pdf"),
    questions=["12.4", "12.7"],
    subject="Physics",
)
response = engine.solve(request, filled)
engine.save_response(response)
```

## Configuration

Edit `config.py` or pass custom config:

```python
from config import PipelineConfig, GeminiModelConfig

# Custom model
custom_config = PipelineConfig(
    solver_model=GeminiModelConfig(
        model_id="gemini-2.5-pro-preview-05-06",
        temperature=0.3,
    ),
    batch_size=3,
    output_dir=Path("custom_output/"),
)
```

## Output Format

Solutions are saved as JSON with this structure:

```json
{
  "metadata": {
    "pdf_file": "keph205.pdf",
    "questions_requested": ["12.4", "12.7"],
    "class": "11th",
    "board": "CBSE",
    "subject": "Physics",
    "model": "gemini-2.5-pro-preview-05-06",
    "processing_time_seconds": 45.2,
    "timestamp": "2024-12-07T10:30:00"
  },
  "solutions": [
    {
      "question_id": "12.4",
      "question_text": "A wire of length L is...",
      "steps": [
        {
          "step_number": 1,
          "step_type": "conceptual",
          "nudge_hint": "What principle governs this?",
          "explanation": "We use Hooke's Law...",
          "latex_formula": "F = kx",
          "visual_asset": {
            "required": false,
            "type": "none",
            "data": "",
            "caption": ""
          }
        }
      ],
      "final_answer": "The elongation is 2.5 mm",
      "generated_images": []
    }
  ]
}
```

## Pipeline Integration

This module is designed to integrate with Stages 1 and 3:

```python
# Future full pipeline
from stage1_extraction import extract_questions  # Stage 1
from main import run_stage2_solver              # Stage 2
from stage3_verification import verify_answers   # Stage 3

# Pipeline flow
questions = extract_questions(pdf_path)
solutions = run_stage2_solver(pdf_path, questions)
verified = verify_answers(solutions, answer_key_path)
```

## Caching Strategy

Content caching reduces API costs when:
- Solving multiple questions from the same chapter
- Re-running after errors
- Testing different prompts on same content

```python
# Automatic caching (default)
response = engine.solve(request, prompt, use_cache=True)

# Disable caching
response = engine.solve(request, prompt, use_cache=False)

# Manual cache control
cache = client.cache_document(pdf_path, model_id, ttl_seconds=3600)
# ... make multiple calls ...
client.clear_cache(cache)
```

## Troubleshooting

### API Key Not Found
```
ValueError: GOOGLE_API_KEY environment variable not set
```
→ Set the environment variable before running

### Model Not Available
```
Error: Model gemini-3-pro-image-preview not found
```
→ Check model availability in your region; fallback to `gemini-2.5-pro-preview-05-06`

### Rate Limiting
```
Error: Resource exhausted
```
→ Increase `batch_delay_seconds` in config or reduce batch size

### JSON Parse Errors
```
Warning: Failed to parse JSON response
```
→ Model output wasn't valid JSON; raw text saved in `final_answer` field
