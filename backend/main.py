"""FastAPI backend for the AI Chatbot project."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .ai_service import generate_chat_response, get_active_model, transcribe_audio, generate_speech
from .schemas import ChatRequest, ChatResponse, ModelsResponse, TranscriptionRequest, TranscriptionResponse, SpeechSynthesisRequest, SpeechSynthesisResponse
try:
    from database import database_status, init_database, save_api_log
except Exception:
    database_status = None
    init_database = None
    save_api_log = None


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

