from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import jwt
import os
from ..database import get_connection


from ..database import get_connection


# Load .env
load_dotenv()


router = APIRouter(
    prefix="/chat",
    tags=["AI Assistant"]
)


# ---------------- JWT SETTINGS ----------------

SECRET_KEY = "SURWI_AI_CHANGE_THIS_SECRET_KEY"
ALGORITHM = "HS256"


# ---------------- OPENAI ----------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is not configured in .env"
    )


client = OpenAI(
    api_key=OPENAI_API_KEY
)


# ---------------- AUTHENTICATION ----------------

security = HTTPBearer()


# ---------------- REQUEST MODEL ----------------

class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None


# ---------------- CURRENT USER ----------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token."
            )

        return int(user_id)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired."
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token."
        )


# ---------------- SEND MESSAGE ----------------

@router.post("/message")
def send_message(
    chat: ChatRequest,
    user_id: int = Depends(get_current_user)
):

    message = chat.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty."
        )


    # ---------------- CONVERSATION ----------------

    connection = get_connection()

    try:

        conversation_id = chat.conversation_id


        # If no conversation ID is provided,
        # create a new conversation for this user.

        if conversation_id is None:

            cursor = connection.execute(
                """
                INSERT INTO conversations
                (user_id, title)
                VALUES (?, ?)
                """,
                (
                    user_id,
                    message[:50]
                )
            )

            conversation_id = cursor.lastrowid

        else:

            # Make sure this conversation belongs
            # to the logged-in user.

            conversation = connection.execute(
                """
                SELECT id
                FROM conversations
                WHERE id = ?
                AND user_id = ?
                """,
                (
                    conversation_id,
                    user_id
                )
            ).fetchone()


            if not conversation:

                connection.close()

                raise HTTPException(
                    status_code=404,
                    detail="Conversation not found."
                )


    except HTTPException:
        raise

    except Exception as error:

        connection.close()

        print(
            "Conversation DB Error:",
            error
        )

        raise HTTPException(
            status_code=500,
            detail="Could not create conversation."
        )


    # ---------------- OPENAI ----------------

    try:

        response = client.responses.create(
            model="gpt-5.5",
            instructions=(
                "You are Surwi AI, a helpful and intelligent AI assistant. "
                "Answer clearly, accurately and naturally. "
                "Be useful and concise unless the user asks for detail."
            ),
            input=message
        )

        ai_response = response.output_text


    except Exception as error:

        print(
            "OpenAI API Error:",
            error
        )

        connection.close()

        raise HTTPException(
            status_code=500,
            detail="AI service is currently unavailable."
        )


    # ---------------- SAVE MESSAGES ----------------

    try:

        # Save user's message

        connection.execute(
            """
            INSERT INTO messages
            (conversation_id, role, content)
            VALUES (?, ?, ?)
            """,
            (
                conversation_id,
                "user",
                message
            )
        )


        # Save AI response

        connection.execute(
            """
            INSERT INTO messages
            (conversation_id, role, content)
            VALUES (?, ?, ?)
            """,
            (
                conversation_id,
                "assistant",
                ai_response
            )
        )


        # Update conversation timestamp

        connection.execute(
            """
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                conversation_id,
            )
        )


        connection.commit()
        connection.close()


    except Exception as error:

        connection.rollback()
        connection.close()

        print(
            "Message DB Error:",
            error
        )

        raise HTTPException(
            status_code=500,
            detail="Could not save chat history."
        )


    # ---------------- RESPONSE ----------------

    return {
        "message": ai_response,
        "user_id": user_id,
        "conversation_id": conversation_id
    }

# ============================================================
# CHAT HISTORY
# ============================================================


@router.get("/conversations")
def get_conversations(
    user_id: int = Depends(get_current_user)
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
            ORDER BY updated_at DESC
            """,
            (user_id,)
        ).fetchall()

        return {
            "user_id": user_id,
            "conversations": [
                dict(conversation)
                for conversation in conversations
            ]
        }

    finally:
        connection.close()


@router.get("/conversations/{conversation_id}")
def get_conversation_messages(
    conversation_id: int,
    user_id: int = Depends(get_current_user)
):
    connection = get_connection()

    try:
        # ----------------------------------------------------
        # Verify that conversation belongs to logged-in user
        # ----------------------------------------------------

        conversation = connection.execute(
            """
            SELECT
                id,
                title,
                created_at,
                updated_at
            FROM conversations
            WHERE id = ?
              AND user_id = ?
            """,
            (conversation_id, user_id)
        ).fetchone()

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found."
            )

        # ----------------------------------------------------
        # Get messages
        # ----------------------------------------------------

        messages = connection.execute(
            """
            SELECT
                id,
                role,
                content,
                created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (conversation_id,)
        ).fetchall()

        return {
            "conversation": dict(conversation),
            "messages": [
                dict(message)
                for message in messages
            ]
        }

    finally:
        connection.close()