FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/websites /app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

# Create directories for generated sites and uploads
RUN mkdir -p /app/generated /app/uploads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
