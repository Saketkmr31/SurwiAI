# SurwiAI Premium Workspace

This package keeps the existing SurwiAI FastAPI authentication, chat, file upload and history endpoints and upgrades the dashboard UI. The new dashboard adds:

- Premium dark red + purple workspace UI
- Daily Tasks with priority, due date, completion and delete
- Monthly Calendar with events
- Dashboard task/event summary
- Quick AI prompt from the dashboard
- Settings modal for display name
- `Made by Saket Kumar` footer

## Important

Tasks and calendar events are stored in browser localStorage for this first version. They persist on the same browser/device, but are not a server-side database yet.

## Local run

1. Copy `.env.example` to `.env` and fill the three values.
2. Install: `pip install -r requirements.txt`
3. Run from the project root: `uvicorn app.main:app --reload`

## Render

Keep the existing Render service connected to GitHub. Commit the package files into the same repository structure, then let Auto-Deploy rebuild. Ensure Render environment variables include `OPENAI_API_KEY`, `SURWI_SECRET_KEY`, and `GOOGLE_CLIENT_ID` (if Google login is enabled).


Update: Premium red/purple dashboard hero added with self-contained profile image. Existing auth, chat, files, tasks and calendar logic is preserved.


UI polish included: dashboard fits standard desktop viewport without a scrollbar; Files page dropzone is full-width and visually polished.
