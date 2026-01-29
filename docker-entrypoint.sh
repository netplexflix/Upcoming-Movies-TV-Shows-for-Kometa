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
chown -R $PUID:$PGID /app 2>/dev/null || log "${YELLOW}Warning: Could not change ownership of some files in /app${NC}"

# Fix ownership of kometa directory specifically and ensure it's writable
if [ -d /app/kometa ]; then
    chown -R $PUID:$PGID /app/kometa 2>/dev/null || log "${YELLOW}Warning: Could not change ownership of some files in /app/kometa${NC}"
    chmod -R u+rw /app/kometa 2>/dev/null || log "${YELLOW}Warning: Could not change permissions of some files in /app/kometa${NC}"
fi

# Ensure logs directory is writable
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

def parse_cron_field(field, min_val, max_val):
    \"\"\"Parse a cron field and return a sorted list of valid values.\"\"\"
    values = set()
    
    for part in field.split(','):
        part = part.strip()
        
        # Handle step values (*/n or n-m/step)
        if '/' in part:
            range_part, step = part.split('/')
            step = int(step)
            
            if range_part == '*':
                start, end = min_val, max_val
            elif '-' in range_part:
                start, end = map(int, range_part.split('-'))
            else:
                start = int(range_part)
                end = max_val
            
            values.update(range(start, end + 1, step))
        
        # Handle ranges (n-m)
        elif '-' in part:
            start, end = map(int, part.split('-'))
            values.update(range(start, end + 1))
        
        # Handle wildcard (*)
        elif part == '*':
            values.update(range(min_val, max_val + 1))
        
        # Handle single number
        else:
            values.add(int(part))
    
    return sorted(list(values))

cron_expression = '$CRON'
parts = cron_expression.split()

if len(parts) != 5:
    print('Unable to parse cron expression')
    exit(0)

minute_field, hour_field, day_field, month_field, dow_field = parts

try:
    # Parse each field
    minutes = parse_cron_field(minute_field, 0, 59)
    hours = parse_cron_field(hour_field, 0, 23)
    days = parse_cron_field(day_field, 1, 31) if day_field != '*' else None
    months = parse_cron_field(month_field, 1, 12) if month_field != '*' else None
    dows = parse_cron_field(dow_field, 0, 6) if dow_field != '*' else None
    
    now = datetime.datetime.now()
    
    # Start searching from the next minute
    search_time = now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    
    # Search for up to 366 days
    for _ in range(366 * 24 * 60):
        # Check month
        if months and search_time.month not in months:
            search_time = search_time.replace(day=1, hour=0, minute=0)
            search_time += datetime.timedelta(days=32)
            search_time = search_time.replace(day=1)
            continue
        
        # Check day of month
        if days and search_time.day not in days:
            search_time = search_time.replace(hour=0, minute=0)
            search_time += datetime.timedelta(days=1)
            continue
        
        # Check day of week (convert Python weekday to cron weekday)
        if dows:
            cron_dow = (search_time.weekday() + 1) % 7
            if cron_dow not in dows:
                search_time = search_time.replace(hour=0, minute=0)
                search_time += datetime.timedelta(days=1)
                continue
        
        # Check hour
        if search_time.hour not in hours:
            search_time = search_time.replace(minute=0)
            search_time += datetime.timedelta(hours=1)
            continue
        
        # Check minute
        if search_time.minute not in minutes:
            search_time += datetime.timedelta(minutes=1)
            continue
        
        # Found a valid time
        print(search_time.strftime('%Y-%m-%d %H:%M:%S'))
        exit(0)
    
    print('Unable to calculate next cron time within 366 days')

except (ValueError, IndexError) as e:
    print('Unable to reliably parse and calculate next cron expression')
"
}

# Function to fix media directory permissions
fix_media_permissions() {   
    # Fix TV show directories if umtk_root_tv is set
    if [ -n "$UMTK_ROOT_TV" ] && [ -d "$UMTK_ROOT_TV" ]; then
        log "${BLUE}Fixing TV directory permissions: $UMTK_ROOT_TV${NC}"
        find "$UMTK_ROOT_TV" -type d -name "Season 00" -exec chown -R $PUID:$PGID {} \; 2>/dev/null || true
        find "$UMTK_ROOT_TV" -type d -name "Season 00" -exec chmod -R 777 {} \; 2>/dev/null || true
        log "${GREEN}TV directory permissions fixed${NC}"
    fi
    
    # Fix movie directories if umtk_root_movies is set
    if [ -n "$UMTK_ROOT_MOVIES" ] && [ -d "$UMTK_ROOT_MOVIES" ]; then
        log "${BLUE}Fixing movie directory permissions: $UMTK_ROOT_MOVIES${NC}"
        find "$UMTK_ROOT_MOVIES" -type d -name "*{edition-Coming Soon}*" -exec chown -R $PUID:$PGID {} \; 2>/dev/null || true
        find "$UMTK_ROOT_MOVIES" -type d -name "*{edition-Coming Soon}*" -exec chmod -R 777 {} \; 2>/dev/null || true
        log "${GREEN}Movie directory permissions fixed${NC}"
    fi
}

# Create a wrapper script that includes the next schedule calculation
# NOTE: Using double quotes to allow ${CRON} interpolation at creation time
cat > /app/run-umtk.sh << WRAPPER_EOF
#!/bin/bash

# Set timezone if TZ is set
if [ -n "\${TZ}" ]; then
    export TZ="\${TZ}"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log with timestamp
log() {
    echo -e "[\$(date '+%Y-%m-%d %H:%M:%S')] \$1"
}

# Function to get next cron run time
get_next_cron_time() {
    python3 -c "
import datetime

def parse_cron_field(field, min_val, max_val):
    \"\"\"Parse a cron field and return a sorted list of valid values.\"\"\"
    values = set()
    
    for part in field.split(','):
        part = part.strip()
        
        # Handle step values (*/n or n-m/step)
        if '/' in part:
            range_part, step = part.split('/')
            step = int(step)
            
            if range_part == '*':
                start, end = min_val, max_val
            elif '-' in range_part:
                start, end = map(int, range_part.split('-'))
            else:
                start = int(range_part)
                end = max_val
            
            values.update(range(start, end + 1, step))
        
        # Handle ranges (n-m)
        elif '-' in part:
            start, end = map(int, part.split('-'))
            values.update(range(start, end + 1))
        
        # Handle wildcard (*)
        elif part == '*':
            values.update(range(min_val, max_val + 1))
        
        # Handle single number
        else:
            values.add(int(part))
    
    return sorted(list(values))

cron_expression = '${CRON}'
parts = cron_expression.split()

if len(parts) != 5:
    print('Unable to parse cron expression')
    exit(0)

minute_field, hour_field, day_field, month_field, dow_field = parts

try:
    # Parse each field
    minutes = parse_cron_field(minute_field, 0, 59)
    hours = parse_cron_field(hour_field, 0, 23)
    days = parse_cron_field(day_field, 1, 31) if day_field != '*' else None
    months = parse_cron_field(month_field, 1, 12) if month_field != '*' else None
    dows = parse_cron_field(dow_field, 0, 6) if dow_field != '*' else None
    
    now = datetime.datetime.now()
    
    # Start searching from the next minute
    search_time = now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    
    # Search for up to 366 days
    for _ in range(366 * 24 * 60):
        # Check month
        if months and search_time.month not in months:
            search_time = search_time.replace(day=1, hour=0, minute=0)
            search_time += datetime.timedelta(days=32)
            search_time = search_time.replace(day=1)
            continue
        
        # Check day of month
        if days and search_time.day not in days:
            search_time = search_time.replace(hour=0, minute=0)
            search_time += datetime.timedelta(days=1)
            continue
        
        # Check day of week (convert Python weekday to cron weekday)
        if dows:
            cron_dow = (search_time.weekday() + 1) % 7
            if cron_dow not in dows:
                search_time = search_time.replace(hour=0, minute=0)
                search_time += datetime.timedelta(days=1)
                continue
        
        # Check hour
        if search_time.hour not in hours:
            search_time = search_time.replace(minute=0)
            search_time += datetime.timedelta(hours=1)
            continue
        
        # Check minute
        if search_time.minute not in minutes:
            search_time += datetime.timedelta(minutes=1)
            continue
        
        # Found a valid time
        print(search_time.strftime('%Y-%m-%d %H:%M:%S'))
        exit(0)
    
    print('Unable to calculate next cron time within 366 days')

except (ValueError, IndexError) as e:
    print('Unable to reliably parse and calculate next cron expression')
"
}

cd /app
export DOCKER=true PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH=/usr/local/bin:\$PATH
/usr/local/bin/python UMTK.py

# Calculate and display next run time
NEXT_RUN=\$(get_next_cron_time)
log "\${BLUE}Next execution scheduled for: \${NEXT_RUN}\${NC}"
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
else
    SWITCH_USER_CMD="su -s /bin/bash umtk -c"
fi

# Get TZ for cron
CRON_TZ="${TZ:-UTC}"

cat > /etc/cron.d/umtk-cron << 'CRONEOF'
PATH=/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin
SHELL=/bin/bash
CRONEOF

echo "TZ=${CRON_TZ}" >> /etc/cron.d/umtk-cron
echo "" >> /etc/cron.d/umtk-cron

# FIX 1: Correctly wrap the gosu/su command in /bin/bash -c "..." for system crontab
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

# FIX 2: Remove duplicate logging of next scheduled run time
# The next run time is already logged by /app/run-umtk.sh during the startup run.
log "${BLUE}Container is now running. Use docker logs -f umtk to follow the logs${NC}"

# Tail the log file to docker logs in the background
tail -F /app/logs/umtk.log &

# Start cron in foreground
exec cron -f