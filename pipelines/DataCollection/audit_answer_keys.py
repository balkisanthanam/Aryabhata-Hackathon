"""
Read-only audit: exam_papers vs exam_answer_keys gap analysis.
Outputs a year/session summary and lists sessions with no AK.
"""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2

def get_connection():
    params = {
        'host':     os.getenv('DB_HOST', 'localhost'),
        'port':     os.getenv('DB_PORT', '5432'),
        'dbname':   os.getenv('DB_NAME', 'postgres'),
        'user':     os.getenv('DB_USER'),
    }
    password = os.getenv('DB_PASSWORD')
    if not password:
        from azure.identity import DefaultAzureCredential
        cred = DefaultAzureCredential()
        token = cred.get_token("https://ossrdbms-aad.database.windows.net/.default")
        params['password'] = token.token
        params['sslmode'] = 'require'
        print("+ Using Entra ID token")
    else:
        params['password'] = password
    return psycopg2.connect(**params)


def run_audit(cur):
    # -- 1. Papers per year -----------------------------------------------
    cur.execute("""
        SELECT year, COUNT(*) AS paper_count
        FROM exam_papers
        GROUP BY year
        ORDER BY year
    """)
    papers_by_year = {row[0]: row[1] for row in cur.fetchall()}

    # -- 2. Answer keys in DB ---------------------------------------------
    cur.execute("""
        SELECT year, session, key_type, blob_url, filename
        FROM exam_answer_keys
        ORDER BY year, session, key_type
    """)
    ak_rows = cur.fetchall()

    # -- 3. Unique paper dates per year (to derive session coverage) -------
    cur.execute("""
        SELECT year,
               MIN(dateofexam) AS earliest,
               MAX(dateofexam) AS latest,
               COUNT(DISTINCT dateofexam) AS distinct_dates,
               COUNT(*) AS total_rows
        FROM exam_papers
        GROUP BY year
        ORDER BY year
    """)
    paper_detail = {row[0]: row[1:] for row in cur.fetchall()}

    # -- 4. Sample papers per year (first 5 per year) ----------------------
    cur.execute("""
        SELECT year, dateofexam, shift, papername, blob_url
        FROM exam_papers
        ORDER BY year, dateofexam, shift
    """)
    all_papers = cur.fetchall()

    # -- 5. Answer key title audit (check for non-AK content) -------------
    cur.execute("""
        SELECT id, title, year, session, key_type, blob_url
        FROM exam_answer_keys
        ORDER BY year, session
    """)
    all_ak = cur.fetchall()

    return papers_by_year, paper_detail, all_papers, all_ak


def print_report(papers_by_year, paper_detail, all_papers, all_ak):
    print("\n" + "="*70)
    print("STEP 1 - ANSWER KEY AUDIT REPORT")
    print("="*70)

    # -- Papers summary ----------------------------------------------------
    print("\n-- exam_papers by year ------------------------------------------")
    print(f"{'Year':<6} {'Papers':>7} {'Dates':>7} {'Earliest':<12} {'Latest':<12}")
    print("-"*50)
    for year, count in sorted(papers_by_year.items()):
        earliest, latest, distinct_dates, total_rows = paper_detail[year]
        print(f"{year:<6} {count:>7} {distinct_dates:>7}    {str(earliest):<12} {str(latest):<12}")

    # -- Answer keys in DB -------------------------------------------------
    print("\n-- exam_answer_keys in DB ---------------------------------------")
    if not all_ak:
        print("  (table is empty)")
    else:
        print(f"{'ID':<5} {'Year':<6} {'Session':<15} {'Type':<12} {'Has blob?':<10} {'Title (truncated)'}")
        print("-"*80)
        for row in all_ak:
            id_, title, year, session, key_type, blob_url = row
            has_blob = "YES" if blob_url else "NO"
            title_short = (title or "")[:45]
            print(f"{id_:<5} {year:<6} {session:<15} {key_type:<12} {has_blob:<10} {title_short}")

    # -- Gap analysis ------------------------------------------------------
    ak_years = set(row[2] for row in all_ak)  # index 2 = year in all_ak
    paper_years = set(papers_by_year.keys())

    print("\n-- Gap analysis (years in exam_papers vs exam_answer_keys) ------")
    print(f"{'Year':<6} {'Papers':>7} {'AK rows':>8} {'Gap?'}")
    print("-"*35)
    all_years = sorted(paper_years | ak_years)
    for year in all_years:
        p_count = papers_by_year.get(year, 0)
        ak_count = sum(1 for row in all_ak if row[2] == year)
        gap = "!! NO AK" if ak_count == 0 else ("OK" if ak_count > 0 else "")
        print(f"{year:<6} {p_count:>7} {ak_count:>8}   {gap}")

    # -- Sample papers listing (useful for session detection) -------------
    print("\n-- All papers in exam_papers (sorted by year, date, shift) ------")
    print(f"{'Year':<6} {'Date':<12} {'Shift':<10} {'Blob?':<7} {'PaperName (truncated)'}")
    print("-"*70)
    prev_year = None
    for row in all_papers:
        year, dateofexam, shift, papername, blob_url = row
        if year != prev_year:
            print(f"  --- {year} ---")
            prev_year = year
        has_blob = "Y" if blob_url else "N"
        name_short = (papername or "")[:35]
        print(f"{year:<6} {str(dateofexam):<12} {str(shift or ''):<10} {has_blob:<7} {name_short}")

    print("\n" + "="*70)
    print("END OF AUDIT — no changes made")
    print("="*70 + "\n")


def main():
    print("Connecting to database...")
    try:
        conn = get_connection()
        cur = conn.cursor()
        print("+ Connected (read-only queries)\n")
        papers_by_year, paper_detail, all_papers, all_ak = run_audit(cur)
        print_report(papers_by_year, paper_detail, all_papers, all_ak)
        cur.close()
        conn.close()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
