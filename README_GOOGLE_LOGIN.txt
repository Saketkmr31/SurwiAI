SURWIAI — GOOGLE LOGIN PATCH

What this adds
- Real Sign in with Google using Google Identity Services.
- Server-side Google ID-token verification with google-auth.
- New Google users are created in the existing users table.
- Existing password accounts are NOT silently merged.
- Normal Surwi JWT is issued after successful Google verification.
- CSRF double-submit check is used for the credential endpoint.
- Existing Files/Chat functionality is not changed.

Files to replace/add
1. backend/app/routers/auth.py
2. backend/app/database.py
3. frontend/templates/index.html
4. install requirements-google.txt

Before testing
1. In Google Cloud Console create a Web application OAuth 2.0 Client ID for Sign in with Google.
2. Add your local origin, normally http://localhost:8000, under Authorized JavaScript origins.
3. Set the client ID in the environment as GOOGLE_CLIENT_ID.
4. Keep the client ID public; NEVER put a Google client secret in frontend code.
5. Install: pip install -r requirements-google.txt
6. Restart FastAPI.

Example environment variable
GOOGLE_CLIENT_ID=1234567890-xxxxxxxxxxxxxxxx.apps.googleusercontent.com

Important
- The backend validates the Google ID token signature, audience and expiry through google-auth.
- The Google account's sub claim is used as the stable Google identifier.
- For an existing password account with the same email, Google login intentionally returns a linking message instead of silently merging accounts.
- A dedicated account-linking flow can be added later from Settings.
