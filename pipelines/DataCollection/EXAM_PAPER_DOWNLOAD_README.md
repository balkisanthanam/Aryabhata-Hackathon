# Exam Paper Downloader

This script automatically downloads JEE Main question papers from the NTA website (https://www.nta.ac.in/Downloads) and stores metadata in a PostgreSQL database.

## Features

- Automatically loops through all available years
- Selects "JEE Main" from the exam type dropdown
- Handles paginated results
- Filters out Architecture and Planning papers
- Downloads PDFs one at a time (respectful of server)
- Stores metadata in PostgreSQL database
- Resumes from where it left off (skips already downloaded files)

## Prerequisites

1. **Python 3.7+**
2. **Chrome Browser** installed
3. **ChromeDriver** (compatible with your Chrome version)
4. **PostgreSQL Database** with the `exam_papers` table created

## Setup

### 1. Install Dependencies

```bash
cd DataCollection
pip install -r requirements.txt
```

### 2. Create Database Table

Run the SQL script to create the required table:

```sql
CREATE TABLE exam_papers (
    id SERIAL PRIMARY KEY,
    ExamName VARCHAR(255),
    PaperName VARCHAR(500),
    Year INTEGER,
    DateOfExam DATE,
    Shift VARCHAR(50),
    FileName VARCHAR(500)
);

CREATE INDEX idx_examyear ON exam_papers(ExamName, Year);
```

### 3. Set Environment Variables

Set the following environment variables for database connection:

**Windows (PowerShell):**
```powershell
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_NAME = "aryabhatta"
$env:DB_USER = "postgres"
$env:DB_PASSWORD = "your_password"
```

**Windows (Command Prompt):**
```cmd
set DB_HOST=localhost
set DB_PORT=5432
set DB_NAME=<DB_NAME>
set DB_USER=postgres
set DB_PASSWORD=your_password
```

**Linux/Mac:**
```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=<DB_NAME>
export DB_USER=postgres
export DB_PASSWORD=your_password
```

**Or create a `.env` file** (requires python-dotenv):
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=<DB_NAME>
DB_USER=postgres
DB_PASSWORD=your_password
```

## Usage

Run the script:

```bash
python download_exam_papers.py
```

The script will:
1. Open Chrome browser
2. Navigate to NTA downloads page
3. Loop through all available years
4. For each year:
   - Select "JEE Main" exam type
   - Click search
   - Process all pages of results
   - Download PDFs (excluding Arch/Planning papers)
   - Store metadata in database
5. Display summary of downloads

## Output

- **Downloaded Files:** `DataCollection/JEEMain/`
- **Filename Format:** `{Year}_{PaperName}.pdf`
- **Database Records:** Table `exam_papers` with metadata

## Configuration

You can modify these parameters in the script:

```python
# Download directory
download_dir="DataCollection/JEEMain"

# Base URL
base_url="https://www.nta.ac.in/Downloads"

# Skip keywords
skip_keywords = ['arch', 'planning']
```

## Troubleshooting

### Issue: ChromeDriver not found
**Solution:** Install ChromeDriver:
- Download from: https://chromedriver.chromium.org/
- Add to PATH or place in script directory

### Issue: Database connection failed
**Solution:** 
- Verify PostgreSQL is running
- Check environment variables are set correctly
- Ensure database and table exist

### Issue: No results found
**Solution:**
- The NTA website structure may have changed
- Check the page manually to verify dropdowns and table structure
- Update element IDs in the script if needed

### Issue: Download timeout
**Solution:**
- Increase `max_wait` in `download_file()` method
- Check internet connection
- Verify download directory permissions

## Script Behavior

- **Respectful Downloads:** 3-second delay between downloads
- **Duplicate Prevention:** Skips files that already exist
- **Error Recovery:** Continues with next paper if one fails
- **Database Safety:** Uses transactions and rollback on error
- **Pagination:** Automatically handles multiple pages of results

## Database Schema

The `exam_papers` table stores:
- `id`: Auto-incrementing primary key
- `ExamName`: Name of the exam (e.g., "JEE Main")
- `PaperName`: Full name of the paper
- `Year`: Year of the exam
- `DateOfExam`: Date the exam was conducted
- `Shift`: Exam shift (Morning/Afternoon/Evening)
- `FileName`: Name of the downloaded PDF file

## Notes

- The script uses Selenium to interact with the website's JavaScript dropdowns
- Downloads happen sequentially to avoid overwhelming the server
- The script can be interrupted (Ctrl+C) and resumed later
- Already downloaded files are automatically skipped

## Future Enhancements

Possible improvements:
- Add support for other exam types
- Implement parallel downloads (with rate limiting)
- Add download verification (checksum)
- Create detailed download log file
- Add email notification on completion
- Support for resume on network failures
