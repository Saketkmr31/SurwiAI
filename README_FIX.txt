SURWI AI - SAFE FIX PACKAGE
============================

What this fixes:
1. Correct project-root path. The old code used parents[2] from app/main.py,
   which pointed to C:\Users\saket instead of C:\Users\saket\SurwiAI.
2. Database now points to <project>\surwi.db and does NOT delete/recreate data.
3. Additive DB migration creates missing tables/columns only.
4. Chat, file routes and auth use one JWT security implementation.
5. Legacy JWT tokens can still be decoded once you reopen/login.
6. Existing frontend/dashboard are retained from the previous SurwiAI work.

IMPORTANT:
- DO NOT replace your existing surwi.db with a new database.
- DO NOT replace your .env. Keep your existing API keys/client IDs.
- Before applying, make a backup of the whole SurwiAI folder.

Apply:
1. Stop Uvicorn with Ctrl+C.
2. Back up C:\Users\saket\SurwiAI.
3. Copy the contents of this package into C:\Users\saket\SurwiAI and replace files.
4. Keep your existing surwi.db and .env.
5. In VS Code terminal:
   . .\.venv\Scripts\Activate.ps1
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
6. Open http://127.0.0.1:8000

If the browser keeps an old token, clear only localStorage for 127.0.0.1:8000
and log in again. Your SQLite data is not deleted by this package.
