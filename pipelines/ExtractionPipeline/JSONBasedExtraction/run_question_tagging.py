"""
JEE Question Tagging Pipeline

This script reads extracted JEE question papers (*_with_images.json) and tags each question
with Topic, SubTopic, and Difficulty using Gemini 2.5 Pro with vision capabilities.

Features:
- Batch processing: Tags multiple questions per API call for efficiency
- Vision support: Sends associated figure images along with question text
- Resumability: Tracks progress and resumes from last tagged question on restart
- Handles missing images gracefully

Usage:
    python run_question_tagging.py

Input:  output/JEEMain/*_with_images.json
Output: output/JEEMain/*_tagged.json
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import google.generativeai as genai

# --- Configuration ---
MODEL_NAME = "gemini-3-pro-preview"  # Use Pro for accuracy
BATCH_SIZE = 5  # Number of questions per API call (adjust based on image count)
HIGH_TIMEOUT_SECONDS = 300  # 5 minutes per batch
 
# Filter settings
SUBJECTS_TO_PROCESS = ["Physics"]  # Add "Chemistry", "Mathematics" to process more
LANGUAGE_FILTER = "english"  # Only process questions in this language

BASE_DIR = Path(__file__).parent
TAGGING_PROMPT_PATH = BASE_DIR / "Prompts" / "JEEMainQuestionPaper_NTA_Tagging.txt"
INPUT_DIR = BASE_DIR / "output" / "JEEMain"
IMAGES_DIR = INPUT_DIR / "images"


def init_model(model_name: str) -> genai.GenerativeModel:
    """Initializes the GenerativeModel with JSON output configuration."""
    try:
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    except KeyError:
        raise EnvironmentError("Error: GOOGLE_API_KEY environment variable not set.")

    generation_config = genai.GenerationConfig(
        response_mime_type="application/json",
    )

    return genai.GenerativeModel(
        model_name=model_name,
        generation_config=generation_config
    )


def clean_json_string(text: str) -> str:
    """Removes markdown code block formatting from a string."""
    start_brace = text.find('{')
    start_bracket = text.find('[')

    if start_brace == -1 and start_bracket == -1:
        return text

    start_pos = min(s for s in [start_brace, start_bracket] if s != -1)

    end_brace = text.rfind('}')
    end_bracket = text.rfind(']')
    end_pos = max(end_brace, end_bracket)

    return text[start_pos : end_pos + 1]


def load_image_as_part(image_path: Path) -> Optional[Dict]:
    """Loads an image file and returns it as a Gemini content part."""
    if not image_path.exists():
        return None
    
    # Determine mime type from extension
    ext = image_path.suffix.lower()
    mime_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    mime_type = mime_map.get(ext, 'image/jpeg')
    
    try:
        image_bytes = image_path.read_bytes()
        return {"mime_type": mime_type, "data": image_bytes}
    except Exception as e:
        print(f"    - Warning: Could not load image {image_path.name}: {e}")
        return None


def extract_question_content(question: Dict, images_dir: Path, language: str = "english") -> Tuple[str, List[Dict], bool]:
    """
    Extracts the text content and images from a question object.
    
    Args:
        question: The question object from JSON
        images_dir: Directory containing extracted images
        language: Language to extract (default: "english")
    
    Returns:
        Tuple of (formatted_text, list_of_image_parts, is_valid)
        is_valid is False if the requested language variant was not found
    """
    text_parts = []
    image_parts = []
    
    q_num = question.get("Question Number", "?")
    q_type = question.get("Question Type", "MCQ")
    
    # Get the specified language version
    question_variants = question.get("Question", [])
    target_variant = None
    for variant in question_variants:
        if variant.get("language", "").lower() == language.lower():
            target_variant = variant
            break
    
    if not target_variant:
        # Language not found - return invalid
        return f"Question {q_num}: [No {language} content available]", [], False
    
    # Build question text
    text_parts.append(f"Question {q_num} ({q_type}):")
    text_parts.append(target_variant.get("Text", "[No text]"))
    
    # Check for question figure
    q_figure = target_variant.get("Figure_File")
    if q_figure:
        img_path = images_dir / q_figure
        img_part = load_image_as_part(img_path)
        if img_part:
            text_parts.append(f"[Figure: {q_figure}]")
            image_parts.append(img_part)
        else:
            text_parts.append(f"[Figure: {q_figure} - NOT FOUND]")
    
    # Add options for MCQs
    options = target_variant.get("Options", [])
    if options:
        text_parts.append("Options:")
        for opt in options:
            opt_id = opt.get("id", "?")
            opt_text = opt.get("Text", "[No text]")
            text_parts.append(f"  ({opt_id}) {opt_text}")
            
            # Check for option figure
            opt_figure = opt.get("Figure_File")
            if opt_figure:
                img_path = images_dir / opt_figure
                img_part = load_image_as_part(img_path)
                if img_part:
                    text_parts.append(f"    [Figure: {opt_figure}]")
                    image_parts.append(img_part)
                else:
                    text_parts.append(f"    [Figure: {opt_figure} - NOT FOUND]")
    
    return "\n".join(text_parts), image_parts, True  # Valid question


def tag_question_batch(
    model: genai.GenerativeModel,
    base_prompt: str,
    questions: List[Dict],
    images_dir: Path
) -> List[Dict]:
    """
    Tags a batch of questions using a single API call.
    
    Args:
        model: The Gemini model instance
        base_prompt: The tagging prompt with syllabus
        questions: List of question objects to tag
        images_dir: Directory containing extracted images
        
    Returns:
        List of tag dictionaries with QuestionNumber, Topic, SubTopic, Difficulty
    """
    # Build the multimodal content parts
    content_parts = [base_prompt, "\n\n--- QUESTIONS TO CLASSIFY ---\n\n"]
    
    for question in questions:
        q_text, q_images, _ = extract_question_content(question, images_dir, LANGUAGE_FILTER)
        content_parts.append(q_text)
        content_parts.extend(q_images)
        content_parts.append("\n---\n")
    
    try:
        print(f"    - Calling Gemini API for {len(questions)} questions...", end="", flush=True)
        response = model.generate_content(
            contents=content_parts,
            request_options={'timeout': HIGH_TIMEOUT_SECONDS}
        )
        print(" Done.")
        
        # Parse the response
        result = json.loads(clean_json_string(response.text))
        
        # Ensure it's a list
        if isinstance(result, dict):
            result = [result]
            
        return result
        
    except Exception as e:
        print(f" ERROR: {e}")
        # Return empty tags for failed batch
        return [
            {
                "QuestionNumber": q.get("Question Number", "?"),
                "Topic": "TAGGING_FAILED",
                "SubTopic": str(e)[:100],
                "Difficulty": "Unknown"
            }
            for q in questions
        ]


def load_progress(progress_path: Path) -> Dict:
    """Loads tagging progress from file."""
    if progress_path.exists():
        return json.loads(progress_path.read_text(encoding="utf-8"))
    return {"tagged_questions": {}}


def save_progress(progress_path: Path, progress: Dict):
    """Saves tagging progress to file."""
    progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def tag_paper(
    model: genai.GenerativeModel,
    base_prompt: str,
    paper_data: Dict,
    images_dir: Path,
    progress_path: Path
) -> Dict:
    """
    Tags all questions in a paper, with resumability support.
    
    Args:
        model: The Gemini model instance
        base_prompt: The tagging prompt with syllabus
        paper_data: The full paper JSON data
        images_dir: Directory containing extracted images
        progress_path: Path to save/load progress
        
    Returns:
        Modified paper_data with tags added to each question
    """
    progress = load_progress(progress_path)
    tagged_questions = progress.get("tagged_questions", {})
    
    total_questions = 0
    tagged_count = len(tagged_questions)
    skipped_count = 0
    
    for subject in SUBJECTS_TO_PROCESS:
        questions = paper_data.get(subject, [])
        if not questions:
            continue
            
        print(f"\n  Processing {subject} ({len(questions)} questions)...")
        
        # Process in batches
        i = 0
        while i < len(questions):
            batch = questions[i:i + BATCH_SIZE]
            batch_q_nums = [str(q.get("Question Number", i+j)) for j, q in enumerate(batch)]
            
            # Check which questions in this batch are already tagged AND have the target language
            untagged_batch = []
            untagged_indices = []
            for j, q in enumerate(batch):
                q_key = f"{subject}_{q.get('Question Number', i+j)}"
                if q_key not in tagged_questions:
                    # Check if question has the target language
                    _, _, is_valid = extract_question_content(q, images_dir, LANGUAGE_FILTER)
                    if is_valid:
                        untagged_batch.append(q)
                        untagged_indices.append(j)
                    else:
                        skipped_count += 1
                        print(f"      Skipping Q{q.get('Question Number', '?')}: No {LANGUAGE_FILTER} version")
            
            if untagged_batch:
                print(f"    Batch {i//BATCH_SIZE + 1}: Questions {batch_q_nums} ({len(untagged_batch)} to tag)")
                
                # Tag the untagged questions
                tags = tag_question_batch(model, base_prompt, untagged_batch, images_dir)
                
                # Match tags back to questions and save progress
                for j, tag in enumerate(tags):
                    if j < len(untagged_batch):
                        orig_idx = untagged_indices[j]
                        q = batch[orig_idx]
                        q_key = f"{subject}_{q.get('Question Number', i+orig_idx)}"
                        
                        # Add tags to the question object
                        q["Topic"] = tag.get("Topic", "Unknown")
                        q["SubTopic"] = tag.get("SubTopic", "Unknown")
                        q["Difficulty"] = tag.get("Difficulty", "Unknown")
                        
                        # Save to progress
                        tagged_questions[q_key] = {
                            "Topic": q["Topic"],
                            "SubTopic": q["SubTopic"],
                            "Difficulty": q["Difficulty"]
                        }
                        tagged_count += 1
                
                # Save progress after each batch
                progress["tagged_questions"] = tagged_questions
                save_progress(progress_path, progress)
                
                # Brief pause between batches to avoid rate limiting
                time.sleep(2)
            else:
                print(f"    Batch {i//BATCH_SIZE + 1}: Questions {batch_q_nums} - Already tagged, skipping.")
                
                # Apply saved tags to questions
                for j, q in enumerate(batch):
                    q_key = f"{subject}_{q.get('Question Number', i+j)}"
                    if q_key in tagged_questions:
                        saved_tag = tagged_questions[q_key]
                        q["Topic"] = saved_tag.get("Topic", "Unknown")
                        q["SubTopic"] = saved_tag.get("SubTopic", "Unknown")
                        q["Difficulty"] = saved_tag.get("Difficulty", "Unknown")
            
            i += BATCH_SIZE
            total_questions += len(batch)
    
    print(f"\n  Total: {total_questions} questions, {tagged_count} newly tagged, {skipped_count} skipped (no {LANGUAGE_FILTER})")
    return paper_data


def main():
    """Main function to run the question tagging pipeline."""
    print("=" * 60)
    print("JEE Question Tagging Pipeline")
    print("=" * 60)
    
    # Initialize model
    print("\nInitializing Gemini model...")
    model = init_model(MODEL_NAME)
    
    # Load tagging prompt
    if not TAGGING_PROMPT_PATH.exists():
        print(f"ERROR: Tagging prompt not found at {TAGGING_PROMPT_PATH}")
        return
    
    base_prompt = TAGGING_PROMPT_PATH.read_text(encoding="utf-8")
    print(f"Loaded tagging prompt ({len(base_prompt)} chars)")
    
    # Find input files
    if not INPUT_DIR.exists():
        print(f"ERROR: Input directory not found: {INPUT_DIR}")
        return
    
    input_files = list(INPUT_DIR.glob("*_with_images.json"))
    if not input_files:
        print(f"No *_with_images.json files found in {INPUT_DIR}")
        return
    
    print(f"\nFound {len(input_files)} paper(s) to tag.\n")
    
    for input_path in input_files:
        file_stem = input_path.stem.replace("_with_images", "")
        output_path = INPUT_DIR / f"{file_stem}_tagged.json"
        progress_path = INPUT_DIR / f"{file_stem}_tagging_progress.json"
        
        print("-" * 60)
        print(f"Processing: {input_path.name}")
        
        # Check if already fully tagged
        if output_path.exists():
            print(f"  Output file {output_path.name} already exists. Skipping.")
            continue
        
        start_time = time.monotonic()
        
        try:
            # Load the paper data
            paper_data = json.loads(input_path.read_text(encoding="utf-8"))
            
            # Tag all questions
            tagged_data = tag_paper(
                model=model,
                base_prompt=base_prompt,
                paper_data=paper_data,
                images_dir=IMAGES_DIR,
                progress_path=progress_path
            )
            
            # Save the tagged output
            output_path.write_text(
                json.dumps(tagged_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            print(f"\n  Saved tagged output to: {output_path.name}")
            
            # Clean up progress file on successful completion
            if progress_path.exists():
                progress_path.unlink()
                print(f"  Cleaned up progress file.")
                
        except Exception as e:
            print(f"\n  ERROR: Failed to process {input_path.name}: {e}")
            print("  Progress saved. Run again to resume.")
            
        finally:
            elapsed = time.monotonic() - start_time
            print(f"  Time: {elapsed:.1f} seconds")
        
        # Pause between papers
        print("\n  Pausing 10 seconds before next paper...")
        time.sleep(10)
    
    print("\n" + "=" * 60)
    print("Tagging pipeline complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
