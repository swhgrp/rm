FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    procps \
    coreutils \
    curl \
    openssl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ /app/
COPY templates/ /app/templates/
COPY css/ /app/static/css/
COPY images/ /app/static/images/
COPY js/ /app/static/js/
COPY html/ /app/static/html/

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "portal.main:app", "--host", "0.0.0.0", "--port", "8000"]
