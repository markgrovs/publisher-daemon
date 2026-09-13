FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    openssh-client \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy publisher package
COPY publisher/ ./publisher/
COPY scripts/ ./scripts/

# Ensure entrypoints are executable
RUN chmod +x scripts/*.py

# Default to nextmountain entrypoint (can be overridden in Compose)
ENTRYPOINT ["python3", "scripts/nextmountain_entrypoint.py"]
