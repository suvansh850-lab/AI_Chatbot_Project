"""Backend configuration.

Environment variables are preferred. The fallback values match the current
Streamlit app so the backend can run with the existing project setup.
"""

import os
import sys

# Add parent directory to sys.path to resolve database import
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from database import get_secret
except Exception:
    def get_secret(key: str, default: str = "") -> str:
        return os.getenv(key, default)


GEMINI_API_KEY = get_secret("GEMINI_API_KEY", "")
GROQ_API_KEY = get_secret("GROQ_API_KEY", "")

DEFAULT_TTS_VOICE = get_secret("DEFAULT_TTS_VOICE", "Alice")

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
