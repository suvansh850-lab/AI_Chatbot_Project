#!/bin/bash

# Sanitize PORT: if it is empty, a literal string, or not a number, default to 8501
if [ -z "$PORT" ] || [ "$PORT" = "\$PORT" ] || [ "$PORT" = "\$port" ] || ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
  export PORT=8501
fi

# Start FastAPI backend in background on local port 8000
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &

# Start Streamlit frontend in foreground
streamlit run app.py --server.port "$PORT" --server.address 0.0.0.0
