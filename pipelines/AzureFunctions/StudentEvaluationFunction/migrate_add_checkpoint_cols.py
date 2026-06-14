"""One-time migration: add pipeline_steps and current_step columns."""
from utils.db import _get_connection

conn = _get_connection()
cur = conn.cursor()

cur.execute("""
    ALTER TABLE solution_evaluations
        ADD COLUMN IF NOT EXISTS pipeline_steps JSONB NULL,
        ADD COLUMN IF NOT EXISTS current_step VARCHAR(100) NULL;
""")
conn.commit()
print("Columns added successfully")

cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'solution_evaluations'
    AND column_name IN ('pipeline_steps', 'current_step')
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

cur.close()
conn.close()
