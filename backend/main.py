import sys
import os
import requests
import threading
from fastapi import FastAPI, HTTPException, Request, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from .ai_service import generate_chat_response, get_active_model, transcribe_audio, generate_speech
from .schemas import ChatRequest, ChatResponse, ModelsResponse, TranscriptionRequest, TranscriptionResponse, SpeechSynthesisRequest, SpeechSynthesisResponse

# Add parent directory to sys.path to resolve database import
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from database import (
        database_status,
        init_database,
        save_api_log,
        ensure_user,
        create_conversation,
        save_message,
        get_connection,
        get_secret
    )
except Exception as e:
    print(f"Error importing from database module in backend: {e}")
    database_status = None
    init_database = None
    save_api_log = None
    ensure_user = None
    create_conversation = None
    save_message = None
    get_connection = None
    def get_secret(key: str, default: str = "") -> str:
        return os.getenv(key, default)


app = FastAPI(title="AI Chatbot Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def setup_database():
    if init_database:
        try:
            init_database()
        except Exception:
            pass
    try:
        from .scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        print(f"Error starting background task scheduler: {e}")


@app.on_event("shutdown")
def shutdown_scheduler():
    try:
        from .scheduler import stop_scheduler
        stop_scheduler()
    except Exception as e:
        print(f"Error stopping background task scheduler: {e}")


@app.get("/health")
def health_check():
    db = database_status() if database_status else {"ok": "false", "error": "Database module unavailable"}
    return {"status": "ok", "database": db}


@app.get("/models/{provider}", response_model=ModelsResponse)
def models(provider: str):
    if provider not in {"Gemini", "Groq"}:
        raise HTTPException(status_code=400, detail="Provider must be Gemini or Groq.")
    return get_active_model(provider)


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        response = generate_chat_response(request)
        if save_api_log:
            try:
                save_api_log(
                    request.conversation_id,
                    request.provider,
                    response.model,
                    request.prompt,
                    response.answer,
                )
            except Exception:
                pass
        return response
    except Exception as ex:
        if save_api_log:
            try:
                save_api_log(request.conversation_id, request.provider, "", request.prompt, "", "error", str(ex))
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=str(ex)) from ex


@app.post("/transcribe", response_model=TranscriptionResponse)
def transcribe(request: TranscriptionRequest):
    try:
        model, text = transcribe_audio(request.audio_base64, request.mime_type, request.provider)
        return TranscriptionResponse(model=model, text=text)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex


@app.post("/synthesize", response_model=SpeechSynthesisResponse)
def synthesize(request: SpeechSynthesisRequest):
    try:
        audio_base64 = generate_speech(request.text, request.voice, request.model, request.provider, request.api_key)
        return SpeechSynthesisResponse(audio_base64=audio_base64)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex


# ── Webhook Helpers and Routes ───────────────────────────────────────

def send_telegram_message(token: str, chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            # Fallback to plain text if Markdown parsing fails
            payload.pop("parse_mode", None)
            response = requests.post(url, json=payload, timeout=10)
        return response
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return None


def get_or_create_telegram_conversation(user_id: int) -> int:
    if not get_connection or not create_conversation:
        raise RuntimeError("Database connection or create_conversation is unavailable")
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id FROM conversations WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                (user_id,)
            )
            row = cursor.fetchone()
            cursor.close()
            if row:
                return int(row["id"])
    except Exception as e:
        print(f"Error finding conversation: {e}")
        
    return create_conversation(user_id, title="Telegram Conversation", provider="Groq")


def send_whatsapp_message(access_token: str, phone_number_id: str, to_number: str, text: str):
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text
        }
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response
    except Exception as e:
        print(f"Error sending WhatsApp message: {e}")
        return None


def get_or_create_whatsapp_conversation(user_id: int) -> int:
    if not get_connection or not create_conversation:
        raise RuntimeError("Database connection or create_conversation is unavailable")
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id FROM conversations WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                (user_id,)
            )
            row = cursor.fetchone()
            cursor.close()
            if row:
                return int(row["id"])
    except Exception as e:
        print(f"Error finding conversation: {e}")
        
    return create_conversation(user_id, title="WhatsApp Conversation", provider="Groq")


# ── Webhook Deduplication and Async Processing ──────────────────────

processed_telegram_updates = set()
processed_telegram_updates_list = []
telegram_lock = threading.Lock()

def is_telegram_duplicate(update_id: int) -> bool:
    with telegram_lock:
        if update_id in processed_telegram_updates:
            return True
        processed_telegram_updates.add(update_id)
        processed_telegram_updates_list.append(update_id)
        if len(processed_telegram_updates_list) > 1000:
            oldest = processed_telegram_updates_list.pop(0)
            processed_telegram_updates.discard(oldest)
        return False


processed_whatsapp_messages = set()
processed_whatsapp_messages_list = []
whatsapp_lock = threading.Lock()

def is_whatsapp_duplicate(message_id: str) -> bool:
    with whatsapp_lock:
        if message_id in processed_whatsapp_messages:
            return True
        processed_whatsapp_messages.add(message_id)
        processed_whatsapp_messages_list.append(message_id)
        if len(processed_whatsapp_messages_list) > 1000:
            oldest = processed_whatsapp_messages_list.pop(0)
            processed_whatsapp_messages.discard(oldest)
        return False


def process_telegram_webhook(chat_id: int, text_body: str, token: str):
    if not ensure_user or not save_message:
        return
        
    try:
        # 1. Ensure user exists
        username = f"telegram_{chat_id}"
        user_id = ensure_user(username, "telegram_webhook_secret_pass")
        
        # 2. Get or create conversation thread
        conversation_id = get_or_create_telegram_conversation(user_id)
        
        # 3. Save incoming user message
        save_message(conversation_id, "user", text_body)
        
        # 4. Generate response using AI Service
        chat_req = ChatRequest(
            prompt=text_body,
            provider="Groq",
            conversation_id=conversation_id,
            messages=[],
            document_text="",
            data_context="",
            image_base64=None,
            image_mime=None,
            web_search=False
        )
        
        try:
            ai_resp = generate_chat_response(chat_req)
            reply_text = ai_resp.answer
            model_name = ai_resp.model
        except Exception as e:
            reply_text = f"Sorry, I encountered an error while generating a response: {str(e)}"
            model_name = "error"
            
        # 5. Save assistant response
        save_message(conversation_id, "assistant", reply_text)
        
        # 6. Save API log
        if save_api_log:
            try:
                save_api_log(
                    conversation_id,
                    "Groq",
                    model_name,
                    text_body,
                    reply_text
                )
            except Exception:
                pass
                
        # 7. Send the message back via Telegram API
        send_telegram_message(token, chat_id, reply_text)
    except Exception as e:
        print(f"Error in background telegram task: {e}")


def process_whatsapp_webhook(access_token: str, phone_number_id: str, from_number: str, text_body: str):
    if not ensure_user or not save_message:
        return
        
    try:
        # 1. Ensure user exists
        username = f"whatsapp_{from_number}"
        user_id = ensure_user(username, "whatsapp_webhook_secret_pass")
        
        # 2. Get or create conversation thread
        conversation_id = get_or_create_whatsapp_conversation(user_id)
        
        # 3. Save incoming user message
        save_message(conversation_id, "user", text_body)
        
        # 4. Generate response using AI Service
        chat_req = ChatRequest(
            prompt=text_body,
            provider="Groq",
            conversation_id=conversation_id,
            messages=[],
            document_text="",
            data_context="",
            image_base64=None,
            image_mime=None,
            web_search=False
        )
        
        try:
            ai_resp = generate_chat_response(chat_req)
            reply_text = ai_resp.answer
            model_name = ai_resp.model
        except Exception as e:
            reply_text = f"Sorry, I encountered an error while generating a response: {str(e)}"
            model_name = "error"
            
        # 5. Save assistant response
        save_message(conversation_id, "assistant", reply_text)
        
        # 6. Save API log
        if save_api_log:
            try:
                save_api_log(
                    conversation_id,
                    "Groq",
                    model_name,
                    text_body,
                    reply_text
                )
            except Exception:
                pass
                
        # 7. Send the message back via WhatsApp Cloud API
        send_whatsapp_message(access_token, phone_number_id, from_number, reply_text)
    except Exception as e:
        print(f"Error in background whatsapp task: {e}")


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request, background_tasks: BackgroundTasks):
    token = get_secret("TELEGRAM_BOT_TOKEN", "")
    if not token or token == "your-telegram-bot-token":
        raise HTTPException(status_code=400, detail="Telegram bot token not configured")
        
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    update_id = payload.get("update_id")
    if update_id is not None:
        if is_telegram_duplicate(update_id):
            return {"status": "ignored", "reason": "duplicate update"}
            
    message = payload.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text_body = message.get("text")
    
    if not chat_id or not text_body:
        return {"status": "ignored", "reason": "no chat_id or text message"}
        
    background_tasks.add_task(process_telegram_webhook, chat_id, text_body, token)
    
    return {"status": "accepted"}


@app.get("/webhook/whatsapp")
async def webhook_whatsapp_verify(request: Request):
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    challenge = params.get("hub.challenge")
    verify_token = params.get("hub.verify_token")
    
    token = get_secret("WHATSAPP_VERIFY_TOKEN", "")
    if not token or token == "your-whatsapp-webhook-verify-token":
        raise HTTPException(status_code=400, detail="WhatsApp verify token not configured")
        
    if mode == "subscribe" and verify_token == token:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request, background_tasks: BackgroundTasks):
    access_token = get_secret("WHATSAPP_ACCESS_TOKEN", "")
    phone_number_id = get_secret("WHATSAPP_PHONE_NUMBER_ID", "")
    
    if not access_token or access_token == "your-whatsapp-access-token":
        raise HTTPException(status_code=400, detail="WhatsApp access token not configured")
    if not phone_number_id or phone_number_id == "your-whatsapp-phone-number-id":
        raise HTTPException(status_code=400, detail="WhatsApp phone number ID not configured")
        
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    entry = payload.get("entry", [])
    if not entry:
        return {"status": "ignored", "reason": "no entry list"}
        
    changes = entry[0].get("changes", [])
    if not changes:
        return {"status": "ignored", "reason": "no changes"}
        
    value = changes[0].get("value", {})
    messages = value.get("messages", [])
    if not messages:
        return {"status": "ignored", "reason": "no messages in payload (status update)"}
        
    message = messages[0]
    if message.get("type") != "text":
        return {"status": "ignored", "reason": "unsupported message type"}
        
    from_number = message.get("from")
    text_body = message.get("text", {}).get("body")
    message_id = message.get("id")
    
    if not from_number or not text_body:
        return {"status": "ignored", "reason": "missing phone number or body"}
        
    if message_id is not None:
        if is_whatsapp_duplicate(message_id):
            return {"status": "ignored", "reason": "duplicate message"}
            
    background_tasks.add_task(process_whatsapp_webhook, access_token, phone_number_id, from_number, text_body)
    
    return {"status": "accepted"}

