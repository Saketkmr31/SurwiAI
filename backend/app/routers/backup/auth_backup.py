from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash

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


SECRET_KEY = "SURWI_AI_CHANGE_THIS_SECRET_KEY"
ALGORITHM = "HS256"


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

    access_token = jwt.encode(
        token_payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

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