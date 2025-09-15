# Use a slim Python image as the base
FROM python:3.11-slim

# Disable .pyc files and enable real-time logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CRON="0 2 * * *" \
    DOCKER=true
# default: run at 2AM daily

# Set working directory
WORKDIR /app

# Install system dependencies including ffmpeg for yt-dlp
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    cron \
    tzdata \
    ffmpeg \
    curl && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy files
COPY . /app

# Copy and prepare the entrypoint
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create necessary directories
RUN mkdir -p /output /media

# Start with the entrypoint script (sets up cron)
ENTRYPOINT ["/entrypoint.sh"]