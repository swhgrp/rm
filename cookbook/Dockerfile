FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including tesseract for OCR fallback)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set Python path
ENV PYTHONPATH=/app/src

# Create necessary directories
RUN mkdir -p /app/uploads /app/alembic/versions /data/chroma /data/uploads

# Copy Alembic files
COPY alembic.ini .
COPY alembic/ ./alembic/

# Expose port
EXPOSE 8000

# Run migrations then start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn restaurant_cookbook.main:app --host 0.0.0.0 --port 8000"]
