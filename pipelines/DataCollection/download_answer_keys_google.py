"""
Google-Driven NTA Answer Key Downloader
========================================
Downloads NTA JEE Main answer key PDFs by:
  1. Scraping the NTA Notice Board Archive (primary, no browser needed)
  2. Falling back to DuckDuckGo search for CDN-hosted 2022/2023 PDFs

DRY_RUN = True  (default) -- searches and validates PDFs but does NOT
                              download to blob or write to DB.
Set DRY_RUN = False only after confirming a successful dry run.

Usage:
    python download_answer_keys_google.py

See ANSWER_KEY_DOWNLOAD_PLAN.md for full design rationale.
"""

import os
import re
import sys
import time
import tempfile
import urllib.parse
import requests
import psycopg2

# Force UTF-8 output on Windows (avoids cp1252 errors with PDF text previews)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# =============================================================================
# CONFIGURATION
# =============================================================================

DRY_RUN = True   # <-- NEVER set to False without explicit user confirmation

NTA_NOTICE_BOARD_URL = "https://www.nta.ac.in/NoticeBoardArchive"
NTA_BASE_URL = "https://nta.ac.in"

# Valid NTA PDF URL patterns (both nta.ac.in and NIC CDN)
NTA_URL_PATTERNS = [
    re.compile(r'https?://(?:www\.)?nta\.ac\.in/Download/Notice/Notice_\d+\.pdf', re.I),
    re.compile(r'https?://cdnbbsr\.s3waas\.gov\.in/\S+\.pdf', re.I),
]

# Q ID validation: PDFs must have numeric IDs of 6+ digits.
# 2024/2025 use 10-11 digit NTA IDs; 2022 uses 6-digit sequential IDs (100001, etc.)
QID_PATTERN = re.compile(r'\b\d{6,}\b')
AK_HEADER_KEYWORDS = [
    'QUESTION ID', 'CORRECT OPTION ID', 'QUESTION\nID', 'CORRECT\nOPTION',
]

# HTTP headers for web requests
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}

# High-priority sessions (confirmed in gap analysis)
TARGET_SESSIONS = [
    {
        "year": 2022,
        "session": "Session 1",
        "label": "2022 Session 1 (Jun 24-30)",
        "key_type_expected": "FINAL",
        # NTA notice board has only PROVISIONAL notices for 2022 S1;
        # FINAL AK is on NIC CDN — use DDG fallback
        "noticeboard_keywords": ["jee", "2022", "session 1", "answer key"],
        "noticeboard_final_only": False,  # accept provisional if no final
        "ddg_fallback_queries": [
            "jee main june 2022 session 1 btech answer key cdnbbsr",
            "jee main 2022 session 1 btech final answer key cdnbbsr filetype:pdf",
        ],
        "replace_row_ids": [4],  # id=4: bad PROVISIONAL notice row
    },
    {
        "year": 2022,
        "session": "Session 2",
        "label": "2022 Session 2 (Jul 25-30)",
        "key_type_expected": "FINAL",
        # 2022 S2 confirmed CDN URL from prior investigation + DDG
        "noticeboard_keywords": ["jee", "2022", "session 2", "answer key"],
        "noticeboard_final_only": False,
        "ddg_fallback_queries": [
            "jee main july 2022 session 2 btech answer key cdnbbsr filetype:pdf",
            "jee main 2022 session 2 btech final answer key cdnbbsr",
        ],
        "replace_row_ids": [3],  # id=3: PROVISIONAL notice row
    },
    {
        "year": 2024,
        "session": "Session 1",
        "label": "2024 Session 1 (Jan 27-Feb 1)",
        "key_type_expected": "FINAL",
        # Notice_20240212120843.pdf confirmed in prior investigation
        "noticeboard_keywords": ["jee", "main", "2024", "session 1", "answer key", "b.e"],
        "noticeboard_final_only": True,
        "ddg_fallback_queries": [
            "jee main 31st jan 2024 shift 1 answer key filetype:pdf site:nta.ac.in",
            "jee main 2024 session 1 btech final answer key filetype:pdf",
        ],
        "replace_row_ids": [],
    },
    {
        "year": 2024,
        "session": "Session 2",
        "label": "2024 Session 2 (Apr 4-9)",
        "key_type_expected": "FINAL",
        # Notice_20240424132602.pdf confirmed in prior investigation
        "noticeboard_keywords": ["jee", "main", "2024", "session 2", "answer key"],
        "noticeboard_final_only": True,
        "ddg_fallback_queries": [
            "jee main april 2024 session 2 btech final answer key filetype:pdf",
        ],
        "replace_row_ids": [],
    },
    {
        "year": 2025,
        "session": "Session 1",
        "label": "2025 Session 1 (Jan 22-28)",
        "key_type_expected": "FINAL",
        # Notice_20250210115032.pdf confirmed in prior investigation
        "noticeboard_keywords": ["jee", "main", "2025", "session", "1", "answer key", "b.e"],
        "noticeboard_final_only": True,
        "ddg_fallback_queries": [
            "jee main 2025 session 1 btech final answer key filetype:pdf",
        ],
        "replace_row_ids": [],
    },
    {
        "year": 2025,
        "session": "Session 2",
        "label": "2025 Session 2 (Apr 2-8)",
        "key_type_expected": "FINAL",
        # NTA Notice Board only has provisional AK (image-based) for Session 2 B.Tech.
        # No FINAL B.Tech AK found in archive as of March 2026 — DDG fallback as last resort.
        "noticeboard_keywords": ["jee", "main", "2025", "session 2", "answer key", "b.e"],
        "noticeboard_final_only": False,  # accept provisional if no final
        "ddg_fallback_queries": [
            "jee main april 2025 session 2 btech answer key cdnbbsr filetype:pdf",
            "jee main 2025 session 2 btech final answer key nta",
        ],
        "replace_row_ids": [],
    },
]


# =============================================================================
# NTA NOTICE BOARD SCRAPER (primary source)
# =============================================================================

_notice_board_entries = None  # cached after first fetch


def fetch_notice_board() -> list:
    """
    Parse the NTA Notice Board Archive page and return a list of dicts:
      {title, url, ts}  where url is the full PDF URL.
    Cached after first call.
    """
    global _notice_board_entries
    if _notice_board_entries is not None:
        return _notice_board_entries

    print("[NTA] Fetching notice board archive...")
    resp = requests.get(NTA_NOTICE_BOARD_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text
    print(f"[NTA] Archive fetched ({len(html):,} bytes)")

    block_pattern = re.compile(
        r'<content[^>]*>(.*?)</content>.*?href=\"(/Download/Notice/Notice_(\d+)\.pdf)\"',
        re.DOTALL | re.I
    )

    entries = []
    for title_raw, pdf_path, ts in block_pattern.findall(html):
        title = re.sub(r'<[^>]+>', '', title_raw)
        title = title.replace('&nbsp;', ' ').replace('&#160;', ' ')
        title = re.sub(r'\s+', ' ', title).strip()
        url = NTA_BASE_URL + pdf_path
        entries.append({'title': title, 'url': url, 'ts': ts})

    print(f"[NTA] Parsed {len(entries)} notice entries")
    _notice_board_entries = entries
    return entries


def search_notice_board(keywords: list, year: int, final_only: bool) -> list:
    """
    Filter notice board entries by year and all keywords (case-insensitive).
    If final_only, prefer entries with 'final' in title; fall back to any match.
    Returns list of matching {title, url} dicts, best match first.
    """
    entries = fetch_notice_board()
    year_str = str(year)

    # Filter: must contain year and all keywords
    kw_lower = [k.lower() for k in keywords]
    candidates = []
    for e in entries:
        t = e['title'].lower()
        if year_str not in t:
            continue
        if all(k in t for k in kw_lower):
            candidates.append(e)

    if not candidates:
        return []

    # Sort: FINAL entries first, then by timestamp desc (newest first)
    def sort_key(e):
        is_final = 1 if 'final' in e['title'].lower() else 0
        return (-is_final, -int(e['ts']))

    candidates.sort(key=sort_key)

    if final_only:
        finals = [c for c in candidates if 'final' in c['title'].lower()]
        return finals if finals else candidates
    return candidates


# =============================================================================
# DUCKDUCKGO FALLBACK (for CDN-hosted 2022/2023 PDFs)
# =============================================================================

def ddg_search(query: str) -> list:
    """
    Search DuckDuckGo HTML interface and return NTA/CDN PDF URLs found.
    """
    print(f"  [DDG] {query}")
    url = 'https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(query)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    uddg_raw = re.findall(r'uddg=([^&"]+)', resp.text)
    decoded = [urllib.parse.unquote(u) for u in uddg_raw]

    nta_urls = []
    seen = set()
    for u in decoded:
        for pat in NTA_URL_PATTERNS:
            if pat.match(u) and u not in seen:
                nta_urls.append(u)
                seen.add(u)
                break

    if nta_urls:
        print(f"  [DDG] Found: {nta_urls}")
    else:
        print(f"  [DDG] No NTA PDF URLs found")

    return nta_urls


# =============================================================================
# PDF VALIDATION
# =============================================================================

def validate_ak_pdf(url: str, year: int) -> dict:
    """
    Download PDF to a temp file and validate page 1 has NTA Q IDs.
    Returns dict: {valid, url, local_path, page_count, reason, q_id_sample, title_page1}
    """
    result = {
        'valid': False, 'url': url, 'local_path': None,
        'page_count': 0, 'reason': '', 'q_id_sample': [],
        'title_page1': '',
    }
    try:
        resp = requests.get(url, stream=True, timeout=30, headers=HEADERS)
        resp.raise_for_status()

        suffix = '.pdf'
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in resp.iter_content(8192):
                tmp.write(chunk)
            result['local_path'] = tmp.name

        import fitz
        doc = fitz.open(result['local_path'])
        result['page_count'] = doc.page_count

        # Scan first up to 3 pages (page 1 may be a header/cover page)
        pages_to_check = min(3, doc.page_count)
        combined_text = ''
        first_nonempty_text = ''
        for page_idx in range(pages_to_check):
            page_text = doc[page_idx].get_text()
            combined_text += page_text
            if not first_nonempty_text and page_text.strip():
                first_nonempty_text = page_text
        doc.close()

        if not combined_text.strip():
            result['reason'] = f'Pages 1-{pages_to_check} all empty (image-based PDF)'
            return result

        # Extract a title hint from first non-empty page
        lines = [l.strip() for l in first_nonempty_text.split('\n') if l.strip()]
        result['title_page1'] = ' | '.join(lines[:4])[:120]

        # Check for AK header keywords
        has_header = any(kw in combined_text for kw in AK_HEADER_KEYWORDS)

        # Check for 6+ digit Q IDs (2022 uses 6-digit sequential; 2024/2025 use 10-11 digit NTA IDs)
        q_ids = QID_PATTERN.findall(combined_text)

        if not has_header:
            result['reason'] = (
                f'No AK header in pages 1-{pages_to_check} (text: {first_nonempty_text[:80].strip()!r})'
            )
            return result

        if len(q_ids) < 3:
            result['reason'] = (
                f'Too few Q IDs in pages 1-{pages_to_check} ({len(q_ids)} found, need >=3)'
            )
            return result

        result['valid'] = True
        result['q_id_sample'] = q_ids[:3]
        result['reason'] = (
            f'OK — {len(q_ids)} Q IDs on page 1 | '
            f'{result["page_count"]} pages | '
            f'first ID: {q_ids[0]}'
        )
        return result

    except requests.exceptions.HTTPError as e:
        result['reason'] = f'HTTP {e.response.status_code}: {url}'
    except Exception as e:
        result['reason'] = f'Error: {type(e).__name__}: {e}'
    return result


# =============================================================================
# BLOB UPLOAD
# =============================================================================

def upload_to_blob(local_path: str, year: int, nta_filename: str) -> 'str | None':
    """Upload PDF to blob storage using the original NTA filename (not the temp file name)."""
    try:
        sys.path.insert(0, str(
            Path(__file__).parent.parent /
            'ExtractionPipeline' / 'SchoolDataExtraction' / 'MultiStep'))
        from blob_client import get_blob_client
        client = get_blob_client()
        blob_path = f"jeedata/answer_keys/{year}/{nta_filename}"
        blob_url = client.upload_image(
            Path(local_path), blob_path, content_type="application/pdf")
        print(f"  [BLOB] Uploaded: {blob_url}")
        return blob_url
    except Exception as e:
        print(f"  [BLOB] Upload failed: {e}")
        return None


# =============================================================================
# DATABASE
# =============================================================================

def get_connection():
    params = {
        'host':   os.getenv('DB_HOST', 'localhost'),
        'port':   os.getenv('DB_PORT', '5432'),
        'dbname': os.getenv('DB_NAME', 'postgres'),
        'user':   os.getenv('DB_USER'),
    }
    password = os.getenv('DB_PASSWORD')
    if not password:
        from azure.identity import DefaultAzureCredential
        cred = DefaultAzureCredential()
        token = cred.get_token("https://ossrdbms-aad.database.windows.net/.default")
        params['password'] = token.token
        params['sslmode'] = 'require'
        print("  [DB] Using Entra ID token")
    else:
        params['password'] = password
    return psycopg2.connect(**params)


def null_out_bad_row(conn, row_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE exam_answer_keys SET blob_url = NULL "
            "WHERE id = %s AND blob_url IS NOT NULL",
            (row_id,)
        )
        affected = cur.rowcount
    conn.commit()
    print(f"  [DB] Nulled blob_url on row id={row_id} (rows affected: {affected})")


def upsert_answer_key(conn, title: str, year: int, session: str,
                      key_type: str, blob_url: str, filename: str):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO exam_answer_keys
                (title, year, session, key_type, blob_url, filename, extraction_status)
            VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')
            ON CONFLICT (year, session, key_type) DO UPDATE
                SET blob_url   = EXCLUDED.blob_url,
                    filename   = EXCLUDED.filename,
                    title      = EXCLUDED.title
                WHERE exam_answer_keys.blob_url IS NULL
        """, (title, year, session, key_type, blob_url, filename))
        affected = cur.rowcount
    conn.commit()
    print(f"  [DB] Upserted {year} {session} [{key_type}] (rows affected: {affected})")


# =============================================================================
# MAIN PIPELINE PER SESSION
# =============================================================================

def find_candidates(session_cfg: dict) -> list:
    """
    Step 1: collect candidate NTA PDF URLs for this session.
    Primary: NTA Notice Board. Fallback: DuckDuckGo.
    Returns list of {'url': ..., 'source': ..., 'notice_title': ...}
    """
    year = session_cfg['year']
    label = session_cfg['label']
    candidates = []

    # --- Primary: NTA Notice Board ---
    nb_results = search_notice_board(
        keywords=session_cfg['noticeboard_keywords'],
        year=year,
        final_only=session_cfg['noticeboard_final_only'],
    )
    if nb_results:
        print(f"  [NTA board] {len(nb_results)} match(es):")
        for r in nb_results[:3]:
            print(f"    {r['ts']}: {r['title'][:90]}")
            print(f"    -> {r['url']}")
        for r in nb_results[:3]:  # try top 3 matches
            candidates.append({
                'url': r['url'],
                'source': 'NTA_NOTICEBOARD',
                'notice_title': r['title'],
            })
    else:
        print(f"  [NTA board] No matches for {label}")

    # --- Fallback: DuckDuckGo ---
    if not candidates or year in (2022, 2023):
        # Always run DDG for 2022/2023 since the real AK may be on CDN
        ddg_queries = session_cfg.get('ddg_fallback_queries', [])
        for q in ddg_queries[:2]:  # max 2 DDG queries per session
            ddg_urls = ddg_search(q)
            for u in ddg_urls:
                if not any(c['url'] == u for c in candidates):
                    candidates.append({
                        'url': u,
                        'source': 'DDG',
                        'notice_title': '',
                    })
            if ddg_urls:
                break  # found something, stop trying queries
            time.sleep(0.5)

    return candidates


def process_session(session_cfg: dict, conn, results: list) -> dict:
    label = session_cfg['label']
    year = session_cfg['year']
    session = session_cfg['session']
    key_type = session_cfg['key_type_expected']

    outcome = {
        'label': label,
        'year': year,
        'session': session,
        'status': 'NOT_FOUND',
        'url_found': None,
        'notice_title': None,
        'validation': None,
        'dry_run': DRY_RUN,
    }

    print(f"\n{'='*60}")
    print(f"SESSION: {label}")
    print(f"{'='*60}")

    candidates = find_candidates(session_cfg)

    if not candidates:
        print(f"  [RESULT] No candidate URLs found")
        results.append(outcome)
        return outcome

    # Validate each candidate until one passes
    for cand in candidates:
        url = cand['url']
        print(f"  [VALIDATE] {url}")
        val = validate_ak_pdf(url, year)
        outcome['url_found'] = url
        outcome['notice_title'] = cand.get('notice_title', '')
        outcome['validation'] = val

        if val['valid']:
            print(f"  [VALID] {val['reason']}")
            print(f"  [PAGE1] {val['title_page1']}")
            print(f"  [Q IDs] {val['q_id_sample']}")

            if DRY_RUN:
                print(f"  [DRY RUN] Would upload to blob and upsert DB — skipped")
                outcome['status'] = 'DRY_RUN_VALID'
            else:
                for row_id in session_cfg.get('replace_row_ids', []):
                    null_out_bad_row(conn, row_id)
                filename = Path(url.split('?')[0]).name
                blob_url = upload_to_blob(val['local_path'], year, filename)
                title = cand.get('notice_title') or f"JEE Main {year} {session} AK (via NTA search)"
                upsert_answer_key(conn, title, year, session, key_type, blob_url, filename)
                outcome['status'] = 'INSERTED'

            break  # done with this session
        else:
            print(f"  [REJECT] {val['reason']}")
            outcome['status'] = 'VALIDATION_FAILED'

    results.append(outcome)
    return outcome


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    print("=" * 60)
    print("NTA Answer Key Downloader (Notice Board + DDG)")
    print(f"Mode: {'DRY RUN (no writes)' if DRY_RUN else '*** LIVE — WRITES ENABLED ***'}")
    print(f"Sessions: {len(TARGET_SESSIONS)}")
    print("=" * 60)

    conn = None
    if not DRY_RUN:
        print("\nConnecting to database...")
        conn = get_connection()
        print("  Connected")

    results = []
    try:
        for session_cfg in TARGET_SESSIONS:
            process_session(session_cfg, conn, results)
            time.sleep(0.5)
    finally:
        if conn:
            conn.close()

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"{'Session':<35} {'Status':<20} {'Pg':>3}  {'First Q ID':<14}  Source")
    print("-" * 90)
    for r in results:
        val = r.get('validation') or {}
        pages = str(val.get('page_count', '-'))
        qid = (val.get('q_id_sample') or ['-'])[0]
        url = r.get('url_found') or ''
        src = 'NTA' if 'nta.ac.in' in url else ('CDN' if 'cdnbbsr' in url else '-')
        print(f"{r['label']:<35} {r['status']:<20} {pages:>3}  {str(qid):<14}  {src}")

    print(f"\nDry run: {DRY_RUN}")
    return results


if __name__ == "__main__":
    main()
