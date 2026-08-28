from pathlib import Path
import csv
import io
import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import os

from pypdf import PdfReader
from docx import Document
from openpyxl import load_workbook

from ..database import get_connection


load_dotenv()

router = APIRouter(prefix="/chat", tags=["AI Assistant"])


from ..security import get_current_user


# ============================================================
# OPENAI
# ============================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not configured in .env")

client = OpenAI(api_key=OPENAI_API_KEY)


# ============================================================
# REQUEST MODEL
# ============================================================

class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None
    file_id: int | None = None


# ============================================================
# FILE TEXT EXTRACTION
# ============================================================

MAX_CONTEXT_CHARS = 60000


def extract_txt(file_path: Path) -> str:
    """
    Extract text from TXT files.
    """

    try:
        return file_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

    except Exception as error:
        print("TXT extraction error:", error)
        raise RuntimeError("Could not read TXT file.")


def extract_csv(file_path: Path) -> str:
    """
    Extract CSV data and convert it into readable text.
    """

    try:
        output = io.StringIO()

        with file_path.open(
            "r",
            encoding="utf-8",
            errors="replace",
            newline="",
        ) as csv_file:

            reader = csv.reader(csv_file)

            for row in reader:
                output.write(" | ".join(str(value) for value in row))
                output.write("\n")

        return output.getvalue()

    except Exception as error:
        print("CSV extraction error:", error)
        raise RuntimeError("Could not read CSV file.")


def extract_pdf(file_path: Path) -> str:
    """
    Extract text from PDF pages.
    """

    try:
        reader = PdfReader(str(file_path))

        text_parts = []

        for page_number, page in enumerate(reader.pages, start=1):

            page_text = page.extract_text() or ""

            if page_text.strip():
                text_parts.append(
                    f"\n--- Page {page_number} ---\n"
                )

                text_parts.append(page_text)

        return "\n".join(text_parts)

    except Exception as error:
        print("PDF extraction error:", error)
        raise RuntimeError("Could not read PDF file.")


def extract_docx(file_path: Path) -> str:
    """
    Extract paragraphs and tables from DOCX.
    """

    try:
        document = Document(str(file_path))

        text_parts = []

        # Paragraphs
        for paragraph in document.paragraphs:

            text = paragraph.text.strip()

            if text:
                text_parts.append(text)

        # Tables
        for table in document.tables:

            text_parts.append("\n--- Table ---")

            for row in table.rows:

                values = []

                for cell in row.cells:
                    values.append(cell.text.strip())

                text_parts.append(
                    " | ".join(values)
                )

        return "\n".join(text_parts)

    except Exception as error:
        print("DOCX extraction error:", error)
        raise RuntimeError("Could not read DOCX file.")


def extract_xlsx(file_path: Path) -> str:
    """
    Extract cell values from XLSX.
    """

    try:
        workbook = load_workbook(
            filename=file_path,
            read_only=True,
            data_only=True,
        )

        text_parts = []

        for worksheet in workbook.worksheets:

            text_parts.append(
                f"\n--- Sheet: {worksheet.title} ---"
            )

            for row in worksheet.iter_rows(
                values_only=True
            ):

                values = []

                for value in row:

                    if value is None:
                        values.append("")
                    else:
                        values.append(str(value))

                # Ignore completely empty rows
                if any(value.strip() for value in values):
                    text_parts.append(
                        " | ".join(values)
                    )

        workbook.close()

        return "\n".join(text_parts)

    except Exception as error:
        print("XLSX extraction error:", error)
        raise RuntimeError("Could not read XLSX file.")


def extract_file_text(
    file_path: Path,
    original_name: str,
) -> str:

    extension = Path(original_name).suffix.lower()

    if extension == ".txt":
        text = extract_txt(file_path)

    elif extension == ".csv":
        text = extract_csv(file_path)

    elif extension == ".pdf":
        text = extract_pdf(file_path)

    elif extension == ".docx":
        text = extract_docx(file_path)

    elif extension == ".xlsx":
        text = extract_xlsx(file_path)

    else:
        raise HTTPException(
            status_code=400,
            detail=(
                "AI reading is currently supported for "
                "PDF, TXT, DOCX, CSV and XLSX files."
            ),
        )

    text = text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="No readable text was found in this file.",
        )

    # Protect the AI request from extremely large documents.
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[:MAX_CONTEXT_CHARS]

        text += (
            "\n\n[Document content truncated because it "
            "exceeded the maximum AI context size.]"
        )

    return text


# ============================================================
# CONVERSATION FILE CONTEXT
# ============================================================

def remember_conversation_file(conversation_id: int, user_id: int, file_id: int):
    """
    Remember the file attached to a conversation.

    IMPORTANT:
    The conversation_files table is created once by database.init_database().
    Do NOT run CREATE TABLE inside every chat request. That was causing
    SQLite locking under concurrent requests.
    """
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO conversation_files
            (conversation_id, user_id, file_id)
            VALUES (?, ?, ?)
            """,
            (conversation_id, user_id, file_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_conversation_file(conversation_id: int, user_id: int):
    """Return the most recently attached file for this conversation."""
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT
                f.id,
                f.original_name,
                f.file_path,
                f.content_type,
                f.file_size,
                f.created_at
            FROM conversation_files cf
            JOIN files f ON f.id = cf.file_id
            WHERE cf.conversation_id = ?
              AND cf.user_id = ?
              AND f.user_id = ?
            ORDER BY cf.created_at DESC, cf.id DESC
            LIMIT 1
            """,
            (conversation_id, user_id, user_id),
        ).fetchone()
    finally:
        connection.close()


def sanitize_sensitive_output(text: str) -> str:
    """Mask high-risk identifiers accidentally produced by the model."""
    if not text:
        return text

    account_pattern = re.compile(
        r"(?i)(\b(?:account\s*(?:number|no\.?|#)|a/c\s*(?:number|no\.?|#))\s*[:\-]?\s*)(\d{8,20})"
    )
    text = account_pattern.sub(
        lambda m: m.group(1) + "*" * (len(m.group(2)) - 4) + m.group(2)[-4:],
        text,
    )

    secret_pattern = re.compile(
        r"(?i)(\b(?:pin|cvv|cvc|password|passcode|access\s*token|secret\s*key)\b\s*[:\-]?\s*)([^\n,;]+)"
    )
    text = secret_pattern.sub(
        lambda m: m.group(1) + "[REDACTED]",
        text,
    )

    id_pattern = re.compile(
        r"(?i)(\b(?:aadhaar|aadhar|government\s*id|national\s*id)\b\s*[:\-]?\s*)(\d{12})"
    )
    text = id_pattern.sub(
        lambda m: m.group(1) + "[REDACTED]",
        text,
    )

    return text


# ============================================================
# GET FILE FOR CURRENT USER
# ============================================================

def get_user_file(
    file_id: int,
    user_id: int,
):
    connection = get_connection()

    try:

        row = connection.execute(
            """
            SELECT
                id,
                original_name,
                file_path,
                content_type,
                file_size,
                created_at
            FROM files
            WHERE id = ? AND user_id = ?
            """,
            (
                file_id,
                user_id,
            ),
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="File not found.",
            )

        return row

    finally:
        connection.close()


# ============================================================
# SEND MESSAGE
# ============================================================

@router.post("/message")
def send_message(
    chat: ChatRequest,
    user_id: int = Depends(get_current_user),
):
    message = chat.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    # ========================================================
    # 1. PREPARE CONVERSATION
    # ========================================================
    #
    # Keep this SQLite connection SHORT-LIVED.
    # Never keep a write transaction open while calling OpenAI.
    #
    connection = get_connection()

    try:
        conversation_id = chat.conversation_id

        if conversation_id is None:
            cursor = connection.execute(
                """
                INSERT INTO conversations (user_id, title)
                VALUES (?, ?)
                """,
                (user_id, message[:50]),
            )
            conversation_id = cursor.lastrowid

            # Release the SQLite write lock immediately.
            connection.commit()

        else:
            conversation = connection.execute(
                """
                SELECT id
                FROM conversations
                WHERE id = ? AND user_id = ?
                """,
                (conversation_id, user_id),
            ).fetchone()

            if not conversation:
                raise HTTPException(
                    status_code=404,
                    detail="Conversation not found.",
                )

        previous_messages = connection.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

        ai_input = [
            {
                "role": row["role"],
                "content": row["content"],
            }
            for row in previous_messages
        ]

    except HTTPException:
        raise

    except Exception as error:
        try:
            connection.rollback()
        except Exception:
            pass

        print("Conversation DB Error:", error)

        raise HTTPException(
            status_code=500,
            detail="Could not prepare conversation.",
        )

    finally:
        connection.close()

    # ========================================================
    # 2. RESOLVE ATTACHED FILE
    # ========================================================

    file_context = None
    attached_file_name = None
    effective_file_id = chat.file_id
    file_row = None

    try:
        if effective_file_id is not None:
            # New file selected in the composer.
            file_row = get_user_file(
                effective_file_id,
                user_id,
            )

            attached_file_name = file_row["original_name"]

            # Save the relationship in its own short transaction.
            remember_conversation_file(
                conversation_id,
                user_id,
                effective_file_id,
            )

        else:
            # Follow-up message: reuse the most recent file
            # attached to this conversation.
            file_row = get_conversation_file(
                conversation_id,
                user_id,
            )

            if file_row:
                effective_file_id = file_row["id"]
                attached_file_name = file_row["original_name"]

        if file_row:
            file_path = Path(file_row["file_path"])

            if not file_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail="Stored file is missing.",
                )

            try:
                file_context = extract_file_text(
                    file_path,
                    attached_file_name,
                )
            except HTTPException:
                raise
            except Exception as error:
                print("File extraction error:", error)
                raise HTTPException(
                    status_code=500,
                    detail="Could not read the selected file.",
                )

    except HTTPException:
        raise

    # ========================================================
    # 3. BUILD AI INPUT
    # ========================================================

    if file_context:
        document_message = (
            "The user has attached the following document.\n\n"
            f"FILE NAME: {attached_file_name}\n\n"
            "DOCUMENT CONTENT:\n"
            "-------------------------\n"
            f"{file_context}\n"
            "-------------------------\n\n"
            "Use this document as context when answering "
            "the user's question. "
            "Do not invent information that is not present "
            "in the document. "
            "If the answer cannot be found in the document, "
            "say so clearly."
        )

        ai_input.append(
            {
                "role": "user",
                "content": document_message,
            }
        )

    # Current user message must always be last.
    ai_input.append(
        {
            "role": "user",
            "content": message,
        }
    )

    # ========================================================
    # 4. OPENAI
    # ========================================================
    #
    # There is NO SQLite connection open here.
    # This is critical for avoiding "database is locked".
    #

    try:
        response = client.responses.create(
            model="gpt-5.5",
            instructions=(
                "You are Surwi AI, a helpful and intelligent "
                "AI assistant. "

                "Answer clearly, accurately and naturally. "

                "Use previous messages as conversation context. "

                "If a document is attached, use its content "
                "as the primary source for document-related "
                "questions. "

                "Never claim that you read information that "
                "is not present in the provided document. "

                "Protect sensitive information by default. Never "
                "reveal full bank account numbers, PINs, CVVs, "
                "passwords, access tokens, secret keys, or government "
                "identifiers from a document. If such a value is "
                "relevant, mask it (for example, account numbers "
                "show only the last four digits) or say that it is "
                "redacted. Do not reveal a secret merely because the "
                "user asks for it. "

                "Be useful and concise unless the user asks "
                "for detail."
            ),
            input=ai_input,
        )

        ai_response = response.output_text.strip()

        ai_response = sanitize_sensitive_output(
            ai_response
        )

        if not ai_response:
            raise RuntimeError(
                "OpenAI returned an empty response."
            )

    except Exception as error:
        print("OpenAI API Error:", error)

        raise HTTPException(
            status_code=500,
            detail="AI service is currently unavailable.",
        )

    # ========================================================
    # 5. SAVE CHAT HISTORY
    # ========================================================

    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT INTO messages (
                conversation_id,
                role,
                content
            )
            VALUES (?, ?, ?)
            """,
            (
                conversation_id,
                "user",
                message,
            ),
        )

        connection.execute(
            """
            INSERT INTO messages (
                conversation_id,
                role,
                content
            )
            VALUES (?, ?, ?)
            """,
            (
                conversation_id,
                "assistant",
                ai_response,
            ),
        )

        connection.execute(
            """
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (
                conversation_id,
                user_id,
            ),
        )

        connection.commit()

    except Exception as error:
        try:
            connection.rollback()
        except Exception:
            pass

        print("Message DB Error:", error)

        raise HTTPException(
            status_code=500,
            detail="Could not save chat history.",
        )

    finally:
        connection.close()

    # ========================================================
    # 6. RESPONSE
    # ========================================================

    return {
        "message": ai_response,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "file_id": effective_file_id,
        "file_name": attached_file_name,
    }


# ============================================================
# CHAT HISTORY
# ============================================================

@router.get("/conversations")
def get_conversations(
    user_id: int = Depends(get_current_user),
):

    connection = get_connection()

    try:

        conversations = connection.execute(
            """
            SELECT
                id,
                title,
                created_at,
                updated_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (
                user_id,
            ),
        ).fetchall()

        return {
            "user_id": user_id,
            "conversations": [
                dict(conversation)
                for conversation in conversations
            ],
        }

    finally:

        connection.close()


# ============================================================
# CONVERSATION MESSAGES
# ============================================================

@router.get(
    "/conversations/{conversation_id}"
)
def get_conversation_messages(
    conversation_id: int,
    user_id: int = Depends(get_current_user),
):

    connection = get_connection()

    try:

        conversation = connection.execute(
            """
            SELECT
                id,
                title,
                created_at,
                updated_at
            FROM conversations
            WHERE id = ? AND user_id = ?
            """,
            (
                conversation_id,
                user_id,
            ),
        ).fetchone()

        if not conversation:

            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            )

        messages = connection.execute(
            """
            SELECT
                id,
                role,
                content,
                created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (
                conversation_id,
            ),
        ).fetchall()

        return {
            "conversation": dict(
                conversation
            ),
            "messages": [
                dict(message)
                for message in messages
            ],
        }

    finally:

        connection.close()