"""Show finding functions for TSSK"""

from datetime import datetime, timedelta, timezone
from collections import defaultdict

from .utils import convert_utc_to_local
from .sonarr import get_sonarr_episodes, has_ignore_finale_tag


def find_new_season_shows(sonarr_url, api_key, all_series, tag_mapping, future_days_new_season, utc_offset=0, skip_unmonitored=False):
    """Find shows with a new season starting within the specified days"""
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_new_season)
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    matched_shows = []
    skipped_shows = []
    
    for series in all_series:
        episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        
        future_episodes = []
        for ep in episodes:
            # Skip specials (season 0)
            season_number = ep.get('seasonNumber', 0)
            if season_number == 0:
                continue
                
            air_date_str = ep.get('airDateUtc')
            if not air_date_str:
                continue
            
            air_date = convert_utc_to_local(air_date_str, utc_offset)
            
            # Skip episodes that have already been downloaded - they should be treated as if they've aired
            if ep.get('hasFile', False):
                continue
                
            if air_date > now_local:
                future_episodes.append((ep, air_date))
        
        future_episodes.sort(key=lambda x: x[1])
        
        if not future_episodes:
            continue
        
        next_future, air_date_next = future_episodes[0]
        
        # Check if this is a new season starting (episode 1 of any season)
        # AND check that it's not a completely new show (season 1)
        if (
            next_future['seasonNumber'] > 1
            and next_future['episodeNumber'] == 1
            and not next_future['hasFile']
            and air_date_next <= cutoff_date
        ):
            tvdb_id = series.get('tvdbId')
            air_date_str_yyyy_mm_dd = air_date_next.date().isoformat()

            show_dict = {
                'title': series['title'],
                'seasonNumber': next_future['seasonNumber'],
                'airDate': air_date_str_yyyy_mm_dd,
                'tvdbId': tvdb_id
            }
            
            if skip_unmonitored:
                episode_monitored = next_future.get("monitored", True)
                
                season_monitored = True
                for season_info in series.get("seasons", []):
                    if season_info.get("seasonNumber") == next_future['seasonNumber']:
                        season_monitored = season_info.get("monitored", True)
                        break
                
                if not episode_monitored or not season_monitored:
                    skipped_shows.append(show_dict)
                    continue
            
            matched_shows.append(show_dict)
        # If it's a completely new show (Season 1), add it to skipped shows for reporting
        elif (
            next_future['seasonNumber'] == 1
            and next_future['episodeNumber'] == 1
            and not next_future['hasFile']
            and air_date_next <= cutoff_date
        ):
            tvdb_id = series.get('tvdbId')
            air_date_str_yyyy_mm_dd = air_date_next.date().isoformat()

            show_dict = {
                'title': series['title'],
                'seasonNumber': next_future['seasonNumber'],
                'airDate': air_date_str_yyyy_mm_dd,
                'tvdbId': tvdb_id,
                'reason': "New show (Season 1)"  # Add reason for skipping
            }
            
            skipped_shows.append(show_dict)
    
    return matched_shows, skipped_shows


def find_upcoming_regular_episodes(sonarr_url, api_key, all_series, future_days_upcoming_episode, utc_offset=0, skip_unmonitored=False, ignore_finales_tags=None, tag_mapping=None):
    """Find shows with upcoming non-premiere, non-finale episodes within the specified days"""
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_upcoming_episode)
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    matched_shows = []
    skipped_shows = []
    
    for series in all_series:
        episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        
        # Check if this series should ignore finale detection
        should_ignore_finales = has_ignore_finale_tag(series, ignore_finales_tags, tag_mapping)
        
        # Group episodes by season
        seasons = defaultdict(list)
        for ep in episodes:
            if ep.get('seasonNumber') > 0:  # Skip specials
                seasons[ep.get('seasonNumber')].append(ep)
        
        # For each season, find the max episode number to identify finales
        season_finales = {}
        if not should_ignore_finales:
            for season_num, season_eps in seasons.items():
                if season_eps:
                    max_ep = max(ep.get('episodeNumber', 0) for ep in season_eps)
                    season_finales[season_num] = max_ep
        
        future_episodes = []
        for ep in episodes:
            # Skip specials (season 0)
            season_number = ep.get('seasonNumber', 0)
            if season_number == 0:
                continue
                
            air_date_str = ep.get('airDateUtc')
            if not air_date_str:
                continue
            
            air_date = convert_utc_to_local(air_date_str, utc_offset)
            
            # Skip episodes that have already been downloaded - they should be treated as if they've aired
            if ep.get('hasFile', False):
                continue
                
            if air_date > now_local and air_date <= cutoff_date:
                future_episodes.append((ep, air_date))
        
        future_episodes.sort(key=lambda x: x[1])
        
        if not future_episodes:
            continue
        
        next_future, air_date = future_episodes[0]
        season_num = next_future.get('seasonNumber')
        episode_num = next_future.get('episodeNumber')
        
        # Skip season premieres (episode 1 of any season)
        if episode_num == 1:
            continue
            
        # Skip season finales (only if not ignoring finales)
        if not should_ignore_finales:
            is_episode_finale = season_num in season_finales and episode_num == season_finales[season_num]
            if is_episode_finale:
                continue
        
        tvdb_id = series.get('tvdbId')
        air_date_str_yyyy_mm_dd = air_date.date().isoformat()

        show_dict = {
            'title': series['title'],
            'seasonNumber': season_num,
            'episodeNumber': episode_num,
            'airDate': air_date_str_yyyy_mm_dd,
            'tvdbId': tvdb_id
        }
        
        if skip_unmonitored:
            episode_monitored = next_future.get("monitored", True)
            
            season_monitored = True
            for season_info in series.get("seasons", []):
                if season_info.get("seasonNumber") == season_num:
                    season_monitored = season_info.get("monitored", True)
                    break
            
            if not episode_monitored or not season_monitored:
                skipped_shows.append(show_dict)
                continue
        
        matched_shows.append(show_dict)
    
    return matched_shows, skipped_shows


def find_upcoming_finales(sonarr_url, api_key, all_series, future_days_upcoming_finale, utc_offset=0, skip_unmonitored=False, ignore_finales_tags=None, tag_mapping=None):
    """Find shows with upcoming season finales within the specified days"""
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_upcoming_finale)
    matched_shows = []
    skipped_shows = []
    
    for series in all_series:
        # Skip shows with ignore finale tags
        if has_ignore_finale_tag(series, ignore_finales_tags, tag_mapping):
            continue
            
        episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        
        # Group episodes by season
        seasons = defaultdict(list)
        for ep in episodes:
            if ep.get('seasonNumber') > 0:  # Skip specials
                seasons[ep.get('seasonNumber')].append(ep)
        
        # For each season, find the max episode number to identify finales
        season_finales = {}
        for season_num, season_eps in seasons.items():
            if season_eps:
                max_ep = max(ep.get('episodeNumber', 0) for ep in season_eps)
                # Only consider it a finale if it's not episode 1
                if max_ep > 1:
                    season_finales[season_num] = max_ep
        
        future_episodes = []
        for ep in episodes:
            # Skip specials (season 0)
            season_number = ep.get('seasonNumber', 0)
            if season_number == 0:
                continue
                
            air_date_str = ep.get('airDateUtc')
            if not air_date_str:
                continue
            
            air_date = convert_utc_to_local(air_date_str, utc_offset)
            
            now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
            
            # Skip episodes that have already been downloaded - they'll be handled by recent_season_finales
            if ep.get('hasFile', False):
                continue
                
            if air_date > now_local and air_date <= cutoff_date:
                future_episodes.append((ep, air_date))
        
        future_episodes.sort(key=lambda x: x[1])
        
        if not future_episodes:
            continue
        
        next_future, air_date = future_episodes[0]
        season_num = next_future.get('seasonNumber')
        episode_num = next_future.get('episodeNumber')
        
        # Only include season finales and ensure episode number is greater than 1
        is_episode_finale = season_num in season_finales and episode_num == season_finales[season_num] and episode_num > 1
        if not is_episode_finale:
            continue
        
        tvdb_id = series.get('tvdbId')
        air_date_str_yyyy_mm_dd = air_date.date().isoformat()

        show_dict = {
            'title': series['title'],
            'seasonNumber': season_num,
            'episodeNumber': episode_num,
            'airDate': air_date_str_yyyy_mm_dd,
            'tvdbId': tvdb_id
        }
        
        if skip_unmonitored:
            episode_monitored = next_future.get("monitored", True)
            
            season_monitored = True
            for season_info in series.get("seasons", []):
                if season_info.get("seasonNumber") == season_num:
                    season_monitored = season_info.get("monitored", True)
                    break
            
            if not episode_monitored or not season_monitored:
                skipped_shows.append(show_dict)
                continue
        
        matched_shows.append(show_dict)
    
    return matched_shows, skipped_shows


def find_recent_season_finales(sonarr_url, api_key, all_series, recent_days_season_finale, utc_offset=0, skip_unmonitored=False, ignore_finales_tags=None, tag_mapping=None):
    """Find shows with status 'continuing' that had a season finale air within the specified days or have a future finale that's already downloaded"""
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    cutoff_date = now_local - timedelta(days=recent_days_season_finale)
    matched_shows = []
    
    for series in all_series:
        # Only include continuing shows
        if series.get('status') not in ['continuing', 'upcoming']:
            continue
            
        # Skip shows with ignore finale tags
        if has_ignore_finale_tag(series, ignore_finales_tags, tag_mapping):
            continue
        
        # Skip unmonitored shows if requested
        if skip_unmonitored and not series.get('monitored', True):
            continue
            
        episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        
        # Group episodes by season and find downloaded episodes
        seasons = defaultdict(list)
        downloaded_episodes = defaultdict(list)
        
        for ep in episodes:
            season_number = ep.get('seasonNumber', 0)
            if season_number > 0:  # Skip specials
                seasons[season_number].append(ep)
                if ep.get('hasFile', False):
                    downloaded_episodes[season_number].append(ep)
        
        # For each season, find the max episode number to identify finales
        season_finales = {}
        for season_num, season_eps in seasons.items():
            # Only consider it a finale if there are multiple episodes in the season
            if len(season_eps) > 1:
                max_ep = max(ep.get('episodeNumber', 0) for ep in season_eps)
                season_finales[season_num] = max_ep
        
        # Look for recently aired season finales
        for season_num, max_episode_num in season_finales.items():
            # Skip if no episodes downloaded for this season
            if season_num not in downloaded_episodes:
                continue
                
            # Find the finale episode
            finale_episode = None
            for ep in downloaded_episodes[season_num]:
                if ep.get('episodeNumber') == max_episode_num:
                    finale_episode = ep
                    break
            
            if not finale_episode:
                continue
                
            # Skip if the season is unmonitored and skip_unmonitored is True
            if skip_unmonitored:
                season_monitored = True
                for season_info in series.get("seasons", []):
                    if season_info.get("seasonNumber") == season_num:
                        season_monitored = season_info.get("monitored", True)
                        break
                
                if not season_monitored:
                    continue
                
                # Also check if the episode itself is monitored
                if not finale_episode.get("monitored", True):
                    continue
            
            air_date_str = finale_episode.get('airDateUtc')
            if not air_date_str:
                continue
                
            air_date = convert_utc_to_local(air_date_str, utc_offset)
            
            # Include if:
            # 1. It aired within the recent period, OR
            # 2. It has a future air date but has already been downloaded
            if (air_date <= now_local and air_date >= cutoff_date) or (air_date > now_local and finale_episode.get('hasFile', False)):
                tvdb_id = series.get('tvdbId')
                
                # If it's a future episode that's already downloaded, use today's date instead
                if air_date > now_local and finale_episode.get('hasFile', False):
                    air_date_str_yyyy_mm_dd = now_local.date().isoformat()
                else:
                    air_date_str_yyyy_mm_dd = air_date.date().isoformat()
                
                show_dict = {
                    'title': series['title'],
                    'seasonNumber': season_num,
                    'episodeNumber': max_episode_num,
                    'airDate': air_date_str_yyyy_mm_dd,
                    'tvdbId': tvdb_id
                }
                
                matched_shows.append(show_dict)
    
    return matched_shows


def find_recent_final_episodes(sonarr_url, api_key, all_series, recent_days_final_episode, utc_offset=0, skip_unmonitored=False, ignore_finales_tags=None, tag_mapping=None):
    """Find shows with status 'ended' that had their final episode air within the specified days or have a future final episode that's already downloaded"""
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    cutoff_date = now_local - timedelta(days=recent_days_final_episode)
    matched_shows = []
  
    for series in all_series:
        # Only include ended shows
        if series.get('status') != 'ended':
            continue
            
        # Skip shows with ignore finale tags
        if has_ignore_finale_tag(series, ignore_finales_tags, tag_mapping):
            continue
            
        # Skip unmonitored shows if requested
        if skip_unmonitored and not series.get('monitored', True):
            continue
            
        episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        
        # Group episodes by season and find downloaded episodes
        seasons = defaultdict(list)
        downloaded_episodes = defaultdict(list)
        
        for ep in episodes:
            season_number = ep.get('seasonNumber', 0)
            if season_number > 0:  # Skip specials
                seasons[season_number].append(ep)
                if ep.get('hasFile', False):
                    downloaded_episodes[season_number].append(ep)
        
        # Skip if no episodes downloaded
        if not any(downloaded_episodes.values()):
            continue
            
        # Find the highest season with downloaded episodes
        max_season = max(downloaded_episodes.keys()) if downloaded_episodes else 0
        
        # Skip if no valid seasons found
        if max_season == 0:
            continue
            
        # Find the highest episode number in the highest season
        max_episode_num = max(ep.get('episodeNumber', 0) for ep in downloaded_episodes[max_season])
        
        # Find the final episode
        final_episode = None
        for ep in downloaded_episodes[max_season]:
            if ep.get('episodeNumber') == max_episode_num:
                final_episode = ep
                break
        
        if not final_episode:
            continue
            
        # Skip if the season is unmonitored and skip_unmonitored is True
        if skip_unmonitored:
            season_monitored = True
            for season_info in series.get("seasons", []):
                if season_info.get("seasonNumber") == max_season:
                    season_monitored = season_info.get("monitored", True)
                    break
            
            if not season_monitored:
                continue
            
            # Also check if the episode itself is monitored
            if not final_episode.get("monitored", True):
                continue
        
        # Check if there are any future episodes that aren't downloaded
        has_future_undownloaded_episodes = False
        for ep in episodes:
            air_date_str = ep.get('airDateUtc')
            season_number = ep.get('seasonNumber', 0)
            has_file = ep.get('hasFile', False)
            
            if season_number == 0:  # Skip specials
                continue
                
            if air_date_str:
                air_date = convert_utc_to_local(air_date_str, utc_offset)
                if air_date > now_local and not has_file:
                    has_future_undownloaded_episodes = True
                    break
        
        if has_future_undownloaded_episodes:
            continue
            
        air_date_str = final_episode.get('airDateUtc')
        if not air_date_str:
            continue
            
        air_date = convert_utc_to_local(air_date_str, utc_offset)
        
        # Include if:
        # 1. It aired within the recent period, OR
        # 2. It has a future air date but has already been downloaded
        if (air_date <= now_local and air_date >= cutoff_date) or (air_date > now_local and final_episode.get('hasFile', False)):
            tvdb_id = series.get('tvdbId')
            
            # If it's a future episode that's already downloaded, use today's date instead
            if air_date > now_local and final_episode.get('hasFile', False):
                air_date_str_yyyy_mm_dd = now_local.date().isoformat()
            else:
                air_date_str_yyyy_mm_dd = air_date.date().isoformat()
            
            show_dict = {
                'title': series['title'],
                'seasonNumber': max_season,
                'episodeNumber': max_episode_num,
                'airDate': air_date_str_yyyy_mm_dd,
                'tvdbId': tvdb_id
            }
            
            matched_shows.append(show_dict)
    
    return matched_shows


def find_new_season_started(sonarr_url, api_key, all_series, recent_days_new_season_started, utc_offset=0, skip_unmonitored=False):
    """Find shows where a new season (not season 1) has been downloaded within the specified days"""
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    cutoff_date = now_local - timedelta(days=recent_days_new_season_started)
    matched_shows = []
   
    for series in all_series:
        # Skip unmonitored shows if requested
        if skip_unmonitored and not series.get('monitored', True):
            continue
            
        episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        
        # Group episodes by season and find downloaded episodes
        seasons = defaultdict(list)
        downloaded_episodes = defaultdict(list)
        
        for ep in episodes:
            season_number = ep.get('seasonNumber', 0)
            if season_number > 0:  # Skip specials
                seasons[season_number].append(ep)
                if ep.get('hasFile', False):
                    downloaded_episodes[season_number].append(ep)
        
        # Skip if there's only one season (new show)
        if len(seasons) <= 1:
            continue
            
        # Find the highest season number with downloaded episodes
        if not downloaded_episodes:
            continue
            
        max_season_with_downloads = max(downloaded_episodes.keys())
        
        # Skip if it's season 1 (new show)
        if max_season_with_downloads <= 1:
            continue
            
        # Check if there are previous seasons with downloads (to confirm it's not a new show)
        has_previous_season_downloads = any(season < max_season_with_downloads for season in downloaded_episodes.keys())
        if not has_previous_season_downloads:
            continue
        
        # Find the first episode of the highest season that was downloaded
        season_episodes = downloaded_episodes[max_season_with_downloads]
        first_episode = min(season_episodes, key=lambda ep: ep.get('episodeNumber', 999))
        
        # Skip if the season is unmonitored and skip_unmonitored is True
        if skip_unmonitored:
            season_monitored = True
            for season_info in series.get("seasons", []):
                if season_info.get("seasonNumber") == max_season_with_downloads:
                    season_monitored = season_info.get("monitored", True)
                    break
            
            if not season_monitored:
                continue
            
            # Also check if the episode itself is monitored
            if not first_episode.get("monitored", True):
                continue
        
        # Check when this episode was downloaded (use air date as proxy)
        air_date_str = first_episode.get('airDateUtc')
        if not air_date_str:
            continue
            
        air_date = convert_utc_to_local(air_date_str, utc_offset)
        
        # Include if it aired within the recent period (assuming download happened around air date)
        if air_date >= cutoff_date and air_date <= now_local:
            tvdb_id = series.get('tvdbId')
            air_date_str_yyyy_mm_dd = air_date.date().isoformat()
            
            show_dict = {
                'title': series['title'],
                'seasonNumber': max_season_with_downloads,
                'episodeNumber': first_episode.get('episodeNumber'),
                'airDate': air_date_str_yyyy_mm_dd,
                'tvdbId': tvdb_id
            }
            
            matched_shows.append(show_dict)
    
    return matched_shows