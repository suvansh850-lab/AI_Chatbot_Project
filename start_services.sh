#!/bin/bash
# Start FastAPI backend in background on local port 8000
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &

# Start Streamlit frontend in foreground, listening on the port allocated by Railway
streamlit run app.py --server.port ${PORT:-8501} --server.address 0.0.0.0
