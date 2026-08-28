SURWIAI FIXED PATCH

Replace these files in your existing project:

backend/app/database.py
backend/app/routers/chat.py
backend/app/routers/files.py
backend/app/routers/auth.py
backend/app/main.py
frontend/templates/dashboard.html
frontend/templates/index.html

IMPORTANT:
1. Stop FastAPI first (Ctrl+C).
2. Keep your existing surwi.db and uploads folder. Do NOT delete them.
3. Replace the files above with these versions.
4. Start the server again.
5. Hard refresh the browser with Ctrl+Shift+R.

Fixes included:
- Files sidebar navigation works.
- Files page upload/download/delete works.
- Chat paperclip opens file selector and existing files.
- Chat can upload a new file from the paperclip.
- Selected file is sent with the chat request.
- Follow-up questions can reuse the latest attached file.
- SQLite conversation_files table is initialized once at startup.
- SQLite WAL/busy-timeout handling reduces "database is locked" errors.
- Logout clears all known auth tokens and returns to login.
- Main app includes the Files router.
- Existing conversations/files are preserved.
