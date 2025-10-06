FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create directories
RUN mkdir -p /app/logs

# Set Python path
ENV PYTHONPATH=/app/src

# Run the application
CMD ["uvicorn", "accounting.main:app", "--host", "0.0.0.0", "--port", "8000"]
