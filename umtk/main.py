"""
Main execution logic for UMTK
"""

import os
import sys
import requests
from datetime import datetime
from pathlib import Path, PureWindowsPath

from .constants import VERSION, GREEN, ORANGE, RED, BLUE, RESET
from .config_loader import load_config, load_localization, get_cookies_path, get_kometa_folder, get_video_folder
from .utils import (
    check_for_updates, check_yt_dlp_installed, check_video_file,
    get_tag_ids_from_names, sanitize_filename
)
from .sonarr import process_sonarr_url, get_sonarr_series
from .radarr import process_radarr_url, get_radarr_movies
from .mdblist import fetch_mdblist_items
from .finders import (
    find_upcoming_shows, find_new_shows, find_upcoming_movies,
    process_trending_tv, process_trending_movies
)
from .media_handlers import (
    search_trailer_on_youtube, download_trailer_tv, download_trailer_movie,
    create_placeholder_tv, create_placeholder_movie
)
from .cleanup import cleanup_tv_content, cleanup_movie_content
from .yaml_generators import (
    create_overlay_yaml_tv, create_collection_yaml_tv,
    create_new_shows_collection_yaml, create_new_shows_overlay_yaml,
    create_overlay_yaml_movies, create_collection_yaml_movies,
    create_trending_collection_yaml_movies, create_trending_collection_yaml_tv,
    create_top10_overlay_yaml_movies, create_top10_overlay_yaml_tv
)
from .plex_integration import update_plex_tv_metadata, update_plex_movie_metadata


def main():
    start_time = datetime.now()
    
    # Add Docker detection message
    if os.environ.get('DOCKER') == 'true':
        print(f"{GREEN}Running in Docker container{RESET}")
    
    check_for_updates()
    
    config = load_config()
    localization = load_localization()  # Load localization
    
    radarr_timeout = config.get('radarr_timeout', 90)
    sonarr_timeout = config.get('sonarr_timeout', 90)
    metadata_retry_limit = config.get('metadata_retry_limit', 4)
    
    # Get umtk root paths
    umtk_root_movies = config.get('umtk_root_movies')
    umtk_root_tv = config.get('umtk_root_tv')
    
    if umtk_root_movies:
        umtk_root_movies = str(umtk_root_movies).strip()
        umtk_root_movies = umtk_root_movies if umtk_root_movies else None
    else:
        umtk_root_movies = None
        
    if umtk_root_tv:
        umtk_root_tv = str(umtk_root_tv).strip()
        umtk_root_tv = umtk_root_tv if umtk_root_tv else None
    else:
        umtk_root_tv = None
    
    if umtk_root_movies:
        print(f"{GREEN}Using custom movie root: {umtk_root_movies}{RESET}")
    if umtk_root_tv:
        print(f"{GREEN}Using custom TV root: {umtk_root_tv}{RESET}")
    
    # Get Plex configuration
    plex_url = config.get('plex_url')
    plex_token = config.get('plex_token')
    movie_libraries = config.get('movie_libraries')
    tv_libraries = config.get('tv_libraries')
    
    if plex_url and plex_token:
        print(f"{GREEN}Plex integration enabled{RESET}")
        if movie_libraries:
            print(f"  Movie libraries: {movie_libraries}")
        if tv_libraries:
            print(f"  TV libraries: {tv_libraries}")
        print(f"  Metadata retry limit: {metadata_retry_limit}")
    
    # Get processing methods
    tv_method = config.get('tv', 1)
    movie_method = config.get('movies', 2)
    trending_tv_method = config.get('trending_tv', 0)
    trending_movies_method = config.get('trending_movies', 0)
    method_fallback = str(config.get("method_fallback", "false")).lower() == "true"
    add_rank_to_sort_title = str(config.get("add_rank_to_sort_title", "false")).lower() == "true"
    append_dates_to_sort_titles = str(config.get("append_dates_to_sort_titles", "true")).lower() == "true"
    edit_episode_titles = str(config.get("edit_S00E00_episode_title", "false")).lower() == "true"
    
    print(f"TV processing method: {tv_method} ({'Disabled' if tv_method == 0 else 'Trailer' if tv_method == 1 else 'Placeholder'})")
    print(f"Movie processing method: {movie_method} ({'Disabled' if movie_method == 0 else 'Trailer' if movie_method == 1 else 'Placeholder'})")
    print(f"Trending TV method: {trending_tv_method} ({'Disabled' if trending_tv_method == 0 else 'Trailer' if trending_tv_method == 1 else 'Placeholder'})")
    print(f"Trending Movies method: {trending_movies_method} ({'Disabled' if trending_movies_method == 0 else 'Trailer' if trending_movies_method == 1 else 'Placeholder'})")
    print(f"Method fallback: {method_fallback}")
    print(f"Append dates to sort titles: {append_dates_to_sort_titles}")
    print(f"Add rank to sort title: {add_rank_to_sort_title}")
    print(f"Edit S00E00 episode titles: {edit_episode_titles}")
    print()
    
    # Check requirements based on methods
    video_folder = get_video_folder()
    
    if tv_method == 1 or movie_method == 1 or trending_tv_method == 1 or trending_movies_method == 1:
        if not check_yt_dlp_installed():
            print(f"{RED}yt-dlp is required for trailer downloading but not installed.{RESET}")
            sys.exit(1)
    
    if tv_method == 2 or movie_method == 2 or trending_tv_method == 2 or trending_movies_method == 2 or \
       (method_fallback and (tv_method == 1 or movie_method == 1 or trending_tv_method == 1 or trending_movies_method == 1)):
        if not check_video_file(video_folder):
            print(f"{RED}UMTK video file is required for placeholder method but not found.{RESET}")
            sys.exit(1)
    
    # Check for cookies file
    cookies_path = get_cookies_path()
    if cookies_path:
        print(f"{GREEN}Found cookies file: {cookies_path}{RESET}")
    
    # Get common configuration values
    utc_offset = float(config.get('utc_offset', 0))
    debug = str(config.get("debug", "false")).lower() == "true"
    cleanup = str(config.get("cleanup", "true")).lower() == "true"
    skip_channels = config.get("skip_channels", [])
    
    if isinstance(skip_channels, str):
        skip_channels = [ch.strip() for ch in skip_channels.split(',') if ch.strip()]
    
    print(f"UTC offset: {utc_offset} hours")
    print(f"cleanup: {cleanup}")
    print(f"debug: {debug}")
    if skip_channels:
        print(f"skip_channels: {skip_channels}")
    print()
    
    kometa_folder = get_kometa_folder()
    kometa_folder.mkdir(exist_ok=True)
    
    try:
        # Initialize variables
        trending_tv_monitored = []
        trending_tv_request_needed = []
        trending_movies_monitored = []
        trending_movies_request_needed = []
        mdblist_tv_items = None
        mdblist_movies_items = None
        all_shows_with_content = []
        all_movies_with_content = []
        
        process_tv = (tv_method > 0 or trending_tv_method > 0)
        tv_processing_failed = False
        
        # Process TV Shows
        if process_tv:
            print(f"{BLUE}{'=' * 50}{RESET}")
            print(f"{BLUE}Processing TV Shows...{RESET}")
            print(f"{BLUE}{'=' * 50}{RESET}\n")
            
            try:
                sonarr_url = process_sonarr_url(config['sonarr_url'], config['sonarr_api_key'], sonarr_timeout)
                sonarr_api_key = config['sonarr_api_key']
                
                all_series = get_sonarr_series(sonarr_url, sonarr_api_key, sonarr_timeout)
                
                exclude_sonarr_tag_names = config.get('exclude_sonarr_tags', [])
                if isinstance(exclude_sonarr_tag_names, str):
                    exclude_sonarr_tag_names = [tag.strip() for tag in exclude_sonarr_tag_names.split(',') if tag.strip()]
                
                exclude_sonarr_tag_ids = get_tag_ids_from_names(sonarr_url, sonarr_api_key, exclude_sonarr_tag_names, sonarr_timeout, debug)
                
                future_days_upcoming_shows = config.get('future_days_upcoming_shows', 30)
                recent_days_new_show = config.get('recent_days_new_show', 7)
                future_only_tv = str(config.get("future_only_tv", "false")).lower() == "true"
                
                print(f"future_days_upcoming_shows: {future_days_upcoming_shows}")
                print(f"recent_days_new_show: {recent_days_new_show}")
                print(f"future_only_tv: {future_only_tv}")
                if exclude_sonarr_tag_names:
                    print(f"exclude_sonarr_tags: {', '.join(exclude_sonarr_tag_names)}")
                print()
                
                future_shows = []
                aired_shows = []
                new_shows = []
                
                if tv_method > 0:
                    future_shows, aired_shows = find_upcoming_shows(
                        all_series, sonarr_url, sonarr_api_key, future_days_upcoming_shows, 
                        utc_offset, debug, exclude_sonarr_tag_ids, future_only_tv
                    )
                   
                    if future_shows:
                        print(f"{GREEN}Found {len(future_shows)} future shows with first episodes within {future_days_upcoming_shows} days:{RESET}")
                        for show in future_shows:
                            print(f"- {show['title']}" + (f" ({show['year']})" if show['year'] else "") + f" - First episode: {show['airDate']}")
                    else:
                        print(f"{ORANGE}No future shows found with first episodes within {future_days_upcoming_shows} days.{RESET}")
                    
                    if aired_shows:
                        print(f"\n{GREEN}Found {len(aired_shows)} aired shows not yet available:{RESET}")
                        for show in aired_shows:
                            print(f"- {show['title']}" + (f" ({show['year']})" if show['year'] else "") + f" - First episode aired: {show['airDate']}")
                    elif not future_only_tv:
                        print(f"{ORANGE}No aired shows found that are not yet available.{RESET}")
                    else:
                        print(f"{ORANGE}Aired shows excluded due to future_only_tv=True.{RESET}")
                    
                    # Find new shows
                    print(f"\n{BLUE}Finding new shows with S01E01 downloaded...{RESET}")
                    new_shows = find_new_shows(
                        all_series, sonarr_url, sonarr_api_key, recent_days_new_show, utc_offset, debug
                    )
                    
                    if new_shows:
                        print(f"{GREEN}Found {len(new_shows)} new shows with S01E01 aired within the past {recent_days_new_show} days:{RESET}")
                        for show in new_shows:
                            print(f"- {show['title']}" + (f" ({show['year']})" if show['year'] else "") + f" - S01E01 aired: {show['airDate']}")
                    else:
                        print(f"{ORANGE}No new shows found with S01E01 aired within the past {recent_days_new_show} days.{RESET}")
                    
                    # Process TV content
                    all_shows = future_shows + aired_shows
                    if all_shows:
                        print(f"\n{BLUE}Processing content for upcoming shows...{RESET}")
                        successful = 0
                        failed = 0
                        skipped_existing = 0
                        fallback_used = 0
                        
                        for show in all_shows:
                            print(f"\nProcessing: {show['title']}")
                            
                            show_path = show.get('path')
                            if show_path:
                                if umtk_root_tv:
                                    show_name = PureWindowsPath(show_path).name
                                    season_00_path = Path(umtk_root_tv) / show_name / "Season 00"
                                else:
                                    season_00_path = Path

                    # Process TV content based on method
                    all_shows = future_shows + aired_shows
                    if all_shows:
                        print(f"\n{BLUE}Processing content for upcoming shows...{RESET}")
                        successful = 0
                        failed = 0
                        skipped_existing = 0
                        fallback_used = 0
                        
                        for show in all_shows:
                            print(f"\nProcessing: {show['title']}")
                            
                            # Check if content already exists
                            show_path = show.get('path')
                            if show_path:
                                if umtk_root_tv:
                                    # Use PureWindowsPath to handle Windows paths from Sonarr
                                    show_name = PureWindowsPath(show_path).name
                                    season_00_path = Path(umtk_root_tv) / show_name / "Season 00"
                                else:
                                    season_00_path = Path(show_path) / "Season 00"
                                
                                clean_title = "".join(c for c in show['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                                
                                # Check for both trailer and coming soon files
                                trailer_pattern = f"{clean_title}.S00E00.Trailer.*"
                                coming_soon_pattern = f"{clean_title}.S00E00.Coming.Soon.*"
                                existing_trailers = []
                                if season_00_path.exists():
                                    existing_trailers = list(season_00_path.glob(trailer_pattern)) + list(season_00_path.glob(coming_soon_pattern))
                                
                                if existing_trailers:
                                    existing_file = existing_trailers[0]
                                    # Determine if it's a trailer or placeholder
                                    show['used_trailer'] = '.Trailer.' in existing_file.name
                                    print(f"{GREEN}Content already exists for {show['title']}: {existing_file.name} - skipping{RESET}")
                                    skipped_existing += 1
                                    successful += 1
                                    all_shows_with_content.append(show)
                                    continue
                            
                            # Process based on method
                            success = False
                            
                            if tv_method == 1:  # Trailer
                                trailer_info = search_trailer_on_youtube(
                                    show['title'], 
                                    show.get('year'), 
                                    show.get('imdbId'),
                                    debug,
                                    skip_channels
                                )
                                
                                if trailer_info:
                                    print(f"Found trailer: {trailer_info['video_title']} ({trailer_info['duration']}) by {trailer_info['uploader']}")
                                    success = download_trailer_tv(show, trailer_info, debug, umtk_root_tv)
                                else:
                                    print(f"{ORANGE}No suitable trailer found for {show['title']}{RESET}")
                                
                                # If trailer method failed and fallback is enabled, try placeholder
                                if not success and method_fallback:
                                    print(f"{ORANGE}Trailer method failed, attempting fallback to placeholder method...{RESET}")
                                    success = create_placeholder_tv(show, debug, umtk_root_tv)
                                    if success:
                                        fallback_used += 1
                                        print(f"{GREEN}Fallback to placeholder successful for {show['title']}{RESET}")
                            
                            elif tv_method == 2:  # Placeholder
                                success = create_placeholder_tv(show, debug, umtk_root_tv)
                            
                            if success:
                                successful += 1
                                all_shows_with_content.append(show)
                            else:
                                failed += 1
                        
                        print(f"\n{GREEN}TV content processing summary:{RESET}")
                        print(f"Successful: {successful}")
                        print(f"Skipped (already exist): {skipped_existing}")
                        if fallback_used > 0:
                            print(f"Fallback used: {fallback_used}")
                        print(f"Failed: {failed}")
                
                # Process Trending TV Shows
                if trending_tv_method > 0:
                    print(f"\n{BLUE}{'=' * 50}{RESET}")
                    print(f"{BLUE}Processing Trending TV Shows...{RESET}")
                    print(f"{BLUE}{'=' * 50}{RESET}\n")
                    
                    mdblist_api_key = config.get('mdblist_api_key')
                    mdblist_tv_url = config.get('mdblist_tv')
                    mdblist_tv_limit = config.get('mdblist_tv_limit', 10)
                    
                    if not mdblist_api_key:
                        print(f"{RED}Error: mdblist_api_key not configured{RESET}")
                    elif not mdblist_tv_url:
                        print(f"{RED}Error: mdblist_tv not configured{RESET}")
                    else:
                        print(f"MDBList TV URL: {mdblist_tv_url}")
                        print(f"MDBList TV Limit: {mdblist_tv_limit}")
                        print()
                        
                        # Fetch trending shows from MDBList
                        print(f"{BLUE}Fetching trending TV shows from MDBList...{RESET}")
                        mdblist_tv_items = fetch_mdblist_items(mdblist_tv_url, mdblist_api_key, mdblist_tv_limit, debug)
                        
                        if mdblist_tv_items:
                            print(f"{GREEN}Fetched {len(mdblist_tv_items)} trending TV shows from MDBList{RESET}")
                            
                            # Process trending shows
                            trending_tv_monitored, trending_tv_request_needed = process_trending_tv(
                                mdblist_tv_items, all_series, sonarr_url, sonarr_api_key, debug
                            )
                            
                            if trending_tv_monitored:
                                print(f"\n{GREEN}Found {len(trending_tv_monitored)} trending shows that are monitored but not available:{RESET}")
                                for show in trending_tv_monitored:
                                    print(f"- {show['title']}" + (f" ({show['year']})" if show['year'] else ""))
                            else:
                                print(f"{ORANGE}No trending shows found that are monitored but not available.{RESET}")
                            
                            if trending_tv_request_needed:
                                print(f"\n{GREEN}Found {len(trending_tv_request_needed)} trending shows that need to be requested:{RESET}")
                                for show in trending_tv_request_needed:
                                    print(f"- {show['title']}" + (f" ({show['year']})" if show['year'] else ""))
                            else:
                                print(f"{ORANGE}No trending shows found that need to be requested.{RESET}")
                            
                            # Process trending TV content
                            all_trending_tv = trending_tv_monitored + trending_tv_request_needed
                            if all_trending_tv:
                                print(f"\n{BLUE}Processing content for trending TV shows...{RESET}")
                                successful = 0
                                failed = 0
                                skipped_existing = 0
                                fallback_used = 0
                                
                                for show in all_trending_tv:
                                    # Mark this as a trending show
                                    show['is_trending'] = True
                                    
                                    print(f"\nProcessing: {show['title']}")
                                    
                                    # Check if content already exists
                                    show_path = show.get('path')
                                    
                                    # Determine the path to check
                                    if show_path:
                                        if umtk_root_tv:
                                            # Use PureWindowsPath to handle Windows paths from Sonarr
                                            show_name = PureWindowsPath(show_path).name
                                            season_00_path = Path(umtk_root_tv) / show_name / "Season 00"
                                        else:
                                            season_00_path = Path(show_path) / "Season 00"
                                    elif umtk_root_tv:
                                        # For shows without a path, construct from umtk_root_tv
                                        show_title = show.get('title', 'Unknown')
                                        show_year = show.get('year', '')
                                        if show_year:
                                            show_folder = sanitize_filename(f"{show_title} ({show_year})")
                                        else:
                                            show_folder = sanitize_filename(show_title)
                                        season_00_path = Path(umtk_root_tv) / show_folder / "Season 00"
                                    else:
                                        season_00_path = None
                                    
                                    # Check for existing content
                                    if season_00_path:
                                        clean_title = "".join(c for c in show['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                                        # Check for both trailer and coming soon files
                                        trailer_pattern = f"{clean_title}.S00E00.Trailer.*"
                                        coming_soon_pattern = f"{clean_title}.S00E00.Coming.Soon.*"
                                        existing_trailers = []
                                        if season_00_path.exists():
                                            existing_trailers = list(season_00_path.glob(trailer_pattern)) + list(season_00_path.glob(coming_soon_pattern))
                                        
                                        if existing_trailers:
                                            existing_file = existing_trailers[0]
                                            # Determine if it's a trailer or placeholder
                                            show['used_trailer'] = '.Trailer.' in existing_file.name
                                            print(f"{GREEN}Content already exists for {show['title']}: {existing_file.name} - skipping{RESET}")
                                            skipped_existing += 1
                                            successful += 1
                                            all_shows_with_content.append(show)
                                            continue
                                    
                                    # Process based on method
                                    success = False
                                    
                                    if trending_tv_method == 1:  # Trailer
                                        trailer_info = search_trailer_on_youtube(
                                            show['title'], 
                                            show.get('year'), 
                                            show.get('imdbId'),
                                            debug,
                                            skip_channels
                                        )
                                        
                                        if trailer_info:
                                            print(f"Found trailer: {trailer_info['video_title']} ({trailer_info['duration']}) by {trailer_info['uploader']}")
                                            success = download_trailer_tv(show, trailer_info, debug, umtk_root_tv)
                                        else:
                                            print(f"{ORANGE}No suitable trailer found for {show['title']}{RESET}")
                                        
                                        # If trailer method failed and fallback is enabled, try placeholder
                                        if not success and method_fallback:
                                            print(f"{ORANGE}Trailer method failed, attempting fallback to placeholder method...{RESET}")
                                            success = create_placeholder_tv(show, debug, umtk_root_tv)
                                            if success:
                                                fallback_used += 1
                                                print(f"{GREEN}Fallback to placeholder successful for {show['title']}{RESET}")
                                    
                                    elif trending_tv_method == 2:  # Placeholder
                                        success = create_placeholder_tv(show, debug, umtk_root_tv)
                                    
                                    if success:
                                        successful += 1
                                        all_shows_with_content.append(show)
                                    else:
                                        failed += 1
                                
                                print(f"\n{GREEN}Trending TV content processing summary:{RESET}")
                                print(f"Successful: {successful}")
                                print(f"Skipped (already exist): {skipped_existing}")
                                if fallback_used > 0:
                                    print(f"Fallback used: {fallback_used}")
                                print(f"Failed: {failed}")
                        else:
                            print(f"{ORANGE}No trending TV shows fetched from MDBList{RESET}")
                
                # Cleanup TV content (after processing both regular and trending)
                if cleanup:
                    print(f"\n{BLUE}Checking for TV content to cleanup...{RESET}")
                    cleanup_tv_content(
                        all_series, sonarr_url, sonarr_api_key, tv_method, debug, 
                        exclude_sonarr_tag_ids, future_days_upcoming_shows, utc_offset, 
                        future_only_tv, umtk_root_tv, trending_tv_monitored, trending_tv_request_needed
                    )
                    print()
                
                # Create TV YAML files (create if either tv_method or trending_tv_method is enabled)
                if tv_method > 0 or trending_tv_method > 0:
                    overlay_file = kometa_folder / "UMTK_TV_UPCOMING_SHOWS_OVERLAYS.yml"
                    collection_file = kometa_folder / "UMTK_TV_UPCOMING_SHOWS_COLLECTION.yml"
                    
                    create_overlay_yaml_tv(
                        str(overlay_file), future_shows, aired_shows, 
                        trending_tv_monitored if trending_tv_method > 0 else [],
                        trending_tv_request_needed if trending_tv_method > 0 else [],
                        {"backdrop": config.get("backdrop_upcoming_shows", {}),
                         "text": config.get("text_upcoming_shows", {}),
                         "backdrop_aired": config.get("backdrop_upcoming_shows_aired", {}),
                         "text_aired": config.get("text_upcoming_shows_aired", {}),
                         "backdrop_trending_request_needed": config.get("backdrop_trending_shows_request_needed", {}),
                         "text_trending_request_needed": config.get("text_trending_shows_request_needed", {})},
                        config,
                        localization
                    )
                    
                    if tv_method > 0:
                        new_shows_overlay_file = kometa_folder / "UMTK_TV_NEW_SHOWS_OVERLAYS.yml"
                        new_shows_collection_file = kometa_folder / "UMTK_TV_NEW_SHOWS_COLLECTION.yml"
                        
                        # Create overlay file for new shows
                        create_new_shows_overlay_yaml(str(new_shows_overlay_file), new_shows,
                                                      {"backdrop": config.get("backdrop_new_show", {}),
                                                       "text": config.get("text_new_show", {})})
                        
                        # Create collection file for new shows
                        create_new_shows_collection_yaml(str(new_shows_collection_file), new_shows, config)
                    
                    create_collection_yaml_tv(str(collection_file), future_shows, aired_shows, config)
                    
                    print(f"\n{GREEN}TV YAML files created successfully{RESET}")
                
                # Create Trending TV collection YAML
                if trending_tv_method > 0:
                    if mdblist_tv_items:
                        # Pass the raw MDBList items for the collection
                        trending_collection_file = kometa_folder / "UMTK_TV_TRENDING_COLLECTION.yml"
                        create_trending_collection_yaml_tv(str(trending_collection_file), mdblist_tv_items, config, trending_tv_request_needed)
                        print(f"{GREEN}Trending TV collection YAML created successfully{RESET}")
            
                        # Create Top 10 TV overlay YAML
                        top10_tv_overlay_file = kometa_folder / "UMTK_TV_TOP10_OVERLAYS.yml"
                        create_top10_overlay_yaml_tv(
                            str(top10_tv_overlay_file), 
                            mdblist_tv_items,
                            {"backdrop": config.get("backdrop_trending_top_10_tv", {}),
                             "text": config.get("text_trending_top_10_tv", {})},
                            limit=mdblist_tv_limit
                        )
                        print(f"{GREEN}Top 10 TV overlay YAML created successfully{RESET}")
            
            except (ConnectionError, requests.exceptions.RequestException) as e:
                print(f"{RED}Error during TV processing: {str(e)}{RESET}")
                print(f"{ORANGE}Skipping TV processing and continuing with movies...{RESET}")
                tv_processing_failed = True
        
        # Determine if we need to process Movies at all (either regular or trending)
        process_movies = (movie_method > 0 or trending_movies_method > 0)
        
        # Process Movies
        if process_movies:
            print(f"\n{BLUE}{'=' * 50}{RESET}")
            print(f"{BLUE}Processing Movies...{RESET}")
            print(f"{BLUE}{'=' * 50}{RESET}\n")
            
            radarr_url = process_radarr_url(config['radarr_url'], config['radarr_api_key'], radarr_timeout)
            radarr_api_key = config['radarr_api_key']
            
            # Fetch all movies once
            all_movies = get_radarr_movies(radarr_url, radarr_api_key, radarr_timeout)
            
            # Get exclude tags for Radarr
            exclude_radarr_tag_names = config.get('exclude_radarr_tags', [])
            if isinstance(exclude_radarr_tag_names, str):
                exclude_radarr_tag_names = [tag.strip() for tag in exclude_radarr_tag_names.split(',') if tag.strip()]
            
            exclude_radarr_tag_ids = get_tag_ids_from_names(radarr_url, radarr_api_key, exclude_radarr_tag_names, radarr_timeout, debug)
            
            if debug and exclude_radarr_tag_names:
                print(f"{BLUE}[DEBUG] Exclude Radarr tags: {exclude_radarr_tag_names} -> IDs: {exclude_radarr_tag_ids}{RESET}")
            
            future_days_upcoming_movies = config.get('future_days_upcoming_movies', 30)
            past_days_upcoming_movies = config.get('past_days_upcoming_movies', 0)
            future_only = str(config.get("future_only", "false")).lower() == "true"
            include_inCinemas = str(config.get("include_inCinemas", "false")).lower() == "true"
            
            print(f"future_days_upcoming_movies: {future_days_upcoming_movies}")
            if past_days_upcoming_movies > 0 and not future_only:
                print(f"past_days_upcoming_movies: {past_days_upcoming_movies}")
            print(f"future_only: {future_only}")
            print(f"include_inCinemas: {include_inCinemas}")
            if exclude_radarr_tag_names:
                print(f"exclude_radarr_tags: {', '.join(exclude_radarr_tag_names)}")
            print()
            
            # Process regular upcoming movies if movie_method is enabled
            future_movies = []
            released_movies = []
            
            if movie_method > 0:
                # Find upcoming movies
                print(f"{BLUE}Finding upcoming movies...{RESET}")
                future_movies, released_movies = find_upcoming_movies(
                    all_movies, radarr_url, radarr_api_key, future_days_upcoming_movies, utc_offset, future_only, include_inCinemas, debug, exclude_radarr_tag_ids, past_days_upcoming_movies
                )
                
                if future_movies:
                    print(f"{GREEN}Found {len(future_movies)} future movies releasing within {future_days_upcoming_movies} days:{RESET}")
                    for movie in future_movies:
                        release_info = f" - {movie['releaseType']} Release: {movie['releaseDate']}"
                        print(f"- {movie['title']}" + (f" ({movie['year']})" if movie['year'] else "") + release_info)
                else:
                    print(f"{ORANGE}No future movies found releasing within {future_days_upcoming_movies} days.{RESET}")
                
                if released_movies:
                    print(f"\n{GREEN}Found {len(released_movies)} released movies not yet available:{RESET}")
                    for movie in released_movies:
                        release_info = f" - {movie['releaseType']} Released: {movie['releaseDate']}"
                        print(f"- {movie['title']}" + (f" ({movie['year']})" if movie['year'] else "") + release_info)
                elif not future_only:
                    print(f"{ORANGE}No released movies found that are not yet available.{RESET}")
                
                # Process movie content based on method
                all_movies_to_process = future_movies + released_movies
                if all_movies_to_process:
                    print(f"\n{BLUE}Processing content for movies...{RESET}")
                    successful = 0
                    failed = 0
                    fallback_used = 0
                    
                    for movie in all_movies_to_process:
                        print(f"\nProcessing: {movie['title']}")
                        
                        # Check if content already exists
                        movie_path = movie.get('path')
                        if movie_path:
                            movie_title = movie.get('title', 'Unknown')
                            movie_year = movie.get('year', '')
                            folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")
                            
                            if umtk_root_movies:
                                coming_soon_path = Path(umtk_root_movies) / folder_name
                            else:
                                base_path = Path(movie_path)
                                parent_dir = base_path.parent
                                coming_soon_path = parent_dir / folder_name
                            
                            # Check if actual video file exists with the Coming Soon edition tag
                            if coming_soon_path.exists():
                                existing_files = list(coming_soon_path.glob("*{edition-Coming Soon}.*"))
                                if existing_files:
                                    existing_file = existing_files[0]
                                    print(f"{GREEN}Content already exists for {movie['title']}: {existing_file.name} - skipping{RESET}")
                                    successful += 1
                                    all_movies_with_content.append(movie)
                                    continue
                        
                        # Process based on method
                        success = False
                        
                        if movie_method == 1:  # Trailer
                            trailer_info = search_trailer_on_youtube(
                                movie['title'], 
                                movie.get('year'), 
                                movie.get('imdbId'),
                                debug,
                                skip_channels
                            )
                            
                            if trailer_info:
                                print(f"Found trailer: {trailer_info['video_title']} ({trailer_info['duration']}) by {trailer_info['uploader']}")
                                success = download_trailer_movie(movie, trailer_info, debug, umtk_root_movies, is_trending=False)
                            else:
                                print(f"{ORANGE}No suitable trailer found for {movie['title']}{RESET}")
                            
                            # If trailer method failed and fallback is enabled, try placeholder
                            if not success and method_fallback:
                                print(f"{ORANGE}Trailer method failed, attempting fallback to placeholder method...{RESET}")
                                success = create_placeholder_movie(movie, debug, umtk_root_movies, is_trending=False)
                                if success:
                                    fallback_used += 1
                                    print(f"{GREEN}Fallback to placeholder successful for {movie['title']}{RESET}")
                        
                        elif movie_method == 2:  # Placeholder
                            success = create_placeholder_movie(movie, debug, umtk_root_movies, is_trending=False)
                        
                        if success:
                            successful += 1
                            all_movies_with_content.append(movie)
                        else:
                            failed += 1
                    
                    print(f"\n{GREEN}Movie content processing summary:{RESET}")
                    print(f"Successful: {successful}")
                    if fallback_used > 0:
                        print(f"Fallback used: {fallback_used}")
                    print(f"Failed: {failed}")
            
            # Process Trending Movies
            if trending_movies_method > 0:
                print(f"\n{BLUE}{'=' * 50}{RESET}")
                print(f"{BLUE}Processing Trending Movies...{RESET}")
                print(f"{BLUE}{'=' * 50}{RESET}\n")
                
                mdblist_api_key = config.get('mdblist_api_key')
                mdblist_movies_url = config.get('mdblist_movies')
                mdblist_movies_limit = config.get('mdblist_movies_limit', 10)
                
                if not mdblist_api_key:
                    print(f"{RED}Error: mdblist_api_key not configured{RESET}")
                elif not mdblist_movies_url:
                    print(f"{RED}Error: mdblist_movies not configured{RESET}")
                else:
                    print(f"MDBList Movies URL: {mdblist_movies_url}")
                    print(f"MDBList Movies Limit: {mdblist_movies_limit}")
                    print()
                    
                    # Fetch trending movies from MDBList
                    print(f"{BLUE}Fetching trending movies from MDBList...{RESET}")
                    mdblist_movies_items = fetch_mdblist_items(mdblist_movies_url, mdblist_api_key, mdblist_movies_limit, debug)
                    
                    if mdblist_movies_items:
                        print(f"{GREEN}Fetched {len(mdblist_movies_items)} trending movies from MDBList{RESET}")
                        
                        # Process trending movies
                        trending_movies_monitored, trending_movies_request_needed = process_trending_movies(
                            mdblist_movies_items, all_movies, radarr_url, radarr_api_key, debug
                        )
                        
                        if trending_movies_monitored:
                            print(f"\n{GREEN}Found {len(trending_movies_monitored)} trending movies that are monitored but not available:{RESET}")
                            for movie in trending_movies_monitored:
                                print(f"- {movie['title']}" + (f" ({movie['year']})" if movie['year'] else ""))
                        else:
                            print(f"{ORANGE}No trending movies found that are monitored but not available.{RESET}")
                        
                        if trending_movies_request_needed:
                            print(f"\n{GREEN}Found {len(trending_movies_request_needed)} trending movies that need to be requested:{RESET}")
                            for movie in trending_movies_request_needed:
                                print(f"- {movie['title']}" + (f" ({movie['year']})" if movie['year'] else ""))
                        else:
                            print(f"{ORANGE}No trending movies found that need to be requested.{RESET}")
                        
                        # Process trending movie content
                        all_trending_movies = trending_movies_monitored + trending_movies_request_needed
                        if all_trending_movies:
                            print(f"\n{BLUE}Processing content for trending movies...{RESET}")
                            successful = 0
                            failed = 0
                            skipped_existing = 0
                            fallback_used = 0
                            
                            for movie in all_trending_movies:
                                print(f"\nProcessing: {movie['title']}")
                                
                                # Determine if this is a request needed movie
                                is_request_needed = movie in trending_movies_request_needed
                                
                                # Check if content already exists
                                movie_path = movie.get('path')
                                content_exists = False
                                
                                if movie_path or umtk_root_movies:
                                    movie_title = movie.get('title', 'Unknown')
                                    movie_year = movie.get('year', '')
                                    
                                    # Check for Trending edition
                                    edition_tag = "Trending" if is_request_needed else "Coming Soon"
                                    folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-{edition_tag}}}")
                                    
                                    if umtk_root_movies:
                                        target_path = Path(umtk_root_movies) / folder_name
                                    elif movie_path:
                                        base_path = Path(movie_path)
                                        parent_dir = base_path.parent
                                        target_path = parent_dir / folder_name
                                    else:
                                        target_path = None
                                    
                                    if target_path and target_path.exists():
                                        existing_files = list(target_path.glob(f"*{{edition-{edition_tag}}}.*"))
                                        if existing_files:
                                            existing_file = existing_files[0]
                                            print(f"{GREEN}Content already exists for {movie['title']}: {existing_file.name} - skipping{RESET}")
                                            skipped_existing += 1
                                            successful += 1
                                            all_movies_with_content.append(movie)
                                            content_exists = True
                                
                                if content_exists:
                                    continue
                                
                                # Process based on method
                                success = False
                                
                                if trending_movies_method == 1:  # Trailer
                                    trailer_info = search_trailer_on_youtube(
                                        movie['title'], 
                                        movie.get('year'), 
                                        movie.get('imdbId'),
                                        debug,
                                        skip_channels
                                    )
                                    
                                    if trailer_info:
                                        print(f"Found trailer: {trailer_info['video_title']} ({trailer_info['duration']}) by {trailer_info['uploader']}")
                                        success = download_trailer_movie(movie, trailer_info, debug, umtk_root_movies, is_trending=is_request_needed)
                                    else:
                                        print(f"{ORANGE}No suitable trailer found for {movie['title']}{RESET}")
                                    
                                    # If trailer method failed and fallback is enabled, try placeholder
                                    if not success and method_fallback:
                                        print(f"{ORANGE}Trailer method failed, attempting fallback to placeholder method...{RESET}")
                                        success = create_placeholder_movie(movie, debug, umtk_root_movies, is_trending=is_request_needed)
                                        if success:
                                            fallback_used += 1
                                            print(f"{GREEN}Fallback to placeholder successful for {movie['title']}{RESET}")
                                
                                elif trending_movies_method == 2:  # Placeholder
                                    success = create_placeholder_movie(movie, debug, umtk_root_movies, is_trending=is_request_needed)
                                
                                if success:
                                    successful += 1
                                    all_movies_with_content.append(movie)
                                else:
                                    failed += 1
                            
                            print(f"\n{GREEN}Trending movie content processing summary:{RESET}")
                            print(f"Successful: {successful}")
                            print(f"Skipped (already exist): {skipped_existing}")
                            if fallback_used > 0:
                                print(f"Fallback used: {fallback_used}")
                            print(f"Failed: {failed}")
                    else:
                        print(f"{ORANGE}No trending movies fetched from MDBList{RESET}")
            
            # Cleanup movie content (after processing both regular and trending)
            if cleanup:
                print(f"\n{BLUE}Checking for movie content to cleanup...{RESET}")
                cleanup_movie_content(
                    all_movies, radarr_url, radarr_api_key, future_movies, released_movies,
                    trending_movies_monitored, trending_movies_request_needed,
                    movie_method, debug, exclude_radarr_tag_ids, umtk_root_movies
                )
            
            # Create Movie YAML files (create if either movie_method or trending_movies_method is enabled)
            if movie_method > 0 or trending_movies_method > 0:
                overlay_file = kometa_folder / "UMTK_MOVIES_UPCOMING_OVERLAYS.yml"
                collection_file = kometa_folder / "UMTK_MOVIES_UPCOMING_COLLECTION.yml"
                
                create_overlay_yaml_movies(
                    str(overlay_file), future_movies, released_movies,
                    trending_movies_monitored if trending_movies_method > 0 else [],
                    trending_movies_request_needed if trending_movies_method > 0 else [],
                    {"backdrop_future": config.get("backdrop_upcoming_movies_future", {}),
                     "text_future": config.get("text_upcoming_movies_future", {}),
                     "backdrop_released": config.get("backdrop_upcoming_movies_released", {}),
                     "text_released": config.get("text_upcoming_movies_released", {}),
                     "backdrop_trending_request_needed": config.get("backdrop_trending_movies_request_needed", {}),
                     "text_trending_request_needed": config.get("text_trending_movies_request_needed", {})},
                    config,
                    localization  
                )
                
                create_collection_yaml_movies(str(collection_file), future_movies, released_movies, config)
                
                print(f"\n{GREEN}Movie YAML files created successfully{RESET}")
            
            # Create Trending Movies collection YAML
            if trending_movies_method > 0:
                if mdblist_movies_items:
                    # Pass the raw MDBList items for the collection
                    trending_collection_file = kometa_folder / "UMTK_MOVIES_TRENDING_COLLECTION.yml"
                    create_trending_collection_yaml_movies(str(trending_collection_file), mdblist_movies_items, config, trending_movies_request_needed)
                    print(f"{GREEN}Trending Movies collection YAML created successfully{RESET}")
            
                    # Create Top 10 Movies overlay YAML
                    top10_movies_overlay_file = kometa_folder / "UMTK_MOVIES_TOP10_OVERLAYS.yml"
                    create_top10_overlay_yaml_movies(
                        str(top10_movies_overlay_file), 
                        mdblist_movies_items,
                        {"backdrop": config.get("backdrop_trending_top_10_movies", {}),
                         "text": config.get("text_trending_top_10_movies", {})},
                        limit=mdblist_movies_limit
                    )
                    print(f"{GREEN}Top 10 Movies overlay YAML created successfully{RESET}")
        
        # ============================================================
        # PLEX METADATA UPDATES - MOVED TO END
        # ============================================================
        
        # Update Plex TV metadata directly - only if TV processing succeeded
        if process_tv and not tv_processing_failed and plex_url and plex_token and tv_libraries:
            print(f"\n{BLUE}{'=' * 50}{RESET}")
            print(f"{BLUE}Updating TV metadata in Plex...{RESET}")
            print(f"{BLUE}{'=' * 50}{RESET}\n")
            update_plex_tv_metadata(
                plex_url, plex_token, tv_libraries,
                all_shows_with_content,
                mdblist_tv_items if trending_tv_method > 0 else None,
                config, debug, 0, metadata_retry_limit
            )
        elif tv_processing_failed and process_tv:
            print(f"{ORANGE}Skipping Plex TV metadata updates due to earlier Sonarr connection failure{RESET}")
        elif debug and process_tv:
            print(f"{ORANGE}[DEBUG] Plex TV metadata updates skipped - missing plex_url, plex_token, or tv_libraries{RESET}")
        
        # Update Plex movie metadata directly (moved to end)
        if process_movies and plex_url and plex_token and movie_libraries:
            print(f"\n{BLUE}{'=' * 50}{RESET}")
            print(f"{BLUE}Updating movie metadata in Plex...{RESET}")
            print(f"{BLUE}{'=' * 50}{RESET}\n")
            update_plex_movie_metadata(
                plex_url, plex_token, movie_libraries,
                all_movies_with_content,
                mdblist_movies_items if trending_movies_method > 0 else None,
                config, debug, 0, metadata_retry_limit
            )
        elif debug and process_movies:
            print(f"{ORANGE}[DEBUG] Plex movie metadata updates skipped - missing plex_url, plex_token, or movie_libraries{RESET}")
        
        # Calculate and display runtime
        end_time = datetime.now()
        runtime = end_time - start_time
        hours, remainder = divmod(runtime.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        runtime_formatted = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        
        print(f"\n{GREEN}All processing complete!{RESET}")
        print(f"Total runtime: {runtime_formatted}")
        
    except ConnectionError as e:
        print(f"{RED}Error: {str(e)}{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}Unexpected error: {str(e)}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()