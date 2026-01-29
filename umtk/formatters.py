"""
Date formatting and localization functions for UMTK
"""

from datetime import datetime, timedelta, timezone

from .constants import (
    RED, RESET,
    ENGLISH_MONTHS_FULL, ENGLISH_MONTHS_ABBR,
    ENGLISH_WEEKDAYS_FULL, ENGLISH_WEEKDAYS_ABBR,
    DEFAULT_LOCALIZATION
)


def translate_date_string(date_str, dt_obj, localization):
    """
    Replace English month and weekday names with localized versions.
    Replaces full names before abbreviated ones to avoid partial replacements.
    """
    result = date_str
    
    # Get the month and weekday indices
    month_num = dt_obj.month
    weekday_num = dt_obj.weekday()  # 0=Monday, 6=Sunday
    
    # Replace full month name first (before abbreviated)
    if ENGLISH_MONTHS_FULL[month_num] in result:
        result = result.replace(
            ENGLISH_MONTHS_FULL[month_num],
            localization['months_full'][month_num]
        )
    # Then replace abbreviated month name
    elif ENGLISH_MONTHS_ABBR[month_num] in result:
        result = result.replace(
            ENGLISH_MONTHS_ABBR[month_num],
            localization['months_abbr'][month_num]
        )
    
    # Replace full weekday name first (before abbreviated)
    if ENGLISH_WEEKDAYS_FULL[weekday_num] in result:
        result = result.replace(
            ENGLISH_WEEKDAYS_FULL[weekday_num],
            localization['weekdays_full'][weekday_num]
        )
    # Then replace abbreviated weekday name
    elif ENGLISH_WEEKDAYS_ABBR[weekday_num] in result:
        result = result.replace(
            ENGLISH_WEEKDAYS_ABBR[weekday_num],
            localization['weekdays_abbr'][weekday_num]
        )
    
    return result


def format_date(yyyy_mm_dd, date_format, capitalize=False, simplify_next_week=False, 
                utc_offset=0, localization=None):
    """
    Format date string according to the specified format with localization support.
    
    Args:
        yyyy_mm_dd: Date string in YYYY-MM-DD format
        date_format: Format string (e.g., 'mmmm dd, yyyy')
        capitalize: If True, uppercase the entire result
        simplify_next_week: If True, use simplified names for dates within next 7 days
        utc_offset: UTC offset in hours
        localization: Localization dictionary (if None, uses English defaults)
    """
    if localization is None:
        localization = DEFAULT_LOCALIZATION
    
    dt_obj = datetime.strptime(yyyy_mm_dd, "%Y-%m-%d")
    
    # If simplify_next_week is enabled, check if date is within next 7 days
    if simplify_next_week:
        now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
        today = now_local.date()
        date_obj = dt_obj.date()
        days_diff = (date_obj - today).days
        
        # Check if date is within the next 7 days (0-6 days from today)
        if 0 <= days_diff <= 6:
            if days_diff == 0:
                result = localization['simplify_next_week']['today']
            elif days_diff == 1:
                result = localization['simplify_next_week']['tomorrow']
            else:
                # Use abbreviated or full weekday based on configuration
                use_abbreviated = localization['simplify_next_week'].get('use_abbreviated', False)
                weekday_num = dt_obj.weekday()
                
                if use_abbreviated:
                    result = localization['weekdays_abbr'][weekday_num]
                else:
                    result = localization['weekdays_full'][weekday_num]
            
            if capitalize:
                result = result.upper()
            return result
    
    # Original date formatting logic
    format_mapping = {
        'mmm': '%b',    # Abbreviated month name
        'mmmm': '%B',   # Full month name
        'mm': '%m',     # 2-digit month
        'm': '%-m',     # 1-digit month
        'dddd': '%A',   # Full weekday name
        'ddd': '%a',    # Abbreviated weekday name
        'dd': '%d',     # 2-digit day
        'd': str(dt_obj.day),  # 1-digit day - direct integer conversion
        'yyyy': '%Y',   # 4-digit year
        'yyy': '%Y',    # 3+ digit year
        'yy': '%y',     # 2-digit year
        'y': '%y'       # Year without century
    }
    
    # Sort format patterns by length (longest first) to avoid partial matches
    patterns = sorted(format_mapping.keys(), key=len, reverse=True)
    
    # First, replace format patterns with temporary markers
    temp_format = date_format
    replacements = {}
    for i, pattern in enumerate(patterns):
        marker = f"@@{i}@@"
        if pattern in temp_format:
            replacements[marker] = format_mapping[pattern]
            temp_format = temp_format.replace(pattern, marker)
    
    # Now replace the markers with strftime formats
    strftime_format = temp_format
    for marker, replacement in replacements.items():
        strftime_format = strftime_format.replace(marker, replacement)
    
    try:
        result = dt_obj.strftime(strftime_format)
        
        # Translate English month and weekday names to localized versions
        result = translate_date_string(result, dt_obj, localization)
        
        if capitalize:
            result = result.upper()
        return result
    except ValueError as e:
        print(f"{RED}Error: Invalid date format '{date_format}'. Using default format.{RESET}")
        return yyyy_mm_dd  # Return original format as fallback