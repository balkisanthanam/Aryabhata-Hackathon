import sys
import os
from pathlib import Path
import psycopg2
from azure.identity import DefaultAzureCredential

cmd_dir = Path(__file__).resolve().parent
sys.path.append(str(cmd_dir.parent))
from db_writer import JEEExtractionDBWriter

def main():
    writer = JEEExtractionDBWriter()
    with writer.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE jee_question_bank ADD COLUMN IF NOT EXISTS evaluator_score JSONB;")
            cur.execute("ALTER TABLE jee_question_bank ADD COLUMN IF NOT EXISTS retry_count INT DEFAULT 0;")
            conn.commit()
    print("Migration successful: added evaluator_score and retry_count.")

if __name__ == "__main__":
    main()
