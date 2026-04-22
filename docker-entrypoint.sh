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

# Extract a simple YAML key value from config file
# Usage: get_config_value "key_name" "/path/to/config.yml"
get_config_value() {
    local key="$1"
    local file="$2"
    if [ -f "$file" ]; then
        grep -E "^${key}:" "$file" 2>/dev/null | sed "s/^${key}:[[:space:]]*//" | sed "s/['\"]//g" | sed 's/#.*//' | sed 's/[[:space:]]*$//'
    fi
}

# Handle PUID/PGID environment variables
PUID=${PUID:-1000}
PGID=${PGID:-1000}

log "${BLUE}Using PUID:${PUID} PGID:${PGID}${NC}"

# Adjust umtk user/group to match requested PUID/PGID
if [ "$PUID" != "1000" ] || [ "$PGID" != "1000" ]; then
    log "${BLUE}Adjusting user/group to PUID:${PUID} PGID:${PGID}${NC}"

    # Adjust group: modify existing umtk group or create new one
    CURRENT_GID=$(getent group umtk 2>/dev/null | cut -d: -f3)
    if [ -n "$CURRENT_GID" ] && [ "$CURRENT_GID" != "$PGID" ]; then
        groupmod -g $PGID umtk 2>/dev/null || true
        log "${GREEN}Modified group umtk to GID:${PGID}${NC}"
    elif [ -z "$CURRENT_GID" ]; then
        if ! getent group $PGID > /dev/null 2>&1; then
            groupadd -g $PGID umtk
            log "${GREEN}Created group umtk with GID:${PGID}${NC}"
        else
            log "${GREEN}GID:${PGID} already exists, using it${NC}"
        fi
    fi

    # Adjust user: modify existing umtk user or create new one
    CURRENT_UID=$(id -u umtk 2>/dev/null)
    if [ -n "$CURRENT_UID" ] && [ "$CURRENT_UID" != "$PUID" ]; then
        usermod -u $PUID -g $PGID -d /app -s /bin/bash umtk 2>/dev/null || true
        log "${GREEN}Modified user umtk to UID:${PUID} GID:${PGID}${NC}"
    elif [ -z "$CURRENT_UID" ]; then
        if ! getent passwd $PUID > /dev/null 2>&1; then
            useradd -u $PUID -g $PGID -d /app -s /bin/bash umtk
            log "${GREEN}Created user umtk with UID:${PUID}${NC}"
        else
            log "${GREEN}UID:${PUID} already exists, using it${NC}"
        fi
    else
        # UID matches but group may need updating
        usermod -g $PGID umtk 2>/dev/null || true
        log "${GREEN}User umtk already has UID:${PUID}, updated GID${NC}"
    fi
fi

# Check and setup directories (as root)
log "${BLUE}Setting up directories...${NC}"
mkdir -p /app/config /video /app/kometa /app/config/overlay /app/logs

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

# Check if tssk_config exists, if not copy sample
if [ ! -f /app/config/tssk_config.yml ]; then
    log "${YELLOW}tssk_config.yml not found, checking for sample config...${NC}"
    if [ -f /app/config/tssk_config.sample.yml ]; then
        cp /app/config/tssk_config.sample.yml /app/config/tssk_config.yml
        log "${GREEN}Copied tssk_config.sample.yml to tssk_config.yml${NC}"
        log "${YELLOW}Please edit /app/config/tssk_config.yml with your settings${NC}"
    elif [ -f /app/tssk_config.sample.yml ]; then
        cp /app/tssk_config.sample.yml /app/config/tssk_config.yml
        log "${GREEN}Copied bundled tssk_config.sample.yml to tssk_config.yml${NC}"
        log "${YELLOW}Please edit /app/config/tssk_config.yml with your settings${NC}"
    else
        log "${YELLOW}No tssk_config.sample.yml found — TSSK will use defaults or be skipped${NC}"
    fi
fi

# Check if video file exists for placeholder method
# Note: /video is the volume mount point (not /app/video)
if grep -E "^(tv|movies):\s*2" /app/config/config.yml > /dev/null 2>&1; then
    if ! ls /video/UMTK.mkv 1> /dev/null 2>&1; then
        log "${YELLOW}Placeholder method detected but no UMTK video file found in /video/${NC}"
        # Look for UMTK video files in the app directory and copy if found
        if ls /app/UMTK.mkv 1> /dev/null 2>&1; then
            cp /app/UMTK.mkv /video/
            log "${GREEN}Copied default UMTK video file to /video/${NC}"
        else
            log "${YELLOW}No default video file found. Please add UMTK video file to /video/${NC}"
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
chown -R $PUID:$PGID /video 2>/dev/null || log "${YELLOW}Warning: Could not change ownership of /video${NC}"

# Fix ownership of kometa directory specifically and ensure it's writable
if [ -d /app/kometa ]; then
    chown -R $PUID:$PGID /app/kometa 2>/dev/null || log "${YELLOW}Warning: Could not change ownership of some files in /app/kometa${NC}"
    chmod -R u+rw /app/kometa 2>/dev/null || log "${YELLOW}Warning: Could not change permissions of some files in /app/kometa${NC}"
fi

# Ensure logs directory is writable
mkdir -p /app/logs
chown -R $PUID:$PGID /app/logs 2>/dev/null || true
chmod -R u+rw /app/logs 2>/dev/null || true

# Pre-create media root directories from config (runs as root)
# This ensures paths like /data/media/movies exist with proper ownership
# before switching to the unprivileged user via gosu.
# Roots can come from per-instance umtk_root:, legacy top-level
# umtk_root_movies / umtk_root_tv, or trending_root_movies / trending_root_tv.
CONFIG_FILE="/app/config/config.yml"
UMTK_ROOTS=""
if [ -f "$CONFIG_FILE" ]; then
    # Per-instance roots (indented under radarr_instances / sonarr_instances).
    # Strip the key prefix, any inline comment, and surrounding whitespace/quotes.
    INSTANCE_ROOTS=$(awk '/^[[:space:]]+umtk_root:[[:space:]]*/ { sub(/^[^:]+:[[:space:]]*/, ""); sub(/[[:space:]]*#.*/, ""); print }' "$CONFIG_FILE" \
        | tr -d '"' | tr -d "'" \
        | awk '{$1=$1; print}')
    LEGACY_ROOT_MOVIES=$(get_config_value "umtk_root_movies" "$CONFIG_FILE")
    LEGACY_ROOT_TV=$(get_config_value "umtk_root_tv" "$CONFIG_FILE")
    TRENDING_ROOT_MOVIES=$(get_config_value "trending_root_movies" "$CONFIG_FILE")
    TRENDING_ROOT_TV=$(get_config_value "trending_root_tv" "$CONFIG_FILE")

    UMTK_ROOTS=$(printf '%s\n%s\n%s\n%s\n%s\n' \
        "$INSTANCE_ROOTS" \
        "$LEGACY_ROOT_MOVIES" \
        "$LEGACY_ROOT_TV" \
        "$TRENDING_ROOT_MOVIES" \
        "$TRENDING_ROOT_TV" \
        | awk 'NF && !seen[$0]++')

    if [ -n "$UMTK_ROOTS" ]; then
        echo "$UMTK_ROOTS" | while IFS= read -r root; do
            [ -z "$root" ] && continue
            log "${BLUE}Ensuring UMTK root directory exists: $root${NC}"
            mkdir -p "$root" 2>/dev/null && chown $PUID:$PGID "$root" 2>/dev/null
        done
        log "${GREEN}UMTK root directories ready${NC}"
    fi
else
    log "${YELLOW}Config file not found yet, skipping media directory pre-creation${NC}"
fi

# Ensure common Docker volume mount points exist with proper ownership
for mount_point in /umtkmovies /umtktv; do
    if [ ! -d "$mount_point" ]; then
        mkdir -p "$mount_point" 2>/dev/null
        chown $PUID:$PGID "$mount_point" 2>/dev/null
        log "${GREEN}Created mount point: $mount_point${NC}"
    else
        chown $PUID:$PGID "$mount_point" 2>/dev/null || true
    fi
done

# Function to fix media directory permissions across all configured roots.
# We apply both the TV-style (Season 00) and movie-style ({edition-...}) find
# patterns to every root since bash doesn't know which root is TV vs movies —
# non-matching patterns are simply a no-op.
fix_media_permissions() {
    [ -z "$UMTK_ROOTS" ] && return 0
    echo "$UMTK_ROOTS" | while IFS= read -r root; do
        [ -z "$root" ] && continue
        [ ! -d "$root" ] && continue
        log "${BLUE}Fixing permissions in UMTK root: $root${NC}"
        find "$root" -type d -name "Season 00" -exec chown -R $PUID:$PGID {} \; 2>/dev/null || true
        find "$root" -type d -name "Season 00" -exec chmod -R 775 {} \; 2>/dev/null || true
        find "$root" -type d -name "*{edition-Coming Soon}*" -exec chown -R $PUID:$PGID {} \; 2>/dev/null || true
        find "$root" -type d -name "*{edition-Coming Soon}*" -exec chmod -R 775 {} \; 2>/dev/null || true
        find "$root" -type d -name "*{edition-Trending}*" -exec chown -R $PUID:$PGID {} \; 2>/dev/null || true
        find "$root" -type d -name "*{edition-Trending}*" -exec chmod -R 775 {} \; 2>/dev/null || true
    done
    log "${GREEN}UMTK directory permissions fixed${NC}"
}

# Fix media permissions before running
fix_media_permissions

# Allow the app user to pip-upgrade packages at runtime (e.g. yt-dlp from the web UI).
# pip was run as root during the image build, so /usr/local is root-owned. Re-owning
# lib, bin, and share covers all locations pip writes to: site-packages, entry-point
# scripts, and data files (e.g. bash completions).
chown -R $PUID:$PGID /usr/local/lib /usr/local/bin /usr/local/share 2>/dev/null || true

# Start UMTK as the configured user
# Python handles: scheduling (CRON env var), web UI (port 2120), log capture
log "${GREEN}Starting UMTK...${NC}"
exec gosu $PUID:$PGID python /app/UMTK.py
