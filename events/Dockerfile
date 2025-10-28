FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for WeasyPrint and PDF generation
RUN apt-get update && apt-get install -y \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set PYTHONPATH to include src directory
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8000

# Start server (run migrations manually first)
CMD ["uvicorn", "events.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
