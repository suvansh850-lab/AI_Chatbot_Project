import subprocess
import os
import sys
import time

# 1. Sanitize the PORT variable
port_str = os.getenv("PORT", "8501").strip()
if not port_str.isdigit():
    print(f"Warning: Allocating fallback port since PORT environment variable was '{port_str}'")
    port_str = "8501"

print(f"Launching FastAPI backend on localhost:8000 in background...")
backend_process = subprocess.Popen([
    sys.executable, "-m", "uvicorn", "backend.main:app",
    "--host", "127.0.0.1", "--port", "8000"
])

# Give FastAPI a moment to start
time.sleep(1)

print(f"Launching Streamlit frontend on 0.0.0.0:{port_str} in foreground...")
try:
    subprocess.run([
        "streamlit", "run", "app.py",
        "--server.port", port_str,
        "--server.address", "0.0.0.0"
    ], check=True)
finally:
    # Safely terminate the backend process on shutdown
    backend_process.terminate()
