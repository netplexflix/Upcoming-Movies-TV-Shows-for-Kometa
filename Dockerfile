# Use a slim Python image as the base
FROM python:3.11-slim

# Create a non-root user
ARG PUID=1000
ARG PGID=1000
RUN groupadd -g ${PGID} umtk && \
    useradd -u ${PUID} -g ${PGID} -d /app -s /bin/bash umtk

# Disable .pyc files and enable real-time logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CRON="0 2 * * *" \
    DOCKER=true
# default: run at 2AM daily

# Install system dependencies including ffmpeg for yt-dlp
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    cron \
    tzdata \
    ffmpeg \
    curl \
    gosu && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy files
COPY . /app

# Create necessary directories with proper permissions
RUN mkdir -p /app/config /app/video /app/kometa /app/config/overlay /app/logs && \
    chown -R umtk:umtk /app && \
    chmod 755 /var/spool/cron/crontabs && \
    chmod 755 /var/spool/cron && \
    chown umtk:umtk /var/spool/cron/crontabs

# Copy and prepare the entrypoint
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Start with the entrypoint script (handles user creation and switches to umtk user)
ENTRYPOINT ["/entrypoint.sh"]