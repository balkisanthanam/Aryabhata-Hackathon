import sys
import os
from audit_answer_keys import get_connection

def query_table(cur, table_name, columns, limit=5):
    query = f"SELECT {columns} FROM {table_name} LIMIT {limit};"
    print(f"\n--- {table_name} ---")
    try:
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error querying {table_name}: {e}")
        cur.connection.rollback()

def main():
    conn = get_connection()
    cur = conn.cursor()
    
    query_table(cur, "chapterdata", "chapterid, subject, class, chapternumber, chaptertitle", 5)
    query_table(cur, "exercisedata", "exerciseid, chapterid, exercise", 5)
    query_table(cur, "ncert_concept_hierarchy", "id, concept_title, chapter_id", 5)
    query_table(cur, "jee_question_bank", "id, subject, year, tier, source", 5)
    query_table(cur, "exam_papers", "id, year, shift, paper_format, extraction_status", 5)
    query_table(cur, "exam_answer_keys", "id, title, year, session", 5)
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
