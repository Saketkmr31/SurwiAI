from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse

from .database import init_database
from .routers.auth import router as auth_router
from .routers.chat import router as chat_router


app = FastAPI(title="Surwi AI")

BASE_DIR = Path(__file__).resolve().parents[2]

init_database()

app.include_router(auth_router)
app.include_router(chat_router)

@app.get("/")
def home():
    return FileResponse(
        BASE_DIR / "frontend" / "templates" / "index.html"
    )


@app.get("/dashboard")
def dashboard():
    return FileResponse(
        BASE_DIR / "frontend" / "templates" / "dashboard.html"
    )