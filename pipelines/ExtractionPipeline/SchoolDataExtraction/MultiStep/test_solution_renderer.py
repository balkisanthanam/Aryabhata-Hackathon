"""
Solution Test Renderer - Visualize generated solutions with step-by-step breakdown.

Usage:
    python test_solution_renderer.py Output/solution_physics_*.json 12.4 --open
    python test_solution_renderer.py Output/solution_physics_*.json --open  # All solutions
    
Options:
    --open      Open the rendered HTML in browser automatically
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
    """Load the solution output JSON."""
    # Handle glob patterns
    if '*' in json_path:
        matches = sorted(glob.glob(json_path))
        if not matches:
            raise FileNotFoundError(f"No files match pattern: {json_path}")
        json_path = matches[-1]  # Use most recent
        print(f"Using: {json_path}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def render_step_html(step: Dict, step_idx: int) -> str:
    """Render a single solution step as HTML."""
    step_num = step.get('step_number', step_idx + 1)
    step_type = step.get('step_type', 'general')
    nudge_hint = step.get('nudge_hint', '')
    explanation = step.get('explanation', '')
    latex_formula = step.get('latex_formula', '')
    
    # Escape HTML but preserve LaTeX
    explanation_html = html.escape(explanation).replace('\n', '<br>')
    nudge_html = html.escape(nudge_hint) if nudge_hint else ''
    
    # Step type badge color
    type_colors = {
        'conceptual': '#8b5cf6',  # purple
        'calculation': '#3b82f6',  # blue
        'formula': '#10b981',  # green
        'conclusion': '#f59e0b',  # amber
        'general': '#6b7280',  # gray
    }
    badge_color = type_colors.get(step_type, '#6b7280')
    
    # LaTeX formula section
    latex_html = ""
    if latex_formula:
        latex_html = f'''
        <div class="latex-block">
            {html.escape(latex_formula)}
        </div>
        '''
    
    # Nudge hint section
    nudge_section = ""
    if nudge_html:
        nudge_section = f'''
        <div class="nudge-hint">
            <span class="nudge-icon">💡</span>
            <span class="nudge-text">{nudge_html}</span>
        </div>
        '''
    
    return f'''
    <div class="step-card">
        <div class="step-header">
            <span class="step-number">Step {step_num}</span>
            <span class="step-type" style="background: {badge_color}">{step_type}</span>
        </div>
        {nudge_section}
        <div class="step-explanation">
            {explanation_html}
        </div>
        {latex_html}
    </div>
    '''


def render_solution_html(solution: Dict) -> str:
    """Render a single solution as HTML."""
    q_id = solution.get('question_id', 'unknown')
    q_text = solution.get('question_text', '')
    steps = solution.get('steps', [])
    final_answer = solution.get('final_answer', '')
    
    # Escape HTML in question text
    q_text_html = html.escape(q_text).replace('\n', '<br>')
    
    # Render all steps
    steps_html = "\n".join(
        render_step_html(step, idx) 
        for idx, step in enumerate(steps)
    )
    
    # Final answer section
    final_html = ""
    if final_answer:
        final_html = f'''
        <div class="final-answer">
            <div class="final-header">✅ Final Answer</div>
            <div class="final-content">{html.escape(final_answer)}</div>
        </div>
        '''
    
    return f'''
    <div class="solution-card">
        <div class="question-section">
            <div class="question-header">
                <h2>Question {q_id}</h2>
            </div>
            <div class="question-text">
                {q_text_html}
            </div>
        </div>
        
        <div class="solution-section">
            <h3>📝 Solution ({len(steps)} steps)</h3>
            {steps_html}
            {final_html}
        </div>
    </div>
    '''


def render_html(
    data: Dict, 
    solutions_to_render: List[Dict],
    title: str = "Solution Test Viewer"
) -> str:
    """Generate full HTML page."""
    metadata = data.get('metadata', {})
    
    # Render all solutions
    solutions_html = "\n".join(
        render_solution_html(s) 
        for s in solutions_to_render
    )
    
    # Stats
    total = len(solutions_to_render)
    total_steps = sum(len(s.get('steps', [])) for s in solutions_to_render)
    
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
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
            line-height: 1.6;
        }}
        .header {{
            background: linear-gradient(135deg, #059669 0%, #10b981 100%);
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
        .metadata {{
            font-size: 13px;
            color: rgba(255,255,255,0.9);
            margin-bottom: 10px;
        }}
        .solution-card {{
            background: white;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .question-section {{
            background: #f8fafc;
            padding: 20px;
            border-bottom: 2px solid #e2e8f0;
        }}
        .question-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }}
        .question-header h2 {{
            margin: 0;
            color: #1e293b;
        }}
        .question-text {{
            font-size: 15px;
            color: #475569;
            padding: 15px;
            background: white;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }}
        .solution-section {{
            padding: 20px;
        }}
        .solution-section h3 {{
            margin: 0 0 20px 0;
            color: #059669;
            font-size: 18px;
        }}
        .step-card {{
            background: #f8fafc;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            border-left: 4px solid #10b981;
        }}
        .step-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }}
        .step-number {{
            font-weight: 600;
            color: #1e293b;
            font-size: 14px;
        }}
        .step-type {{
            color: white;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 500;
            text-transform: uppercase;
        }}
        .nudge-hint {{
            background: #fef3c7;
            border: 1px solid #fcd34d;
            border-radius: 6px;
            padding: 10px 12px;
            margin-bottom: 10px;
            display: flex;
            align-items: flex-start;
            gap: 8px;
        }}
        .nudge-icon {{
            font-size: 16px;
        }}
        .nudge-text {{
            font-size: 13px;
            color: #92400e;
            font-style: italic;
        }}
        .step-explanation {{
            font-size: 14px;
            color: #334155;
            margin-bottom: 10px;
        }}
        .latex-block {{
            background: #ecfdf5;
            border: 1px solid #a7f3d0;
            border-radius: 6px;
            padding: 12px;
            font-size: 14px;
            overflow-x: auto;
        }}
        .final-answer {{
            background: #dcfce7;
            border: 2px solid #22c55e;
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
        }}
        .final-header {{
            font-weight: 600;
            color: #166534;
            margin-bottom: 8px;
            font-size: 16px;
        }}
        .final-content {{
            color: #15803d;
            font-size: 15px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📚 {title}</h1>
        <div class="metadata">
            PDF: {metadata.get('pdf_file', 'N/A')} | 
            Subject: {metadata.get('subject', 'N/A')} |
            Model: {metadata.get('model', 'N/A')}
        </div>
        <div class="stats">
            <span class="stat">📝 {total} solutions</span>
            <span class="stat">📊 {total_steps} total steps</span>
        </div>
    </div>
    
    {solutions_html}
    
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
    parser = argparse.ArgumentParser(description="Render solutions for visual inspection")
    parser.add_argument("json_file", help="Path to the solution output JSON (supports glob patterns)")
    parser.add_argument("question_id", nargs="?", default=None, help="Question ID to render (e.g., '12.4'). Omit for all.")
    parser.add_argument("--open", "-o", action="store_true", help="Open in browser automatically")
    parser.add_argument("--output", "-f", default=None, help="Output HTML file path")
    
    args = parser.parse_args()
    
    # Load JSON
    data = load_json(args.json_file)
    solutions = data.get('solutions', [])
    
    if not solutions:
        print("No solutions found in JSON!")
        return
    
    # Filter solutions
    if args.question_id:
        solutions_to_render = [s for s in solutions if s.get('question_id') == args.question_id]
        if not solutions_to_render:
            print(f"Solution for {args.question_id} not found. Available: {[s.get('question_id') for s in solutions]}")
            return
        title = f"Solution {args.question_id}"
    else:
        solutions_to_render = solutions
        title = "All Solutions"
    
    # Determine output path
    json_path = Path(args.json_file)
    if '*' in args.json_file:
        matches = sorted(glob.glob(args.json_file))
        json_path = Path(matches[-1])
    output_dir = json_path.parent
    
    # Generate HTML
    html_content = render_html(data, solutions_to_render, title)
    
    # Save HTML
    if args.output:
        html_path = Path(args.output)
    else:
        html_path = output_dir / f"test_solution_view_{json_path.stem}.html"
    
    html_path.write_text(html_content, encoding='utf-8')
    print(f"✅ Rendered {len(solutions_to_render)} solutions to: {html_path}")
    
    # Open in browser
    if args.open:
        webbrowser.open(f"file://{html_path.absolute()}")
        print("🌐 Opened in browser")


if __name__ == "__main__":
    main()
