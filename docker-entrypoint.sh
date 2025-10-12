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

# Handle PUID/PGID environment variables
log "${BLUE}Setting up user permissions...${NC}"
PUID=${PUID:-1000}
PGID=${PGID:-1000}

log "${BLUE}Using PUID:${PUID} PGID:${PGID}${NC}"

# Check if we need to create/modify user
if [ "$PUID" != "1000" ] || [ "$PGID" != "1000" ]; then
    log "${BLUE}Creating user with PUID:${PUID} PGID:${PGID}${NC}"
    
    # Create group if it doesn't exist
    if ! getent group $PGID > /dev/null 2>&1; then
        groupadd -g $PGID umtk
        log "${GREEN}Created group with GID:${PGID}${NC}"
    fi
    
    # Create user if it doesn't exist
    if ! getent passwd $PUID > /dev/null 2>&1; then
        useradd -u $PUID -g $PGID -d /app -s /bin/bash umtk
        log "${GREEN}Created user with UID:${PUID}${NC}"
    else
        # Update existing user's group
        usermod -g $PGID umtk 2>/dev/null || true
        log "${GREEN}Updated user group to GID:${PGID}${NC}"
    fi
fi

# Check and setup directories (as root)
log "${BLUE}Setting up directories...${NC}"
mkdir -p /app/config /app/video /app/kometa /app/config/overlay /app/logs

# Check if config exists, if not copy sample
if [ ! -f /app/config/config.yml ]; then
    log "${YELLOW}config.yml not found, checking for sample config...${NC}"
    if [ -f /app/config/config.sample.yml ]; then
        cp /app/config/config.sample.yml /app/config/config.yml
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
    if ! ls /app/video/UMTK.* 1> /dev/null 2>&1; then
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
else
    log "${GREEN}Video files check completed${NC}"
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

# Fix ownership of all directories before switching user
log "${BLUE}Setting ownership of /app to ${PUID}:${PGID}...${NC}"
chown -R $PUID:$PGID /app 2>/dev/null || log "${YELLOW}Warning: Could not change ownership of some files in /app${NC}"

# Fix ownership of kometa directory specifically and ensure it's writable
if [ -d /app/kometa ]; then
    log "${BLUE}Fixing ownership and permissions of /app/kometa...${NC}"
    chown -R $PUID:$PGID /app/kometa 2>/dev/null || log "${YELLOW}Warning: Could not change ownership of some files in /app/kometa${NC}"
    chmod -R u+rw /app/kometa 2>/dev/null || log "${YELLOW}Warning: Could not change permissions of some files in /app/kometa${NC}"
fi

# Ensure logs directory is writable
log "${BLUE}Setting up logging...${NC}"
mkdir -p /app/logs
chown -R $PUID:$PGID /app/logs 2>/dev/null || true
chmod -R u+rw /app/logs 2>/dev/null || true
touch /app/logs/umtk.log
chown $PUID:$PGID /app/logs/umtk.log 2>/dev/null || true
chmod u+rw /app/logs/umtk.log 2>/dev/null || true

# Function to get next cron run time
get_next_cron_time() {
    python3 -c "
import datetime
import re

cron_expression = '$CRON'
parts = cron_expression.split()
if len(parts) == 5:
    minute, hour, day, month, dow = parts
    now = datetime.datetime.now()
    
    # Function to parse cron field with step values
    def parse_field(field, min_val, max_val, current_val):
        if field == '*':
            return None  # Wildcard
        elif '/' in field:
            # Handle step values like */6
            base, step = field.split('/')
            step = int(step)
            if base == '*':
                # Find next value divisible by step
                next_val = ((current_val // step) * step) + step
                if next_val > max_val:
                    next_val = 0
                return next_val
            else:
                # Handle ranges with steps (not common, but supported)
                return int(base)
        elif ',' in field:
            # Handle comma-separated values
            values = [int(v) for v in field.split(',')]
            for v in sorted(values):
                if v > current_val:
                    return v
            return sorted(values)[0]  # Wrap to first
        elif '-' in field:
            # Handle ranges
            start, end = map(int, field.split('-'))
            if current_val < start:
                return start
            elif current_val < end:
                return current_val + 1
            else:
                return start  # Wrap around
        else:
            return int(field)
    
    # Parse minute and hour
    target_minute = parse_field(minute, 0, 59, now.minute)
    target_hour = parse_field(hour, 0, 23, now.hour)
    
    # Calculate next run time
    next_run = now.replace(second=0, microsecond=0)
    
    if target_hour is None and target_minute is None:
        # Every minute (unlikely but handle it)
        next_run = next_run + datetime.timedelta(minutes=1)
    elif target_hour is None:
        # Every hour at target minute
        next_run = next_run.replace(minute=target_minute)
        if next_run <= now:
            next_run = next_run + datetime.timedelta(hours=1)
    elif target_minute is None:
        # Target hour, every minute (unlikely)
        next_run = next_run.replace(hour=target_hour)
        if next_run <= now:
            next_run = next_run + datetime.timedelta(days=1)
    else:
        # Specific hour and minute
        next_run = next_run.replace(hour=target_hour, minute=target_minute)
        
        # If time has passed today, calculate next occurrence
        if next_run <= now:
            if '/' in hour:
                # Step value in hour - add step hours
                _, step = hour.split('/')
                next_run = next_run + datetime.timedelta(hours=int(step))
            else:
                # Fixed hour - move to next day
                next_run = next_run + datetime.timedelta(days=1)
    
    print(next_run.strftime('%Y-%m-%d %H:%M:%S'))
else:
    print('Unable to parse cron expression')
"
}

# Function to fix media directory permissions
fix_media_permissions() {
    log "${BLUE}Fixing permissions on media directories...${NC}"
    
    # Fix TV show directories if umtk_root_tv is set
    if [ -n "$UMTK_ROOT_TV" ] && [ -d "$UMTK_ROOT_TV" ]; then
        log "${BLUE}Fixing TV directory permissions: $UMTK_ROOT_TV${NC}"
        find "$UMTK_ROOT_TV" -type d -name "Season 00" -exec chown -R $PUID:$PGID {} \; 2>/dev/null || true
        find "$UMTK_ROOT_TV" -type d -name "Season 00" -exec chmod -R u+rwX {} \; 2>/dev/null || true
        log "${GREEN}TV directory permissions fixed${NC}"
    fi
    
    # Fix movie directories if umtk_root_movies is set
    if [ -n "$UMTK_ROOT_MOVIES" ] && [ -d "$UMTK_ROOT_MOVIES" ]; then
        log "${BLUE}Fixing movie directory permissions: $UMTK_ROOT_MOVIES${NC}"
        find "$UMTK_ROOT_MOVIES" -type d -name "*{edition-Coming Soon}*" -exec chown -R $PUID:$PGID {} \; 2>/dev/null || true
        find "$UMTK_ROOT_MOVIES" -type d -name "*{edition-Coming Soon}*" -exec chmod -R u+rwX {} \; 2>/dev/null || true
        find "$UMTK_ROOT_MOVIES" -type d -name "*{edition-Trending}*" -exec chown -R $PUID:$PGID {} \; 2>/dev/null || true
        find "$UMTK_ROOT_MOVIES" -type d -name "*{edition-Trending}*" -exec chmod -R u+rwX {} \; 2>/dev/null || true
        log "${GREEN}Movie directory permissions fixed${NC}"
    fi
}

# Create a wrapper script that includes the next schedule calculation
cat > /app/run-umtk.sh << 'WRAPPER_EOF'
#!/bin/bash

# Set timezone if TZ is set
if [ -n "${TZ}" ]; then
    export TZ="${TZ}"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log with timestamp
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to get next cron run time
get_next_cron_time() {
    python3 -c "
import datetime
import re

cron_expression = '${CRON}'
parts = cron_expression.split()
if len(parts) == 5:
    minute, hour, day, month, dow = parts
    now = datetime.datetime.now()
    
    # Function to parse cron field with step values
    def parse_field(field, min_val, max_val, current_val):
        if field == '*':
            return None  # Wildcard
        elif '/' in field:
            # Handle step values like */6
            base, step = field.split('/')
            step = int(step)
            if base == '*':
                # Find next value divisible by step
                next_val = ((current_val // step) * step) + step
                if next_val > max_val:
                    next_val = 0
                return next_val
            else:
                # Handle ranges with steps (not common, but supported)
                return int(base)
        elif ',' in field:
            # Handle comma-separated values
            values = [int(v) for v in field.split(',')]
            for v in sorted(values):
                if v > current_val:
                    return v
            return sorted(values)[0]  # Wrap to first
        elif '-' in field:
            # Handle ranges
            start, end = map(int, field.split('-'))
            if current_val < start:
                return start
            elif current_val < end:
                return current_val + 1
            else:
                return start  # Wrap around
        else:
            return int(field)
    
    # Parse minute and hour
    target_minute = parse_field(minute, 0, 59, now.minute)
    target_hour = parse_field(hour, 0, 23, now.hour)
    
    # Calculate next run time
    next_run = now.replace(second=0, microsecond=0)
    
    if target_hour is None and target_minute is None:
        # Every minute (unlikely but handle it)
        next_run = next_run + datetime.timedelta(minutes=1)
    elif target_hour is None:
        # Every hour at target minute
        next_run = next_run.replace(minute=target_minute)
        if next_run <= now:
            next_run = next_run + datetime.timedelta(hours=1)
    elif target_minute is None:
        # Target hour, every minute (unlikely)
        next_run = next_run.replace(hour=target_hour)
        if next_run <= now:
            next_run = next_run + datetime.timedelta(days=1)
    else:
        # Specific hour and minute
        next_run = next_run.replace(hour=target_hour, minute=target_minute)
        
        # If time has passed today, calculate next occurrence
        if next_run <= now:
            if '/' in hour:
                # Step value in hour - add step hours
                _, step = hour.split('/')
                next_run = next_run + datetime.timedelta(hours=int(step))
            else:
                # Fixed hour - move to next day
                next_run = next_run + datetime.timedelta(days=1)
    
    print(next_run.strftime('%Y-%m-%d %H:%M:%S'))
else:
    print('Unable to parse cron expression')
"
}

cd /app
export DOCKER=true PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH=/usr/local/bin:$PATH
/usr/local/bin/python UMTK.py

# Calculate and display next run time
NEXT_RUN=$(get_next_cron_time)
log "${BLUE}Next execution scheduled for: ${NEXT_RUN}${NC}"
WRAPPER_EOF

chmod +x /app/run-umtk.sh
chown $PUID:$PGID /app/run-umtk.sh

# Get next scheduled run time
NEXT_RUN=$(get_next_cron_time)

# Setup cron job - Run as root and use gosu to switch to umtk user
log "${BLUE}Setting up cron schedule: ${CRON}${NC}"

# Find the full path to gosu, fallback to su if gosu not available
if command -v gosu &> /dev/null; then
    SWITCH_USER_CMD="$(which gosu) ${PUID}:${PGID}"
    log "${BLUE}Using gosu to switch users${NC}"
else
    SWITCH_USER_CMD="su -s /bin/bash umtk -c"
    log "${BLUE}Using su to switch users${NC}"
fi

# Get TZ for cron
CRON_TZ="${TZ:-UTC}"

cat > /etc/cron.d/umtk-cron << 'CRONEOF'
PATH=/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin
SHELL=/bin/bash
CRONEOF

echo "TZ=${CRON_TZ}" >> /etc/cron.d/umtk-cron
echo "" >> /etc/cron.d/umtk-cron

# Correctly wrap the gosu/su command in /bin/bash -c "..." for system crontab
if command -v gosu &> /dev/null; then
    GOSU_CMD=$(which gosu)
    # The entire command to be executed by 'root' needs to be wrapped for redirection
    echo "${CRON} root /bin/bash -c \"${GOSU_CMD} ${PUID}:${PGID} /app/run-umtk.sh >> /app/logs/umtk.log 2>&1\"" >> /etc/cron.d/umtk-cron
else
    # su command already properly wrapped for redirection
    echo "${CRON} root /bin/bash -c \"su -s /bin/bash umtk -c '/app/run-umtk.sh' >> /app/logs/umtk.log 2>&1\"" >> /etc/cron.d/umtk-cron
fi

chmod 0644 /etc/cron.d/umtk-cron
crontab /etc/cron.d/umtk-cron

log "${BLUE}Cron job installed. Contents:${NC}"
cat /etc/cron.d/umtk-cron | tail -1

# Fix media permissions before running
fix_media_permissions

# Run once on startup as umtk user with explicit UID:GID
log "${GREEN}Running UMTK on startup...${NC}"
gosu $PUID:$PGID bash -c "/app/run-umtk.sh"

log "${BLUE}Container is now running. Use docker logs -f umtk to follow the logs${NC}"

# Tail the log file to docker logs in the background
tail -F /app/logs/umtk.log &

# Start cron in foreground
exec cron -f