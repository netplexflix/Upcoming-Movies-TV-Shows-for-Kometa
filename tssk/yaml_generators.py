"""YAML file generation functions for TSSK"""

import os
import yaml
from collections import defaultdict, OrderedDict
from copy import deepcopy

from .constants import GREEN, RED, RESET
from .config_loader import get_output_directory, load_localization
from .formatters import format_date
from .utils import debug_print, sanitize_show_title


def create_collection_yaml(output_file, shows, config):
    """Create a collection YAML file"""
    # Get the output directory
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)

    try:
        # Add representer for OrderedDict
        def represent_ordereddict(dumper, data):
            return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
        
        yaml.add_representer(OrderedDict, represent_ordereddict, Dumper=yaml.SafeDumper)

        # Determine collection type and get the appropriate config section
        collection_config = {}
        collection_name = ""
        default_summary = ""
        
        if "SEASON_FINALE" in output_file:
            config_key = "collection_season_finale"
            default_summary = f"Shows with a season finale that aired within the past {config.get('recent_days_season_finale', 21)} days"
        elif "FINAL_EPISODE" in output_file:
            config_key = "collection_final_episode"
            default_summary = f"Shows with a final episode that aired within the past {config.get('recent_days_final_episode', 21)} days"
        elif "NEW_SEASON_STARTED" in output_file:
            config_key = "collection_new_season_started"
            default_summary = f"Shows with a new season that started within the past {config.get('recent_days_new_season_started', 14)} days"
        elif "NEW_SEASON" in output_file:
            config_key = "collection_new_season"
            default_summary = f"Shows with a new season starting within {config.get('future_days_new_season', 31)} days"
        elif "UPCOMING_EPISODE" in output_file:
            config_key = "collection_upcoming_episode"
            default_summary = f"Shows with an upcoming episode within {config.get('future_days_upcoming_episode', 31)} days"
        elif "UPCOMING_FINALE" in output_file:
            config_key = "collection_upcoming_finale"
            default_summary = f"Shows with a season finale within {config.get('future_days_upcoming_finale', 31)} days"
        else:
            # Default fallback
            config_key = None
            collection_name = "TV Collection"
            default_summary = "TV Collection"
        
        # Get the collection configuration if available
        if config_key and config_key in config:
            # Create a deep copy to avoid modifying the original config
            collection_config = deepcopy(config[config_key])
            # Extract the collection name and remove it from the config
            collection_name = collection_config.pop("collection_name", "TV Collection")
        
        # Extract user-provided summary and sort_title
        user_summary = collection_config.pop("summary", None)
        user_sort_title = collection_config.pop("sort_title", None)
        
        # Use user summary if provided, otherwise use default
        summary = user_summary if user_summary else default_summary
        
        class QuotedString(str):
            pass

        def quoted_str_presenter(dumper, data):
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

        yaml.add_representer(QuotedString, quoted_str_presenter, Dumper=yaml.SafeDumper)

        # Handle the case when no shows are found
        if not shows:
            # Determine label to remove: use item_label if available, otherwise collection_name
            label_to_remove = collection_config.get("item_label", collection_name)
            
            # Create the template for empty collections
            data = {
                "collections": {
                    collection_name: {
                        "plex_all": True,
                        "item_label.remove": label_to_remove,
                        "build_collection": False
                    }
                }
            }
            
            with open(output_file_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
            debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
            return
        
        tvdb_ids = [s['tvdbId'] for s in shows if s.get('tvdbId')]
        if not tvdb_ids:
            # Determine label to remove: use item_label if available, otherwise collection_name
            label_to_remove = collection_config.get("item_label", collection_name)
            
            # Create the template for empty collections
            data = {
                "collections": {
                    collection_name: {
                        "plex_all": True,
                        "item_label.remove": label_to_remove,
                        "build_collection": False
                    }
                }
            }
            
            with open(output_file_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
            debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
            return

        # Convert to comma-separated
        tvdb_ids_str = ", ".join(str(i) for i in sorted(tvdb_ids))

        # Create the collection data structure as a regular dict
        collection_data = {}
        collection_data["summary"] = summary
        
        # Add sort_title if user provided it
        if user_sort_title:
            collection_data["sort_title"] = QuotedString(user_sort_title)
        
        # Add all remaining parameters from the collection config
        for key, value in collection_config.items():
            collection_data[key] = value
            
        # Add tvdb_show as the last item
        collection_data["tvdb_show"] = tvdb_ids_str

        # Create the final structure with ordered keys
        ordered_collection = OrderedDict()
        
        # Add summary first
        ordered_collection["summary"] = collection_data["summary"]
        
        # Add sort_title second (if it exists)
        if "sort_title" in collection_data:
            ordered_collection["sort_title"] = collection_data["sort_title"]
        
        # Add all other keys except summary, sort_title, and tvdb_show
        for key, value in collection_data.items():
            if key not in ["summary", "sort_title", "tvdb_show"]:
                ordered_collection[key] = value
        
        # Add tvdb_show at the end
        ordered_collection["tvdb_show"] = collection_data["tvdb_show"]

        data = {
            "collections": {
                collection_name: ordered_collection
            }
        }

        with open(output_file_path, "w", encoding="utf-8") as f:
            # Use SafeDumper so our custom representer is used
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")


def create_overlay_yaml(output_file, shows, config_sections, config, backdrop_block_name="backdrop", localization=None):
    """Create an overlay YAML file"""
    # Get the output directory
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)

    try:
        if not shows:
            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write("#No matching shows found")
            debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
            return
        
        # Load localization if not provided
        if localization is None:
            localization = load_localization()
        
        # Check if this is a new season overlay (needs season number grouping)
        is_new_season = "NEW_SEASON_OVERLAYS" in output_file or "NEW_SEASON_STARTED_OVERLAYS" in output_file
        is_new_season_started = "NEW_SEASON_STARTED_OVERLAYS" in output_file
        is_upcoming_finale = "UPCOMING_FINALE_OVERLAYS" in output_file
        is_season_finale = "SEASON_FINALE_OVERLAYS" in output_file
        
        # Check if [#] placeholder is being used
        use_text_value = config_sections.get("text", {}).get("use_text", "")
        has_season_placeholder = "[#]" in use_text_value
        
        # Group shows by date and season number if it's new season overlay
        date_season_to_tvdb_ids = defaultdict(lambda: defaultdict(list))
        season_to_tvdb_ids = defaultdict(list)  # For NEW_SEASON_STARTED and SEASON_FINALE with [#] (no dates)
        date_to_tvdb_ids = defaultdict(list)
        all_tvdb_ids = set()
        
        # Check if this is a category that doesn't need dates
        no_date_needed = "SEASON_FINALE" in output_file or "FINAL_EPISODE" in output_file
        
        for s in shows:
            if s.get("tvdbId"):
                all_tvdb_ids.add(s['tvdbId'])
            
            # For NEW_SEASON_STARTED or SEASON_FINALE with [#], group by season only (no dates)
            if (is_new_season_started or is_season_finale) and has_season_placeholder and s.get("seasonNumber"):
                season_to_tvdb_ids[s['seasonNumber']].append(s.get('tvdbId'))
            # For NEW_SEASON or UPCOMING_FINALE with [#], group by date AND season
            elif (is_new_season or is_upcoming_finale) and has_season_placeholder and s.get("airDate") and s.get("seasonNumber"):
                date_season_to_tvdb_ids[s['airDate']][s['seasonNumber']].append(s.get('tvdbId'))
            # For all other cases with dates (including NEW_SEASON without [#])
            elif s.get("airDate") and not no_date_needed:
                date_to_tvdb_ids[s['airDate']].append(s.get('tvdbId'))
        
        overlays_dict = {}
        
        # -- Backdrop Block --
        backdrop_config = deepcopy(config_sections.get("backdrop", {}))
        # Extract enable flag and default to True if not specified
        enable_backdrop = backdrop_config.pop("enable", True)

        # Only add backdrop overlay if enabled
        if enable_backdrop and all_tvdb_ids:
            # Check if user provided a custom name
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            all_tvdb_ids_str = ", ".join(str(i) for i in sorted(all_tvdb_ids) if i)
            
            overlays_dict[backdrop_block_name] = {
                "overlay": backdrop_config,
                "tvdb_show": all_tvdb_ids_str
            }
        
        # -- Text Blocks --
        text_config = deepcopy(config_sections.get("text", {}))
        enable_text = text_config.pop("enable", True)
        
        # Get global settings
        simplify_next_week = config.get("simplify_next_week_dates", False)
        utc_offset = float(config.get('utc_offset', 0))
        
        if enable_text and all_tvdb_ids:
            date_format = text_config.pop("date_format", "yyyy-mm-dd")
            use_text = text_config.pop("use_text", "New Season")
            # capitalize_dates is category-specific, extracted from text_config
            capitalize_dates = text_config.pop("capitalize_dates", True)
            
            # Check if user provided a custom name
            has_custom_name = "name" in text_config
            
            # For NEW_SEASON_STARTED or SEASON_FINALE with [#] placeholder (no dates)
            if (is_new_season_started or is_season_finale) and has_season_placeholder and season_to_tvdb_ids:
                for season_num in sorted(season_to_tvdb_ids.keys()):
                    sub_overlay_config = deepcopy(text_config)
                    
                    # Replace [#] with actual season number
                    season_text = use_text.replace("[#]", str(season_num))
                    
                    # Only set name if user didn't provide a custom one
                    if not has_custom_name:
                        sub_overlay_config["name"] = f"text({season_text})"
                    
                    tvdb_ids_for_season = sorted(tvdb_id for tvdb_id in season_to_tvdb_ids[season_num] if tvdb_id)
                    tvdb_ids_str = ", ".join(str(i) for i in tvdb_ids_for_season)
                    
                    block_key = f"TSSK_S{season_num}"
                    overlays_dict[block_key] = {
                        "overlay": sub_overlay_config,
                        "tvdb_show": tvdb_ids_str
                    }
            # For NEW_SEASON_STARTED or SEASON_FINALE without [#] placeholder (no dates needed, group all shows together)
            elif (is_new_season_started or is_season_finale) and not has_season_placeholder:
                sub_overlay_config = deepcopy(text_config)
                
                # Only set name if user didn't provide a custom one
                if not has_custom_name:
                    sub_overlay_config["name"] = f"text({use_text})"
                
                tvdb_ids_str = ", ".join(str(i) for i in sorted(all_tvdb_ids) if i)
                
                # Determine block key based on category
                if is_new_season_started:
                    block_key = "TSSK_new_season_started"
                else:  # is_season_finale
                    block_key = "TSSK_season_finale"
                
                overlays_dict[block_key] = {
                    "overlay": sub_overlay_config,
                    "tvdb_show": tvdb_ids_str
                }
            # For NEW_SEASON and UPCOMING_FINALE with [#] placeholder (with dates)
            elif (is_new_season or is_upcoming_finale) and has_season_placeholder and date_season_to_tvdb_ids:
                for date_str in sorted(date_season_to_tvdb_ids):
                    formatted_date = format_date(date_str, date_format, capitalize_dates, simplify_next_week, utc_offset, localization)
                    
                    # Group by season number for this date
                    for season_num in sorted(date_season_to_tvdb_ids[date_str].keys()):
                        sub_overlay_config = deepcopy(text_config)
                        
                        # Replace [#] with actual season number
                        season_text = use_text.replace("[#]", str(season_num))
                        
                        # Only set name if user didn't provide a custom one
                        if not has_custom_name:
                            sub_overlay_config["name"] = f"text({season_text} {formatted_date})"
                        
                        tvdb_ids_for_date_season = sorted(tvdb_id for tvdb_id in date_season_to_tvdb_ids[date_str][season_num] if tvdb_id)
                        tvdb_ids_str = ", ".join(str(i) for i in tvdb_ids_for_date_season)
                        
                        block_key = f"TSSK_{formatted_date}_S{season_num}"
                        overlays_dict[block_key] = {
                            "overlay": sub_overlay_config,
                            "tvdb_show": tvdb_ids_str
                        }
            # For categories that need dates and shows with air dates (no [#] placeholder)
            elif date_to_tvdb_ids and not no_date_needed and not is_new_season_started and not is_season_finale and not (is_upcoming_finale and has_season_placeholder):
                for date_str in sorted(date_to_tvdb_ids):
                    formatted_date = format_date(date_str, date_format, capitalize_dates, simplify_next_week, utc_offset, localization)
                    sub_overlay_config = deepcopy(text_config)
                    
                    # Only set name if user didn't provide a custom one
                    if not has_custom_name:
                        sub_overlay_config["name"] = f"text({use_text} {formatted_date})"
                    
                    tvdb_ids_for_date = sorted(tvdb_id for tvdb_id in date_to_tvdb_ids[date_str] if tvdb_id)
                    tvdb_ids_str = ", ".join(str(i) for i in tvdb_ids_for_date)
                    
                    block_key = f"TSSK_{formatted_date}"
                    overlays_dict[block_key] = {
                        "overlay": sub_overlay_config,
                        "tvdb_show": tvdb_ids_str
                    }
            # For shows without air dates or categories that don't need dates
            else:
                sub_overlay_config = deepcopy(text_config)
                
                # Only set name if user didn't provide a custom one
                if not has_custom_name:
                    sub_overlay_config["name"] = f"text({use_text})"
                
                tvdb_ids_str = ", ".join(str(i) for i in sorted(all_tvdb_ids) if i)
                
                # Extract category name from filename
                if is_new_season_started:
                    block_key = "TSSK_new_season_started"
                elif is_season_finale:
                    block_key = "TSSK_season_finale"
                elif "FINAL_EPISODE" in output_file:
                    block_key = "TSSK_final_episode"
                elif is_upcoming_finale:
                    block_key = "TSSK_upcoming_finale"
                else:
                    block_key = "TSSK_text"  # fallback
                
                overlays_dict[block_key] = {
                    "overlay": sub_overlay_config,
                    "tvdb_show": tvdb_ids_str
                }
        
        final_output = {"overlays": overlays_dict}
        
        with open(output_file_path, "w", encoding="utf-8") as f:
            yaml.dump(final_output, f, sort_keys=False)
        debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")


def create_new_show_collection_yaml(output_file, config, recent_days):
    """Create collection YAML for new shows using Plex filters"""
    # Get the output directory
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)

    try:
        # Add representer for OrderedDict
        def represent_ordereddict(dumper, data):
            return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
        
        yaml.add_representer(OrderedDict, represent_ordereddict, Dumper=yaml.SafeDumper)

        class QuotedString(str):
            pass

        def quoted_str_presenter(dumper, data):
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

        yaml.add_representer(QuotedString, quoted_str_presenter, Dumper=yaml.SafeDumper)

        # Get collection configuration
        collection_config = deepcopy(config.get("collection_new_show", {}))
        collection_name = collection_config.pop("collection_name", "New Shows")
        
        # Extract user-provided summary and sort_title
        user_summary = collection_config.pop("summary", None)
        user_sort_title = collection_config.pop("sort_title", None)
        
        # Use user summary if provided, otherwise use default
        summary = user_summary if user_summary else f"New Shows added in the past {recent_days} days"

        # Create the collection data structure as a regular dict
        collection_data = {}
        collection_data["summary"] = summary
        
        # Add sort_title if user provided it
        if user_sort_title:
            collection_data["sort_title"] = QuotedString(user_sort_title)
        
        # Add all remaining parameters from the collection config
        for key, value in collection_config.items():
            collection_data[key] = value
            
        # Add plex_all and filters instead of tvdb_show
        collection_data["plex_all"] = True
        collection_data["filters"] = {
            "added": recent_days,
            "label.not": "Coming Soon"
        }

        # Create the final structure with ordered keys
        ordered_collection = OrderedDict()
        
        # Add summary first
        ordered_collection["summary"] = collection_data["summary"]
        
        # Add sort_title second (if it exists)
        if "sort_title" in collection_data:
            ordered_collection["sort_title"] = collection_data["sort_title"]
        
        # Add all other keys except summary, sort_title, plex_all, and filters
        for key, value in collection_data.items():
            if key not in ["summary", "sort_title", "plex_all", "filters"]:
                ordered_collection[key] = value
        
        # Add plex_all and filters at the end
        ordered_collection["plex_all"] = collection_data["plex_all"]
        ordered_collection["filters"] = collection_data["filters"]

        data = {
            "collections": {
                collection_name: ordered_collection
            }
        }

        with open(output_file_path, "w", encoding="utf-8") as f:
            # Use SafeDumper so our custom representer is used
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")


def create_new_show_overlay_yaml(output_file, config_sections, recent_days, config, backdrop_block_name="backdrop_new_show"):
    """Create overlay YAML for new shows using Plex filters instead of Sonarr data"""  
    # Get the output directory
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)
    
    try:
        overlays_dict = {}
        
        # -- Backdrop Block --
        backdrop_config = deepcopy(config_sections.get("backdrop", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop:
            # Check if user provided a custom name
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            overlays_dict[backdrop_block_name] = {
                "plex_all": True,
                "filters": {
                    "added": recent_days,
                    "label.not": "Coming Soon, RequestNeeded"
                },
                "overlay": backdrop_config
            }
        
        # -- Text Block --
        text_config = deepcopy(config_sections.get("text", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text:
            use_text = text_config.pop("use_text", "New Show")
            text_config.pop("date_format", None)  # Remove if present
            text_config.pop("capitalize_dates", None)  # Remove if present
            
            # Check if user provided a custom name
            if "name" not in text_config:
                text_config["name"] = f"text({use_text})"
            
            overlays_dict["new_show"] = {
                "plex_all": True,
                "filters": {
                    "added": recent_days,
                    "label.not": "Coming Soon, RequestNeeded"
                },
                "overlay": text_config
            }
        
        final_output = {"overlays": overlays_dict}
        
        with open(output_file_path, "w", encoding="utf-8") as f:
            yaml.dump(final_output, f, sort_keys=False)
        debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")


def create_returning_show_collection_yaml(output_file, config, use_tvdb=False):
    """Create collection YAML for returning shows using Plex filters instead of Sonarr data"""
    # Get the output directory
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)

    try:
        # Add representer for OrderedDict
        def represent_ordereddict(dumper, data):
            return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
        
        yaml.add_representer(OrderedDict, represent_ordereddict, Dumper=yaml.SafeDumper)

        class QuotedString(str):
            pass

        def quoted_str_presenter(dumper, data):
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

        yaml.add_representer(QuotedString, quoted_str_presenter, Dumper=yaml.SafeDumper)

        # Get collection configuration
        collection_config = deepcopy(config.get("collection_returning", {}))
        collection_name = collection_config.pop("collection_name", "Returning Shows")
        
        # Extract user-provided summary and sort_title
        user_summary = collection_config.pop("summary", None)
        user_sort_title = collection_config.pop("sort_title", None)
        
        # Use user summary if provided, otherwise use default
        summary = user_summary if user_summary else "Returning Shows without upcoming episodes within the chosen timeframes"
        
        # Extract additional filters from config
        additional_filters = collection_config.pop("filters", {})

        # Create the collection data structure as a regular dict
        collection_data = {}
        collection_data["summary"] = summary
        
        # Add sort_title if user provided it
        if user_sort_title:
            collection_data["sort_title"] = QuotedString(user_sort_title)
        
        # Add all remaining parameters from the collection config
        for key, value in collection_config.items():
            collection_data[key] = value
            
        # Add plex_all and filters instead of tvdb_show
        collection_data["plex_all"] = True
        status_filter = "tvdb_status" if use_tvdb else "tmdb_status"
        status_value = "continuing" if use_tvdb else "returning"
        
        # Create filters dict with status filter first, then additional filters
        filters_dict = {status_filter: status_value}
        filters_dict.update(additional_filters)
        collection_data["filters"] = filters_dict

        # Create the final structure with ordered keys
        ordered_collection = OrderedDict()
        
        # Add summary first
        ordered_collection["summary"] = collection_data["summary"]
        
        # Add sort_title second (if it exists)
        if "sort_title" in collection_data:
            ordered_collection["sort_title"] = collection_data["sort_title"]
        
        # Add all other keys except summary, sort_title, plex_all, and filters
        for key, value in collection_data.items():
            if key not in ["summary", "sort_title", "plex_all", "filters"]:
                ordered_collection[key] = value
        
        # Add plex_all and filters at the end
        ordered_collection["plex_all"] = collection_data["plex_all"]
        ordered_collection["filters"] = collection_data["filters"]

        data = {
            "collections": {
                collection_name: ordered_collection
            }
        }

        with open(output_file_path, "w", encoding="utf-8") as f:
            # Use SafeDumper so our custom representer is used
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")


def create_returning_show_overlay_yaml(output_file, config_sections, use_tvdb=False, config=None, backdrop_block_name="backdrop_returning"):
    """Create overlay YAML for returning shows using Plex filters instead of Sonarr data"""  
    # Get the output directory
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)
    
    try:
        overlays_dict = {}
        
        # -- Backdrop Block --
        backdrop_config = deepcopy(config_sections.get("backdrop", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        # Extract additional filters from backdrop config
        backdrop_additional_filters = backdrop_config.pop("filters", {})
        
        status_filter = "tvdb_status" if use_tvdb else "tmdb_status"
        status_value = "continuing" if use_tvdb else "returning"
        
        if enable_backdrop:
            # Check if user provided a custom name
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            # Create filters dict with status filter first, then additional filters
            backdrop_filters = {status_filter: status_value}
            backdrop_filters.update(backdrop_additional_filters)
            
            overlays_dict[backdrop_block_name] = {
                "plex_all": True,
                "filters": backdrop_filters,
                "overlay": backdrop_config
            }
        
        # -- Text Block --
        text_config = deepcopy(config_sections.get("text", {}))
        enable_text = text_config.pop("enable", True)
        
        # Extract additional filters from text config
        text_additional_filters = text_config.pop("filters", {})
        
        if enable_text:
            use_text = text_config.pop("use_text", "Returning")
            text_config.pop("date_format", None)  # Remove if present
            text_config.pop("capitalize_dates", None)  # Remove if present
            
            # Check if user provided a custom name
            if "name" not in text_config:
                text_config["name"] = f"text({use_text})"
            
            # Create filters dict with status filter first, then additional filters
            text_filters = {status_filter: status_value}
            text_filters.update(text_additional_filters)
            
            overlays_dict["returning_show"] = {
                "plex_all": True,
                "filters": text_filters,
                "overlay": text_config
            }
        
        final_output = {"overlays": overlays_dict}
        
        with open(output_file_path, "w", encoding="utf-8") as f:
            yaml.dump(final_output, f, sort_keys=False)
        if config:
            debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")


def create_ended_show_collection_yaml(output_file, config, use_tvdb=False):
    """Create collection YAML for ended shows using Plex filters instead of Sonarr data"""
    # Get the output directory
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)

    try:
        # Add representer for OrderedDict
        def represent_ordereddict(dumper, data):
            return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
        
        yaml.add_representer(OrderedDict, represent_ordereddict, Dumper=yaml.SafeDumper)

        class QuotedString(str):
            pass

        def quoted_str_presenter(dumper, data):
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

        yaml.add_representer(QuotedString, quoted_str_presenter, Dumper=yaml.SafeDumper)

        # Get collection configuration
        collection_config = deepcopy(config.get("collection_ended", {}))
        collection_name = collection_config.pop("collection_name", "Ended Shows")
        
        # Extract user-provided summary and sort_title
        user_summary = collection_config.pop("summary", None)
        user_sort_title = collection_config.pop("sort_title", None)
        
        # Use user summary if provided, otherwise use default
        summary = user_summary if user_summary else "Shows that have ended"
        
        # Extract additional filters from config
        additional_filters = collection_config.pop("filters", {})

        # Create the collection data structure as a regular dict
        collection_data = {}
        collection_data["summary"] = summary
        
        # Add sort_title if user provided it
        if user_sort_title:
            collection_data["sort_title"] = QuotedString(user_sort_title)
        
        # Add all remaining parameters from the collection config
        for key, value in collection_config.items():
            collection_data[key] = value
            
        # Add plex_all and filters instead of tvdb_show
        collection_data["plex_all"] = True
        status_filter = "tvdb_status" if use_tvdb else "tmdb_status"
        
        # Create filters dict with status filter first, then additional filters
        filters_dict = {status_filter: "ended"}
        filters_dict.update(additional_filters)
        collection_data["filters"] = filters_dict

        # Create the final structure with ordered keys
        ordered_collection = OrderedDict()
        
        # Add summary first
        ordered_collection["summary"] = collection_data["summary"]
        
        # Add sort_title second (if it exists)
        if "sort_title" in collection_data:
            ordered_collection["sort_title"] = collection_data["sort_title"]
        
        # Add all other keys except summary, sort_title, plex_all, and filters
        for key, value in collection_data.items():
            if key not in ["summary", "sort_title", "plex_all", "filters"]:
                ordered_collection[key] = value
        
        # Add plex_all and filters at the end
        ordered_collection["plex_all"] = collection_data["plex_all"]
        ordered_collection["filters"] = collection_data["filters"]

        data = {
            "collections": {
                collection_name: ordered_collection
            }
        }

        with open(output_file_path, "w", encoding="utf-8") as f:
            # Use SafeDumper so our custom representer is used
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")


def create_ended_show_overlay_yaml(output_file, config_sections, use_tvdb=False, config=None, backdrop_block_name="backdrop_ended"):
    """Create overlay YAML for ended shows using Plex filters instead of Sonarr data"""  
    # Get the output directory
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)
    
    try:
        overlays_dict = {}
        
        # -- Backdrop Block --
        backdrop_config = deepcopy(config_sections.get("backdrop", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        # Extract additional filters from backdrop config
        backdrop_additional_filters = backdrop_config.pop("filters", {})
        
        status_filter = "tvdb_status" if use_tvdb else "tmdb_status"
        
        if enable_backdrop:
            # Check if user provided a custom name
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            # Create filters dict with status filter first, then additional filters
            backdrop_filters = {status_filter: "ended"}
            backdrop_filters.update(backdrop_additional_filters)
            
            overlays_dict[backdrop_block_name] = {
                "plex_all": True,
                "filters": backdrop_filters,
                "overlay": backdrop_config
            }
        
        # -- Text Block --
        text_config = deepcopy(config_sections.get("text", {}))
        enable_text = text_config.pop("enable", True)
        
        # Extract additional filters from text config
        text_additional_filters = text_config.pop("filters", {})
        
        if enable_text:
            use_text = text_config.pop("use_text", "Ended")
            text_config.pop("date_format", None)  # Remove if present
            text_config.pop("capitalize_dates", None)  # Remove if present
            
            # Check if user provided a custom name
            if "name" not in text_config:
                text_config["name"] = f"text({use_text})"
            
            # Create filters dict with status filter first, then additional filters
            text_filters = {status_filter: "ended"}
            text_filters.update(text_additional_filters)
            
            overlays_dict["ended_show"] = {
                "plex_all": True,
                "filters": text_filters,
                "overlay": text_config
            }
        
        final_output = {"overlays": overlays_dict}
        
        with open(output_file_path, "w", encoding="utf-8") as f:
            yaml.dump(final_output, f, sort_keys=False)
        if config:
            debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")


def create_canceled_show_collection_yaml(output_file, config, use_tvdb=False):
    """Create collection YAML for canceled shows using Plex filters instead of Sonarr data"""
    # Get the output directory
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)

    try:
        # Add representer for OrderedDict
        def represent_ordereddict(dumper, data):
            return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
        
        yaml.add_representer(OrderedDict, represent_ordereddict, Dumper=yaml.SafeDumper)

        class QuotedString(str):
            pass

        def quoted_str_presenter(dumper, data):
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

        yaml.add_representer(QuotedString, quoted_str_presenter, Dumper=yaml.SafeDumper)

        # Get collection configuration
        collection_config = deepcopy(config.get("collection_canceled", {}))
        collection_name = collection_config.pop("collection_name", "Canceled Shows")
        
        # Extract user-provided summary and sort_title
        user_summary = collection_config.pop("summary", None)
        user_sort_title = collection_config.pop("sort_title", None)
        
        # Use user summary if provided, otherwise use default
        summary = user_summary if user_summary else "Shows that have been canceled"
        
        # Extract additional filters from config
        additional_filters = collection_config.pop("filters", {})

        # Create the collection data structure as a regular dict
        collection_data = {}
        collection_data["summary"] = summary
        
        # Add sort_title if user provided it
        if user_sort_title:
            collection_data["sort_title"] = QuotedString(user_sort_title)
        
        # Add all remaining parameters from the collection config
        for key, value in collection_config.items():
            collection_data[key] = value
           
        # Add plex_all and filters instead of tvdb_show
        collection_data["plex_all"] = True
        status_filter = "tvdb_status" if use_tvdb else "tmdb_status"
        
        # Create filters dict with status filter first, then additional filters
        filters_dict = {status_filter: "canceled"}
        filters_dict.update(additional_filters)
        collection_data["filters"] = filters_dict

        # Create the final structure with ordered keys
        ordered_collection = OrderedDict()
        
        # Add summary first
        ordered_collection["summary"] = collection_data["summary"]
        
        # Add sort_title second (if it exists)
        if "sort_title" in collection_data:
            ordered_collection["sort_title"] = collection_data["sort_title"]
        
        # Add all other keys except summary, sort_title, plex_all, and filters
        for key, value in collection_data.items():
            if key not in ["summary", "sort_title", "plex_all", "filters"]:
                ordered_collection[key] = value
        
        # Add plex_all and filters at the end
        ordered_collection["plex_all"] = collection_data["plex_all"]
        ordered_collection["filters"] = collection_data["filters"]

        data = {
            "collections": {
                collection_name: ordered_collection
            }
        }

        with open(output_file_path, "w", encoding="utf-8") as f:
            # Use SafeDumper so our custom representer is used
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")


def create_canceled_show_overlay_yaml(output_file, config_sections, use_tvdb=False, config=None, backdrop_block_name="backdrop_canceled"):
    """Create overlay YAML for canceled shows using Plex filters"""  
    # Get the output directory
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)
    
    try:
        overlays_dict = {}
        
        # -- Backdrop Block --
        backdrop_config = deepcopy(config_sections.get("backdrop", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        # Extract additional filters from backdrop config
        backdrop_additional_filters = backdrop_config.pop("filters", {})
        
        status_filter = "tvdb_status" if use_tvdb else "tmdb_status"
        
        if enable_backdrop:
            # Check if user provided a custom name
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            # Create filters dict with status filter first, then additional filters
            backdrop_filters = {status_filter: "canceled"}
            backdrop_filters.update(backdrop_additional_filters)
            
            overlays_dict[backdrop_block_name] = {
                "plex_all": True,
                "filters": backdrop_filters,
                "overlay": backdrop_config
            }
        
        # -- Text Block --
        text_config = deepcopy(config_sections.get("text", {}))
        enable_text = text_config.pop("enable", True)
        
        # Extract additional filters from text config
        text_additional_filters = text_config.pop("filters", {})
        
        if enable_text:
            use_text = text_config.pop("use_text", "Canceled")
            text_config.pop("date_format", None)  # Remove if present
            text_config.pop("capitalize_dates", None)  # Remove if present
            
            # Check if user provided a custom name
            if "name" not in text_config:
                text_config["name"] = f"text({use_text})"
            
            # Create filters dict with status filter first, then additional filters
            text_filters = {status_filter: "canceled"}
            text_filters.update(text_additional_filters)
            
            overlays_dict["canceled_show"] = {
                "plex_all": True,
                "filters": text_filters,
                "overlay": text_config
            }
        
        final_output = {"overlays": overlays_dict}
        
        with open(output_file_path, "w", encoding="utf-8") as f:
            yaml.dump(final_output, f, sort_keys=False)
        if config:
            debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")


def create_metadata_yaml(output_file, shows, config, sonarr_url, api_key, all_series, sonarr_timeout=90):
    """Create metadata YAML file with sort_title based on air date and show name"""
    output_dir = get_output_directory()
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"{RED}Error creating directory {output_dir}: {str(e)}{RESET}")
        return
    
    output_file_path = os.path.join(output_dir, output_file)

    try:
        # Read existing metadata file to track previously modified shows
        previously_modified_tvdb_ids = set()
        try:
            with open(output_file_path, 'r', encoding='utf-8') as f:
                existing_data = yaml.safe_load(f)
                if existing_data and 'metadata' in existing_data:
                    # Only include shows that have sort_title starting with !yyyymmdd
                    for tvdb_id, metadata in existing_data['metadata'].items():
                        sort_title = metadata.get('sort_title', '')
                        # Check if sort_title starts with ! followed by 8 digits
                        if sort_title and sort_title.startswith('!') and len(sort_title) > 9:
                            date_part = sort_title[1:9]  # Extract the 8 characters after !
                            if date_part.isdigit():
                                previously_modified_tvdb_ids.add(tvdb_id)
        except FileNotFoundError:
            pass  # First run, no existing file
        except Exception as e:
            print(f"{ORANGE}Warning: Could not read existing metadata file: {str(e)}{RESET}")
        
        # Build metadata dictionary for current matches
        metadata_dict = {}
        current_tvdb_ids = set()
        
        for show in shows:
            tvdb_id = show.get('tvdbId')
            air_date = show.get('airDate')  # Format: YYYY-MM-DD
            title = show.get('title', '')
            
            if not tvdb_id or not air_date or not title:
                continue
            
            current_tvdb_ids.add(tvdb_id)
            
            # Convert date from YYYY-MM-DD to YYYYMMDD
            date_yyyymmdd = air_date.replace('-', '')
            
            # Sanitize show title
            clean_title = sanitize_show_title(title)
            
            # Create sort_title value with date prefix
            sort_title_value = f"!{date_yyyymmdd} {clean_title}"
            
            # Add to metadata dict
            metadata_dict[tvdb_id] = {
                'sort_title': sort_title_value
            }
        
        # Find shows that were previously modified but are no longer in current matches
        # These need to have their sort_title reverted to original title
        shows_to_revert = previously_modified_tvdb_ids - current_tvdb_ids
        
        if shows_to_revert:
            # Create a mapping of tvdb_id to series title from all_series
            tvdb_to_title = {series.get('tvdbId'): series.get('title', '') 
                           for series in all_series if series.get('tvdbId')}
            
            for tvdb_id in shows_to_revert:
                # Get the original title from Sonarr data
                original_title = tvdb_to_title.get(tvdb_id)
                if original_title:
                    # Sanitize the title to match what we did for the prefixed version
                    clean_title = sanitize_show_title(original_title)
                    metadata_dict[tvdb_id] = {
                        'sort_title': clean_title
                    }
        
        # Handle empty result
        if not metadata_dict:
            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write("#No matching shows found\n")
            debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
            return
        
        # Sort by tvdb_id for consistent output
        sorted_metadata = OrderedDict(sorted(metadata_dict.items()))
        
        final_output = {"metadata": sorted_metadata}
        
        # Custom representer to ensure tvdb_id is written as integer without quotes
        def represent_int_key_dict(dumper, data):
            return dumper.represent_mapping('tag:yaml.org,2002:map', 
                                          ((int(k), v) for k, v in data.items()))
        
        yaml.add_representer(OrderedDict, represent_int_key_dict, Dumper=yaml.SafeDumper)
        
        with open(output_file_path, "w", encoding="utf-8") as f:
            yaml.dump(final_output, f, Dumper=yaml.SafeDumper, sort_keys=False, default_flow_style=False)
        
        if shows_to_revert:
            print(f"{GREEN}Reverting sort_title for {len(shows_to_revert)} shows no longer in 'new season soon' category{RESET}")
        
        debug_print(f"{GREEN}Created: {output_file_path}{RESET}", config)
        
    except Exception as e:
        print(f"{RED}Error writing file {output_file_path}: {str(e)}{RESET}")