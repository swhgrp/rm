FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set Python path to find our modules
ENV PYTHONPATH=/app/src

# Create necessary directories
RUN mkdir -p /app/uploads
RUN mkdir -p /app/alembic/versions

# Copy additional files
COPY alembic.ini .
COPY alembic/ ./alembic/

# Expose port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "restaurant_inventory.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
