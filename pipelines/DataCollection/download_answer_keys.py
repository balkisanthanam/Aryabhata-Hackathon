import os
import re
import time
import random
import requests
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class AnswerKeyDownloader:
    ARCHIVE_URL = "https://jeemain.nta.nic.in/document-category/archive/"

    def __init__(self):
        self.download_dir = Path(os.getenv('DOWNLOAD_DIR', 'DataCollection/JEEMain_AnswerKeys'))
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.driver = None
        self.db_conn = None
        self.db_cursor = None
        self.db_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'aryabhatta'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', ''),
        }

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    def setup_driver(self):
        print("Setting up Chrome driver...")
        opts = Options()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        self.driver = webdriver.Chrome(options=opts)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        print("✓ Chrome driver ready")

    def connect_to_database(self) -> bool:
        try:
            print("Connecting to database...")
            conn_params = dict(self.db_params)
            if not conn_params.get('password'):
                from azure.identity import DefaultAzureCredential
                cred = DefaultAzureCredential()
                token = cred.get_token("https://ossrdbms-aad.database.windows.net/.default")
                conn_params['password'] = token.token
                conn_params['sslmode'] = 'require'
                print("✓ Using Entra ID token for database authentication")
            self.db_conn = psycopg2.connect(**conn_params)
            self.db_cursor = self.db_conn.cursor()
            print("✓ Database connection established")
            return True
        except Exception as e:
            print(f"✗ Database connection failed: {e}")
            return False

    def upload_to_blob(self, local_path: str, year: int) -> 'str | None':
        """Upload PDF to Azure Blob. Returns blob URL or None on failure."""
        try:
            import sys
            sys.path.insert(
                0, str(Path(__file__).parent.parent /
                        'ExtractionPipeline' / 'SchoolDataExtraction' / 'MultiStep'))
            from blob_client import get_blob_client
            client = get_blob_client()
            blob_path = f"jeedata/answer_keys/{year}/{Path(local_path).name}"
            blob_url = client.upload_image(
                Path(local_path), blob_path, content_type="application/pdf")
            print(f"✓ Uploaded to blob: {blob_url}")
            return blob_url
        except Exception as e:
            print(f"⚠ Blob upload failed (non-fatal): {e}")
            return None

    def _with_backoff(self, fn, max_retries=4, base_delay=2.0, max_delay=60.0):
        """Call fn() with exponential backoff + ±20% jitter."""
        last_exc = None
        for attempt in range(max_retries):
            try:
                return fn()
            except Exception as e:
                last_exc = e
                if attempt == max_retries - 1:
                    break
                delay = min(base_delay * (2 ** attempt), max_delay)
                delay *= (0.8 + 0.4 * random.random())
                print(f"⚠ Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
        raise last_exc

    # ------------------------------------------------------------------
    # Title classification
    # ------------------------------------------------------------------

    def classify_title(self, title: str) -> 'dict | None':
        """
        Returns {year, session, key_type} if title is a relevant B.Tech answer key.
        Returns None if title should be skipped.
        """
        t = title.lower()

        if 'answer key' not in t:
            return None

        # Skip B.Arch / Planning papers
        if any(kw in t for kw in ['paper-2', 'paper 2', 'b.arch', 'b.planning', 'architecture', 'planning']):
            return None

        # Must contain a recognisable year
        year_match = re.search(r'\b(20\d{2})\b', title)
        if not year_match:
            return None
        year = int(year_match.group(1))

        key_type = 'PROVISIONAL' if 'provisional' in t else 'FINAL'

        # Session identifier
        session_match = re.search(r'session[- ]?(\d+)', t)
        if session_match:
            session = f"Session {session_match.group(1)}"
        else:
            month_match = re.search(
                r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b', t)
            session = month_match.group(1).upper() if month_match else 'All'

        return {'year': year, 'session': session, 'key_type': key_type}

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------

    def _get_pdf_url_from_row(self, row) -> 'str | None':
        """Extract the direct PDF URL from a table row's View link."""
        try:
            # "View" link is the first <a> in the View/Download cell
            links = row.find_elements(By.TAG_NAME, 'a')
            for link in links:
                href = link.get_attribute('href') or ''
                if href.lower().endswith('.pdf') or 'pdf' in href.lower():
                    return href
                # Sometimes the link text says "View" and href is the viewer URL
                text = link.text.strip().lower()
                if text == 'view' and href:
                    return href
            # Fall back: any <a> with a non-empty href
            for link in links:
                href = link.get_attribute('href') or ''
                if href.startswith('http'):
                    return href
            return None
        except Exception:
            return None

    def scrape_all_entries(self) -> list:
        """
        Navigate archive, filter by 'answer key', paginate all pages.
        Returns list of dicts: {title, pdf_url, year, session, key_type}.
        """
        print(f"Navigating to: {self.ARCHIVE_URL}")
        self.driver.get(self.ARCHIVE_URL)
        time.sleep(3)
        # No filter applied — the archive uses a category <select> dropdown with no Answer Keys category.
        # classify_title() handles all filtering per-row.

        entries = []
        page = 1
        while True:
            print(f"  Scraping page {page}...")
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))
            except Exception:
                print("  ⚠ No table rows found on this page")
                break

            rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, 'td')
                if not cells:
                    continue
                title = cells[0].text.strip()
                if not title:
                    continue

                meta = self.classify_title(title)
                if meta is None:
                    continue

                pdf_url = self._get_pdf_url_from_row(row)
                if not pdf_url:
                    print(f"  ⚠ No PDF URL found for: {title}")
                    continue

                entry = {**meta, 'title': title, 'pdf_url': pdf_url}
                entries.append(entry)
                print(f"  ✓ Found: [{meta['key_type']}] {meta['year']} {meta['session']} — {title}")

            # Pagination: look for Next link
            try:
                next_link = self.driver.find_element(
                    By.XPATH, "//a[contains(text(),'Next')]")
                next_link.click()
                time.sleep(2)
                page += 1
            except Exception:
                print(f"  No more pages (stopped at page {page})")
                break

        print(f"\nTotal relevant entries found: {len(entries)}")
        return entries

    # ------------------------------------------------------------------
    # Deduplication: prefer FINAL over PROVISIONAL for same (year, session)
    # ------------------------------------------------------------------

    def deduplicate(self, entries: list) -> list:
        """
        For each (year, session) group, if a FINAL key exists drop any PROVISIONAL.
        """
        groups: dict = {}
        for e in entries:
            key = (e['year'], e['session'])
            groups.setdefault(key, []).append(e)

        result = []
        for (year, session), group in groups.items():
            has_final = any(e['key_type'] == 'FINAL' for e in group)
            for e in group:
                if has_final and e['key_type'] == 'PROVISIONAL':
                    print(f"  ⏭ Skipping PROVISIONAL (FINAL exists): {year} {session}")
                    continue
                result.append(e)
        return result

    # ------------------------------------------------------------------
    # Download + store
    # ------------------------------------------------------------------

    def _download_pdf(self, pdf_url: str, dest_path: Path):
        """Download PDF from URL to dest_path using requests."""
        resp = requests.get(pdf_url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

    def _safe_filename(self, title: str, year: int) -> str:
        """Convert title to a safe filename."""
        safe = re.sub(r'[<>:"/\\|?*]', '_', title)
        safe = re.sub(r'\s+', '_', safe).strip('_')
        safe = safe[:150]
        return f"{safe}.pdf"

    def download_and_store(self, entry: dict):
        year = entry['year']
        year_dir = self.download_dir / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        filename = self._safe_filename(entry['title'], year)
        dest_path = year_dir / filename

        if dest_path.exists():
            print(f"  ↩ Already downloaded: {filename}")
            blob_url = self.upload_to_blob(str(dest_path), year)
        else:
            print(f"  ↓ Downloading: {entry['title']}")
            try:
                self._with_backoff(
                    lambda: self._download_pdf(entry['pdf_url'], dest_path))
                print(f"  ✓ Saved: {dest_path}")
                blob_url = self.upload_to_blob(str(dest_path), year)
            except Exception as e:
                print(f"  ✗ Download failed after retries: {e}")
                blob_url = None

        self.insert_record(
            title=entry['title'],
            year=year,
            session=entry['session'],
            key_type=entry['key_type'],
            filename=filename,
            blob_url=blob_url,
        )

    def insert_record(self, title, year, session, key_type, filename, blob_url):
        if not self.db_conn:
            return
        try:
            query = """
                INSERT INTO exam_answer_keys
                    (title, year, session, key_type, filename, blob_url, extraction_status)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')
                ON CONFLICT (year, session, key_type) DO UPDATE
                    SET blob_url = EXCLUDED.blob_url,
                        filename = EXCLUDED.filename
                    WHERE exam_answer_keys.blob_url IS NULL
            """
            self.db_cursor.execute(
                query, (title, year, session, key_type, filename, blob_url))
            self.db_conn.commit()
            print(f"  ✓ DB record saved for {year} {session} [{key_type}]")
        except Exception as e:
            print(f"  ✗ DB insert failed: {e}")
            self.db_conn.rollback()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self):
        try:
            self.setup_driver()
            self.connect_to_database()

            all_entries = self.scrape_all_entries()

            # Filter by YEARS_TO_DOWNLOAD if set
            years_override = os.getenv('YEARS_TO_DOWNLOAD', '').strip()
            if years_override:
                years_filter = {
                    int(y) for y in years_override.split(',')
                    if y.strip().isdigit()
                }
                before = len(all_entries)
                all_entries = [e for e in all_entries if e['year'] in years_filter]
                print(f"✓ YEARS_TO_DOWNLOAD filter: {before} → {len(all_entries)} entries "
                      f"(keeping {sorted(years_filter)})")

            entries = self.deduplicate(all_entries)
            print(f"\nDownloading {len(entries)} answer key(s)...\n")

            for i, entry in enumerate(entries, 1):
                print(f"[{i}/{len(entries)}] {entry['year']} {entry['session']} "
                      f"[{entry['key_type']}]")
                self.download_and_store(entry)
                time.sleep(1)

            print("\n✓ All done.")
        finally:
            if self.driver:
                self.driver.quit()
            if self.db_conn:
                self.db_conn.close()


def main():
    AnswerKeyDownloader().run()


if __name__ == "__main__":
    main()
