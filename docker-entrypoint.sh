#!/bin/bash

# Check if config exists
if [ ! -f /app/config/config.yml ]; then
    echo "Error: config.yml not found in /app/config directory"
    echo "Please either:"
    echo "1. Mount your custom config: -v ./config:/app/config"
    echo "2. Or copy the default config from the container and customize it"
    echo "   docker cp container_name:/app/config/config.yml ./config.yml"
    exit 1
fi

# Check if video file exists (only if placeholder method is used)
if grep -E "^(tv|movies):\s*2" /app/config/config.yml > /dev/null 2>&1; then
    if [ ! -f /video/UMTK.* ]; then
        echo "Warning: No UMTK video file found in /video directory"
        echo "Placeholder method requires a video file named UMTK (with any extension)"
        echo "Either:"
        echo "1. Use the default video file (already included)"
        echo "2. Mount your custom video: -v ./video:/video"
    else
        echo "Found UMTK video file for placeholder method"
    fi
fi

# Check if the config has default/placeholder values that need to be updated
if grep -q "your_sonarr_url_here\|your_api_key_here" /app/config/config.yml 2>/dev/null; then
    echo "Warning: Default placeholder values detected in config.yml"
    echo "Please update your config.yml with your actual Sonarr/Radarr URLs and API keys"
fi

# Set up cron job
echo "$CRON cd /app && DOCKER=true /usr/local/bin/python UMTK.py 2>&1 | tee -a /var/log/cron.log" > /etc/cron.d/umtk-cron
chmod 0644 /etc/cron.d/umtk-cron
crontab /etc/cron.d/umtk-cron
echo "UMTK is starting with the following cron schedule: $CRON"

# Run once on startup
echo "Running UMTK on startup..."
cd /app && DOCKER=true /usr/local/bin/python UMTK.py

# Start cron and tail logs
touch /var/log/cron.log
cron
tail -f /var/log/cron.log