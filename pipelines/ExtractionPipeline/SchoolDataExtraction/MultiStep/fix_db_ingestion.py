"""
Quick fix script to push existing solutions from JSON to database.
Use when pipeline completed Stage 2 but DB ingestion was skipped.
"""
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from e2e_pipeline import E2EPipeline, PipelineState

def fix_db_ingestion(pdf_name: str):
    """Push solutions from JSON to database for a specific PDF."""
    output_dir = Path(__file__).parent / "Output"
    
    # Load state
    state_path = output_dir / f"{pdf_name}_pipeline_state.json"
    if not state_path.exists():
        print(f"ERROR: State file not found: {state_path}")
        return False
    
    state = PipelineState.load(state_path)
    print(f"Loaded state for {pdf_name}")
    print(f"  Chapter: {state.chapter_number}")
    print(f"  Questions: {len(state.question_ids)}")
    print(f"  Solved: {len(state.solved_questions)}")
    print(f"  DB Ingestion Complete: {state.db_ingestion_complete}")
    
    # Load solutions
    solutions_path = output_dir / f"{pdf_name}_solutions.json"
    if not solutions_path.exists():
        print(f"ERROR: Solutions file not found: {solutions_path}")
        return False
    
    with open(solutions_path, 'r', encoding='utf-8') as f:
        solutions_data = json.load(f)
    
    solution_count = len(solutions_data.get("solutions", []))
    print(f"  Solutions in JSON: {solution_count}")
    
    if solution_count == 0:
        print("ERROR: No solutions in JSON file")
        return False
    
    # Create pipeline instance
    pipeline = E2EPipeline(local_only=False)
    
    # Push solutions to DB
    print("\nPushing solutions to database...")
    pipeline._update_solutions_from_json(solutions_data, state)
    
    # Mark as complete
    state.db_ingestion_complete = True
    state.save(state_path)
    
    print(f"✅ DB ingestion complete for {pdf_name}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_db_ingestion.py <pdf_name>")
        print("Example: python fix_db_ingestion.py kech104")
        sys.exit(1)
    
    pdf_name = sys.argv[1]
    success = fix_db_ingestion(pdf_name)
    sys.exit(0 if success else 1)
