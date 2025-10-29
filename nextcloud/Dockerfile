FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set Python path
ENV PYTHONPATH=/app/src

# Create necessary directories
RUN mkdir -p /app/logs
RUN mkdir -p /app/alembic/versions

# Copy Alembic configuration
COPY alembic.ini .
COPY alembic/ ./alembic/

EXPOSE 8000

CMD ["uvicorn", "nextcloud.main:app", "--host", "0.0.0.0", "--port", "8000"]
