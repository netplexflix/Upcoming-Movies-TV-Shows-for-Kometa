#!/bin/bash

# Check if config exists
if [ ! -f /app/config/config.yml ]; then
    echo "Error: config.yml not found in /app/config directory"
    echo "Please mount your config file to /app/config/config.yml"
    exit 1
fi

# Check if video file exists (only if placeholder method is used)
if [ ! -f /video/UMTK.* ] && grep -E "^(tv|movies):\s*2" /app/config/config.yml > /dev/null 2>&1; then
    echo "Warning: UMTK video file not found in /video directory"
    echo "Placeholder method requires a video file named UMTK (with any extension)"
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