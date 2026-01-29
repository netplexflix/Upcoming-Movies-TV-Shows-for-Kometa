"""
Content finder functions for UMTK - identifies shows and movies to process
"""

import requests
from datetime import datetime, timedelta, timezone

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .utils import convert_utc_to_local
from .sonarr import get_sonarr_episodes


def find_upcoming_shows(all_series, sonarr_url, api_key, future_days_upcoming_shows, 
                        utc_offset=0, debug=False, exclude_tags=None, future_only_tv=False):
    """Find shows with upcoming episodes that have their first episode airing within specified days"""
    future_shows = []
    aired_shows = []
    
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_upcoming_shows)
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    
    if debug:
        print(f"{BLUE}[DEBUG] Cutoff date: {cutoff_date}, Now local: {now_local}{RESET}")
        print(f"{BLUE}[DEBUG] Future only TV: {future_only_tv}{RESET}")
        print(f"{BLUE}[DEBUG] Found {len(all_series)} total series in Sonarr{RESET}")
   
    for series in all_series:
        if debug:
            print(f"{BLUE}[DEBUG] Processing show: {series['title']} (status: {series.get('status')}, monitored: {series.get('monitored', True)}){RESET}")
        
        # Always skip unmonitored shows
        if not series.get('monitored', True):
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping unmonitored show: {series['title']}{RESET}")
            continue
        
        # Check for excluded tags
        if exclude_tags:
            series_tags = series.get('tags', [])
            if any(tag in series_tags for tag in exclude_tags):
                if debug:
                    print(f"{ORANGE}[DEBUG] Skipping show with excluded tags: {series['title']}{RESET}")
                continue
        
        try:
            episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        except requests.exceptions.RequestException:
            raise
        
        if debug:
            print(f"{BLUE}[DEBUG] Found {len(episodes)} episodes for {series['title']}{RESET}")
        
        # Find S01E01 specifically
        first_episode = None
        
        for ep in episodes:
            if ep.get('seasonNumber') == 1 and ep.get('episodeNumber') == 1:
                first_episode = ep
                break
        
        if not first_episode:
            if debug:
                print(f"{ORANGE}[DEBUG] No Season 1 Episode 1 found for {series['title']}{RESET}")
            continue
        
        # Skip if S01E01 is not monitored
        if not first_episode.get('monitored', False):
            if debug:
                print(f"{ORANGE}[DEBUG] S01E01 not monitored for {series['title']}{RESET}")
            continue
        
        # Skip if S01E01 is already downloaded
        if first_episode.get('hasFile', False):
            if debug:
                print(f"{ORANGE}[DEBUG] S01E01 already downloaded for {series['title']} - skipping{RESET}")
            continue
        
        air_date_str = first_episode.get('airDateUtc')
        if not air_date_str:
            if debug:
                print(f"{ORANGE}[DEBUG] No air date found for {series['title']} S01E01{RESET}")
            continue
        
        air_date = convert_utc_to_local(air_date_str, utc_offset)
        
        if debug:
            print(f"{BLUE}[DEBUG] {series['title']} air date: {air_date}, within range: {air_date <= cutoff_date}{RESET}")
        
        # Check if air date is within our range
        if air_date <= cutoff_date:
            tvdb_id = series.get('tvdbId')
            air_date_str_yyyy_mm_dd = air_date.date().isoformat()
            
            show_dict = {
                'title': series['title'],
                'tvdbId': tvdb_id,
                'path': series.get('path', ''),
                'imdbId': series.get('imdbId', ''),
                'year': series.get('year', None),
                'airDate': air_date_str_yyyy_mm_dd
            }
            
            # Categorize based on whether it has aired or not
            if air_date >= now_local:
                future_shows.append(show_dict)
                if debug:
                    print(f"{GREEN}[DEBUG] Added to future shows: {series['title']}{RESET}")
            elif not future_only_tv:  # Only add aired shows if future_only_tv is false
                aired_shows.append(show_dict)
                if debug:
                    print(f"{GREEN}[DEBUG] Added to aired shows: {series['title']}{RESET}")
            elif debug:
                print(f"{ORANGE}[DEBUG] Skipping aired show due to future_only_tv=True: {series['title']}{RESET}")
    
    return future_shows, aired_shows


def find_new_shows(all_series, sonarr_url, api_key, recent_days_new_show, utc_offset=0, debug=False):
    """Find shows where S01E01 has been downloaded and aired within specified past days"""
    new_shows = []
    
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    cutoff_date = now_local - timedelta(days=recent_days_new_show)
    
    if debug:
        print(f"{BLUE}[DEBUG] Looking for shows with S01E01 aired between {cutoff_date} and {now_local}{RESET}")
        print(f"{BLUE}[DEBUG] Found {len(all_series)} total series in Sonarr{RESET}")
    
    for series in all_series:
        if debug:
            print(f"{BLUE}[DEBUG] Checking series: {series['title']} (monitored: {series.get('monitored', True)}){RESET}")
        
        # Always skip unmonitored shows
        if not series.get('monitored', True):
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping unmonitored show: {series['title']}{RESET}")
            continue
        
        try:
            episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        except requests.exceptions.RequestException:
            raise
        
        s01e01 = None
        for ep in episodes:
            if ep.get('seasonNumber') == 1 and ep.get('episodeNumber') == 1:
                s01e01 = ep
                break
        
        if not s01e01:
            if debug:
                print(f"{ORANGE}[DEBUG] No S01E01 found for {series['title']}{RESET}")
            continue
        
        if not s01e01.get('hasFile', False):
            if debug:
                print(f"{ORANGE}[DEBUG] S01E01 not downloaded for {series['title']}{RESET}")
            continue
        
        air_date_str = s01e01.get('airDateUtc')
        if not air_date_str:
            if debug:
                print(f"{ORANGE}[DEBUG] No air date for {series['title']} S01E01{RESET}")
            continue
        
        air_date = convert_utc_to_local(air_date_str, utc_offset)
        
        if debug:
            print(f"{BLUE}[DEBUG] {series['title']} S01E01 aired: {air_date}, within range: {cutoff_date <= air_date <= now_local}{RESET}")
        
        if cutoff_date <= air_date <= now_local:
            tvdb_id = series.get('tvdbId')
            air_date_str_yyyy_mm_dd = air_date.date().isoformat()
            
            show_dict = {
                'title': series['title'],
                'tvdbId': tvdb_id,
                'path': series.get('path', ''),
                'imdbId': series.get('imdbId', ''),
                'year': series.get('year', None),
                'airDate': air_date_str_yyyy_mm_dd
            }
            
            new_shows.append(show_dict)
            
            if debug:
                print(f"{GREEN}[DEBUG] Added to new shows: {series['title']}{RESET}")
    
    return new_shows


def find_upcoming_movies(all_movies, radarr_url, api_key, future_days_upcoming_movies, 
                         utc_offset=0, future_only=False, include_inCinemas=False, 
                         debug=False, exclude_tags=None, past_days_upcoming_movies=0):
    """Find movies that are monitored and meet release date criteria"""
    future_movies = []
    released_movies = []
    
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_upcoming_movies)
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    
    # Calculate past cutoff date if past_days_upcoming_movies is set
    past_cutoff_date = None
    if past_days_upcoming_movies > 0 and not future_only:
        past_cutoff_date = now_local - timedelta(days=past_days_upcoming_movies)
    
    if debug:
        print(f"{BLUE}[DEBUG] Cutoff date: {cutoff_date}, Now local: {now_local}{RESET}")
        print(f"{BLUE}[DEBUG] Future only mode: {future_only}{RESET}")
        print(f"{BLUE}[DEBUG] Include inCinemas: {include_inCinemas}{RESET}")
        if past_cutoff_date:
            print(f"{BLUE}[DEBUG] Past cutoff date: {past_cutoff_date} (past_days_upcoming_movies: {past_days_upcoming_movies}){RESET}")
        print(f"{BLUE}[DEBUG] Found {len(all_movies)} total movies in Radarr{RESET}")
    
    for movie in all_movies:
        if not movie.get('monitored', False):
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping unmonitored movie: {movie['title']}{RESET}")
            continue
        
        if movie.get('hasFile', False):
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping downloaded movie: {movie['title']}{RESET}")
            continue
        
        # Check for excluded tags
        if exclude_tags:
            movie_tags = movie.get('tags', [])
            if any(tag in movie_tags for tag in exclude_tags):
                if debug:
                    print(f"{ORANGE}[DEBUG] Skipping movie with excluded tags: {movie['title']}{RESET}")
                continue
        
        release_date_str = None
        release_type = None
        
        if include_inCinemas:
            dates_to_check = [
                (movie.get('digitalRelease'), 'Digital'),
                (movie.get('physicalRelease'), 'Physical'),
                (movie.get('inCinemas'), 'Cinema')
            ]
            
            valid_dates = [(date_str, rel_type) for date_str, rel_type in dates_to_check if date_str]
            
            if valid_dates:
                valid_dates.sort(key=lambda x: x[0])
                release_date_str, release_type = valid_dates[0]
        else:
            if movie.get('digitalRelease'):
                release_date_str = movie['digitalRelease']
                release_type = 'Digital'
            elif movie.get('physicalRelease'):
                release_date_str = movie['physicalRelease']
                release_type = 'Physical'
        
        if not release_date_str:
            if debug:
                print(f"{ORANGE}[DEBUG] No suitable release date found for {movie['title']}{RESET}")
            continue
        
        release_date = convert_utc_to_local(release_date_str, utc_offset)
        release_date_str_yyyy_mm_dd = release_date.date().isoformat()
        
        if debug:
            print(f"{BLUE}[DEBUG] {movie['title']} release date: {release_date} ({release_type}){RESET}")
        
        # Check if release date is too far in the past
        if past_cutoff_date and release_date < past_cutoff_date:
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping {movie['title']} - release date {release_date} is before past cutoff {past_cutoff_date}{RESET}")
            continue
        
        movie_dict = {
            'title': movie['title'],
            'tmdbId': movie.get('tmdbId'),
            'imdbId': movie.get('imdbId'),
            'path': movie.get('path', ''),
            'folderName': movie.get('folderName', ''),
            'year': movie.get('year', None),
            'releaseDate': release_date_str_yyyy_mm_dd,
            'releaseType': release_type
        }
        
        if release_date >= now_local and release_date <= cutoff_date:
            future_movies.append(movie_dict)
            if debug:
                print(f"{GREEN}[DEBUG] Added to future movies: {movie['title']}{RESET}")
        elif release_date < now_local and not future_only:
            released_movies.append(movie_dict)
            if debug:
                print(f"{GREEN}[DEBUG] Added to released movies: {movie['title']}{RESET}")
    
    return future_movies, released_movies


def process_trending_tv(mdblist_items, all_series, sonarr_url, api_key, debug=False):
    """
    Process trending TV shows from MDBList
    Returns: (monitored_not_available, not_found_or_unmonitored)
    """
    monitored_not_available = []
    not_found_or_unmonitored = []
    
    if debug:
        print(f"{BLUE}[DEBUG] Processing {len(mdblist_items)} trending TV shows{RESET}")
    
    # Create lookup dictionaries for Sonarr series
    sonarr_by_tvdb = {}
    sonarr_by_imdb = {}
    sonarr_by_tmdb = {}
    
    for series in all_series:
        if series.get('tvdbId'):
            sonarr_by_tvdb[str(series['tvdbId'])] = series
        if series.get('imdbId'):
            sonarr_by_imdb[series['imdbId']] = series
        if series.get('tmdbId'):
            sonarr_by_tmdb[str(series['tmdbId'])] = series
    
    for item in mdblist_items:
        tvdb_id = str(item.get('tvdb_id', '')) if item.get('tvdb_id') else None
        tmdb_id = str(item.get('tmdb_id', '')) if item.get('tmdb_id') else None
        imdb_id = item.get('imdb_id', '')
        title = item.get('title', 'Unknown')
        year = item.get('year')
        rank = item.get('rank')
        
        if debug:
            print(f"{BLUE}[DEBUG] Processing trending show: {title} ({year}) - TVDB: {tvdb_id}, TMDB: {tmdb_id}, IMDB: {imdb_id}, Rank: {rank}{RESET}")
        
        # Try to find in Sonarr
        sonarr_series = None
        if tvdb_id and tvdb_id in sonarr_by_tvdb:
            sonarr_series = sonarr_by_tvdb[tvdb_id]
        elif tmdb_id and tmdb_id in sonarr_by_tmdb:
            sonarr_series = sonarr_by_tmdb[tmdb_id]
        elif imdb_id and imdb_id in sonarr_by_imdb:
            sonarr_series = sonarr_by_imdb[imdb_id]
        
        if sonarr_series:
            if debug:
                print(f"{BLUE}[DEBUG] Found in Sonarr: {sonarr_series['title']}{RESET}")
            
            try:
                episodes = get_sonarr_episodes(sonarr_url, api_key, sonarr_series['id'])
            except requests.exceptions.RequestException:
                raise
            
            has_downloaded_episodes = any(ep.get('hasFile', False) for ep in episodes)
            
            if has_downloaded_episodes:
                if debug:
                    print(f"{BLUE}[DEBUG] Has downloaded episodes, skipping completely{RESET}")
                continue
            
            if not sonarr_series.get('monitored', False):
                if debug:
                    print(f"{BLUE}[DEBUG] Not monitored and no downloads - adding to not_found_or_unmonitored{RESET}")
                
                show_dict = {
                    'title': sonarr_series['title'],
                    'tvdbId': sonarr_series.get('tvdbId'),
                    'tmdbId': sonarr_series.get('tmdbId'),
                    'path': sonarr_series.get('path', ''),
                    'imdbId': sonarr_series.get('imdbId', ''),
                    'year': sonarr_series.get('year', None),
                    'airDate': None,
                    'rank': rank
                }
                not_found_or_unmonitored.append(show_dict)
                continue
            
            has_monitored_episodes = any(ep.get('monitored', False) for ep in episodes)
            
            if not has_monitored_episodes:
                if debug:
                    print(f"{BLUE}[DEBUG] Show is monitored but no episodes are monitored - adding to not_found_or_unmonitored{RESET}")
                
                show_dict = {
                    'title': sonarr_series['title'],
                    'tvdbId': sonarr_series.get('tvdbId'),
                    'tmdbId': sonarr_series.get('tmdbId'),
                    'path': sonarr_series.get('path', ''),
                    'imdbId': sonarr_series.get('imdbId', ''),
                    'year': sonarr_series.get('year', None),
                    'airDate': None,
                    'rank': rank
                }
                not_found_or_unmonitored.append(show_dict)
                continue
            
            if debug:
                print(f"{BLUE}[DEBUG] Monitored with monitored episodes but no downloads - adding to monitored_not_available{RESET}")
            
            show_dict = {
                'title': sonarr_series['title'],
                'tvdbId': sonarr_series.get('tvdbId'),
                'tmdbId': sonarr_series.get('tmdbId'),
                'path': sonarr_series.get('path', ''),
                'imdbId': sonarr_series.get('imdbId', ''),
                'year': sonarr_series.get('year', None),
                'airDate': None,
                'rank': rank
            }
            monitored_not_available.append(show_dict)
        else:
            if debug:
                print(f"{BLUE}[DEBUG] Not found in Sonarr - adding to not_found_or_unmonitored{RESET}")
            
            show_dict = {
                'title': title,
                'tvdbId': int(tvdb_id) if tvdb_id and tvdb_id.isdigit() else None,
                'tmdbId': int(tmdb_id) if tmdb_id and tmdb_id.isdigit() else None,
                'path': None,
                'imdbId': imdb_id,
                'year': year,
                'airDate': None,
                'rank': rank
            }
            not_found_or_unmonitored.append(show_dict)
    
    return monitored_not_available, not_found_or_unmonitored


def process_trending_movies(mdblist_items, all_movies, radarr_url, api_key, debug=False):
    """
    Process trending movies from MDBList
    Returns: (monitored_not_available, not_found_or_unmonitored)
    """
    monitored_not_available = []
    not_found_or_unmonitored = []
    
    if debug:
        print(f"{BLUE}[DEBUG] Processing {len(mdblist_items)} trending movies{RESET}")
    
    # Create lookup dictionaries for Radarr movies
    radarr_by_tmdb = {}
    radarr_by_imdb = {}
    
    for movie in all_movies:
        if movie.get('tmdbId'):
            radarr_by_tmdb[str(movie['tmdbId'])] = movie
        if movie.get('imdbId'):
            radarr_by_imdb[movie['imdbId']] = movie
    
    for item in mdblist_items:
        tmdb_id = str(item.get('tmdb_id', ''))
        imdb_id = item.get('imdb_id', '')
        title = item.get('title', 'Unknown')
        year = item.get('year')
        rank = item.get('rank')
        
        if debug:
            print(f"{BLUE}[DEBUG] Processing trending movie: {title} ({year}) - TMDB: {tmdb_id}, IMDB: {imdb_id}, Rank: {rank}{RESET}")
        
        # Try to find in Radarr
        radarr_movie = None
        if tmdb_id and tmdb_id in radarr_by_tmdb:
            radarr_movie = radarr_by_tmdb[tmdb_id]
        elif imdb_id and imdb_id in radarr_by_imdb:
            radarr_movie = radarr_by_imdb[imdb_id]
        
        if radarr_movie:
            if debug:
                print(f"{BLUE}[DEBUG] Found in Radarr: {radarr_movie['title']}{RESET}")
            
            if radarr_movie.get('hasFile', False):
                if debug:
                    print(f"{BLUE}[DEBUG] Already downloaded, skipping completely{RESET}")
                continue
            
            if radarr_movie.get('monitored', False):
                if debug:
                    print(f"{BLUE}[DEBUG] Monitored but not available - adding to monitored_not_available{RESET}")
                
                movie_dict = {
                    'title': radarr_movie['title'],
                    'tmdbId': radarr_movie.get('tmdbId'),
                    'imdbId': radarr_movie.get('imdbId'),
                    'path': radarr_movie.get('path', ''),
                    'folderName': radarr_movie.get('folderName', ''),
                    'year': radarr_movie.get('year', None),
                    'releaseDate': None,
                    'releaseType': 'Trending',
                    'rank': rank
                }
                monitored_not_available.append(movie_dict)
            else:
                if debug:
                    print(f"{BLUE}[DEBUG] Not monitored and not downloaded - adding to not_found_or_unmonitored{RESET}")
                
                movie_dict = {
                    'title': radarr_movie['title'],
                    'tmdbId': radarr_movie.get('tmdbId'),
                    'imdbId': radarr_movie.get('imdbId'),
                    'path': radarr_movie.get('path', ''),
                    'folderName': radarr_movie.get('folderName', ''),
                    'year': radarr_movie.get('year', None),
                    'releaseDate': None,
                    'releaseType': 'Trending',
                    'rank': rank
                }
                not_found_or_unmonitored.append(movie_dict)
        else:
            if debug:
                print(f"{BLUE}[DEBUG] Not found in Radarr - adding to not_found_or_unmonitored{RESET}")
            
            movie_dict = {
                'title': title,
                'tmdbId': int(tmdb_id) if tmdb_id and tmdb_id.isdigit() else None,
                'imdbId': imdb_id,
                'path': None,
                'folderName': None,
                'year': year,
                'releaseDate': None,
                'releaseType': 'Trending',
                'rank': rank
            }
            not_found_or_unmonitored.append(movie_dict)
    
    return monitored_not_available, not_found_or_unmonitored