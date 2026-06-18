"""Backend configuration.

Environment variables are preferred. The fallback values match the current
Streamlit app so the backend can run with the existing project setup.
"""

import os


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

DEFAULT_TTS_VOICE = os.getenv("DEFAULT_TTS_VOICE", "Alice")

GEMINI_MODEL_PRIORITY = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

GROQ_MODEL_PRIORITY = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]

