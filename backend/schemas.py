"""Request and response models for the backend API."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    provider: Literal["Gemini", "ChatGPT", "OpenRouter", "Groq"] = "Gemini"
    conversation_id: int | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    document_text: str = ""
    data_context: str = ""
    image_base64: str | None = None
    image_mime: str | None = None
    web_search: bool = False


class ChatResponse(BaseModel):
    provider: str
    model: str
    answer: str


class ModelsResponse(BaseModel):
    provider: str
    active_model: str
    available_models: list[str]
    error: str = ""


class TranscriptionRequest(BaseModel):
    audio_base64: str = Field(..., min_length=1)
    mime_type: str = "audio/wav"
    provider: str = "Gemini"  # "Gemini" or "Whisper"


class TranscriptionResponse(BaseModel):
    model: str
    text: str


class SpeechSynthesisRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice: str = "Alice"  # ElevenLabs default voice
    model: str = "eleven_multilingual_v2"
    provider: str = "ElevenLabs"
    api_key: str | None = None


class SpeechSynthesisResponse(BaseModel):
    audio_base64: str
    format: str = "mp3"
