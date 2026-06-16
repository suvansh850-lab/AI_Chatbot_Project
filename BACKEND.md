# AI Chatbot Backend

This project now includes a FastAPI backend in `backend/`.

## Run

```powershell
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

Open the API docs at:

```text
http://localhost:8000/docs
```

## Endpoints

- `GET /health` - backend and database health check
- `GET /models/Gemini` - active and available Gemini models
- `GET /models/ChatGPT` - active and available OpenAI models
- `POST /chat` - generate a chat response
- `POST /transcribe` - transcribe base64 audio with the available Gemini model

## Example Chat Request

```json
{
  "provider": "Gemini",
  "prompt": "Hello, summarize what this chatbot can do.",
  "messages": []
}
```

## API Keys

The backend reads `GEMINI_API_KEY` and `OPENAI_API_KEY` from environment variables when they are set. If they are not set, it falls back to the current values used by the Streamlit app.

## MySQL / phpMyAdmin with XAMPP

1. Open XAMPP Control Panel and start `Apache` and `MySQL`.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run the Streamlit app:

```powershell
streamlit run app.py
```

The app automatically creates a MySQL database named `ai_chatbot_db` using the default XAMPP user `root` with no password. You can view all saved chatbot data in phpMyAdmin:

```text
http://localhost/phpmyadmin
```

Tables created:

- `users` - login user records
- `conversations` - chat sessions
- `messages` - user and assistant chat messages, snippets, and images
- `uploads` - documents, images, spreadsheets, Google Drive imports, and dataset previews
- `voice_transcriptions` - voice-search audio and transcript text
- `api_logs` - model provider, prompt, response, status, and errors

If your MySQL username/password/database are different, set these environment variables before starting the app:

```powershell
$env:MYSQL_HOST="localhost"
$env:MYSQL_PORT="3306"
$env:MYSQL_USER="root"
$env:MYSQL_PASSWORD=""
$env:MYSQL_DATABASE="ai_chatbot_db"
```

You can also import `database_schema.sql` manually in phpMyAdmin if you prefer creating the schema yourself.
