FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including LibreOffice for document conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libreoffice \
    libreoffice-writer \
    libreoffice-calc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ /app/src/

# Set Python path
ENV PYTHONPATH=/app/src

# Create directories
RUN mkdir -p /app/logs /app/storage

EXPOSE 8000

CMD ["uvicorn", "files.main:app", "--host", "0.0.0.0", "--port", "8000"]
