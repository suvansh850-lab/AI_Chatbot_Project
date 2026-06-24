"""AI provider logic used by the backend API."""

import base64

from .config import (
    GEMINI_API_KEY,
    GEMINI_MODEL_PRIORITY,
    GROQ_API_KEY,
    GROQ_MODEL_PRIORITY,
)
from .schemas import ChatMessage, ChatRequest, ChatResponse, ModelsResponse

try:
    from database import load_messages, load_conversation_uploads
except ImportError:
    load_messages = None
    load_conversation_uploads = None


def import_genai_module():
    try:
        import google.generativeai as genai
        return genai
    except ImportError:
        return None


def import_openai_client():
    try:
        from openai import OpenAI
        return OpenAI
    except ImportError:
        return None



SYSTEM_PROMPT = (
    "You are a powerful, friendly, and general-purpose AI assistant. "
    "You can perform all tasks that an AI chatbot can do, answer any question, "
    "analyse tabular data (CSV/Excel), identify trends, summarise datasets, "
    "interpret statistics, analyse documents and images, and explain complex topics. "
    "When given dataset context, reference specific columns, values, and statistics in your answers. "
    "Format responses clearly with headings, bullet points, and tables where useful. "
    "When using Google Tools (Gmail drafting/Calendar events), ensure that the subject, body, or description you pass into the tool arguments matches EXACTLY the final text you show to the user in the chat interface. Do not rewrite, expand, or alter the content after executing the tool."
)


def open_local_browser_tab(url: str) -> str:
    """Opens a web page in a new browser tab.
    Use this tool when the user asks to open a website, browse a URL locally, or open a link in a tab.

    Args:
        url: The exact HTTP/HTTPS URL of the website to open.
    """
    import webbrowser
    try:
        clean_url = url.strip().strip("'\"")
        webbrowser.open(clean_url)
        return f"Successfully opened new tab for: {clean_url}"
    except Exception as e:
        return f"Failed to open browser tab: {e}"

def browse_webpage(url: str) -> str:
    """Fetches and reads the text content of a webpage so you can answer questions about it.
    Use this tool when the user asks to read, analyze, search, or summarize the contents of a specific URL.

    Args:
        url: The HTTP/HTTPS URL of the webpage to read.
    """
    import urllib.request
    import urllib.parse
    from bs4 import BeautifulSoup
    try:
        clean_url = url.strip().strip("'\"")
        req = urllib.request.Request(
            clean_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read()
        soup = BeautifulSoup(html, "html.parser")
        for s in soup(["script", "style", "meta", "noscript", "header", "footer", "nav"]):
            s.decompose()
        text = soup.get_text(separator=" ", strip=True)
        truncated_text = text[:4000]
        if len(text) > 4000:
            truncated_text += "\n\n[Content truncated for length limit]"
        return f"Successfully fetched content from {clean_url}:\n\n{truncated_text}"
    except Exception as e:
        return f"Failed to read webpage content from {url}: {e}"


def configure_gemini() -> None:
    if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
        genai = import_genai_module()
        if genai is None:
            raise RuntimeError("Install google-generativeai first: pip install google-generativeai")
        genai.configure(api_key=GEMINI_API_KEY)


def get_available_gemini_models() -> list[str]:
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        return []

    configure_gemini()
    genai = import_genai_module()
    if genai is None:
        return []

    available = []
    for model in genai.list_models():
        methods = getattr(model, "supported_generation_methods", [])
        if "generateContent" in methods:
            name = model.name.split("/")[-1]
            if name.startswith("gemini"):
                available.append(name)
    return sorted(set(available))



def get_available_groq_models() -> list[str]:
    if not GROQ_API_KEY or GROQ_API_KEY == "YOUR_GROQ_API_KEY_HERE":
        return []

    OpenAI = import_openai_client()
    if OpenAI is None:
        return []

    try:
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)
        model_ids = [model.id for model in client.models.list().data]
        return sorted(set(model_ids))
    except Exception:
        return GROQ_MODEL_PRIORITY


def choose_available_model(available_models: list[str], preferred_models: list[str]) -> str:
    if not available_models:
        return ""

    for preferred in preferred_models:
        if preferred in available_models:
            return preferred

    return available_models[0]


def get_active_model(provider: str) -> ModelsResponse:
    try:
        if provider == "Gemini":
            available = get_available_gemini_models()
            active = choose_available_model(available, GEMINI_MODEL_PRIORITY)
            return ModelsResponse(provider=provider, active_model=active, available_models=available)

        if provider == "Groq":
            available = get_available_groq_models()
            active = choose_available_model(available, GROQ_MODEL_PRIORITY)
            return ModelsResponse(provider=provider, active_model=active, available_models=available)

        raise ValueError(f"Unknown or unsupported provider: {provider}")
    except Exception as ex:
        return ModelsResponse(provider=provider, active_model="", available_models=[], error=str(ex))


def build_context_text(request: ChatRequest) -> str:
    parts = []
    
    # Retrieve relevant semantic vector context if conversation exists
    if getattr(request, "conversation_id", None):
        try:
            from .vector_service import query_relevant_context
            vector_context = query_relevant_context(request.conversation_id, request.prompt)
            if vector_context:
                parts.append(f"[Relevant Context from uploaded files]:\n{vector_context}")
        except Exception as ve:
            print(f"Error querying vector database context: {ve}")

    if request.document_text:
        parts.append(f"[Document content]:\n{request.document_text[:3000]}")
    if request.data_context:
        parts.append(request.data_context)
    parts.append(f"User: {request.prompt}" if parts else request.prompt)
    return "\n\n".join(parts)


def build_openai_messages(previous_messages: list[ChatMessage], current_text: str, request: ChatRequest, sys_prompt: str = SYSTEM_PROMPT):
    messages = [{"role": "system", "content": sys_prompt}]
    for msg in previous_messages:
        role = "user" if msg.role == "user" else "assistant"
        messages.append({"role": role, "content": msg.content})

    if request.image_base64:
        mime = request.image_mime or "image/jpeg"
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": current_text},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{request.image_base64}"}},
            ],
        })
    else:
        messages.append({"role": "user", "content": current_text})

    return messages


def generate_chat_response(request: ChatRequest) -> ChatResponse:
    model_info = get_active_model(request.provider)
    if model_info.error:
        raise RuntimeError(model_info.error)
    if not model_info.active_model:
        raise RuntimeError(f"No compatible {request.provider} model was found for this API key.")

    # Fetch Google token if user has connected their Google account
    user_id = None
    access_token = None
    if request.conversation_id:
        try:
            from database import get_connection
            if get_connection:
                with get_connection() as conn:
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute("SELECT user_id FROM conversations WHERE id = %s", (request.conversation_id,))
                    row = cursor.fetchone()
                    if row:
                        user_id = int(row["user_id"])
                    cursor.close()
        except Exception:
            pass

    if user_id is not None:
        try:
            from .google_service import get_valid_token
            access_token, _ = get_valid_token(user_id)
        except Exception:
            pass

    # Load history and uploads from DB if conversation_id is provided and database is available
    history_messages = []
    db_document_text = ""
    db_data_context = ""
    db_image_base64 = None
    db_image_mime = None

    if request.conversation_id:
        if load_messages:
            try:
                db_msgs = load_messages(request.conversation_id)
                if db_msgs:
                    for msg in db_msgs:
                        history_messages.append(
                            ChatMessage(role=msg["role"], content=msg["content"])
                        )
            except Exception:
                pass

        if load_conversation_uploads:
            try:
                uploads = load_conversation_uploads(request.conversation_id) or []
                for up in uploads:
                    ftype = up["file_type"]
                    if ftype == "document" and up["text_content"]:
                        db_document_text = up["text_content"]
                    elif ftype == "image" and up["image_data"]:
                        db_image_base64 = base64.b64encode(up["image_data"]).decode("utf-8")
                        db_image_mime = up["mime_type"]
                    elif ftype == "dataset" and up["data_json"]:
                        try:
                            import pandas as pd
                            import io
                            import json
                            df = pd.DataFrame(json.loads(up["data_json"]))
                            buf = io.StringIO()
                            df.info(buf=buf)
                            info_str = buf.getvalue()
                            desc_str = df.describe(include='all').to_string()
                            sample_str = df.head(20).to_string(index=False)
                            db_data_context = (
                                f"\n\n[Uploaded Dataset: {up['filename']}]\n"
                                f"Shape: {df.shape[0]} rows x {df.shape[1]} columns\n"
                                f"Columns: {', '.join(df.columns.tolist())}\n\n"
                                f"Data Info:\n{info_str}\n"
                                f"Statistical Summary:\n{desc_str}\n\n"
                                f"First 20 rows:\n{sample_str}"
                            )
                        except Exception:
                            pass
            except Exception:
                pass

    if not request.document_text and db_document_text:
        request.document_text = db_document_text
    if not request.data_context and db_data_context:
        request.data_context = db_data_context
    if not request.image_base64 and db_image_base64:
        request.image_base64 = db_image_base64
        request.image_mime = db_image_mime

    # Merge history messages with any messages sent in the request body
    combined_messages = history_messages + request.messages

    current_text = build_context_text(request)

    sys_prompt = SYSTEM_PROMPT
    if request.web_search:
        try:
            from web_search import perform_ddg_search, format_search_results_context
            search_results = perform_ddg_search(request.prompt, max_results=5)
            if search_results:
                search_context = format_search_results_context(search_results, request.prompt)
                current_text = f"{search_context}\n\n{current_text}"
                sys_prompt += (
                    "\n\nYou have access to real-time search results. Use the web search results "
                    "below to answer the user's request. You must cite your sources using inline links (e.g., [Title](URL)) "
                    "or list them at the end of your response under a 'Sources' section."
                )
        except Exception:
            pass

    if request.provider == "Groq":
        OpenAI = import_openai_client()
        if OpenAI is None:
            raise RuntimeError("Install the OpenAI package first: pip install openai")

        if not GROQ_API_KEY or GROQ_API_KEY == "YOUR_GROQ_API_KEY_HERE":
            raise RuntimeError("Add your Groq API key to use Groq.")
        client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

        messages = build_openai_messages(combined_messages, current_text, request, sys_prompt)

        # Prepare tools
        tools_list = []
        if access_token:
            tools_list = [
                {
                    "type": "function",
                    "function": {
                        "name": "draft_gmail_email",
                        "description": "Draft a new email in Gmail.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "recipient": {"type": "string", "description": "The email address of the receiver."},
                                "subject": {"type": "string", "description": "The subject of the email."},
                                "body": {"type": "string", "description": "The plain text body of the email."}
                            },
                            "required": ["recipient", "subject", "body"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "create_calendar_event",
                        "description": "Create a new event in Google Calendar.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string", "description": "The event title."},
                                "start_time": {"type": "string", "description": "Start time of the event in ISO 8601 format (e.g. '2026-06-15T09:00:00')."},
                                "end_time": {"type": "string", "description": "End time of the event in ISO 8601 format (e.g. '2026-06-15T10:00:00')."},
                                "description": {"type": "string", "description": "Description of the event (optional)."},
                                "location": {"type": "string", "description": "Location of the event (optional)."}
                            },
                            "required": ["summary", "start_time", "end_time"]
                        }
                    }
                }
            ]

        kwargs = {
            "model": model_info.active_model,
            "messages": messages,
        }
        if tools_list:
            kwargs["tools"] = tools_list
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)
        response_message = response.choices[0].message

        if response_message.tool_calls:
            import json
            from .google_service import draft_email, create_event

            # Add assistant's message with tool calls to the history
            messages.append(response_message)

            for tool_call in response_message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                if tool_call.function.name == "draft_gmail_email":
                    res = draft_email(args.get("recipient", ""), args.get("subject", ""), args.get("body", ""), access_token)
                elif tool_call.function.name == "create_calendar_event":
                    res = create_event(
                        args.get("summary", ""),
                        args.get("start_time", ""),
                        args.get("end_time", ""),
                        args.get("description", ""),
                        args.get("location", ""),
                        access_token
                    )
                else:
                    res = "Unknown function call"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": res
                })

            # Second call to get final text
            final_response = client.chat.completions.create(
                model=model_info.active_model,
                messages=messages
            )
            answer = final_response.choices[0].message.content or ""
        else:
            answer = response_message.content or ""

        return ChatResponse(provider=request.provider, model=model_info.active_model, answer=answer)

    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        raise RuntimeError("Add your Gemini API key to use Gemini.")

    configure_gemini()
    genai = import_genai_module()
    if genai is None:
        raise RuntimeError("Install google-generativeai first: pip install google-generativeai")

    tools = [open_local_browser_tab, browse_webpage]

    if access_token:
        from .google_service import draft_email, create_event

        def draft_gmail_email(recipient: str, subject: str, body: str) -> str:
            """Draft a new email in Gmail.

            Args:
                recipient: The email address of the receiver.
                subject: The subject of the email.
                body: The plain text body of the email.
            """
            return draft_email(recipient, subject, body, access_token)

        def create_calendar_event(summary: str, start_time: str, end_time: str, description: str = "", location: str = "") -> str:
            """Create a new event in Google Calendar.

            Args:
                summary: The event title.
                start_time: Start time of the event in ISO 8601 format (e.g. '2026-06-15T09:00:00').
                end_time: End time of the event in ISO 8601 format (e.g. '2026-06-15T10:00:00').
                description: Description of the event (optional).
                location: Location of the event (optional).
            """
            return create_event(summary, start_time, end_time, description, location, access_token)

        tools.extend([draft_gmail_email, create_calendar_event])

    model = genai.GenerativeModel(model_info.active_model, system_instruction=sys_prompt, tools=tools)
    history = []
    for msg in combined_messages:
        role = "user" if msg.role == "user" else "model"
        history.append({"role": role, "parts": [msg.content]})

    current_parts = [current_text]
    if request.image_base64:
        current_parts.append({
            "mime_type": request.image_mime or "image/jpeg",
            "data": base64.b64decode(request.image_base64),
        })

    chat = model.start_chat(history=history, enable_automatic_function_calling=True)
    response = chat.send_message(current_parts)
    return ChatResponse(provider=request.provider, model=model_info.active_model, answer=response.text)


def transcribe_audio(audio_base64: str, mime_type: str, provider: str = "Gemini") -> tuple[str, str]:
    # Default to Gemini
    model_info = get_active_model("Gemini")
    if model_info.error:
        raise RuntimeError(model_info.error)
    if not model_info.active_model:
        raise RuntimeError("No compatible Gemini model was found for voice transcription.")

    configure_gemini()
    genai = import_genai_module()
    if genai is None:
        raise RuntimeError("Install google-generativeai first: pip install google-generativeai")

    model = genai.GenerativeModel(model_info.active_model)
    audio_part = {"mime_type": mime_type, "data": base64.b64decode(audio_base64)}
    response = model.generate_content([
        "Please accurately transcribe this audio into text. Output only the transcription, nothing else.",
        audio_part,
    ])
    return model_info.active_model, response.text


def generate_speech(text: str, voice: str = "Alice", model: str = "", provider: str = "Edge-TTS", api_key: str | None = None) -> str:
    import asyncio
    import edge_tts
    import base64
    
    voice_map = {
        "alice": "en-GB-SoniaNeural",
        "sarah": "en-US-AriaNeural",
        "charlie": "en-US-ChristopherNeural",
        "george": "en-GB-RyanNeural",
        "callum": "en-AU-WilliamNeural",
        "river": "en-US-MichelleNeural",
        "liam": "en-US-GuyNeural",
        "matilda": "en-US-JennyNeural",
        "will": "en-US-EricNeural",
        "jessica": "en-US-JennyNeural",
        "eric": "en-US-EricNeural",
        "bella": "en-US-AriaNeural",
        "chris": "en-US-ChristopherNeural",
        "brian": "en-GB-RyanNeural",
        "daniel": "en-US-GuyNeural",
        "lily": "en-US-JennyNeural",
        "adam": "en-US-ChristopherNeural",
        "bill": "en-US-EricNeural"
    }
    
    voice_id = voice_map.get(voice.lower(), "en-US-AriaNeural")
    
    async def _synthesize(text, voice):
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
        
    try:
        audio_content = asyncio.run(_synthesize(text, voice_id))
        if not audio_content:
            raise RuntimeError("Edge-TTS API error: Empty audio returned")
        audio_base64 = base64.b64encode(audio_content).decode("utf-8")
        return audio_base64
    except Exception as e:
        raise RuntimeError(f"Edge-TTS synthesis failed: {e}")



