"""
Inspect & Evaluate Pipeline
Reads recently generated (UNVERIFIED or PENDING_HUMAN_REVIEW) JSON solutions from the DB 
and displays them cleanly using 
ich. Allows manual triage of edge cases.
"""

import sys
from pathlib import Path
import json

# Setup paths
cwd = Path(__file__).resolve().parent
project_root = cwd.parent.parent
extraction_dir = project_root / "pipelines" / "ExtractionPipeline" / "SchoolDataExtraction" / "MultiStep"
sys.path.insert(0, str(extraction_dir))

from db_writer import JEEExtractionDBWriter

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.syntax import Syntax
    from rich.markdown import Markdown
except ImportError:
    print("This CLI requires 'rich'. Please install it: pip install rich")
    sys.exit(1)

console = Console()

def mark_status(db_writer: JEEExtractionDBWriter, question_id: int, new_status: str):
    query = """
        UPDATE jee_question_bank 
        SET review_status = %s 
        WHERE id = %s
    """
    with db_writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (new_status, question_id))
        conn.commit()

def main():
    db_writer = JEEExtractionDBWriter()
    
    # Target anything awaiting review
    query = """
        SELECT id, subject, nta_question_id, question_content, solution, answer_key 
        FROM jee_question_bank 
        WHERE is_generated = TRUE AND review_status IN ('UNVERIFIED', 'PENDING_HUMAN_REVIEW')
        ORDER BY id ASC
        LIMIT 50
    """
    
    with db_writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            columns = [desc[0] for desc in cur.description]
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]
            
    if not rows:
        console.print("[green]No matching generations found in the DB. Queue is clear![/green]")
        return

    console.print(f"[bold cyan]Found {len(rows)} generations awaiting review.[/bold cyan]\n")
    
    for idx, r in enumerate(rows, 1):
        q_id = r['id']
        nta_id = r['nta_question_id']
        subject = r['subject']
        
        qc = r['question_content'] or {}
        sol = r['solution'] or {}
        ans_key = r['answer_key']
        
        # Format the question and extracted options
        problem_text = qc.get('raw_text', 'No text found.')
        
        # Add options if they exist in question_content
        options = qc.get('options', [])
        if options:
            problem_text += "\n\n**Options:**\n"
            for i, opt in enumerate(options):
                opt_letter = chr(65 + i) # Map 0,1,2,3 to A,B,C,D
                opt_text = opt.get('text', 'No text')
                
                # Check if it has a specific NTA ID attached, appending gently if present but relying on ABCD for main label
                opt_id_str = f" (ID: {opt.get('option_id')})" if opt.get('option_id') else ""
                problem_text += f"- [{opt_letter}] {opt_text}{opt_id_str}\n"
                
        # Add the ground truth answer key to the problem panel
        if ans_key:
            problem_text += f"\n\n**Official Answer Key:** `{ans_key}`"
            
        q_panel = Panel(Markdown(problem_text), title=f"Question ID: {q_id} (NTA: {nta_id}) | {subject} | {idx}/{len(rows)}", border_style="cyan")
        
        # Format the solution
        sol_content = []
        if 'steps' in sol:
            for step in sol['steps']:
                step_num = step.get('step_number', '?')
                step_text = step.get('explanation', '')
                formula = step.get('formula', '')
                sol_content.append(f"**Step {step_num}**: {step_text}")
                if formula:
                    sol_content.append(f"> {formula}")
        
        if 'final_answer' in sol:
            gen_ans = sol.get('final_answer')
            sol_content.append(f"\n**Final Answer**: {gen_ans}")
            
            # Simple visual check if it matches the answer key
            if ans_key and str(ans_key) in str(gen_ans):
                sol_content.append("\n✅ **Looks like a Match!** The official key is present in the final answer.")
            elif ans_key:
                sol_content.append("\n❌ **Possible Mismatch!** Ensure you verify manually.")
            
        sol_markdown = "\n".join(sol_content)
        s_panel = Panel(Markdown(sol_markdown), title="[bold yellow]Generated Solution[/bold yellow]", border_style="yellow")

        # Layout
        console.clear()
        console.print(q_panel)
        console.print(s_panel)
        
        # Raw JSON option if needed
        json_syntax = Syntax(json.dumps(sol, indent=2), "json", theme="monokai", line_numbers=False)
        
        console.print("\n[bold cyan]Options:[/bold cyan]")
        console.print("[green]a[/green] - Approve (Mark as APPROVED_GOLD)")
        console.print("[red]r[/red] - Reject / Rewrite (Mark as NEEDS_REWRITE)")
        console.print("[yellow]v[/yellow] - View Raw JSON")
        console.print("[white]s[/white] - Skip")
        console.print("[red]q[/red] - Quit")
        
        while True:
            choice = Prompt.ask("Action", choices=["a", "r", "v", "s", "q"], default="a")
            if choice == 'v':
                console.print(json_syntax)
                continue
            elif choice == 'a':
                mark_status(db_writer, q_id, 'APPROVED_GOLD')
                console.print(f"[green]✓ Marked Q {q_id} as APPROVED_GOLD[/green]")
                break
            elif choice == 'r':
                mark_status(db_writer, q_id, 'NEEDS_REWRITE')
                console.print(f"[red]✗ Marked Q {q_id} as NEEDS_REWRITE[/red]")
                break
            elif choice == 's':
                console.print("[yellow]Skipped.[/yellow]")
                break
            elif choice == 'q':
                console.print("[bold red]Exiting review tool...[/bold red]")
                return

if __name__ == '__main__':
    main()
