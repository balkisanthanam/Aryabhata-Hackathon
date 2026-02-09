# Pre-Flight Checklist - Before Running the Script

Use this checklist to ensure everything is ready before running the exam paper downloader.

## ☐ System Requirements

- [ ] Windows/Linux/Mac OS installed
- [ ] Python 3.7 or higher installed
- [ ] Google Chrome browser installed
- [ ] PostgreSQL database server installed and running
- [ ] Internet connection active
- [ ] At least 1 GB free disk space

## ☐ Python Dependencies

- [ ] Open terminal/command prompt
- [ ] Navigate to `DataCollection` directory
- [ ] Run: `pip install -r requirements.txt`
- [ ] Verify installation: `pip list | grep selenium`
- [ ] Verify installation: `pip list | grep psycopg2`

## ☐ Database Setup

- [ ] PostgreSQL service is running
- [ ] Database `aryabhatta` exists (or your chosen database name)
- [ ] User has appropriate permissions
- [ ] Table `exam_papers` created (run SQL script)
- [ ] Can connect to database using credentials

### Test Database Connection
```bash
# Linux/Mac
psql -h localhost -U postgres -d aryabhatta -c "SELECT version();"

# Windows (if psql is in PATH)
psql -h localhost -U postgres -d aryabhatta -c "SELECT version();"
```

## ☐ Environment Configuration

Choose ONE of these methods:

### Option A: Batch File (Windows)
- [ ] Edit `run_exam_download.bat`
- [ ] Update `DB_HOST`, `DB_PORT`, `DB_NAME`
- [ ] Update `DB_USER`, `DB_PASSWORD`
- [ ] Save file

### Option B: Environment Variables (Any OS)
**Windows PowerShell:**
- [ ] Run: `$env:DB_HOST="localhost"`
- [ ] Run: `$env:DB_PORT="5432"`
- [ ] Run: `$env:DB_NAME="aryabhatta"`
- [ ] Run: `$env:DB_USER="postgres"`
- [ ] Run: `$env:DB_PASSWORD="your_password"`

**Windows CMD:**
- [ ] Run: `set DB_HOST=localhost`
- [ ] Run: `set DB_PORT=5432`
- [ ] Run: `set DB_NAME=aryabhatta`
- [ ] Run: `set DB_USER=postgres`
- [ ] Run: `set DB_PASSWORD=your_password`

**Linux/Mac:**
- [ ] Run: `export DB_HOST=localhost`
- [ ] Run: `export DB_PORT=5432`
- [ ] Run: `export DB_NAME=aryabhatta`
- [ ] Run: `export DB_USER=postgres`
- [ ] Run: `export DB_PASSWORD=your_password`

### Option C: .env File
- [ ] Copy `.env.example` to `.env`
- [ ] Edit `.env` file
- [ ] Update all database credentials
- [ ] Save file

## ☐ Chrome and ChromeDriver

- [ ] Google Chrome is installed
- [ ] ChromeDriver is installed
- [ ] ChromeDriver version matches Chrome version
- [ ] ChromeDriver is in PATH or script directory

### Check Chrome Version
- Open Chrome
- Go to: `chrome://version/`
- Note the version number

### Download ChromeDriver
- Visit: https://chromedriver.chromium.org/
- Download version matching your Chrome
- Extract to a folder in PATH

## ☐ Directory Setup

- [ ] `DataCollection` folder exists
- [ ] `DataCollection/JEEMain` folder exists (or will be created automatically)
- [ ] Have write permissions in the directory
- [ ] Sufficient disk space available

## ☐ Network & Website Access

- [ ] Can access: https://www.nta.ac.in/Downloads
- [ ] No proxy blocking the connection
- [ ] Firewall allows outbound connections
- [ ] Website is currently up and running

### Test Website Access
```bash
# Windows PowerShell
Invoke-WebRequest -Uri "https://www.nta.ac.in/Downloads"

# Linux/Mac
curl -I https://www.nta.ac.in/Downloads
```

## ☐ Final Verification

- [ ] All dependencies installed
- [ ] Database connection tested
- [ ] Environment variables set
- [ ] ChromeDriver accessible
- [ ] Download directory ready
- [ ] Website accessible

## 🚀 Ready to Launch!

Once all items are checked, you can run the script:

**Windows (using batch file):**
```cmd
run_exam_download.bat
```

**Direct Python execution:**
```bash
python download_exam_papers.py
```

## 📝 What to Expect

After launching, you should see:
1. "Setting up Chrome driver..." - Browser opens
2. "Connecting to database..." - Database connection established
3. "Navigating to..." - Page loads
4. "Found X years to process" - Years detected
5. "Processing Year: XXXX" - Downloads begin
6. Progress updates for each paper
7. "DOWNLOAD COMPLETE" - Final summary

## ⚠️ Common Issues

### If Chrome doesn't open:
- Check ChromeDriver is installed
- Verify ChromeDriver version matches Chrome
- Try installing ChromeDriver to script directory

### If database connection fails:
- Verify PostgreSQL is running: `pg_isready`
- Check credentials are correct
- Test connection manually with psql

### If downloads fail:
- Check internet connection
- Verify website is accessible
- Check disk space available
- Review file permissions

### If no years found:
- Website structure may have changed
- Check the website manually
- Update script element IDs if needed

## 📞 Need Help?

1. Check `EXAM_PAPER_DOWNLOAD_README.md` for detailed docs
2. Review `QUICK_START.md` for quick reference
3. Check error messages in console
4. Verify all checklist items are completed

---

**Last Updated:** November 2025
**Script Version:** 1.0
