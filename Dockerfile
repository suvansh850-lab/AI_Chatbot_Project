FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for building packages
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create directory to store persistent SQLite and ChromaDB data
RUN mkdir -p /app/data

# Mark launch script as executable
RUN chmod +x /app/start_services.sh

# Expose Streamlit's default port
EXPOSE 8501

CMD ["/app/start_services.sh"]
