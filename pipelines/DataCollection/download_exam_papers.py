import os
import time
import requests
from datetime import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import psycopg2
from psycopg2.extras import execute_values
import re

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Continue without .env support

class ExamPaperDownloader:
    def __init__(self, download_dir="DataCollection/JEEMain", base_url="https://www.nta.ac.in/Downloads"):
        """
        Initialize the exam paper downloader
        
        Args:
            download_dir (str): Directory to save downloaded PDFs
            base_url (str): Base URL of the downloads page
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url
        self.driver = None
        self.db_conn = None
        self.db_cursor = None
        
        # Database connection parameters from environment
        self.db_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'aryabhatta'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', '')
        }
    
    def setup_driver(self):
        """Setup Chrome driver with appropriate options"""
        print("Setting up Chrome driver...")
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Set download preferences
        prefs = {
            "download.default_directory": str(self.download_dir.absolute()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        print("✓ Chrome driver ready")
    
    def connect_to_database(self):
        """Connect to PostgreSQL database"""
        try:
            print("Connecting to database...")
            self.db_conn = psycopg2.connect(**self.db_params)
            self.db_cursor = self.db_conn.cursor()
            print("✓ Database connection established")
            return True
        except Exception as e:
            print(f"✗ Database connection failed: {e}")
            print(f"Connection params: host={self.db_params['host']}, "
                  f"port={self.db_params['port']}, database={self.db_params['database']}")
            return False
    
    def insert_record(self, exam_name, paper_name, year, date_of_exam, shift, filename):
        """Insert a record into the database"""
        try:
            query = """
                INSERT INTO exam_papers (ExamName, PaperName, Year, DateOfExam, Shift, FileName)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """
            self.db_cursor.execute(query, (exam_name, paper_name, year, date_of_exam, shift, filename))
            self.db_conn.commit()
            print(f"✓ Database record inserted for {filename}")
            return True
        except Exception as e:
            print(f"✗ Database insert failed: {e}")
            self.db_conn.rollback()
            return False
    
    def sanitize_filename(self, filename):
        """Sanitize filename for Windows"""
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove extra whitespace
        filename = re.sub(r'\s+', '_', filename)
        # Limit length
        name_part = filename[:200] if len(filename) > 200 else filename
        # Ensure it ends with .pdf
        if not name_part.lower().endswith('.pdf'):
            name_part += '.pdf'
        return name_part
    
    def navigate_to_page(self):
        """Navigate to the downloads page"""
        print(f"Navigating to: {self.base_url}")
        self.driver.get(self.base_url)
        time.sleep(3)
        print("✓ Initial page loaded")
        
        # Click on the Downloads link in the navigation bar
        try:
            print("Clicking Downloads link in navigation...")
            downloads_link = self.driver.find_element(By.XPATH, "//a[@href='/Downloads']")
            downloads_link.click()
            time.sleep(3)
            print("✓ Downloads page loaded")
        except Exception as e:
            print(f"⚠ Error clicking Downloads link: {e}")
            print("Continuing anyway...")
    
    def get_available_years(self):
        """Get all available years from the Year dropdown"""
        try:
            year_dropdown = Select(self.driver.find_element(By.ID, "drpYear"))
            years = []
            for option in year_dropdown.options:
                year_value = option.get_attribute("value")
                year_text = option.text.strip()
                # Only include years that are valid integers (2025, 2024, etc.)
                try:
                    if year_value and int(year_value) > 0:
                        years.append(year_value)
                        print(f"Found year: {year_text}")
                except ValueError:
                    # Skip non-integer values like "--select--"
                    pass
            return years
        except Exception as e:
            print(f"✗ Error getting years: {e}")
            return []
    
    def select_year(self, year):
        """Select a specific year from the dropdown"""
        try:
            year_dropdown = Select(self.driver.find_element(By.ID, "drpYear"))
            year_dropdown.select_by_value(str(year))
            time.sleep(1)
            print(f"✓ Selected year: {year}")
            return True
        except Exception as e:
            print(f"✗ Error selecting year {year}: {e}")
            return False
    
    def select_exam_type(self, exam_type="JEE-Main"):
        """Select exam type from the dropdown"""
        try:
            exam_dropdown = Select(self.driver.find_element(By.ID, "drpExamType"))
            exam_dropdown.select_by_visible_text(exam_type)
            time.sleep(1)
            print(f"✓ Selected exam type: {exam_type}")
            return True
        except Exception as e:
            print(f"✗ Error selecting exam type: {e}")
            return False
    
    def click_search(self):
        """Click the Search button"""
        try:
            search_button = self.driver.find_element(By.ID, "btnSearch")
            search_button.click()
            time.sleep(3)
            print("✓ Search button clicked")
            return True
        except Exception as e:
            print(f"✗ Error clicking search: {e}")
            return False
    
    def should_skip_paper(self, paper_name):
        """Check if paper should be skipped based on name"""
        skip_keywords = ['arch', 'planning']
        paper_lower = paper_name.lower()
        for keyword in skip_keywords:
            if keyword in paper_lower:
                print(f"⏭ Skipping paper (contains '{keyword}'): {paper_name}")
                return True
        return False
    
    def get_table_rows(self):
        """Get all rows from the results table"""
        try:
            # Wait for table to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "tbldownload"))
            )
            
            table = self.driver.find_element(By.ID, "tbldownload")
            tbody = table.find_element(By.ID, "tbldownloadBody")
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            
            # Filter out rows that don't have the expected structure
            data_rows = [row for row in rows if row.find_elements(By.TAG_NAME, "td")]
            print(f"✓ Found {len(data_rows)} rows in table")
            return data_rows
        except TimeoutException:
            print("⚠ No results table found")
            return []
        except Exception as e:
            print(f"✗ Error getting table rows: {e}")
            return []
    
    def parse_date(self, date_str):
        """Parse date string to date object"""
        try:
            # Try different date formats
            date_formats = [
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%Y-%m-%d",
                "%d.%m.%Y"
            ]
            
            for fmt in date_formats:
                try:
                    return datetime.strptime(date_str.strip(), fmt).date()
                except ValueError:
                    continue
            
            print(f"⚠ Could not parse date: {date_str}")
            return None
        except Exception as e:
            print(f"⚠ Date parsing error: {e}")
            return None
    
    def extract_row_data(self, row):
        """Extract data from a table row"""
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 7:
                return None
            
            # Extract data from cells based on the actual table structure
            # Column 0: Sr No (ignore)
            # Column 1: Exam Name (e.g., "JEE-Main") - ignore for now
            # Column 2: Paper Name (e.g., "B Planning 30th Jan 2025 Shift 2 Eng & Hindi") - check for skip
            # Column 3: Year (e.g., "2025") - ignore
            # Column 4: Date (e.g., "30-01-2025")
            # Column 5: Shift (e.g., "2")
            # Column 6: Download button
            data = {
                'exam_name': cells[1].text.strip() if len(cells) > 1 else 'JEE-Main',
                'paper_name': cells[2].text.strip() if len(cells) > 2 else '',
                'date_of_exam': self.parse_date(cells[4].text.strip()) if len(cells) > 4 else None,
                'shift': cells[5].text.strip() if len(cells) > 5 else '',
                'download_element': cells[6].find_element(By.TAG_NAME, "a") if len(cells) > 6 and cells[6].find_elements(By.TAG_NAME, "a") else None
            }
            
            return data
        except Exception as e:
            print(f"✗ Error extracting row data: {e}")
            return None
    
    def download_file(self, download_element, paper_name, year):
        """Download a single file"""
        try:
            # Get the download link
            download_url = download_element.get_attribute("href")
            
            # Get current files in download directory before download
            initial_files = set(self.download_dir.glob('*'))
            
            # Scroll element into view and click the download link
            print(f"Downloading: {paper_name}...")
              
            # Scroll the element into view with offset to avoid navbar
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", download_element)
            time.sleep(1)  # Let the page settle after scrolling
            
            # Try different click methods
            click_successful = False
            
            # Method 1: Regular click
            try:
                download_element.click()
                click_successful = True
                print("✓ Clicked download button (regular click)")
            except Exception as e1:
                print(f"⚠ Regular click failed: {e1}")
                
                # Method 2: JavaScript click
                try:
                    self.driver.execute_script("arguments[0].click();", download_element)
                    click_successful = True
                    print("✓ Clicked download button (JavaScript click)")
                except Exception as e2:
                    print(f"⚠ JavaScript click failed: {e2}")
                    
                    # Method 3: ActionChains click
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(self.driver).move_to_element(download_element).click().perform()
                        click_successful = True
                        print("✓ Clicked download button (ActionChains click)")
                    except Exception as e3:
                        print(f"✗ All click methods failed: {e3}")
                        return None
            
            if not click_successful:
                print("✗ Could not click download button")
                return None
            
            # Wait for and handle the modal dialog popup (not a browser alert, but a jconfirm modal)
            try:
                print("Waiting for download confirmation dialog...")
                # Wait for the jconfirm dialog to appear
                dialog = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "jconfirm"))
                )
                print("✓ Dialog detected")
                
                # Find and click the OK button
                ok_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.btn-primary"))
                )
                ok_button.click()
                print("✓ OK button clicked, download initiated")
                
                # Wait for the dialog to close completely
                print("Waiting for dialog to close...")
                WebDriverWait(self.driver, 10).until(
                    EC.invisibility_of_element_located((By.CLASS_NAME, "jconfirm"))
                )
                print("✓ Dialog closed")
                time.sleep(1)  # Extra buffer to ensure UI is ready
            except TimeoutException:
                print("⚠ No dialog appeared (might not be needed for this file)")
            except Exception as e:
                print(f"⚠ Error handling dialog: {e}")
            
            # Wait for download to complete
            max_wait = 60  # seconds
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                time.sleep(2)
                current_files = set(self.download_dir.glob('*'))
                new_files = current_files - initial_files
                
                if new_files:
                    # Check if download is complete (no .crdownload or .tmp files)
                    completed_files = [f for f in new_files 
                                     if not f.name.endswith(('.crdownload', '.tmp', '.part'))]
                    if completed_files:
                        downloaded_file = completed_files[0]
                        file_size = downloaded_file.stat().st_size
                        filename = downloaded_file.name  # Use the actual downloaded filename
                        
                        # Verify it's a valid PDF
                        if file_size < 1000:  # Less than 1KB is suspicious
                            print(f"⚠ Downloaded file seems too small: {file_size} bytes")
                        
                        # Keep the original filename from the server
                        print(f"✓ Downloaded: {filename} ({file_size / 1024 / 1024:.1f} MB)")
                        
                        return filename
            
            print(f"✗ Download timeout after {max_wait} seconds")
            return None
            
        except Exception as e:
            print(f"✗ Error downloading file: {e}")
            return None
    
    def go_to_next_page(self):
        """Navigate to the next page if available"""
        try:
            # Look for the Next button by its ID
            next_button = self.driver.find_element(By.ID, "tbldownload_next")
            
            # Check if the Next button is disabled (last page reached)
            button_classes = next_button.get_attribute("class")
            if "disabled" in button_classes:
                print("⚠ Reached last page (Next button disabled)")
                return False
            
            # Find the clickable link inside the Next button
            next_link = next_button.find_element(By.TAG_NAME, "a")
            
            if next_link.is_displayed() and next_link.is_enabled():
                next_link.click()
                time.sleep(3)
                print("✓ Navigated to next page")
                return True
            else:
                print("⚠ Next button not clickable")
                return False
            
        except NoSuchElementException:
            print("⚠ No next page button found")
            return False
        except Exception as e:
            print(f"✗ Error navigating to next page: {e}")
            return False
    
    def process_year(self, year):
        """Process all papers for a specific year"""
        print(f"\n{'='*60}")
        print(f"Processing Year: {year}")
        print(f"{'='*60}")
        
        # Select year
        if not self.select_year(year):
            return 0
        
        # Select JEE Main
        if not self.select_exam_type("JEE-Main"):
            return 0
        
        # Click search
        if not self.click_search():
            return 0
        
        total_downloaded = 0
        page_number = 1
        
        # Process all pages
        while True:
            print(f"\nProcessing page {page_number}...")
            
            # Get all rows from current page
            rows = self.get_table_rows()
            
            if not rows:
                print("No results found for this year")
                break
            
            # Process each row
            for i, row in enumerate(rows, 1):
                try:
                    print(f"\nRow {i}/{len(rows)}:")
                    
                    # Extract row data
                    data = self.extract_row_data(row)
                    if not data or not data['download_element']:
                        print("⏭ Skipping row (no data or download link)")
                        continue
                    
                    paper_name = data['paper_name']
                    print(f"Paper: {paper_name}")
                    
                    # Check if we should skip this paper
                    if self.should_skip_paper(paper_name):
                        continue
                    
                    # Download the file
                    filename = self.download_file(data['download_element'], paper_name, year)
                    
                    if filename:
                        # Insert into database
                        self.insert_record(
                            exam_name=data['exam_name'],
                            paper_name=paper_name,
                            year=int(year),
                            date_of_exam=data['date_of_exam'],
                            shift=data['shift'],
                            filename=filename
                        )
                        total_downloaded += 1
                        
                        # Wait between downloads to avoid overwhelming the server
                        time.sleep(3)
                    
                except StaleElementReferenceException:
                    print("⚠ Row became stale, refreshing table...")
                    # Re-get the rows and continue from next row
                    break
                except Exception as e:
                    print(f"✗ Error processing row: {e}")
                    continue
            
            # Try to go to next page
            if not self.go_to_next_page():
                break
            
            page_number += 1
        
        print(f"\n✓ Year {year} complete. Downloaded {total_downloaded} papers")
        return total_downloaded
    
    def run(self):
        """Main execution method"""
        print("Exam Paper Downloader")
        print("=" * 60)
        
        start_time = time.time()
        download_summary = {
            'total_years_processed': 0,
            'total_papers_downloaded': 0,
            'total_papers_skipped': 0,
            'errors': []
        }
        
        try:
            # Setup
            self.setup_driver()
            
            if not self.connect_to_database():
                print("⚠ Continuing without database connection")
            
            # Navigate to the page
            self.navigate_to_page()
            
            # Get all available years
            years = self.get_available_years()
            
            if not years:
                print("✗ No years found")
                return
            
            print(f"\nFound {len(years)} years to process")
            
            # Process each year
            for year in years:
                try:
                    downloaded = self.process_year(year)
                    download_summary['total_papers_downloaded'] += downloaded
                    download_summary['total_years_processed'] += 1
                    # Wait 1 minute before processing the next year
                    sleep_time = 30
                    if year != years[-1]:  # Don't wait after the last year
                        print(f"\n⏳ Waiting {sleep_time} seconds before processing next year...")
                        time.sleep(sleep_time)
                except Exception as e:
                    error_msg = f"Error processing year {year}: {e}"
                    print(f"✗ {error_msg}")
                    download_summary['errors'].append(error_msg)
                    continue
            
            # Summary
            elapsed_time = time.time() - start_time
            print(f"\n{'='*60}")
            print(f"DOWNLOAD COMPLETE")
            print(f"{'='*60}")
            print(f"Years processed: {download_summary['total_years_processed']}/{len(years)}")
            print(f"Papers downloaded: {download_summary['total_papers_downloaded']}")
            print(f"Time elapsed: {elapsed_time/60:.1f} minutes")
            print(f"Download directory: {self.download_dir.absolute()}")
            
            if download_summary['errors']:
                print(f"\nErrors encountered: {len(download_summary['errors'])}")
                for error in download_summary['errors'][:5]:  # Show first 5 errors
                    print(f"  - {error}")
                if len(download_summary['errors']) > 5:
                    print(f"  ... and {len(download_summary['errors']) - 5} more")
            
            print(f"{'='*60}")
            
        except KeyboardInterrupt:
            print("\n⚠ Download interrupted by user")
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            if self.db_cursor:
                self.db_cursor.close()
            if self.db_conn:
                self.db_conn.close()
            if self.driver:
                self.driver.quit()
            print("\n✓ Cleanup complete")

def main():
    """Main entry point"""
    downloader = ExamPaperDownloader()
    downloader.run()

if __name__ == "__main__":
    main()
