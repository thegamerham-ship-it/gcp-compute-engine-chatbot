# Google Cloud Run optimized Dockerfile (ADC Keyless Mode)
# Python 3.11 slim image for fast startup and minimal footprint
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install system dependencies (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies first for efficient layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source and frontend assets
COPY server.py .
COPY public/ ./public/

# Expose port (Cloud Run defaults to 8080)
EXPOSE 8080

# Cloud Run injects $PORT at runtime. Using shell exec ensures SIGTERM signals reach uvicorn directly.
CMD exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
