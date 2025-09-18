#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== UMTK Docker Container Starting ===${NC}"

# Function to log with timestamp
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Check and setup directories
log "${BLUE}Setting up directories...${NC}"
mkdir -p /app/config /app/video /app/kometa /app/config/overlay

# Check if config exists, if not copy sample
if [ ! -f /app/config/config.yml ]; then
    log "${YELLOW}config.yml not found, checking for sample config...${NC}"
    if [ -f /app/config.sample.yml ]; then
        cp /app/config.sample.yml /app/config/config.yml
        log "${GREEN}Copied config.sample.yml to config.yml${NC}"
        log "${YELLOW}Please edit /app/config/config.yml with your settings${NC}"
    else
        log "${RED}Error: No config.yml or config.sample.yml found!${NC}"
        log "${RED}Please mount your config directory or ensure config files are present${NC}"
        exit 1
    fi
fi

# Check if video file exists for placeholder method
log "${BLUE}Checking video files...${NC}"
if grep -E "^(tv|movies):\s*2" /app/config/config.yml > /dev/null 2>&1; then
    if [ ! -f /app/video/UMTK.* ]; then
        log "${YELLOW}Placeholder method detected but no UMTK video file found${NC}"
        # Look for UMTK video files in the app directory and copy if found
        if ls /app/UMTK.* 1> /dev/null 2>&1; then
            cp /app/UMTK.* /app/video/
            log "${GREEN}Copied default UMTK video file to video directory${NC}"
        else
            log "${YELLOW}No default video file found. Please add UMTK video file to /app/video/${NC}"
        fi
    else
        log "${GREEN}UMTK video file found for placeholder method${NC}"
    fi
fi

# Copy overlay images if they don't exist
log "${BLUE}Checking overlay files...${NC}"
if [ -d /app/overlay ] && [ ! -f /app/config/overlay/red_frame.png ]; then
    cp -r /app/overlay/* /app/config/overlay/ 2>/dev/null || true
    log "${GREEN}Copied overlay files to config directory${NC}"
fi

# Validate required volume mounts
log "${BLUE}Validating volume mounts...${NC}"
if [ ! -w /app/kometa ]; then
    log "${RED}Error: /app/kometa directory is not writable!${NC}"
    log "${RED}Please ensure proper volume mount for output directory${NC}"
    exit 1
fi

# Check config for placeholder values
if grep -q "your_sonarr_url_here\|your_api_key_here" /app/config/config.yml 2>/dev/null; then
    log "${YELLOW}Warning: Default placeholder values detected in config.yml${NC}"
    log "${YELLOW}Please update your config.yml with your actual Sonarr/Radarr URLs and API keys${NC}"
fi

# Function to get next cron run time
get_next_cron_time() {
    python3 -c "
import subprocess
import datetime
from datetime import timezone
import re

cron_expression = '$CRON'
parts = cron_expression.split()
if len(parts) == 5:
    minute, hour, day, month, dow = parts
    now = datetime.datetime.now()
    
    # Simple calculation for next run (basic implementation)
    next_hour = int(hour) if hour != '*' else now.hour
    next_minute = int(minute) if minute != '*' else now.minute
    
    # Calculate next run time
    next_run = now.replace(hour=next_hour, minute=next_minute, second=0, microsecond=0)
    
    # If time has passed today, move to tomorrow
    if next_run <= now:
        next_run += datetime.timedelta(days=1)
    
    print(next_run.strftime('%Y-%m-%d %H:%M:%S'))
else:
    print('Unable to parse cron expression')
"
}

# Setup cron job as non-root user
log "${BLUE}Setting up cron schedule: ${CRON}${NC}"
echo "$CRON cd /app && DOCKER=true /usr/local/bin/python UMTK.py 2>&1 | tee -a /var/log/cron.log" > /tmp/umtk-cron
sudo crontab -u umtk /tmp/umtk-cron
rm /tmp/umtk-cron

# Get next scheduled run time
NEXT_RUN=$(get_next_cron_time)
log "${GREEN}Next scheduled run: ${NEXT_RUN}${NC}"

# Run once on startup
log "${GREEN}Running UMTK on startup...${NC}"
cd /app && DOCKER=true /usr/local/bin/python UMTK.py

# Start cron and tail logs
log "${BLUE}Starting cron daemon...${NC}"
log "${BLUE}Container is now running. Next execution scheduled for: ${NEXT_RUN}${NC}"
log "${BLUE}Use 'docker logs -f umtk' to follow the logs${NC}"

sudo touch /var/log/cron.log
sudo chmod 666 /var/log/cron.log
sudo cron
tail -f /var/log/cron.log