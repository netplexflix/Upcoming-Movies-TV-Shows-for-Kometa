"""
YAML file generators for UMTK - creates Kometa configuration files
"""

import yaml
from datetime import datetime
from pathlib import Path
from collections import defaultdict, OrderedDict
from copy import deepcopy

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .formatters import format_date


class QuotedString(str):
    """String subclass for quoted YAML output"""
    pass


def _quoted_str_presenter(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')


def _represent_ordereddict(dumper, data):
    return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())


# Register custom representers
yaml.add_representer(QuotedString, _quoted_str_presenter, Dumper=yaml.SafeDumper)
yaml.add_representer(OrderedDict, _represent_ordereddict, Dumper=yaml.SafeDumper)


def create_overlay_yaml_tv(output_file, future_shows, aired_shows, trending_monitored, 
                           trending_request_needed, config_sections, config, localization=None):
    """Create overlay YAML file for TV shows"""
    if not future_shows and not aired_shows and not trending_monitored and not trending_request_needed:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No matching shows found")
        return
    
    overlays_dict = {}
    
    # Get global settings
    simplify_next_week = config.get("simplify_next_week_dates", False)
    utc_offset = float(config.get('utc_offset', 0))
    
    # Process future shows (haven't aired yet)
    if future_shows:
        date_to_tvdb_ids = defaultdict(list)
        all_future_tvdb_ids = set()
        
        for s in future_shows:
            if s.get("tvdbId"):
                all_future_tvdb_ids.add(s['tvdbId'])
            
            if s.get("airDate"):
                date_to_tvdb_ids[s['airDate']].append(s.get('tvdbId'))
        
        backdrop_config = deepcopy(config_sections.get("backdrop", {}))
        enable_backdrop = backdrop_config.pop("enable", True)

        if enable_backdrop and all_future_tvdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            all_tvdb_ids_str = ", ".join(str(i) for i in sorted(all_future_tvdb_ids) if i)
            
            overlays_dict["backdrop_future"] = {
                "overlay": backdrop_config,
                "tvdb_show": all_tvdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_future_tvdb_ids:
            date_format = text_config.pop("date_format", "yyyy-mm-dd")
            use_text = text_config.pop("use_text", "Coming Soon")
            capitalize_dates = text_config.pop("capitalize_dates", True)
            
            if date_to_tvdb_ids:
                for date_str in sorted(date_to_tvdb_ids):
                    formatted_date = format_date(date_str, date_format, capitalize_dates, 
                                                 simplify_next_week, utc_offset, localization)
                    sub_overlay_config = deepcopy(text_config)
                    if "name" not in sub_overlay_config:
                        sub_overlay_config["name"] = f"text({use_text} {formatted_date})"
                    
                    tvdb_ids_for_date = sorted(tvdb_id for tvdb_id in date_to_tvdb_ids[date_str] if tvdb_id)
                    tvdb_ids_str = ", ".join(str(i) for i in tvdb_ids_for_date)
                    
                    block_key = f"UMTK_future_{formatted_date}"
                    overlays_dict[block_key] = {
                        "overlay": sub_overlay_config,
                        "tvdb_show": tvdb_ids_str
                    }
            else:
                sub_overlay_config = deepcopy(text_config)
                if "name" not in sub_overlay_config:
                    sub_overlay_config["name"] = f"text({use_text})"
                
                tvdb_ids_str = ", ".join(str(i) for i in sorted(all_future_tvdb_ids) if i)
                
                overlays_dict["UMTK_upcoming_shows_future"] = {
                    "overlay": sub_overlay_config,
                    "tvdb_show": tvdb_ids_str
                }
    
    # Process aired shows (have aired but not downloaded)
    if aired_shows:
        all_aired_tvdb_ids = set()
        
        for s in aired_shows:
            if s.get("tvdbId"):
                all_aired_tvdb_ids.add(s['tvdbId'])
        
        backdrop_config = deepcopy(config_sections.get("backdrop_aired", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_aired_tvdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tvdb_ids_str = ", ".join(str(i) for i in sorted(all_aired_tvdb_ids) if i)
            
            overlays_dict["backdrop_aired"] = {
                "overlay": backdrop_config,
                "tvdb_show": all_tvdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_aired", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_aired_tvdb_ids:
            use_text = text_config.pop("use_text", "Available Now")
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            
            tvdb_ids_str = ", ".join(str(i) for i in sorted(all_aired_tvdb_ids) if i)
            
            overlays_dict["UMTK_aired"] = {
                "overlay": sub_overlay_config,
                "tvdb_show": tvdb_ids_str
            }
    
    # Process trending monitored shows
    if trending_monitored:
        tvdb_monitored = []
        tmdb_monitored = []
        
        for s in trending_monitored:
            if s.get("tvdbId"):
                tvdb_monitored.append(s['tvdbId'])
            elif s.get("tmdbId"):
                tmdb_monitored.append(s['tmdbId'])
        
        if tvdb_monitored:
            backdrop_config = deepcopy(config_sections.get("backdrop_aired", {}))
            enable_backdrop = backdrop_config.pop("enable", True)
            
            if enable_backdrop:
                if "name" not in backdrop_config:
                    backdrop_config["name"] = "backdrop"
                
                tvdb_ids_str = ", ".join(str(i) for i in sorted(tvdb_monitored))
                
                overlays_dict["backdrop_trending_monitored_tvdb"] = {
                    "overlay": backdrop_config,
                    "tvdb_show": tvdb_ids_str
                }
        
        if tmdb_monitored:
            backdrop_config = deepcopy(config_sections.get("backdrop_aired", {}))
            enable_backdrop = backdrop_config.pop("enable", True)
            
            if enable_backdrop:
                if "name" not in backdrop_config:
                    backdrop_config["name"] = "backdrop"
                
                tmdb_ids_str = ", ".join(str(i) for i in sorted(tmdb_monitored))
                
                overlays_dict["backdrop_trending_monitored_tmdb"] = {
                    "overlay": backdrop_config,
                    "tmdb_show": tmdb_ids_str
                }
        
        if tvdb_monitored:
            text_config = deepcopy(config_sections.get("text_aired", {}))
            enable_text = text_config.pop("enable", True)
            
            if enable_text:
                use_text = text_config.pop("use_text", "Available Now")
                text_config.pop("date_format", None)
                text_config.pop("capitalize_dates", None)
                
                sub_overlay_config = deepcopy(text_config)
                
                if "name" not in sub_overlay_config:
                    sub_overlay_config["name"] = f"text({use_text})"
                
                tvdb_ids_str = ", ".join(str(i) for i in sorted(tvdb_monitored))
                
                overlays_dict["UMTK_trending_monitored_tvdb"] = {
                    "overlay": sub_overlay_config,
                    "tvdb_show": tvdb_ids_str
                }
        
        if tmdb_monitored:
            text_config = deepcopy(config_sections.get("text_aired", {}))
            enable_text = text_config.pop("enable", True)
            
            if enable_text:
                use_text = text_config.pop("use_text", "Available Now")
                text_config.pop("date_format", None)
                text_config.pop("capitalize_dates", None)
                
                sub_overlay_config = deepcopy(text_config)
                
                if "name" not in sub_overlay_config:
                    sub_overlay_config["name"] = f"text({use_text})"
                
                tmdb_ids_str = ", ".join(str(i) for i in sorted(tmdb_monitored))
                
                overlays_dict["UMTK_trending_monitored_tmdb"] = {
                    "overlay": sub_overlay_config,
                    "tmdb_show": tmdb_ids_str
                }
    
    # Process trending request needed shows
    if trending_request_needed:
        tvdb_request = []
        tmdb_request = []
        
        for s in trending_request_needed:
            if s.get("tvdbId"):
                tvdb_request.append(s['tvdbId'])
            elif s.get("tmdbId"):
                tmdb_request.append(s['tmdbId'])
        
        if tvdb_request:
            backdrop_config = deepcopy(config_sections.get("backdrop_trending_request_needed", {}))
            enable_backdrop = backdrop_config.pop("enable", True)
            
            if enable_backdrop:
                if "name" not in backdrop_config:
                    backdrop_config["name"] = "backdrop"
                
                tvdb_ids_str = ", ".join(str(i) for i in sorted(tvdb_request))
                
                overlays_dict["backdrop_trending_request_tvdb"] = {
                    "overlay": backdrop_config,
                    "tvdb_show": tvdb_ids_str
                }
        
        if tmdb_request:
            backdrop_config = deepcopy(config_sections.get("backdrop_trending_request_needed", {}))
            enable_backdrop = backdrop_config.pop("enable", True)
            
            if enable_backdrop:
                if "name" not in backdrop_config:
                    backdrop_config["name"] = "backdrop"
                
                tmdb_ids_str = ", ".join(str(i) for i in sorted(tmdb_request))
                
                overlays_dict["backdrop_trending_request_tmdb"] = {
                    "overlay": backdrop_config,
                    "tmdb_show": tmdb_ids_str
                }
        
        if tvdb_request:
            text_config = deepcopy(config_sections.get("text_trending_request_needed", {}))
            enable_text = text_config.pop("enable", True)
            
            if enable_text:
                use_text = text_config.pop("use_text", "Request Needed")
                text_config.pop("date_format", None)
                text_config.pop("capitalize_dates", None)
                
                sub_overlay_config = deepcopy(text_config)
                
                if "name" not in sub_overlay_config:
                    sub_overlay_config["name"] = f"text({use_text})"
                
                tvdb_ids_str = ", ".join(str(i) for i in sorted(tvdb_request))
                
                overlays_dict["UMTK_trending_request_tvdb"] = {
                    "overlay": sub_overlay_config,
                    "tvdb_show": tvdb_ids_str
                }
        
        if tmdb_request:
            text_config = deepcopy(config_sections.get("text_trending_request_needed", {}))
            enable_text = text_config.pop("enable", True)
            
            if enable_text:
                use_text = text_config.pop("use_text", "Request Needed")
                text_config.pop("date_format", None)
                text_config.pop("capitalize_dates", None)
                
                sub_overlay_config = deepcopy(text_config)
                
                if "name" not in sub_overlay_config:
                    sub_overlay_config["name"] = f"text({use_text})"
                
                tmdb_ids_str = ", ".join(str(i) for i in sorted(tmdb_request))
                
                overlays_dict["UMTK_trending_request_tmdb"] = {
                    "overlay": sub_overlay_config,
                    "tmdb_show": tmdb_ids_str
                }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)


def create_collection_yaml_tv(output_file, future_shows, aired_shows, config):
    """Create collection YAML file for TV shows"""
    config_key = "collection_upcoming_shows"
    collection_config = {}
    collection_name = "Upcoming Shows"
    
    if config_key in config:
        collection_config = deepcopy(config[config_key])
        collection_name = collection_config.pop("collection_name", "Upcoming Shows")
    
    future_days = config.get('future_days_upcoming_shows', 30)
    if "summary" not in collection_config:
        summary = f"Shows with their first episode premiering within {future_days} days or already aired but not yet available"
    else:
        summary = collection_config.pop("summary")

    all_shows = future_shows + aired_shows

    if not all_shows:
        # Get item_label from config, default to collection_name
        item_label = collection_config.get("item_label", collection_name)
        
        data = {
            "collections": {
                collection_name: {
                    "plex_all": True,
                    "item_label.remove": item_label,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return
    
    tvdb_ids = [s['tvdbId'] for s in all_shows if s.get('tvdbId')]
    if not tvdb_ids:
        # Get item_label from config, default to collection_name
        item_label = collection_config.get("item_label", collection_name)
        
        data = {
            "collections": {
                collection_name: {
                    "plex_all": True,
                    "item_label.remove": item_label,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return

    tvdb_ids_str = ", ".join(str(i) for i in sorted(tvdb_ids))

    collection_data = {}
    collection_data["summary"] = summary
    
    for key, value in collection_config.items():
        if key == "sort_title":
            collection_data[key] = QuotedString(value)
        else:
            collection_data[key] = value
    
    if "sync_mode" not in collection_data:
        collection_data["sync_mode"] = "sync"
    
    collection_data["tvdb_show"] = tvdb_ids_str

    ordered_collection = OrderedDict()
    
    ordered_collection["summary"] = collection_data["summary"]
    if "sort_title" in collection_data:
        ordered_collection["sort_title"] = collection_data["sort_title"]
    
    for key, value in collection_data.items():
        if key not in ["summary", "sort_title", "sync_mode", "tvdb_show"]:
            ordered_collection[key] = value
    
    ordered_collection["sync_mode"] = collection_data["sync_mode"]
    ordered_collection["tvdb_show"] = collection_data["tvdb_show"]

    data = {
        "collections": {
            collection_name: ordered_collection
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)


def create_new_shows_collection_yaml(output_file, shows, config):
    """Create collection YAML file for new shows"""
    config_key = "collection_new_show"
    collection_config = {}
    collection_name = "New Shows"
    
    if config_key in config:
        collection_config = deepcopy(config[config_key])
        collection_name = collection_config.pop("collection_name", "New Shows")
    
    recent_days = config.get('recent_days_new_show', 7)
    if "summary" not in collection_config:
        summary = f"Shows that premiered within the past {recent_days} days"
    else:
        summary = collection_config.pop("summary")

    if not shows:
        # Get item_label from config, default to collection_name
        item_label = collection_config.get("item_label", collection_name)
        
        data = {
            "collections": {
                collection_name: {
                    "plex_all": True,
                    "item_label.remove": item_label,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return
    
    tvdb_ids = [s['tvdbId'] for s in shows if s.get('tvdbId')]
    if not tvdb_ids:
        # Get item_label from config, default to collection_name
        item_label = collection_config.get("item_label", collection_name)
        
        data = {
            "collections": {
                collection_name: {
                    "plex_all": True,
                    "item_label.remove": item_label,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return

    tvdb_ids_str = ", ".join(str(i) for i in sorted(tvdb_ids))

    collection_data = {}
    collection_data["summary"] = summary
    
    for key, value in collection_config.items():
        if key == "sort_title":
            collection_data[key] = QuotedString(value)
        else:
            collection_data[key] = value
    
    if "sync_mode" not in collection_data:
        collection_data["sync_mode"] = "sync"
    
    collection_data["tvdb_show"] = tvdb_ids_str

    ordered_collection = OrderedDict()
    
    ordered_collection["summary"] = collection_data["summary"]
    if "sort_title" in collection_data:
        ordered_collection["sort_title"] = collection_data["sort_title"]
    
    for key, value in collection_data.items():
        if key not in ["summary", "sort_title", "sync_mode", "tvdb_show"]:
            ordered_collection[key] = value
    
    ordered_collection["sync_mode"] = collection_data["sync_mode"]
    ordered_collection["tvdb_show"] = collection_data["tvdb_show"]

    data = {
        "collections": {
            collection_name: ordered_collection
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)


def create_new_shows_overlay_yaml(output_file, shows, config_sections):
    """Create overlay YAML file for new shows"""
    if not shows:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No new shows found")
        return
    
    all_tvdb_ids = set()
    for s in shows:
        if s.get("tvdbId"):
            all_tvdb_ids.add(s['tvdbId'])
    
    overlays_dict = {}
    
    backdrop_config = deepcopy(config_sections.get("backdrop", {}))
    enable_backdrop = backdrop_config.pop("enable", True)

    if enable_backdrop and all_tvdb_ids:
        if "name" not in backdrop_config:
            backdrop_config["name"] = "backdrop"
        all_tvdb_ids_str = ", ".join(str(i) for i in sorted(all_tvdb_ids) if i)
        
        overlays_dict["backdrop"] = {
            "overlay": backdrop_config,
            "tvdb_show": all_tvdb_ids_str,
            "filters": {
                "label.not": "RequestNeeded"
            }
        }
    
    text_config = deepcopy(config_sections.get("text", {}))
    enable_text = text_config.pop("enable", True)
    
    if enable_text and all_tvdb_ids:
        use_text = text_config.pop("use_text", "New Show")
        
        text_config.pop("date_format", None)
        text_config.pop("capitalize_dates", None)
        
        sub_overlay_config = deepcopy(text_config)
        if "name" not in sub_overlay_config:
            sub_overlay_config["name"] = f"text({use_text})"
        
        tvdb_ids_str = ", ".join(str(i) for i in sorted(all_tvdb_ids) if i)
        
        overlays_dict["UMTK_new_shows"] = {
            "overlay": sub_overlay_config,
            "tvdb_show": tvdb_ids_str,
            "filters": {
                "label.not": "RequestNeeded"
            }
        }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)


def create_overlay_yaml_movies(output_file, future_movies, released_movies, trending_monitored, 
                               trending_request_needed, config_sections, config, localization=None):
    """Create overlay YAML file for movies"""
    if not future_movies and not released_movies and not trending_monitored and not trending_request_needed:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No matching movies found")
        return
    
    overlays_dict = {}
    
    # Get global settings
    simplify_next_week = config.get("simplify_next_week_dates", False)
    utc_offset = float(config.get('utc_offset', 0))
    
    # Process future movies (upcoming releases)
    if future_movies:
        date_to_tmdb_ids = defaultdict(list)
        all_future_tmdb_ids = set()
        
        for m in future_movies:
            if m.get("tmdbId"):
                all_future_tmdb_ids.add(m['tmdbId'])
                if m.get("releaseDate"):
                    date_to_tmdb_ids[m['releaseDate']].append(m.get('tmdbId'))
        
        backdrop_config = deepcopy(config_sections.get("backdrop_future", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_future_tmdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tmdb_ids_str = ", ".join(str(i) for i in sorted(all_future_tmdb_ids) if i)
            
            overlays_dict["backdrop_future"] = {
                "overlay": backdrop_config,
                "tmdb_movie": all_tmdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_future", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_future_tmdb_ids:
            date_format = text_config.pop("date_format", "yyyy-mm-dd")
            use_text = text_config.pop("use_text", "Coming Soon")
            capitalize_dates = text_config.pop("capitalize_dates", True)
            
            for date_str in sorted(date_to_tmdb_ids):
                formatted_date = format_date(date_str, date_format, capitalize_dates, 
                                             simplify_next_week, utc_offset, localization)
                sub_overlay_config = deepcopy(text_config)
                
                if "name" not in sub_overlay_config:
                    sub_overlay_config["name"] = f"text({use_text} {formatted_date})"
                else:
                    base_name = sub_overlay_config["name"]
                    sub_overlay_config["name"] = f"{base_name}({use_text} {formatted_date})"
                
                tmdb_ids_for_date = sorted(tmdb_id for tmdb_id in date_to_tmdb_ids[date_str] if tmdb_id)
                tmdb_ids_str = ", ".join(str(i) for i in tmdb_ids_for_date)
                
                block_key = f"UMTK_future_{formatted_date}"
                overlays_dict[block_key] = {
                    "overlay": sub_overlay_config,
                    "tmdb_movie": tmdb_ids_str
                }
    
    # Process released movies (released but not available)
    if released_movies:
        all_released_tmdb_ids = set()
        
        for m in released_movies:
            if m.get("tmdbId"):
                all_released_tmdb_ids.add(m['tmdbId'])
        
        backdrop_config = deepcopy(config_sections.get("backdrop_released", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_released_tmdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tmdb_ids_str = ", ".join(str(i) for i in sorted(all_released_tmdb_ids) if i)
            
            overlays_dict["backdrop_released"] = {
                "overlay": backdrop_config,
                "tmdb_movie": all_tmdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_released", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_released_tmdb_ids:
            use_text = text_config.pop("use_text", "Available Now")
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            else:
                base_name = sub_overlay_config["name"]
                sub_overlay_config["name"] = f"{base_name}({use_text})"
            
            tmdb_ids_str = ", ".join(str(i) for i in sorted(all_released_tmdb_ids) if i)
            
            overlays_dict["UMTK_released"] = {
                "overlay": sub_overlay_config,
                "tmdb_movie": tmdb_ids_str
            }
    
    # Process trending monitored movies
    if trending_monitored:
        all_trending_monitored_tmdb_ids = set()
        
        for m in trending_monitored:
            if m.get("tmdbId"):
                all_trending_monitored_tmdb_ids.add(m['tmdbId'])
        
        backdrop_config = deepcopy(config_sections.get("backdrop_released", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_trending_monitored_tmdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tmdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_monitored_tmdb_ids) if i)
            
            overlays_dict["backdrop_trending_monitored"] = {
                "overlay": backdrop_config,
                "tmdb_movie": all_tmdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_released", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_trending_monitored_tmdb_ids:
            use_text = text_config.pop("use_text", "Available Now")
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            else:
                base_name = sub_overlay_config["name"]
                sub_overlay_config["name"] = f"{base_name}({use_text})"
            
            tmdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_monitored_tmdb_ids) if i)
            
            overlays_dict["UMTK_trending_monitored"] = {
                "overlay": sub_overlay_config,
                "tmdb_movie": tmdb_ids_str
            }
    
    # Process trending request needed movies
    if trending_request_needed:
        all_trending_request_tmdb_ids = set()
        
        for m in trending_request_needed:
            if m.get("tmdbId"):
                all_trending_request_tmdb_ids.add(m['tmdbId'])
        
        backdrop_config = deepcopy(config_sections.get("backdrop_trending_request_needed", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_trending_request_tmdb_ids:
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tmdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_request_tmdb_ids) if i)
            
            overlays_dict["backdrop_trending_request"] = {
                "overlay": backdrop_config,
                "tmdb_movie": all_tmdb_ids_str
            }
        
        text_config = deepcopy(config_sections.get("text_trending_request_needed", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_trending_request_tmdb_ids:
            use_text = text_config.pop("use_text", "Request Needed")
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            else:
                base_name = sub_overlay_config["name"]
                sub_overlay_config["name"] = f"{base_name}({use_text})"
            
            tmdb_ids_str = ", ".join(str(i) for i in sorted(all_trending_request_tmdb_ids) if i)
            
            overlays_dict["UMTK_trending_request"] = {
                "overlay": sub_overlay_config,
                "tmdb_movie": tmdb_ids_str
            }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)


def create_collection_yaml_movies(output_file, future_movies, released_movies, config):
    """Create collection YAML file for movies"""
    config_key = "collection_upcoming_movies"
    collection_config = {}
    collection_name = "Upcoming Movies"
    
    if config_key in config:
        collection_config = deepcopy(config[config_key])
        collection_name = collection_config.pop("collection_name", "Upcoming Movies")
    
    if "summary" not in collection_config:
        future_days = config.get('future_days_upcoming_movies', 30)
        summary = f"Movies releasing within {future_days} days or already released but not yet available"
        collection_config["summary"] = summary

    all_movies = future_movies + released_movies
    
    if not all_movies:
        # Get item_label from config, default to collection_name
        item_label = collection_config.get("item_label", collection_name)
        
        data = {
            "collections": {
                collection_name: {
                    "plex_all": True,
                    "item_label.remove": item_label,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return
    
    tmdb_ids = [m['tmdbId'] for m in all_movies if m.get('tmdbId')]
    if not tmdb_ids:
        # Get item_label from config, default to collection_name
        item_label = collection_config.get("item_label", collection_name)
        
        data = {
            "collections": {
                collection_name: {
                    "plex_all": True,
                    "item_label.remove": item_label,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return

    tmdb_ids_str = ", ".join(str(i) for i in sorted(tmdb_ids))

    collection_data = deepcopy(collection_config)
    
    if "sync_mode" not in collection_data:
        collection_data["sync_mode"] = "sync"
    
    collection_data["tmdb_movie"] = tmdb_ids_str

    ordered_collection = OrderedDict()
    
    if "summary" in collection_data:
        ordered_collection["summary"] = collection_data["summary"]
    
    if "sort_title" in collection_data:
        if isinstance(collection_data["sort_title"], str):
            ordered_collection["sort_title"] = QuotedString(collection_data["sort_title"])
        else:
            ordered_collection["sort_title"] = collection_data["sort_title"]
    
    for key, value in collection_data.items():
        if key not in ["summary", "sort_title", "sync_mode", "tmdb_movie"]:
            ordered_collection[key] = value
    
    ordered_collection["sync_mode"] = collection_data["sync_mode"]
    ordered_collection["tmdb_movie"] = collection_data["tmdb_movie"]

    data = {
        "collections": {
            collection_name: ordered_collection
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)


def create_trending_collection_yaml_movies(output_file, mdblist_items, config, trending_request_needed=None):
    """Create trending collection YAML file for movies using TMDB IDs from all MDBList items"""
    config_key = "collection_trending_movies"
    collection_config = {}
    collection_name = "Trending Movies"
    
    if config_key in config:
        collection_config = deepcopy(config[config_key])
        collection_name = collection_config.pop("collection_name", "Trending Movies")

    if not mdblist_items:
        # Get item_label from config, default to collection_name
        item_label = collection_config.get("item_label", collection_name)
        
        data = {
            "collections": {
                collection_name: {
                    "plex_all": True,
                    "item_label.remove": item_label,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return
    
    tmdb_ids = []
    for item in mdblist_items:
        tmdb_id = item.get('tmdb_id') or item.get('id')
        if tmdb_id:
            tmdb_ids.append(str(tmdb_id))
    
    if not tmdb_ids:
        # Get item_label from config, default to collection_name
        item_label = collection_config.get("item_label", collection_name)
        
        data = {
            "collections": {
                collection_name: {
                    "plex_all": True,
                    "item_label.remove": item_label,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return

    collection_data = deepcopy(collection_config)
    
    tmdb_ids_str = ", ".join(tmdb_ids)
    collection_data["tmdb_movie"] = tmdb_ids_str
    
    if "sync_mode" not in collection_data:
        collection_data["sync_mode"] = "sync"

    ordered_collection = OrderedDict()
    
    for key, value in collection_data.items():
        if key == "sort_title" and isinstance(value, str):
            ordered_collection[key] = QuotedString(value)
        else:
            ordered_collection[key] = value

    data = {
        "collections": {
            collection_name: ordered_collection
        }
    }

    label_request_needed = str(config.get("label_request_needed", "false")).lower() == "true"
    if label_request_needed and trending_request_needed:
        request_tmdb_ids = []
        for movie in trending_request_needed:
            if movie.get("tmdbId"):
                request_tmdb_ids.append(str(movie['tmdbId']))
        
        if request_tmdb_ids:
            tmdb_ids_str = ", ".join(request_tmdb_ids)
            data["collections"]["RequestNeededMovies"] = {
                "item_label": "RequestNeeded",
                "non_item_remove_label": "RequestNeeded",
                "build_collection": False,
                "sync_mode": "append",
                "tmdb_movie": tmdb_ids_str
            }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)


def create_trending_collection_yaml_tv(output_file, mdblist_items, config, trending_request_needed=None):
    """Create trending collection YAML file for TV shows using TVDB/TMDB IDs from all MDBList items"""
    config_key = "collection_trending_shows"
    collection_config = {}
    collection_name = "Trending Shows"
    
    if config_key in config:
        collection_config = deepcopy(config[config_key])
        collection_name = collection_config.pop("collection_name", "Trending Shows")

    if not mdblist_items:
        # Get item_label from config, default to collection_name
        item_label = collection_config.get("item_label", collection_name)
        
        data = {
            "collections": {
                collection_name: {
                    "plex_all": True,
                    "item_label.remove": item_label,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return
    
    tvdb_ids = []
    tmdb_ids = []
    
    for item in mdblist_items:
        tvdb_id = item.get('tvdb_id')
        tmdb_id = item.get('tmdb_id') or item.get('id')
        
        if tvdb_id:
            tvdb_ids.append(str(tvdb_id))
        elif tmdb_id:
            tmdb_ids.append(str(tmdb_id))
    
    if not tvdb_ids and not tmdb_ids:
        # Get item_label from config, default to collection_name
        item_label = collection_config.get("item_label", collection_name)
        
        data = {
            "collections": {
                collection_name: {
                    "plex_all": True,
                    "item_label.remove": item_label,
                    "build_collection": collection_config.get("build_collection", False)
                }
            }
        }
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return

    collection_data = deepcopy(collection_config)
    
    if tvdb_ids:
        tvdb_ids_str = ", ".join(tvdb_ids)
        collection_data["tvdb_show"] = tvdb_ids_str
    
    if tmdb_ids:
        tmdb_ids_str = ", ".join(tmdb_ids)
        collection_data["tmdb_show"] = tmdb_ids_str
    
    if "sync_mode" not in collection_data:
        collection_data["sync_mode"] = "sync"

    ordered_collection = OrderedDict()
    
    for key, value in collection_data.items():
        if key == "sort_title" and isinstance(value, str):
            ordered_collection[key] = QuotedString(value)
        else:
            ordered_collection[key] = value

    data = {
        "collections": {
            collection_name: ordered_collection
        }
    }

    label_request_needed = str(config.get("label_request_needed", "false")).lower() == "true"
    if label_request_needed and trending_request_needed:
        request_tvdb_ids = []
        request_tmdb_ids = []
        
        for show in trending_request_needed:
            if show.get("tvdbId"):
                request_tvdb_ids.append(str(show['tvdbId']))
            elif show.get("tmdbId"):
                request_tmdb_ids.append(str(show['tmdbId']))
        
        if request_tvdb_ids:
            tvdb_ids_str = ", ".join(request_tvdb_ids)
            data["collections"]["RequestNeededTV"] = {
                "item_label": "RequestNeeded",
                "non_item_remove_label": "RequestNeeded",
                "build_collection": False,
                "sync_mode": "append",
                "tvdb_show": tvdb_ids_str
            }
        elif request_tmdb_ids:
            tmdb_ids_str = ", ".join(request_tmdb_ids)
            data["collections"]["RequestNeededTV"] = {
                "item_label": "RequestNeeded",
                "non_item_remove_label": "RequestNeeded",
                "build_collection": False,
                "sync_mode": "append",
                "tmdb_show": tmdb_ids_str
            }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)


def create_top10_overlay_yaml_movies(output_file, mdblist_items, config_sections, limit=10):
    """Create Top N overlay YAML file for movies based on MDBList ranking"""
    if not mdblist_items:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No trending movies found for Top 10")
        return
    
    # Use the configured limit instead of hardcoded 10
    top_items = mdblist_items[:limit]
    
    overlays_dict = {}
    
    backdrop_config = deepcopy(config_sections.get("backdrop", {}))
    enable_backdrop = backdrop_config.pop("enable", True)
    
    urlup = backdrop_config.pop("urlup", None)
    urldown = backdrop_config.pop("urldown", None)
    urlequal = backdrop_config.pop("urlequal", None)
    
    track_ranking_changes = all([urlup, urldown, urlequal])
    
    today = datetime.now().date()
    
    previous_rankings = {}
    previous_categories = {}
    file_date = None
    
    if track_ranking_changes and Path(output_file).exists():
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
                first_line = content.split('\n')[0] if content else ''
                if first_line.startswith('#Last updated:'):
                    date_str = first_line.replace('#Last updated:', '').strip()
                    try:
                        file_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        pass
                
                existing_data = yaml.safe_load(content)
                if existing_data and 'overlays' in existing_data:
                    for key, value in existing_data['overlays'].items():
                        if key.startswith('trending_top10_'):
                            parts = key.split('_')
                            if len(parts) >= 3 and parts[2].isdigit():
                                rank = int(parts[2])
                                tmdb_id = value.get('tmdb_movie')
                                if tmdb_id:
                                    previous_rankings[str(tmdb_id)] = rank
                    
                    for key, value in existing_data['overlays'].items():
                        if 'backdrop_trending_top_10_up' in key:
                            tmdb_ids = value.get('tmdb_movie', '').split(', ')
                            for tmdb_id in tmdb_ids:
                                if tmdb_id.strip():
                                    previous_categories[tmdb_id.strip()] = 'up'
                        elif 'backdrop_trending_top_10_equal' in key:
                            tmdb_ids = value.get('tmdb_movie', '').split(', ')
                            for tmdb_id in tmdb_ids:
                                if tmdb_id.strip():
                                    previous_categories[tmdb_id.strip()] = 'equal'
                        elif 'backdrop_trending_top_10_down' in key:
                            tmdb_ids = value.get('tmdb_movie', '').split(', ')
                            for tmdb_id in tmdb_ids:
                                if tmdb_id.strip():
                                    previous_categories[tmdb_id.strip()] = 'down'
        except Exception as e:
            print(f"{ORANGE}Could not read previous rankings from {output_file}: {e}{RESET}")
            previous_rankings = {}
            previous_categories = {}
    
    same_day_run = file_date == today
    
    if enable_backdrop:
        if track_ranking_changes:
            tmdb_up = []
            tmdb_equal = []
            tmdb_down = []
            
            for item in top_items:
                current_rank = item.get('rank')
                tmdb_id = item.get('id') or item.get('tmdb_id')
                
                if not current_rank or not tmdb_id:
                    continue
                
                tmdb_id_str = str(tmdb_id)
                previous_rank = previous_rankings.get(tmdb_id_str)
                previous_category = previous_categories.get(tmdb_id_str)
                
                if previous_rank is None:
                    tmdb_up.append(tmdb_id_str)
                elif current_rank < previous_rank:
                    tmdb_up.append(tmdb_id_str)
                elif current_rank > previous_rank:
                    tmdb_down.append(tmdb_id_str)
                else:
                    if same_day_run and previous_category:
                        if previous_category == 'up':
                            tmdb_up.append(tmdb_id_str)
                        elif previous_category == 'down':
                            tmdb_down.append(tmdb_id_str)
                        else:
                            tmdb_equal.append(tmdb_id_str)
                    else:
                        tmdb_equal.append(tmdb_id_str)
            
            if tmdb_up:
                up_config = deepcopy(backdrop_config)
                up_config["name"] = backdrop_config.get("name", "backdrop") + "up"
                up_config["url"] = urlup
                overlays_dict["backdrop_trending_top_10_up"] = {
                    "overlay": up_config,
                    "tmdb_movie": ", ".join(tmdb_up)
                }
            
            if tmdb_equal:
                equal_config = deepcopy(backdrop_config)
                equal_config["name"] = backdrop_config.get("name", "backdrop") + "equal"
                equal_config["url"] = urlequal
                overlays_dict["backdrop_trending_top_10_equal"] = {
                    "overlay": equal_config,
                    "tmdb_movie": ", ".join(tmdb_equal)
                }
            
            if tmdb_down:
                down_config = deepcopy(backdrop_config)
                down_config["name"] = backdrop_config.get("name", "backdrop") + "down"
                down_config["url"] = urldown
                overlays_dict["backdrop_trending_top_10_down"] = {
                    "overlay": down_config,
                    "tmdb_movie": ", ".join(tmdb_down)
                }
        
        else:
            all_tmdb_ids = []
            for item in top_items:
                tmdb_id = item.get('id') or item.get('tmdb_id')
                if tmdb_id:
                    all_tmdb_ids.append(str(tmdb_id))
            
            if all_tmdb_ids:
                if "name" not in backdrop_config:
                    backdrop_config["name"] = "backdrop"
                
                tmdb_ids_str = ", ".join(all_tmdb_ids)
                
                overlays_dict["backdrop_trending_top_10"] = {
                    "overlay": backdrop_config,
                    "tmdb_movie": tmdb_ids_str
                }
    
    text_config = deepcopy(config_sections.get("text", {}))
    enable_text = text_config.pop("enable", True)
    
    text_config.pop("use_text", None)
    text_config.pop("date_format", None)
    text_config.pop("capitalize_dates", None)
    
    if enable_text:
        for item in top_items:
            rank = item.get('rank')
            tmdb_id = item.get('id') or item.get('tmdb_id')
            
            if not rank or not tmdb_id:
                continue
            
            rank_text_config = deepcopy(text_config)
            rank_text_config["name"] = f"text({rank})"
            
            block_key = f"trending_top10_{rank}"
            overlays_dict[block_key] = {
                "overlay": rank_text_config,
                "tmdb_movie": str(tmdb_id)
            }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        if track_ranking_changes:
            f.write(f"#Last updated: {today}\n")
        yaml.dump(final_output, f, sort_keys=False)


def create_top10_overlay_yaml_tv(output_file, mdblist_items, config_sections, limit=10):
    """Create Top N overlay YAML file for TV shows based on MDBList ranking"""
    if not mdblist_items:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No trending shows found for Top 10")
        return
    
    # Use the configured limit instead of hardcoded 10
    top_items = mdblist_items[:limit]
    
    overlays_dict = {}
    
    backdrop_config = deepcopy(config_sections.get("backdrop", {}))
    enable_backdrop = backdrop_config.pop("enable", True)
    
    urlup = backdrop_config.pop("urlup", None)
    urldown = backdrop_config.pop("urldown", None)
    urlequal = backdrop_config.pop("urlequal", None)
    
    track_ranking_changes = all([urlup, urldown, urlequal])
    
    today = datetime.now().date()
    
    previous_rankings = {}
    previous_categories = {}
    file_date = None
    
    if track_ranking_changes and Path(output_file).exists():
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
                first_line = content.split('\n')[0] if content else ''
                if first_line.startswith('#Last updated:'):
                    date_str = first_line.replace('#Last updated:', '').strip()
                    try:
                        file_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        pass
                
                existing_data = yaml.safe_load(content)
                if existing_data and 'overlays' in existing_data:
                    for key, value in existing_data['overlays'].items():
                        if key.startswith('trending_top10_') and '_tvdb' in key:
                            parts = key.split('_')
                            if len(parts) >= 3 and parts[2].isdigit():
                                rank = int(parts[2])
                                tvdb_id = value.get('tvdb_show')
                                if tvdb_id:
                                    previous_rankings[str(tvdb_id)] = rank
                        elif key.startswith('trending_top10_') and '_tmdb' in key:
                            parts = key.split('_')
                            if len(parts) >= 3 and parts[2].isdigit():
                                rank = int(parts[2])
                                tmdb_id = value.get('tmdb_show')
                                if tmdb_id:
                                    previous_rankings[f"tmdb_{tmdb_id}"] = rank
                    
                    for key, value in existing_data['overlays'].items():
                        if 'backdrop_trending_top_10_tvdb_up' in key:
                            tvdb_ids = value.get('tvdb_show', '').split(', ')
                            for tvdb_id in tvdb_ids:
                                if tvdb_id.strip():
                                    previous_categories[tvdb_id.strip()] = 'up'
                        elif 'backdrop_trending_top_10_tvdb_equal' in key:
                            tvdb_ids = value.get('tvdb_show', '').split(', ')
                            for tvdb_id in tvdb_ids:
                                if tvdb_id.strip():
                                    previous_categories[tvdb_id.strip()] = 'equal'
                        elif 'backdrop_trending_top_10_tvdb_down' in key:
                            tvdb_ids = value.get('tvdb_show', '').split(', ')
                            for tvdb_id in tvdb_ids:
                                if tvdb_id.strip():
                                    previous_categories[tvdb_id.strip()] = 'down'
                        elif 'backdrop_trending_top_10_tmdb_up' in key:
                            tmdb_ids = value.get('tmdb_show', '').split(', ')
                            for tmdb_id in tmdb_ids:
                                if tmdb_id.strip():
                                    previous_categories[f"tmdb_{tmdb_id.strip()}"] = 'up'
                        elif 'backdrop_trending_top_10_tmdb_equal' in key:
                            tmdb_ids = value.get('tmdb_show', '').split(', ')
                            for tmdb_id in tmdb_ids:
                                if tmdb_id.strip():
                                    previous_categories[f"tmdb_{tmdb_id.strip()}"] = 'equal'
                        elif 'backdrop_trending_top_10_tmdb_down' in key:
                            tmdb_ids = value.get('tmdb_show', '').split(', ')
                            for tmdb_id in tmdb_ids:
                                if tmdb_id.strip():
                                    previous_categories[f"tmdb_{tmdb_id.strip()}"] = 'down'
        except Exception as e:
            print(f"{ORANGE}Could not read previous rankings from {output_file}: {e}{RESET}")
            previous_rankings = {}
            previous_categories = {}
    
    same_day_run = file_date == today
    
    if enable_backdrop:
        if track_ranking_changes:
            tvdb_up = []
            tvdb_equal = []
            tvdb_down = []
            tmdb_up = []
            tmdb_equal = []
            tmdb_down = []
            
            for item in top_items:
                current_rank = item.get('rank')
                tvdb_id = item.get('tvdb_id')
                tmdb_id = item.get('tmdb_id')
                
                if not current_rank:
                    continue
                
                if tvdb_id:
                    tvdb_id_str = str(tvdb_id)
                    previous_rank = previous_rankings.get(tvdb_id_str)
                    previous_category = previous_categories.get(tvdb_id_str)
                    
                    if previous_rank is None:
                        tvdb_up.append(tvdb_id_str)
                    elif current_rank < previous_rank:
                        tvdb_up.append(tvdb_id_str)
                    elif current_rank > previous_rank:
                        tvdb_down.append(tvdb_id_str)
                    else:
                        if same_day_run and previous_category:
                            if previous_category == 'up':
                                tvdb_up.append(tvdb_id_str)
                            elif previous_category == 'down':
                                tvdb_down.append(tvdb_id_str)
                            else:
                                tvdb_equal.append(tvdb_id_str)
                        else:
                            tvdb_equal.append(tvdb_id_str)
                
                elif tmdb_id:
                    tmdb_id_str = str(tmdb_id)
                    tmdb_key = f"tmdb_{tmdb_id_str}"
                    previous_rank = previous_rankings.get(tmdb_key)
                    previous_category = previous_categories.get(tmdb_key)
                    
                    if previous_rank is None:
                        tmdb_up.append(tmdb_id_str)
                    elif current_rank < previous_rank:
                        tmdb_up.append(tmdb_id_str)
                    elif current_rank > previous_rank:
                        tmdb_down.append(tmdb_id_str)
                    else:
                        if same_day_run and previous_category:
                            if previous_category == 'up':
                                tmdb_up.append(tmdb_id_str)
                            elif previous_category == 'down':
                                tmdb_down.append(tmdb_id_str)
                            else:
                                tmdb_equal.append(tmdb_id_str)
                        else:
                            tmdb_equal.append(tmdb_id_str)
            
            if tvdb_up:
                up_config = deepcopy(backdrop_config)
                up_config["name"] = backdrop_config.get("name", "backdrop") + "up"
                up_config["url"] = urlup
                overlays_dict["backdrop_trending_top_10_tvdb_up"] = {
                    "overlay": up_config,
                    "tvdb_show": ", ".join(tvdb_up)
                }
            
            if tvdb_equal:
                equal_config = deepcopy(backdrop_config)
                equal_config["name"] = backdrop_config.get("name", "backdrop") + "equal"
                equal_config["url"] = urlequal
                overlays_dict["backdrop_trending_top_10_tvdb_equal"] = {
                    "overlay": equal_config,
                    "tvdb_show": ", ".join(tvdb_equal)
                }
            
            if tvdb_down:
                down_config = deepcopy(backdrop_config)
                down_config["name"] = backdrop_config.get("name", "backdrop") + "down"
                down_config["url"] = urldown
                overlays_dict["backdrop_trending_top_10_tvdb_down"] = {
                    "overlay": down_config,
                    "tvdb_show": ", ".join(tvdb_down)
                }
            
            if tmdb_up:
                up_config = deepcopy(backdrop_config)
                up_config["name"] = backdrop_config.get("name", "backdrop") + "up"
                up_config["url"] = urlup
                overlays_dict["backdrop_trending_top_10_tmdb_up"] = {
                    "overlay": up_config,
                    "tmdb_show": ", ".join(tmdb_up)
                }
            
            if tmdb_equal:
                equal_config = deepcopy(backdrop_config)
                equal_config["name"] = backdrop_config.get("name", "backdrop") + "equal"
                equal_config["url"] = urlequal
                overlays_dict["backdrop_trending_top_10_tmdb_equal"] = {
                    "overlay": equal_config,
                    "tmdb_show": ", ".join(tmdb_equal)
                }
            
            if tmdb_down:
                down_config = deepcopy(backdrop_config)
                down_config["name"] = backdrop_config.get("name", "backdrop") + "down"
                down_config["url"] = urldown
                overlays_dict["backdrop_trending_top_10_tmdb_down"] = {
                    "overlay": down_config,
                    "tmdb_show": ", ".join(tmdb_down)
                }
        
        else:
            tvdb_ids = []
            tmdb_ids = []
            
            for item in top_items:
                if item.get('tvdb_id'):
                    tvdb_ids.append(str(item['tvdb_id']))
                elif item.get('tmdb_id'):
                    tmdb_ids.append(str(item['tmdb_id']))
            
            if tvdb_ids:
                if "name" not in backdrop_config:
                    backdrop_config["name"] = "backdrop"
                
                tvdb_ids_str = ", ".join(tvdb_ids)
                
                overlays_dict["backdrop_trending_top_10_tvdb"] = {
                    "overlay": backdrop_config,
                    "tvdb_show": tvdb_ids_str
                }
            
            if tmdb_ids:
                tmdb_config = deepcopy(backdrop_config)
                if "name" not in tmdb_config:
                    tmdb_config["name"] = "backdrop"
                
                tmdb_ids_str = ", ".join(tmdb_ids)
                
                overlays_dict["backdrop_trending_top_10_tmdb"] = {
                    "overlay": tmdb_config,
                    "tmdb_show": tmdb_ids_str
                }
    
    text_config = deepcopy(config_sections.get("text", {}))
    enable_text = text_config.pop("enable", True)
    
    text_config.pop("use_text", None)
    text_config.pop("date_format", None)
    text_config.pop("capitalize_dates", None)
    
    if enable_text:
        for item in top_items:
            rank = item.get('rank')
            tvdb_id = item.get('tvdb_id')
            tmdb_id = item.get('tmdb_id')
            
            if not rank:
                continue
            
            rank_text_config = deepcopy(text_config)
            rank_text_config["name"] = f"text({rank})"
            
            if tvdb_id:
                block_key = f"trending_top10_{rank}_tvdb"
                overlays_dict[block_key] = {
                    "overlay": rank_text_config,
                    "tvdb_show": str(tvdb_id)
                }
            elif tmdb_id:
                block_key = f"trending_top10_{rank}_tmdb"
                overlays_dict[block_key] = {
                    "overlay": rank_text_config,
                    "tmdb_show": str(tmdb_id)
                }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        if track_ranking_changes:
            f.write(f"#Last updated: {today}\n")
        yaml.dump(final_output, f, sort_keys=False)