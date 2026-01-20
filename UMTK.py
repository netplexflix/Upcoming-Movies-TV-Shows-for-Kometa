#!/usr/bin/env python3
"""
Upcoming Movies & TV Shows for Kometa (UMTK)
Main entry point script
"""

import sys
from umtk.main import main
from umtk.constants import VERSION, BLUE, RESET

if __name__ == "__main__":
    print(f"{BLUE}{'*' * 50}")
    print(f"{'*' * 1}Upcoming Movies & TV Shows for Kometa {VERSION}{'*' * 1}")
    print(f"{'*' * 50}{RESET}")
    
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)