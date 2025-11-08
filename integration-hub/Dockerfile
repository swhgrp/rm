FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ /app/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "integration_hub.main:app", "--host", "0.0.0.0", "--port", "8000"]
