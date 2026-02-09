QuestionGeneratorFunction — Local debug guide

Steps to debug locally (Windows):

1. Create & activate a virtual environment (from repository root):

   ```powershell
   cd pipelines\AzureFunctions\QuestionGeneratorFunction
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1    # or call .venv\Scripts\activate.bat in cmd
   pip install -r requirements.txt
   ```

2. Start the function host with the debug flag (use the provided VS Code task):

   - In VS Code run the task: `Run Task` → `Run Question Generator (debug)`
   - This sets `PY_FUNC_DEBUG=1` before starting the host so the Python worker will start `debugpy` and listen on port `5678`.

3. Attach the debugger:

   - Open the Run view and choose `Attach to QuestionGenerator (debugpy)` then press `Start Debugging` (F5).

4. Test the function:

   - Send a POST to `http://localhost:9092/api/generate-questions` with JSON body, e.g.: `{ "subject": "Maths", "numQuestions": 3 }`.

Notes:

- `debugpy` is optional and only started when `PY_FUNC_DEBUG=1` is set.
- If you prefer manual steps, run in a terminal:

  ```powershell
  set PY_FUNC_DEBUG=1
  .venv\Scripts\activate
  func start --python-port 9092
  ```
