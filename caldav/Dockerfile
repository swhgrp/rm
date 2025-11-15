FROM python:3.11-slim

# Install Radicale
RUN pip install --no-cache-dir radicale passlib bcrypt

# Create data directory
RUN mkdir -p /data/collections

# Copy configuration
COPY config /etc/radicale/config
COPY rights /etc/radicale/rights

EXPOSE 5232

CMD ["radicale", "--config", "/etc/radicale/config"]
