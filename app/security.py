import os
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

load_dotenv()

SECRET_KEY = os.getenv("SURWI_SECRET_KEY", "").strip()
ALGORITHM = "HS256"

if not SECRET_KEY:
    raise RuntimeError("SURWI_SECRET_KEY is not configured in .env")

if len(SECRET_KEY) < 32:
    raise RuntimeError("SURWI_SECRET_KEY must be at least 32 characters long")

security = HTTPBearer(auto_error=True)


def create_access_token(payload: dict) -> str:
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token.")
        return int(user_id)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token.")
