import os
import json
import argparse
import glob
from pathlib import Path
from PIL import Image
from google import genai
from google.genai import types

# Configuration
PROJECT_ID = "animated-rope-453904-j7"
LOCATION = "global"
MODEL_ID = "gemini-3-pro-preview"

def get_subfolders(input_root):
    """Returns a list of subdirectories in the input root."""
    return [
        Path(f) for f in glob.glob(os.path.join(input_root, "*/")) 
        if os.path.isdir(f)
    ]

def get_images_in_folder(folder):
    """Returns sorted list of image files in a folder."""
    # Extensions to look for
    extensions = ("*.jpg", "*.jpeg", "*.png")
    images = []
    for ext in extensions:
        images.extend(glob.glob(os.path.join(folder, ext)))
    
    # Sort specifically to handle 1.jpeg, 2.jpeg, 10.jpeg correctly
    # detailed natural sort might be needed if filenames are just numbers
    def natural_sort_key(path):
        filename = os.path.basename(path)
        stem = os.path.splitext(filename)[0]
        if stem.isdigit():
            return int(stem)
        return filename

    return sorted(images, key=natural_sort_key)

def load_prompt(prompt_path):
    """Loads text from the prompt file."""
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

import time

def process_submission(client, image_paths, prompt):
    """Sends images and prompt to Gemini and returns parsed JSON."""
    
    print(f"  - Processing {len(image_paths)} images...")
    
    contents = []
    
    # Load all images
    for img_path in image_paths:
        with open(img_path, "rb") as f:
            image_bytes = f.read()
            mime_type = "image/jpeg" if img_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
            
    contents.append(prompt)
    
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1
    )
    
    max_retries = 3
    base_delay = 5
    
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=contents,
                config=config
            )
            
            # Check if response has text
            if not response.text:
                print("  ! Error: Empty response text from Gemini.")
                return None
                
            try:
                return json.loads(response.text)
            except json.JSONDecodeError as e:
                print(f"  ! Error decoding JSON: {e}")
                print(f"  ! Raw response: {response.text[:200]}...") # Print snippet
                return None

        except Exception as e:
            # Check for 429 or other retryable errors
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    print(f"  ! Rate limited (429). Retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                else:
                    print(f"  ! API Error (Exhausted retries): {e}")
                    return None
            else:
                print(f"  ! API Error: {e}")
                return None
    return None

def stitch_and_crop(submission_folder, image_paths, json_data, output_root):
    """Crops solutions and stitches multi-part ones."""
    if not json_data or "solutions" not in json_data:
        print("  ! No 'solutions' found in JSON data.")
        return

    subfolder_name = submission_folder.name
    output_dir = os.path.join(output_root, subfolder_name)
    os.makedirs(output_dir, exist_ok=True)
    
    # Save raw JSON
    with open(os.path.join(output_dir, "response.json"), "w", encoding='utf-8') as f:
        json.dump(json_data, f, indent=2)

    # 1. Group solutions by problem_id (stripping _part suffix if exists to handle arbitrary stitching)
    # Actually, let's look at the logic. User says: "Q13_part1", "Q13_part2".
    # We want to group these as "Q13".
    
    solutions_map = {}
    
    for sol in json_data.get("solutions", []):
        problem_id_raw = sol.get("problem_id", "unknown")
        
        # Simple heuristic to identify base problem ID
        # If it contains "_part", split it. 
        if "_part" in problem_id_raw:
            base_id = problem_id_raw.split("_part")[0]
            # Use the part number for sorting. default to 0 if not found
            try:
                part_num = int(problem_id_raw.split("_part")[1])
            except ValueError:
                part_num = 0
        else:
            base_id = problem_id_raw
            part_num = 0
            
        if base_id not in solutions_map:
            solutions_map[base_id] = []
        
        solutions_map[base_id].append({
            "part_num": part_num,
            "data": sol
        })
        
    # 2. Open all source images once
    source_images = [Image.open(p) for p in image_paths]
    
    # 3. Process each problem
    for base_id, parts in solutions_map.items():
        # Sort parts
        parts.sort(key=lambda x: x["part_num"])
        
        crops = []
        
        for p in parts:
            sol = p["data"]
            img_idx = sol.get("image_index", 0)
            
            # Validation
            if img_idx >= len(source_images):
                print(f"    ! Warning: Image index {img_idx} out of range for {base_id}")
                continue
                
            img = source_images[img_idx]
            width, height = img.size
            
            # Coordinates
            ymin, xmin, ymax, xmax = sol["box_2d"]
            
            left = (xmin / 1000) * width
            top = (ymin / 1000) * height
            right = (xmax / 1000) * width
            bottom = (ymax / 1000) * height
            
            # Validate Crop Dimensions
            if right <= left or bottom <= top:
                print(f"    ! Warning: Invalid dimensions for {base_id} part")
                continue
                
            crop = img.crop((left, top, right, bottom))
            crops.append(crop)
            
        # Stitch
        if not crops:
            continue
            
        if len(crops) == 1:
            final_img = crops[0]
        else:
            # Vertical stitch
            total_height = sum(c.height for c in crops)
            max_width = max(c.width for c in crops)
            
            final_img = Image.new('RGB', (max_width, total_height), (255, 255, 255))
            
            y_offset = 0
            for c in crops:
                # Center align or left align? standard is usually left.
                final_img.paste(c, (0, y_offset))
                y_offset += c.height
                
        # Save
        # Sanitize filename
        safe_name = "".join([c for c in base_id if c.isalnum() or c in ('-','_')])
        save_path = os.path.join(output_dir, f"{safe_name}.jpg")
        final_img.save(save_path)
        print(f"    Saved: {save_path}")

    # Close images
    for img in source_images:
        img.close()

def main():
    parser = argparse.ArgumentParser(description="Validate Gemini Prompt for Student HW Split")
    parser.add_argument("--input", default="apps/backend/experiment/input", help="Input directory containing subfolders")
    parser.add_argument("--output", default="apps/backend/experiment/output", help="Output directory")
    args = parser.parse_args()

    # client = genai.Client(api_key=API_KEY)
    print(f"Initializing Vertex AI Client (Project: {PROJECT_ID}, Location: {LOCATION})")
    client = genai.Client(
        vertexai=True, 
        project=PROJECT_ID, 
        location=LOCATION
    )
    
    # Load Prompt
    prompt_file = os.path.join(os.path.dirname(__file__), "Student_HW_Split.md")
    if not os.path.exists(prompt_file):
        print(f"Error: Prompt file not found at {prompt_file}")
        return
        
    prompt_text = load_prompt(prompt_file)
    print(f"Loaded prompt from {prompt_file}")
    
    # Input/Output paths
    # Resolve relative paths relative to CWD or Script
    # Assuming run from root of repo usually, but let's be robust
    # If path starts with apps/..., assuming absolute or relative to cwd
    input_root = os.path.abspath(args.input)
    output_root = os.path.abspath(args.output)
    
    print(f"Input Root: {input_root}")
    print(f"Output Root: {output_root}")
    
    if not os.path.exists(input_root):
        print("Error: Input directory does not exist.")
        return

    subfolders = get_subfolders(input_root)
    print(f"Found {len(subfolders)} subfolders.")

    for sub in subfolders:
        # Check if output already exists
        sub_output_dir = os.path.join(output_root, sub.name)
        if os.path.exists(sub_output_dir):
            print(f"\nSkipping {sub.name} (Output exists: {sub_output_dir})")
            continue

        print(f"\nProcessing Folder: {sub.name}")
        
        images = get_images_in_folder(sub)
        if not images:
            print("  No images found.")
            continue
            
        json_data = process_submission(client, images, prompt_text)
        
        if json_data:
            stitch_and_crop(sub, images, json_data, output_root)
            
        # Add explicit delay between folders to avoid rate limits
        print("  Sleeping for 10 seconds...")
        time.sleep(20)

if __name__ == "__main__":
    main()
