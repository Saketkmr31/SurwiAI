from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..database import get_connection
from ..security import get_current_user


router = APIRouter(prefix="/files", tags=["Files"])


# =========================================================
# STORAGE
# =========================================================

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "uploads"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".doc",
    ".docx",
    ".csv",
    ".xlsx",
    ".xls",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


# =========================================================
# UPLOAD
# =========================================================

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="File name is required.",
        )

    original_name = Path(file.filename).name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. "
                "Allowed: PDF, TXT, DOC, DOCX, CSV, XLS, XLSX, "
                "PPT, PPTX and common images."
            ),
        )

    stored_name = f"{uuid4().hex}{extension}"
    destination = UPLOAD_DIR / stored_name

    total_size = 0

    try:
        with destination.open("wb") as output:

            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    output.close()
                    destination.unlink(missing_ok=True)

                    raise HTTPException(
                        status_code=413,
                        detail="File is too large. Maximum size is 20 MB.",
                    )

                output.write(chunk)

    except HTTPException:
        raise

    except Exception as error:
        destination.unlink(missing_ok=True)

        print("File upload error:", error)

        raise HTTPException(
            status_code=500,
            detail="Could not upload file.",
        )

    finally:
        await file.close()

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT INTO files (
                user_id,
                original_name,
                stored_name,
                file_path,
                content_type,
                file_size
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                original_name,
                stored_name,
                str(destination),
                file.content_type,
                total_size,
            ),
        )

        connection.commit()

        file_id = cursor.lastrowid

    except Exception as error:
        connection.rollback()
        destination.unlink(missing_ok=True)

        print("File DB Error:", error)

        raise HTTPException(
            status_code=500,
            detail="Could not save file information.",
        )

    finally:
        connection.close()

    return {
        "message": "File uploaded successfully.",
        "file": {
            "id": file_id,
            "name": original_name,
            "content_type": file.content_type,
            "size": total_size,
        },
    }


# =========================================================
# LIST FILES
# =========================================================

@router.get("")
def get_files(
    user_id: int = Depends(get_current_user),
):
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                id,
                original_name,
                content_type,
                file_size,
                created_at
            FROM files
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()

        return {
            "user_id": user_id,
            "files": [dict(row) for row in rows],
        }

    finally:
        connection.close()


# =========================================================
# PREVIEW
# =========================================================

@router.get("/{file_id}/preview")
def preview_file(
    file_id: int,
    user_id: int = Depends(get_current_user),
):
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                original_name,
                file_path,
                content_type
            FROM files
            WHERE id = ? AND user_id = ?
            """,
            (file_id, user_id),
        ).fetchone()

    finally:
        connection.close()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    file_path = Path(row["file_path"])

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Stored file is missing.",
        )

    original_name = row["original_name"]
    extension = Path(original_name).suffix.lower()

    # Browser-native preview formats
    previewable_extensions = {
        ".pdf",
        ".txt",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    }

    if extension not in previewable_extensions:
        raise HTTPException(
            status_code=415,
            detail=(
                "This file type cannot be previewed in the browser. "
                "Please use Download."
            ),
        )

    content_type = row["content_type"]

    # Correct MIME types
    if extension == ".pdf":
        content_type = "application/pdf"

    elif extension == ".txt":
        content_type = "text/plain"

    elif extension == ".png":
        content_type = "image/png"

    elif extension in {".jpg", ".jpeg"}:
        content_type = "image/jpeg"

    elif extension == ".webp":
        content_type = "image/webp"

    return FileResponse(
        path=file_path,
        media_type=content_type or "application/octet-stream",
        content_disposition_type="inline",
        filename=original_name,
    )


# =========================================================
# DOWNLOAD
# =========================================================

@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    user_id: int = Depends(get_current_user),
):
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                original_name,
                file_path,
                content_type
            FROM files
            WHERE id = ? AND user_id = ?
            """,
            (file_id, user_id),
        ).fetchone()

    finally:
        connection.close()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    file_path = Path(row["file_path"])

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Stored file is missing.",
        )

    return FileResponse(
        path=file_path,
        filename=row["original_name"],
        media_type=row["content_type"] or "application/octet-stream",
        content_disposition_type="attachment",
    )


# =========================================================
# DELETE
# =========================================================

@router.delete("/{file_id}")
def delete_file(
    file_id: int,
    user_id: int = Depends(get_current_user),
):
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT file_path
            FROM files
            WHERE id = ? AND user_id = ?
            """,
            (file_id, user_id),
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="File not found.",
            )

        connection.execute(
            """
            DELETE FROM files
            WHERE id = ? AND user_id = ?
            """,
            (file_id, user_id),
        )

        connection.commit()

    except HTTPException:
        raise

    except Exception as error:
        connection.rollback()

        print("File delete DB Error:", error)

        raise HTTPException(
            status_code=500,
            detail="Could not delete file.",
        )

    finally:
        connection.close()

    Path(row["file_path"]).unlink(missing_ok=True)

    return {
        "message": "File deleted successfully.",
        "file_id": file_id,
    }