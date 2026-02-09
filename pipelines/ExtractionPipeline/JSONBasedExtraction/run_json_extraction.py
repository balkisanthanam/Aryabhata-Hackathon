import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import fitz  # PyMuPDF
import google.generativeai as genai

# --- Configuration ---
MODEL_NAME = "gemini-2.5-pro"  # Use the most capable model for the main content extraction.
HEADER_MODEL_NAME = "gemini-2.5-flash-lite" # Use the latest flash model for header extraction.
FIG_CHECK_MODEL_NAME = "gemini-2.5-pro"  # Use the latest flash model for figure classification.
HIGH_TIMEOUT_SECONDS = 900  # 15 minutes, adjust as needed
USE_BATCH_SUBJECT_EXTRACTION = True  # Set to False to extract subjects one by one as a fallback.
SUBJECTS = ["Physics", "Chemistry", "Mathematics"]

BASE_DIR = Path(__file__).parent
PROMPT_PATH_SINGLE = BASE_DIR / "Prompts" / "JEEMainQuestionPaper_NTA_V2.txt"
PROMPT_PATH_BATCH = BASE_DIR / "Prompts" / "JEEMainQuestionPaper_NTA_V2_batch.txt"
HEADER_PROMPT_PATH = BASE_DIR / "Prompts" / "JEEMainQuestionPaper_NTA_Header.txt"
FIG_CHECK_PROMPT_PATH = BASE_DIR / "Prompts" / "JEEMainQuestionPaper_NTA_figcheck_batch.txt"
INPUT_DIR = BASE_DIR / "input" # Input directory remains the same
OUTPUT_DIR = BASE_DIR / "output" / "JEEMain" # Output directory now includes "JEEMain" subdirectory


def init_model(model_name: str) -> genai.GenerativeModel:
    """Initializes the GenerativeModel, configuring it with the API key."""
    try:
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    except KeyError:
        raise EnvironmentError("Error: GOOGLE_API_KEY environment variable not set.")

    generation_config = None
    if "pro" in model_name:
        # Pro models support forced JSON output
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
        )

    return genai.GenerativeModel(
        model_name=model_name,
        generation_config=generation_config
    )


def call_gemini_streaming(
    model: genai.GenerativeModel, prompt: str, file_path: Path
) -> str:
    """
    Calls the Gemini model with a prompt and a file, getting the result
    in a streaming fashion with a high timeout.
    """
    uploaded_file = None
    try:
        print(f"  - Uploading file: {file_path.name}...")
        # The SDK handles the upload and makes the file available to the model.
        # For local files, it uploads; for gs:// URIs, it performs a server-side copy.
        # For local files, it uploads.
        uploaded_file = genai.upload_file(path=file_path)

        parts = [prompt, uploaded_file]

        print(f"  - Generating content for {file_path.name} (streaming)...", flush=True)
        response_stream = model.generate_content(
            contents=parts,
            stream=True,
            request_options={'timeout': HIGH_TIMEOUT_SECONDS}
        )

        # 1. Progress indicator
        full_response = ""
        for chunk in response_stream:
            full_response += chunk.text
            print(".", end="", flush=True)
        
        return full_response

    finally:
        # This block will always execute, ensuring the file is deleted.
        if uploaded_file:
            # Clean up the uploaded file from the File Service after processing
            genai.delete_file(uploaded_file.name)
            print(f"\n  - Cleaned up file resource: {uploaded_file.name}")


def clean_json_string(text: str) -> str:
    """Removes markdown code block formatting from a string."""
    # Find the start of the JSON content
    start_brace = text.find('{')
    start_bracket = text.find('[')

    # Handle cases where no JSON object/array is found
    if start_brace == -1 and start_bracket == -1:
        return text

    start_pos = min(s for s in [start_brace, start_bracket] if s != -1)

    # Find the end of the JSON content
    end_brace = text.rfind('}')
    end_bracket = text.rfind(']')
    end_pos = max(end_brace, end_bracket)

    return text[start_pos : end_pos + 1]


def save_output(base_dir: Path, input_path: Path, text: str, suffix: str = "") -> Path:
    """Saves the output text to a timestamped JSON file."""
    base_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    filename = f"{stem}{suffix}.json"
    out_path = base_dir / filename
    # Try to pretty-print JSON if valid
    cleaned_text = clean_json_string(text)
    try:
        parsed = json.loads(cleaned_text)
        out_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        out_path.write_text(cleaned_text, encoding="utf-8") # Save the cleaned text even if parsing fails
    print(f"  - Saved output to: {out_path}")
    return out_path


def extract_figures_from_pdf(
    pdf_path: Path, json_data: Dict, image_output_dir: Path,
    fig_check_model: genai.GenerativeModel, fig_check_prompt: str,
    save_path: Path
):
    """
    Extracts all images from a PDF, uses a batch call to Gemini to identify which are figures,
    saves only the figures, and injects the filenames back into the JSON data.

    Args:
        pdf_path: Path to the source PDF file.
        json_data: The parsed JSON response from Gemini.
        image_output_dir: The directory to save extracted figure images.
        fig_check_model: The Gemini model used for classifying images.
        fig_check_prompt: The prompt to use for the figure check.
        save_path: The path to save the final JSON file with image links.
    """
    print(f"  - Checking for figures to extract from {pdf_path.name}...")
    image_output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Find all nodes in the JSON that have a "~figure~" placeholder.
    figure_placeholders = []
    def find_figure_nodes(node, path=[]):
        if isinstance(node, dict):
            if node.get("Figure") == "~figure~":
                figure_placeholders.append(node)
            for key, value in node.items():
                find_figure_nodes(value, path + [key])
        elif isinstance(node, list):
            for i, item in enumerate(node):
                find_figure_nodes(item, path + [i])

    find_figure_nodes(json_data)

    if not figure_placeholders:
        print("  - No 'figure' placeholders found in JSON. Skipping image extraction.")
        # Save the original JSON data if no figures are found, to maintain pipeline consistency
        save_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  - Saved unmodified JSON to: {save_path}")
        return

    print(f"  - Found {len(figure_placeholders)} figure placeholder(s).")

    # 2. Extract all images from the entire PDF to be checked in a batch.
    print("  - Scanning all PDF pages for images to verify...")
    doc = fitz.open(pdf_path)
    file_stem = pdf_path.stem
    
    image_candidates = []
    model_parts = [fig_check_prompt]

    for page_index in range(len(doc)):
        page_num = page_index + 1
        image_list = doc.get_page_images(page_index, full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Unique identifier for the model to reference
                image_id = f"{file_stem}_p{page_num}_img{img_index+1}"
                
                candidate_info = {
                    "id": image_id,
                    "bytes": image_bytes,
                    "ext": image_ext
                }
                image_candidates.append(candidate_info)
                model_parts.append(f"Image ID: {image_id}")
                model_parts.append({"mime_type": f"image/{image_ext}", "data": image_bytes})

            except Exception as e:
                print(f"\n    - Warning: Could not extract image {img_index+1} on page {page_num}: {e}")

    doc.close()
    print(f"\n  - Extracted {len(image_candidates)} total images. Verifying in a single batch call...")

    # 3. Make a single batch call to Gemini to identify all figures.
    all_figures = []
    if image_candidates:
        try:
            # Set a specific mime_type for the batch response
            batch_generation_config = genai.GenerationConfig(response_mime_type="application/json")
            response = fig_check_model.generate_content(model_parts, generation_config=batch_generation_config)
            # The model should return a JSON list of IDs for images that are figures.
            figure_ids = json.loads(clean_json_string(response.text))
            
            # Create a set for quick lookups
            figure_id_set = set(figure_ids)

            # 4. Save only the images identified as figures.
            for candidate in image_candidates:
                if candidate["id"] in figure_id_set:
                    img_filename = f"{candidate['id']}.{candidate['ext']}"
                    img_path = image_output_dir / img_filename
                    img_path.write_bytes(candidate["bytes"])
                    all_figures.append(img_path.name)
                    print(f"    - Identified and saved figure: {img_filename}")
        except Exception as e:
            print(f"\n  - [ERROR] Batch figure check failed: {e}. No figures will be linked. Aborting this step to allow for retry.")
            # Return without saving to allow the resumable pipeline to retry this step.
            return

    # 5. Sequentially assign the found figures to the placeholders.
    if all_figures:
        for i, node in enumerate(figure_placeholders):
            if i < len(all_figures):
                node['Figure_File'] = all_figures[i]
                print(f"  - Assigned '{all_figures[i]}' to placeholder {i+1}.")
    else:
        print("  - Warning: No actual figures were identified in the PDF despite placeholders in JSON.")

    # Save the modified JSON with a new name
    save_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  - Saved final JSON with image links to: {save_path}")

def main():
    """Main function to run the JSON-based extraction pipeline."""
    print("Starting JSON-Based Question Extraction Pipeline...")
    main_model = init_model(MODEL_NAME)
    header_model = init_model(HEADER_MODEL_NAME)
    fig_check_model = init_model(FIG_CHECK_MODEL_NAME)
    
    # Load the correct prompt based on the selected mode
    main_prompt_text = (
        PROMPT_PATH_BATCH.read_text(encoding="utf-8") if USE_BATCH_SUBJECT_EXTRACTION 
        else PROMPT_PATH_SINGLE.read_text(encoding="utf-8")
    )
    header_prompt_text = HEADER_PROMPT_PATH.read_text(encoding="utf-8")
    fig_check_prompt = FIG_CHECK_PROMPT_PATH.read_text(encoding="utf-8")

    if not INPUT_DIR.exists() or not any(INPUT_DIR.iterdir()):
        print(f"\nWarning: Input directory '{INPUT_DIR}' is empty or does not exist.")
        print("Please create it and add your PDF files to process.")
        return

    input_files = [p for p in INPUT_DIR.glob("*.pdf")]
    print(f"Found {len(input_files)} PDF(s) to process in '{INPUT_DIR}'.\n")

    for file_path in input_files:
        print(f"Processing: {file_path.name}")
        start_time = time.monotonic()
        
        # Define paths for all potential output files to check for resumability
        file_stem = file_path.stem
        header_json_path = OUTPUT_DIR / f"{file_stem}_Header.json"
        merged_json_path = OUTPUT_DIR / f"{file_stem}.json"
        final_json_path = OUTPUT_DIR / f"{file_stem}_with_images.json"

        try:
            # Check if the final output already exists
            if final_json_path.exists():
                print(f"  - Final output '{final_json_path.name}' already exists. Skipping.")
                continue

            full_paper_data = {}

            # Check if the merged JSON exists, which allows skipping all initial extractions
            if merged_json_path.exists():
                print(f"\n--- Steps 1-3: Merged file '{merged_json_path.name}' found. Loading it. ---")
                full_paper_data = json.loads(merged_json_path.read_text(encoding="utf-8"))
            else:
                # Step 1: Extract Header
                print("\n--- Step 1: Extracting Header ---")
                if header_json_path.exists():
                    print(f"  - Header file '{header_json_path.name}' already exists. Loading it.")
                else:
                    header_text = call_gemini_streaming(header_model, header_prompt_text, file_path)
                    save_output(OUTPUT_DIR, file_path, header_text, suffix="_Header")
                full_paper_data["Header"] = json.loads(header_json_path.read_text(encoding="utf-8"))

                if USE_BATCH_SUBJECT_EXTRACTION:
                    # Step 2 (Batch Mode): Extract all Subject Sections in a single call
                    print(f"\n--- Step 2: Batch Extracting {', '.join(SUBJECTS)} Sections ---")
                    subject_text = call_gemini_streaming(main_model, main_prompt_text, file_path)
                    # The model should return a JSON with keys "Physics", "Chemistry", etc.
                    full_paper_data.update(json.loads(clean_json_string(subject_text)))
                else:
                    # Step 2 (Single Mode): Make a single batch call with 3 requests (one for each subject)
                    subject_json_paths = {subject: OUTPUT_DIR / f"{file_stem}_{subject}.json" for subject in SUBJECTS}
                    
                    # Check if all subject files already exist
                    all_exist = all(subject_json_paths[subject].exists() for subject in SUBJECTS)
                    
                    if not all_exist:
                        print(f"\n--- Step 2: Extracting {', '.join(SUBJECTS)} Sections (optimized with single upload) ---")
                        
                        # Upload the file once and reuse it for all three subject calls
                        uploaded_file = None
                        try:
                            print(f"  - Uploading file: {file_path.name}...")
                            uploaded_file = genai.upload_file(path=file_path)
                            
                            # Make three separate streaming calls, one for each subject, reusing the uploaded file
                            for subject in SUBJECTS:
                                json_path = subject_json_paths[subject]
                                if json_path.exists():
                                    print(f"\n  - {subject}: Already exists, loading from {json_path.name}")
                                    full_paper_data[subject] = json.loads(json_path.read_text(encoding="utf-8"))
                                    continue
                                
                                print(f"\n  - Extracting {subject}...")
                                prompt_text_single = main_prompt_text.replace("{Subject}", subject)
                                parts = [prompt_text_single, uploaded_file]
                                
                                print(f"    Generating content (streaming)...", flush=True)
                                response_stream = main_model.generate_content(
                                    contents=parts,
                                    stream=True,
                                    request_options={'timeout': HIGH_TIMEOUT_SECONDS}
                                )
                                
                                # Collect the full response from the stream with progress indicator
                                full_response = ""
                                for chunk in response_stream:
                                    full_response += chunk.text
                                    print(".", end="", flush=True)
                                print()  # New line after progress dots
                                
                                # Save the subject data
                                subject_data = json.loads(clean_json_string(full_response))
                                json_path.write_text(json.dumps(subject_data, ensure_ascii=False, indent=2), encoding="utf-8")
                                print(f"    Saved to: {json_path}")
                                full_paper_data[subject] = subject_data
                        
                        finally:
                            # Clean up the uploaded file
                            if uploaded_file:
                                genai.delete_file(uploaded_file.name)
                                print(f"\n  - Cleaned up file resource: {uploaded_file.name}")
                    else:
                        print(f"\n--- Step 2: All subject files already exist. Loading them ---")
                        for subject in SUBJECTS:
                            json_path = subject_json_paths[subject]
                            print(f"  - Loading: {json_path.name}")
                            full_paper_data[subject] = json.loads(json_path.read_text(encoding="utf-8"))

                # Step 3: Merge all JSON parts
                print("\n--- Step 3: Merging all JSON parts ---")
                merged_json_path.write_text(json.dumps(full_paper_data, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  - Merged JSON saved to: {merged_json_path}")

            # Step 4: Process figures using the merged JSON
            print("\n--- Step 4: Processing Figures ---")
            # This step is implicitly resumable because we check for final_json_path at the start.
            # If the script fails here, rerunning will start from this step.
            if not final_json_path.exists():
                extract_figures_from_pdf(
                    pdf_path=file_path,
                    json_data=full_paper_data,
                    image_output_dir=OUTPUT_DIR / "images", # Images stored in a sub-directory
                    fig_check_model=fig_check_model,
                    fig_check_prompt=fig_check_prompt,
                    save_path=final_json_path
                )
            else:
                 print(f"  - Final file with images '{final_json_path.name}' already exists. Nothing to do.")

        except Exception as e:
            print(f"\n  [ERROR] Failed to process {file_path.name}: {e}")
            print("  Skipping to the next file.")
        finally:
            # Timer for the entire processing of one file
            end_time = time.monotonic()
            elapsed = end_time - start_time
            print(f"\n  - Total time for {file_path.name}: {elapsed:.2f} seconds")
            print("-" * 30)
            # Take a 30-second break after processing each file
            print("  - Taking a 30-second break before the next file...")
            time.sleep(30)

    print("Pipeline finished.")

if __name__ == "__main__":
    main()
    