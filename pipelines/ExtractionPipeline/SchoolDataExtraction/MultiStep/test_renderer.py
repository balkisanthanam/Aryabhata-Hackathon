"""
Test Renderer - Visualize extracted questions with their associated images.

Usage:
    python test_renderer.py Output/questions_chemistry_kech202_*.json 8.4
    python test_renderer.py Output/questions_chemistry_kech202_*.json 8.15 --open
    python test_renderer.py Output/questions_chemistry_kech202_*.json  # All questions
    
Options:
    --open      Open the rendered HTML in browser automatically
    --all       Render all questions (default if no question_id specified)
"""

import argparse
import json
import webbrowser
import html
import base64
from pathlib import Path
from typing import Optional, List, Dict
import glob


def load_json(json_path: str) -> Dict:
    """Load the extraction output JSON."""
    # Handle glob patterns
    if '*' in json_path:
        matches = sorted(glob.glob(json_path))
        if not matches:
            raise FileNotFoundError(f"No files match pattern: {json_path}")
        json_path = matches[-1]  # Use most recent
        print(f"Using: {json_path}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_image_base64(image_path: Path, output_dir: Path) -> Optional[str]:
    """Load image and convert to base64 for embedding in HTML."""
    # Try relative to output dir first
    full_path = output_dir / image_path
    if not full_path.exists():
        # Try as absolute path
        full_path = Path(image_path)
    
    if not full_path.exists():
        return None
    
    with open(full_path, 'rb') as f:
        data = f.read()
    
    # Determine MIME type
    suffix = full_path.suffix.lower()
    mime = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
    }.get(suffix, 'image/png')
    
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def render_question_html(question: Dict, output_dir: Path) -> str:
    """Render a single question as HTML."""
    q_id = question.get('question_id', 'unknown')
    q_text = question.get('question_text', '')
    page_num = question.get('page_number', '?')
    visual_required = question.get('visual_required', False)
    visual_data = question.get('visual_data', {}) or {}
    figure_refs = question.get('figure_references', [])
    
    # Escape HTML in question text but preserve LaTeX
    q_text_escaped = html.escape(q_text)
    # Convert newlines to <br>
    q_text_html = q_text_escaped.replace('\n', '<br>')
    
    # Build visual section
    visual_html = ""
    if visual_required and visual_data:
        img_path = visual_data.get('cropped_image_path', '')
        box_2d = visual_data.get('box_2d', [])
        visual_type = visual_data.get('type', 'DIAGRAM')
        description = visual_data.get('description', '')
        
        if img_path:
            img_base64 = get_image_base64(Path(img_path), output_dir)
            if img_base64:
                visual_html = f'''
                <div class="visual-container">
                    <div class="visual-label">
                        <span class="badge">{visual_type}</span>
                        <span class="box-coords">box: {box_2d}</span>
                    </div>
                    <img src="{img_base64}" alt="Figure for {q_id}" class="question-image">
                    {f'<p class="description">{html.escape(description)}</p>' if description else ''}
                </div>
                '''
            else:
                visual_html = f'''
                <div class="visual-container error">
                    <p>⚠️ Image not found: {img_path}</p>
                    <p>Box: {box_2d}</p>
                </div>
                '''
        else:
            visual_html = f'''
            <div class="visual-container warning">
                <p>⚠️ Visual required but no image path</p>
                <p>Box: {box_2d}</p>
            </div>
            '''
    elif figure_refs:
        visual_html = f'''
        <div class="visual-container warning">
            <p>⚠️ Figure references found but no visual extracted:</p>
            <p>{', '.join(figure_refs)}</p>
        </div>
        '''
    
    # Status indicator
    status_class = "success" if (not visual_required or (visual_data and visual_data.get('cropped_image_path'))) else "warning"
    if figure_refs and not visual_required:
        status_class = "warning"
    
    return f'''
    <div class="question-card {status_class}">
        <div class="question-header">
            <h2>Question {q_id}</h2>
            <span class="page-badge">Page {page_num}</span>
            {'<span class="visual-badge">📷 Has Visual</span>' if visual_required else ''}
        </div>
        <div class="question-text">
            {q_text_html}
        </div>
        {visual_html}
        {f'<div class="figure-refs">Figure refs: {", ".join(figure_refs)}</div>' if figure_refs else ''}
    </div>
    '''


def render_html(
    data: Dict, 
    questions_to_render: List[Dict],
    output_dir: Path,
    title: str = "Extraction Test Viewer"
) -> str:
    """Generate full HTML page."""
    metadata = data.get('metadata', {})
    
    # Render all questions
    questions_html = "\n".join(
        render_question_html(q, output_dir) 
        for q in questions_to_render
    )
    
    # Stats
    total = len(questions_to_render)
    with_visual = sum(1 for q in questions_to_render if q.get('visual_required'))
    with_image = sum(1 for q in questions_to_render 
                     if q.get('visual_data', {}) and q.get('visual_data', {}).get('cropped_image_path'))
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script>
        MathJax = {{
            loader: {{
                load: ['[tex]/mhchem', '[tex]/physics']
            }},
            tex: {{
                inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
                displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
                processEscapes: true,
                packages: {{'[+]': ['mhchem', 'physics']}}
            }},
            options: {{
                skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre']
            }}
        }};
    </script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-mml-chtml.min.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{ margin: 0 0 10px 0; }}
        .stats {{
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }}
        .stat {{
            background: rgba(255,255,255,0.2);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
        }}
        .question-card {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        }}
        .question-card.warning {{
            border-left-color: #f59e0b;
        }}
        .question-card.error {{
            border-left-color: #ef4444;
        }}
        .question-card.success {{
            border-left-color: #10b981;
        }}
        .question-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .question-header h2 {{
            margin: 0;
            color: #333;
        }}
        .page-badge {{
            background: #e5e7eb;
            color: #374151;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
        }}
        .visual-badge {{
            background: #dbeafe;
            color: #1d4ed8;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
        }}
        .question-text {{
            font-size: 16px;
            line-height: 1.6;
            color: #444;
            margin-bottom: 15px;
            padding: 15px;
            background: #f9fafb;
            border-radius: 8px;
        }}
        .visual-container {{
            margin-top: 15px;
            padding: 15px;
            background: #f0fdf4;
            border-radius: 8px;
            border: 1px solid #bbf7d0;
        }}
        .visual-container.warning {{
            background: #fffbeb;
            border-color: #fde68a;
        }}
        .visual-container.error {{
            background: #fef2f2;
            border-color: #fecaca;
        }}
        .visual-label {{
            display: flex;
            gap: 10px;
            margin-bottom: 10px;
            align-items: center;
        }}
        .badge {{
            background: #10b981;
            color: white;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        }}
        .box-coords {{
            font-family: monospace;
            font-size: 12px;
            color: #666;
        }}
        .question-image {{
            max-width: 100%;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            display: block;
        }}
        .description {{
            margin-top: 10px;
            font-style: italic;
            color: #666;
            font-size: 14px;
        }}
        .figure-refs {{
            margin-top: 10px;
            font-size: 13px;
            color: #666;
            padding: 8px;
            background: #f3f4f6;
            border-radius: 4px;
        }}
        .metadata {{
            font-size: 13px;
            color: rgba(255,255,255,0.9);
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📝 {title}</h1>
        <div class="metadata">
            PDF: {metadata.get('pdf_file', 'N/A')} | 
            Subject: {metadata.get('subject', 'N/A')} |
            Model: {metadata.get('model', 'N/A')}
        </div>
        <div class="stats">
            <span class="stat">📄 {total} questions</span>
            <span class="stat">📷 {with_visual} need visuals</span>
            <span class="stat">✅ {with_image} have images</span>
        </div>
    </div>
    
    {questions_html}
    
    <script>
        // Trigger MathJax to render LaTeX
        if (typeof MathJax !== 'undefined') {{
            MathJax.typesetPromise();
        }}
    </script>
</body>
</html>
'''


def main():
    parser = argparse.ArgumentParser(description="Render extracted questions for visual inspection")
    parser.add_argument("json_file", help="Path to the extraction output JSON (supports glob patterns)")
    parser.add_argument("question_id", nargs="?", default=None, help="Question ID to render (e.g., '8.4'). Omit for all.")
    parser.add_argument("--open", "-o", action="store_true", help="Open in browser automatically")
    parser.add_argument("--output", "-f", default=None, help="Output HTML file path")
    
    args = parser.parse_args()
    
    # Load JSON
    data = load_json(args.json_file)
    questions = data.get('questions', [])
    
    if not questions:
        print("No questions found in JSON!")
        return
    
    # Filter questions
    if args.question_id:
        questions_to_render = [q for q in questions if q.get('question_id') == args.question_id]
        if not questions_to_render:
            print(f"Question {args.question_id} not found. Available: {[q.get('question_id') for q in questions[:10]]}...")
            return
        title = f"Question {args.question_id}"
    else:
        questions_to_render = questions
        title = "All Questions"
    
    # Determine output directory (where cropped_images folder is)
    json_path = Path(args.json_file)
    if '*' in args.json_file:
        matches = sorted(glob.glob(args.json_file))
        json_path = Path(matches[-1])
    output_dir = json_path.parent
    
    # Generate HTML
    html_content = render_html(data, questions_to_render, output_dir, title)
    
    # Save HTML
    if args.output:
        html_path = Path(args.output)
    else:
        html_path = output_dir / f"test_view_{json_path.stem}.html"
    
    html_path.write_text(html_content, encoding='utf-8')
    print(f"✅ Rendered {len(questions_to_render)} questions to: {html_path}")
    
    # Open in browser
    if args.open:
        webbrowser.open(f"file://{html_path.absolute()}")
        print("🌐 Opened in browser")


if __name__ == "__main__":
    main()
