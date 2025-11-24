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
    DOCKER=true \
    DENO_INSTALL="/usr/local" \
    DENO_DIR="/app/.deno"
# default: run at 2AM daily

# Install system dependencies including ffmpeg for yt-dlp and unzip for Deno
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    cron \
    tzdata \
    ffmpeg \
    curl \
    unzip \
    gosu && \
    rm -rf /var/lib/apt/lists/*

# Install Deno - using direct binary download for reliability
RUN DENO_VERSION="2.5.6" && \
    ARCH="$(dpkg --print-architecture)" && \
    if [ "$ARCH" = "amd64" ]; then DENO_ARCH="x86_64"; \
    elif [ "$ARCH" = "arm64" ]; then DENO_ARCH="aarch64"; \
    else echo "Unsupported architecture: $ARCH" && exit 1; fi && \
    curl -fsSL "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-${DENO_ARCH}-unknown-linux-gnu.zip" -o /tmp/deno.zip && \
    unzip -q /tmp/deno.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/deno && \
    rm /tmp/deno.zip && \
    deno --version

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy files
COPY . /app

# Create necessary directories with proper permissions
RUN mkdir -p /app/config /app/video /app/kometa /app/config/overlay /app/logs /app/.deno && \
    chown -R umtk:umtk /app

# Copy and prepare the entrypoint
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Start with the entrypoint script (handles user creation and switches to umtk user)
ENTRYPOINT ["/entrypoint.sh"]