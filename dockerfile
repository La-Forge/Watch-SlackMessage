# Minimal, production-friendly Python image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps if needed (openssl/ca-certificates are already there)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY slack_to_airtable.py .

# Default envs (override via docker run -e ...)
ENV CHANNEL_PREFIX="share" \
    TEST_MODE="false"

# Run
ENTRYPOINT ["python", "slack_to_airtable.py"]