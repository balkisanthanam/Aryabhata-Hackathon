import os
import json
import glob
from pathlib import Path
from flask import Flask, render_template, jsonify, send_from_directory

app = Flask(__name__)

# Constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/input/<path:filename>')
def serve_input(filename):
    return send_from_directory(INPUT_DIR, filename)

@app.route('/output/<path:filename>')
def serve_output(filename):
    return send_from_directory(OUTPUT_DIR, filename)

@app.route('/api/list')
def list_folders():
    """Lists available categories and subfolders."""
    structure = {}
    
    if os.path.exists(INPUT_DIR):
        for category in os.listdir(INPUT_DIR):
            cat_path = os.path.join(INPUT_DIR, category)
            if os.path.isdir(cat_path):
                subfolders = []
                for sub in os.listdir(cat_path):
                    if os.path.isdir(os.path.join(cat_path, sub)):
                        subfolders.append(sub)
                if subfolders:
                    structure[category] = sorted(subfolders)
                    
    return jsonify(structure)

@app.route('/api/details/<category>/<subfolder>')
def get_details(category, subfolder):
    """Returns details for a specific subfolder."""
    
    # 1. Input Images
    input_path = os.path.join(INPUT_DIR, category, subfolder)
    input_images = []
    if os.path.exists(input_path):
        # reuse logic from validate_split logic basically
        exts = ["*.jpg", "*.jpeg", "*.png"]
        for ext in exts:
            for f in glob.glob(os.path.join(input_path, ext)):
                input_images.append(os.path.basename(f))
                
    # Sort naturally
    def natural_sort_key(s):
        import re
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split('([0-9]+)', s)]
    
    input_images.sort(key=natural_sort_key)
    
    # 2. Output Versions
    versions_data = {}
    output_cat_dir = os.path.join(OUTPUT_DIR, category)
    
    if os.path.exists(output_cat_dir):
        # Look for V1, V2 folders
        for version in os.listdir(output_cat_dir):
            if version.startswith("V") and os.path.isdir(os.path.join(output_cat_dir, version)):
                # Check if subfolder exists inside this version
                version_sub_path = os.path.join(output_cat_dir, version, subfolder)
                if os.path.exists(version_sub_path):
                    # Get list of crops
                    crops = []
                    for f in os.listdir(version_sub_path):
                        if f.lower().endswith((".jpg", ".jpeg", ".png")):
                            crops.append(f)
                    crops.sort(key=natural_sort_key)
                    versions_data[version] = crops
                    
    return jsonify({
        "input_images": input_images,
        "versions": versions_data
    })

if __name__ == '__main__':
    print(f"Starting Experiment Viewer on http://localhost:5001")
    app.run(debug=True, port=5001)
