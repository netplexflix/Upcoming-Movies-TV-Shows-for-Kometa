"""Constants and color codes for TSSK"""

import os

# Environment detection
IS_DOCKER = os.getenv("DOCKER", "false").lower() == "true"

# ANSI color codes
GREEN = '\033[32m'
ORANGE = '\033[33m'
BLUE = '\033[34m'
RED = '\033[31m'
RESET = '\033[0m'
BOLD = '\033[1m'