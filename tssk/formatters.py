"""Date formatting and localization functions for TSSK"""

from datetime import datetime, timedelta, timezone

from .constants import RED, RESET
from .config_loader import load_localization


def format_date(yyyy_mm_dd, date_format, capitalize=False, simplify_next_week=False, utc_offset=0, localization=None):
    """Format a date string according to the specified format and localization"""
    if localization is None:
        localization = load_localization()  # Load defaults if not provided
    
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


def translate_date_string(date_str, dt_obj, localization):
    """Translate English month and weekday names to localized versions"""
    result = date_str
    
    # Get the month and weekday indices
    month_num = dt_obj.month
    weekday_num = dt_obj.weekday()  # 0=Monday, 6=Sunday
    
    # Create English defaults for replacement
    english_months_full = {
        1: 'January', 2: 'February', 3: 'March', 4: 'April',
        5: 'May', 6: 'June', 7: 'July', 8: 'August',
        9: 'September', 10: 'October', 11: 'November', 12: 'December'
    }
    english_months_abbr = {
        1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
        5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug',
        9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
    }
    english_weekdays_full = {
        0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday',
        4: 'Friday', 5: 'Saturday', 6: 'Sunday'
    }
    english_weekdays_abbr = {
        0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu',
        4: 'Fri', 5: 'Sat', 6: 'Sun'
    }
    
    # Replace full month name first (before abbreviated)
    if english_months_full[month_num] in result:
        result = result.replace(
            english_months_full[month_num],
            localization['months_full'][month_num]
        )
    # Then replace abbreviated month name
    elif english_months_abbr[month_num] in result:
        result = result.replace(
            english_months_abbr[month_num],
            localization['months_abbr'][month_num]
        )
    
    # Replace full weekday name first (before abbreviated)
    if english_weekdays_full[weekday_num] in result:
        result = result.replace(
            english_weekdays_full[weekday_num],
            localization['weekdays_full'][weekday_num]
        )
    # Then replace abbreviated weekday name
    elif english_weekdays_abbr[weekday_num] in result:
        result = result.replace(
            english_weekdays_abbr[weekday_num],
            localization['weekdays_abbr'][weekday_num]
        )
    
    return result