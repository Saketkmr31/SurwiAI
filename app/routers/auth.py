from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
import os
import secrets
from dotenv import load_dotenv
load_dotenv()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
from pwdlib import PasswordHash
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from ..database import get_connection


router = APIRouter(prefix="/auth", tags=["Authentication"])

password_hash = PasswordHash.recommended()


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


@router.post("/signup")
def signup(user: SignupRequest):
    name = user.name.strip()
    email = str(user.email).lower().strip()

    if len(name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Name must be at least 2 characters."
        )

    if len(user.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters."
        )

    connection = get_connection()

    existing_user = connection.execute(
        "SELECT id FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    if existing_user:
        connection.close()
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists."
        )

    hashed_password = password_hash.hash(user.password)

    cursor = connection.execute(
        """
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
        """,
        (name, email, hashed_password)
    )

    connection.commit()
    user_id = cursor.lastrowid
    connection.close()

    return {
        "message": "Account created successfully.",
        "user_id": user_id,
        "name": name,
        "email": email
    }

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


from ..security import create_access_token

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()


@router.post("/login")
def login(user: LoginRequest):
    email = str(user.email).lower().strip()

    connection = get_connection()

    db_user = connection.execute(
        """
        SELECT id, name, email, password_hash
        FROM users
        WHERE email = ?
        """,
        (email,)
    ).fetchone()

    connection.close()

    if not db_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    if not db_user["password_hash"]:
        raise HTTPException(
            status_code=401,
            detail="This account does not have a password login."
        )

    try:
        password_valid = password_hash.verify(
            user.password,
            db_user["password_hash"]
        )
    except Exception:
        password_valid = False

    if not password_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    token_payload = {
        "sub": str(db_user["id"]),
        "email": db_user["email"],
        "name": db_user["name"],
        "exp": datetime.now(timezone.utc) + timedelta(days=7)
    }

    access_token = create_access_token(token_payload)

    return {
        "message": "Login successful.",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": db_user["id"],
            "name": db_user["name"],
            "email": db_user["email"]
        }
    }

class GoogleLoginRequest(BaseModel):
    credential: str
    csrf_token: str


@router.get("/google/config")
def google_config(request: Request, response: Response):
    """Return public Google client configuration and issue a CSRF token."""
    if not GOOGLE_CLIENT_ID:
        return {"enabled": False, "client_id": ""}

    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        "surwi_google_csrf",
        csrf_token,
        httponly=False,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=600,
        path="/",
    )
    return {"enabled": True, "client_id": GOOGLE_CLIENT_ID, "csrf_token": csrf_token}


@router.post("/google/login")
def google_login(payload: GoogleLoginRequest, request: Request):
    """Verify a Google ID token and issue the normal Surwi JWT."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google login is not configured on this server.")

    cookie_csrf = request.cookies.get("surwi_google_csrf")
    if not cookie_csrf or not secrets.compare_digest(cookie_csrf, payload.csrf_token):
        raise HTTPException(status_code=403, detail="Google login security check failed. Please try again.")

    # try:
    #     idinfo = id_token.verify_oauth2_token(
    #         payload.credential,
    #         google_requests.Request(),
    #         GOOGLE_CLIENT_ID,
    #     )
    # except ValueError:
    #     raise HTTPException(status_code=401, detail="Invalid Google credential.")
    try:
        idinfo = id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception as e:
        print("GOOGLE TOKEN VERIFICATION ERROR:", repr(e))
        raise HTTPException(
            status_code=401,
            detail=f"Google token verification failed: {str(e)}"
        )

    issuer = idinfo.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status_code=401, detail="Invalid Google token issuer.")

    google_id = str(idinfo.get("sub") or "").strip()
    email = str(idinfo.get("email") or "").lower().strip()
    name = str(idinfo.get("name") or idinfo.get("given_name") or "Google User").strip()
    email_verified = bool(idinfo.get("email_verified"))

    if not google_id or not email or not email_verified:
        raise HTTPException(status_code=401, detail="Google account email could not be verified.")

    connection = get_connection()
    try:
        db_user = connection.execute(
            "SELECT id, name, email, password_hash, google_id FROM users WHERE google_id = ?",
            (google_id,),
        ).fetchone()

        if not db_user:
            db_user = connection.execute(
                "SELECT id, name, email, password_hash, google_id FROM users WHERE email = ?",
                (email,),
            ).fetchone()

        if db_user:
            # Do not silently merge a Google account into an existing password account.
            # The user can use password login until an explicit account-linking flow exists.
            if db_user["google_id"] and db_user["google_id"] != google_id:
                raise HTTPException(status_code=409, detail="This email is already linked to another Google account.")
            if not db_user["google_id"]:
                if db_user["password_hash"]:
                    raise HTTPException(
                        status_code=409,
                        detail="An account with this email already exists. Sign in with your password first; Google account linking will be added separately.",
                    )
                connection.execute(
                    "UPDATE users SET google_id = ? WHERE id = ?",
                    (google_id, db_user["id"]),
                )
                connection.commit()
                db_user = connection.execute(
                    "SELECT id, name, email, password_hash, google_id FROM users WHERE id = ?",
                    (db_user["id"],),
                ).fetchone()
        else:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash, google_id) VALUES (?, ?, NULL, ?)",
                (name or "Google User", email, google_id),
            )
            connection.commit()
            db_user = connection.execute(
                "SELECT id, name, email, password_hash, google_id FROM users WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()

        token_payload = {
            "sub": str(db_user["id"]),
            "email": db_user["email"],
            "name": db_user["name"],
            "exp": datetime.now(timezone.utc) + timedelta(days=7),
        }
        access_token = create_access_token(token_payload)

        return {
            "message": "Google login successful.",
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": db_user["id"],
                "name": db_user["name"],
                "email": db_user["email"],
            },
        }
    finally:
        connection.close()
