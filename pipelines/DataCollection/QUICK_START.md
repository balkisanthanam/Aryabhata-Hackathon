# Quick Start Guide - Exam Paper Downloader

## 🚀 Quick Setup (5 minutes)

### Step 1: Install Dependencies
```bash
cd DataCollection
pip install -r requirements.txt
```

### Step 2: Configure Database
Edit `run_exam_download.bat` and set your database credentials:
```batch
set DB_HOST=localhost
set DB_PORT=5432
set DB_NAME=<DB_NAME>
set DB_USER=postgres
set DB_PASSWORD=your_actual_password
```

### Step 3: Create Database Table
Run this SQL in your PostgreSQL database:
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
```

### Step 4: Run the Script
Double-click `run_exam_download.bat` or run:
```bash
python download_exam_papers.py
```

## ✅ What It Does

1. Opens NTA website (https://www.nta.ac.in/Downloads)
2. Loops through all available years
3. Selects "JEE Main" for each year
4. Downloads all question papers (except Arch/Planning)
5. Saves PDFs to `DataCollection/JEEMain/`
6. Stores metadata in PostgreSQL database

## 📋 Script Features

- ✅ Automatic pagination handling
- ✅ Filters out Architecture/Planning papers
- ✅ Skips already downloaded files
- ✅ 3-second delay between downloads (server-friendly)
- ✅ Database transaction safety
- ✅ Resume capability after interruption
- ✅ Detailed progress reporting

## 🗂️ Output Structure

**Files:** `DataCollection/JEEMain/{Year}_{PaperName}.pdf`

**Database Record:**
```
ExamName: "JEE Main"
PaperName: "JEE Main Paper 1 (B.E./B.Tech)"
Year: 2024
DateOfExam: 2024-04-15
Shift: "Morning"
FileName: "2024_JEE_Main_Paper_1_(B.E._B.Tech).pdf"
```

## ⚙️ Configuration Options

Edit the script to customize:

```python
# Change download folder
download_dir="DataCollection/JEEMain"

# Change wait time for downloads
max_wait = 60  # seconds

# Change delay between downloads
time.sleep(3)  # seconds

# Change papers to skip
skip_keywords = ['arch', 'planning']
```

## 🔧 Troubleshooting

### "ChromeDriver not found"
Install ChromeDriver: https://chromedriver.chromium.org/

### "Database connection failed"
- Check PostgreSQL is running
- Verify credentials in environment variables
- Ensure database exists

### "No results found"
- Website structure may have changed
- Check the site manually
- Update element IDs in script if needed

## 📞 Support

For issues or questions:
1. Check EXAM_PAPER_DOWNLOAD_README.md for detailed documentation
2. Review error messages in console
3. Check download folder permissions

## 🎯 Expected Results

For a typical run:
- **Years processed:** 10-15 years
- **Papers per year:** 5-50 papers (varies by year)
- **Time:** ~30-60 minutes (depends on number of papers)
- **File size:** 50-500 MB total

---
Last Updated: 2025
