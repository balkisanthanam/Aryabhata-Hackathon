import sys, os, json, psycopg2

# Try dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

host = os.environ.get("DB_HOST") or os.environ.get("AZURE_PG_HOST")
name = os.environ.get("DB_NAME") or os.environ.get("AZURE_PG_DATABASE")
user = os.environ.get("DB_USER") or os.environ.get("AZURE_PG_USER")
port = os.environ.get("DB_PORT") or os.environ.get("AZURE_PG_PORT", "5432")
password = os.environ.get("DB_PASSWORD") or os.environ.get("AZURE_PG_PASSWORD")

if not password:
    try:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        password = credential.get_token("https://ossrdbms-aad.database.windows.net/.default").token
    except Exception:
        pass
        
conn = psycopg2.connect(host=host, port=port, dbname=name, user=user, password=password, sslmode="require")
cur = conn.cursor()

queries = [
    ("Math_Golden", "SELECT q.content, q.solution FROM questiondata q JOIN exercisedata e ON q.exerciseid = e.exerciseid JOIN chapterdata c ON e.chapterid = c.chapterid WHERE c.class = '11' AND c.subject ILIKE 'Math%' AND c.chapterfulltitle ILIKE '%Trigonometric%' AND e.exercisetitle ILIKE '%3.1%' LIMIT 1"),
    ("Physics_Pedagogy", "SELECT q.content, q.solution FROM questiondata q JOIN exercisedata e ON q.exerciseid = e.exerciseid JOIN chapterdata c ON e.chapterid = c.chapterid WHERE c.class = '11' AND c.subject ILIKE 'Physics%' AND c.chapterfulltitle ILIKE '%THERMODYNAMICS%' AND (e.exercisetitle ILIKE '%11.1%' OR q.questionref ILIKE '%11.1%') LIMIT 1"),
    ("Physics_Drift", "SELECT q.content, q.solution FROM questiondata q JOIN exercisedata e ON q.exerciseid = e.exerciseid JOIN chapterdata c ON e.chapterid = c.chapterid WHERE c.class = '12' AND c.subject ILIKE 'Physics%' AND c.chapterfulltitle ILIKE '%CURRENT ELECTRICITY%' AND q.questionref ILIKE '%7%' LIMIT 1"),
    ("Chemistry_Hallucination", "SELECT q.content, q.solution FROM questiondata q JOIN exercisedata e ON q.exerciseid = e.exerciseid JOIN chapterdata c ON e.chapterid = c.chapterid WHERE c.class = '11' AND c.subject ILIKE 'Chemistry%' AND c.chapterfulltitle ILIKE '%BONDING%' AND q.questionref ILIKE '%14%' LIMIT 1")
]

results = {}
for name, q in queries:
    try:
        cur.execute(q)
        row = cur.fetchone()
        results[name] = {"content": row[0], "solution": row[1]} if row else None
    except Exception as e:
        print(f"Failed query for {name}: {e}")
        conn.rollback()
        results[name] = None
    
with open("example_payloads.json", "w") as f:
    json.dump(results, f, indent=2)
    
print("Saved to example_payloads.json")
