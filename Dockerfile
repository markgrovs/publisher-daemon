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

# Copy setup files first
COPY setup.py setup.py

# Copy publisher package and scripts
COPY publisher/ ./publisher/
COPY scripts/ ./scripts/

# Install publisher package in development mode so imports work
RUN pip install -e . && \
    python3 -c "from publisher import PublisherDaemon; print('✓ Publisher module installed')"

# Ensure entrypoints are executable
RUN chmod +x scripts/*.py

# Default to nextmountain entrypoint (can be overridden in Compose)
ENTRYPOINT ["python3", "scripts/nextmountain_entrypoint.py"]
