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

# Check if config exists, if not copy sample or create minimal config
if [ ! -f /app/config/config.yml ]; then
    log "${YELLOW}config.yml not found, checking for sample config...${NC}"
    if [ -f /app/config/config.sample.yml ]; then
        cp /app/config/config.sample.yml /app/config/config.yml
        log "${GREEN}Copied config.sample.yml to config.yml${NC}"
        log "${YELLOW}Please edit /app/config/config.yml with your settings${NC}"
    elif [ -f /app/config.sample.yml ]; then
        cp /app/config.sample.yml /app/config/config.yml
        log "${GREEN}Copied bundled config.sample.yml to config.yml${NC}"
        log "${YELLOW}Please edit your config via the Web UI at port 2120${NC}"
    else
        log "${YELLOW}No config.yml or sample found — creating minimal config${NC}"
        log "${YELLOW}Please configure your settings via the Web UI at port 2120${NC}"
        cat > /app/config/config.yml <<'CFGEOF'
enable_umtk: 'true'
plex_url: 'http://localhost:32400'
plex_token: ''
movie_libraries: 'Movies'
tv_libraries: 'TV Shows'
radarr_url: 'http://localhost:7878'
radarr_api_key: ''
sonarr_url: 'http://localhost:8989'
sonarr_api_key: ''
movies: 2
tv: 2
CFGEOF
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

# Fix media permissions before running
fix_media_permissions

# Start UMTK as the configured user
# Python handles: scheduling (CRON env var), web UI (port 2120), log capture
log "${GREEN}Starting UMTK...${NC}"
exec gosu $PUID:$PGID python /app/UMTK.py
