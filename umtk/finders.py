"""
Content finder functions for UMTK - identifies shows and movies to process
"""

import requests
from datetime import datetime, timedelta, timezone

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .utils import convert_utc_to_local
from .sonarr import get_sonarr_episodes, sonarr_series_lookup


def _show_dict(series, air_date):
    """The show entry content creation, YML generation and Plex updates work with."""
    return {
        'title': series['title'],
        'tvdbId': series.get('tvdbId'),
        'tmdbId': series.get('tmdbId'),
        'path': series.get('path', ''),
        'imdbId': series.get('imdbId', ''),
        'year': series.get('year', None),
        'airDate': air_date.date().isoformat()
    }


def _premiere_bucket(series, episodes, cutoff_date, now_local, utc_offset, future_only_tv, debug=False):
    """Classify a show by its S01E01: ('future' | 'aired', show_dict) or (None, None)."""
    # Find S01E01 specifically
    first_episode = None

    for ep in episodes:
        if ep.get('seasonNumber') == 1 and ep.get('episodeNumber') == 1:
            first_episode = ep
            break

    if not first_episode:
        if debug:
            print(f"{ORANGE}[DEBUG] No Season 1 Episode 1 found for {series['title']}{RESET}")
        return None, None

    # Skip if S01E01 is not monitored
    if not first_episode.get('monitored', False):
        if debug:
            print(f"{ORANGE}[DEBUG] S01E01 not monitored for {series['title']}{RESET}")
        return None, None

    # Skip if S01E01 is already downloaded
    if first_episode.get('hasFile', False):
        if debug:
            print(f"{ORANGE}[DEBUG] S01E01 already downloaded for {series['title']} - skipping{RESET}")
        return None, None

    air_date_str = first_episode.get('airDateUtc')
    if not air_date_str:
        if debug:
            print(f"{ORANGE}[DEBUG] No air date found for {series['title']} S01E01{RESET}")
        return None, None

    air_date = convert_utc_to_local(air_date_str, utc_offset)

    if debug:
        print(f"{BLUE}[DEBUG] {series['title']} air date: {air_date}, within range: {air_date <= cutoff_date}{RESET}")

    # Check if air date is within our range
    if air_date > cutoff_date:
        return None, None

    # Categorize based on whether it has aired or not
    if air_date >= now_local:
        if debug:
            print(f"{GREEN}[DEBUG] Added to future shows: {series['title']}{RESET}")
        return 'future', _show_dict(series, air_date)
    if not future_only_tv:  # Only add aired shows if future_only_tv is false
        if debug:
            print(f"{GREEN}[DEBUG] Added to aired shows: {series['title']}{RESET}")
        return 'aired', _show_dict(series, air_date)
    if debug:
        print(f"{ORANGE}[DEBUG] Skipping aired show due to future_only_tv=True: {series['title']}{RESET}")
    return None, None


def _new_season_premiere(series, episodes, cutoff_date, now_local, utc_offset,
                         globally_downloaded_ids=None, debug=False):
    """A show with nothing downloaded whose next episode is a monitored season
    premiere (season > 1) airing by cutoff_date - the New Season Placeholders
    case. Mirrors TSSK's find_new_season_shows so both agree on the show.
    Returns the show dict (with 'seasonNumber' and 'new_season') or None."""
    # Downloaded anywhere -> the show is already in Plex, nothing to place.
    if globally_downloaded_ids and series.get('tvdbId') in globally_downloaded_ids:
        if debug:
            print(f"{ORANGE}[DEBUG] {series['title']} has episodes downloaded in another instance - no new season placeholder{RESET}")
        return None
    if any(ep.get('hasFile', False) for ep in episodes):
        if debug:
            print(f"{ORANGE}[DEBUG] {series['title']} has downloaded episodes - no new season placeholder{RESET}")
        return None

    future_episodes = []
    for ep in episodes:
        if ep.get('seasonNumber', 0) == 0:  # Skip specials
            continue
        air_date_str = ep.get('airDateUtc')
        if not air_date_str:
            continue
        air_date = convert_utc_to_local(air_date_str, utc_offset)
        if air_date > now_local:
            future_episodes.append((ep, air_date))

    if not future_episodes:
        return None

    future_episodes.sort(key=lambda x: x[1])
    next_episode, air_date = future_episodes[0]
    season_number = next_episode.get('seasonNumber', 0)

    if not (season_number > 1 and next_episode.get('episodeNumber') == 1 and air_date <= cutoff_date):
        if debug:
            print(f"{ORANGE}[DEBUG] {series['title']}: next episode S{season_number:02d}E{next_episode.get('episodeNumber', 0):02d} on {air_date} is not a season premiere within range{RESET}")
        return None

    season_monitored = next((s.get('monitored', True) for s in series.get('seasons', [])
                             if s.get('seasonNumber') == season_number), True)
    if not next_episode.get('monitored', True) or not season_monitored:
        if debug:
            print(f"{ORANGE}[DEBUG] {series['title']}: season {season_number} is not monitored - no new season placeholder{RESET}")
        return None

    if debug:
        print(f"{GREEN}[DEBUG] Added to new season shows: {series['title']} (season {season_number}){RESET}")
    show_dict = _show_dict(series, air_date)
    show_dict['seasonNumber'] = season_number
    show_dict['new_season'] = True
    return show_dict


def find_upcoming_shows(all_series, sonarr_url, api_key, future_days_upcoming_shows,
                        utc_offset=0, debug=False, exclude_tags=None, future_only_tv=False,
                        globally_available_ids=None, new_season_days=None,
                        globally_downloaded_ids=None):
    """Find shows with upcoming episodes that have their first episode airing within specified days.

    With new_season_days set, shows that don't qualify by their S01E01 but have
    nothing downloaded and a monitored season premiere (season > 1) within that
    many days are returned as a third list (New Season Placeholders), reusing
    the episodes fetched for the S01E01 check.

    Returns (future_shows, aired_shows, new_season_shows)."""
    future_shows = []
    aired_shows = []
    new_season_shows = []

    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_upcoming_shows)
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    new_season_cutoff = (datetime.now(timezone.utc) + timedelta(days=new_season_days)
                         if new_season_days is not None else None)

    if debug:
        print(f"{BLUE}[DEBUG] Cutoff date: {cutoff_date}, Now local: {now_local}{RESET}")
        print(f"{BLUE}[DEBUG] Future only TV: {future_only_tv}{RESET}")
        if new_season_cutoff:
            print(f"{BLUE}[DEBUG] New season placeholder cutoff date: {new_season_cutoff}{RESET}")
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

        # Cross-instance availability: S01E01 already downloaded in another instance -> treat as available
        if globally_available_ids and series.get('tvdbId') in globally_available_ids:
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping {series['title']} - S01E01 already downloaded in another instance{RESET}")
            continue

        try:
            episodes = get_sonarr_episodes(sonarr_url, api_key, series['id'])
        except requests.exceptions.RequestException:
            raise

        if debug:
            print(f"{BLUE}[DEBUG] Found {len(episodes)} episodes for {series['title']}{RESET}")

        bucket, show_dict = _premiere_bucket(series, episodes, cutoff_date, now_local,
                                             utc_offset, future_only_tv, debug)
        if bucket == 'future':
            future_shows.append(show_dict)
        elif bucket == 'aired':
            aired_shows.append(show_dict)
        elif new_season_cutoff is not None:
            show_dict = _new_season_premiere(series, episodes, new_season_cutoff, now_local,
                                             utc_offset, globally_downloaded_ids, debug)
            if show_dict:
                new_season_shows.append(show_dict)

    return future_shows, aired_shows, new_season_shows


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
                'tmdbId': series.get('tmdbId'),
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
                         debug=False, exclude_tags=None, past_days_upcoming_movies=0,
                         globally_available_ids=None):
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

        # Cross-instance availability: already downloaded in another instance -> treat as available
        if globally_available_ids and movie.get('tmdbId') in globally_available_ids:
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping {movie['title']} - already downloaded in another instance{RESET}")
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


def _build_sonarr_series_lookups(sonarr_instances_data):
    """Per-instance ID -> series indexes for the shows already in each library."""
    per_instance_lookups = []
    for inst in sonarr_instances_data:
        by_tvdb, by_imdb, by_tmdb = {}, {}, {}
        for series in inst.get('all_series', []):
            if series.get('tvdbId'):
                by_tvdb[str(series['tvdbId'])] = series
            if series.get('imdbId'):
                by_imdb[series['imdbId']] = series
            if series.get('tmdbId'):
                by_tmdb[str(series['tmdbId'])] = series
        per_instance_lookups.append({
            'instance': inst,
            'by_tvdb': by_tvdb,
            'by_imdb': by_imdb,
            'by_tmdb': by_tmdb,
        })
    return per_instance_lookups


def resolve_trending_tv_ids(trending_lists, sonarr_instances_data, debug=False):
    """Anchor each trending TV item to an authoritative TVDB ID.

    MDBList sometimes carries a stale TVDB ID for a show — one that has since
    been deleted or merged on TVDB — along with the wrong title and year from
    that dead record. Every downstream consumer (placeholder folder name, Plex
    lookup, Kometa collection and overlay YAMLs) keys on the TVDB ID, so a bad
    ID silently poisons all of them.

    For each item:
      - If its TVDB ID already matches a series in one of the Sonarr libraries,
        it's authoritative and left alone.
      - Otherwise Sonarr's metadata proxy is asked to resolve it, by TVDB first
        (an exact lookup — a live ID is kept as-is, a merged one comes back as
        the surviving record), then IMDb, then TMDB. On a hit the item's tvdb_id
        and year are rewritten to Sonarr's canonical values. A free-text title
        search is deliberately NOT attempted — a fuzzy match risks binding to
        the wrong series.
      - IMDb/TMDB results are only accepted when the returned series actually
        carries the ID that was asked for. SkyHook's 'tmdb:<n>' search also
        matches a series whose *TVDB* ID is <n> (e.g. tmdb:285322 returns TVDB
        285322 'Beppes good night' instead of 'Below', whose TMDB ID it is), so
        an unchecked result would bind to an unrelated show.

    The title is deliberately left alone: it feeds the placeholder *file* name,
    so rewriting it would orphan the existing file and create a duplicate
    alongside it. Only the ID and year — which affect the folder name, and which
    cleanup reconciles — are corrected.
      - If nothing resolves, the item is flagged '_id_unresolved' so callers can
        skip it instead of creating content that can never be matched.

    Operates on each list's own '_items' (not a deduped union) so every list's
    copy of an item gets corrected. Returns the number of unresolved items.
    """
    if not sonarr_instances_data:
        return 0

    per_instance_lookups = _build_sonarr_series_lookups(sonarr_instances_data)
    primary = sonarr_instances_data[0]

    # An item can appear in several lists; resolve each distinct ID set once.
    resolution_cache = {}
    unresolved_count = 0

    for lst in trending_lists:
        for item in (lst.get('_items') or []):
            tvdb_id = str(item['tvdb_id']) if item.get('tvdb_id') else None
            tmdb_id = str(item['tmdb_id']) if item.get('tmdb_id') else None
            imdb_id = item.get('imdb_id') or None
            title = item.get('title', 'Unknown')

            # Already known to one of the libraries -> authoritative.
            if tvdb_id and any(tvdb_id in lk['by_tvdb'] for lk in per_instance_lookups):
                continue

            cache_key = (tvdb_id, tmdb_id, imdb_id)
            if cache_key in resolution_cache:
                resolved, resolved_via = resolution_cache[cache_key]
            else:
                resolved, resolved_via = None, None
                # (term, predicate a result must satisfy to count as a hit)
                lookups = (
                    (f"tvdb:{tvdb_id}" if tvdb_id else None,
                     lambda s: bool(s.get('tvdbId'))),
                    (f"imdb:{imdb_id}" if imdb_id else None,
                     lambda s: bool(s.get('tvdbId')) and s.get('imdbId') == imdb_id),
                    (f"tmdb:{tmdb_id}" if tmdb_id else None,
                     lambda s: bool(s.get('tvdbId')) and str(s.get('tmdbId')) == tmdb_id),
                )
                for term, accepts in lookups:
                    if not term:
                        continue
                    results = sonarr_series_lookup(primary['url'], primary['api_key'],
                                                   term, primary.get('timeout') or 90)
                    match = next((s for s in results if accepts(s)), None)
                    if match:
                        if debug:
                            print(f"{BLUE}[DEBUG] Resolved trending show '{title}' via {term} "
                                  f"-> TVDB {match['tvdbId']}{RESET}")
                        resolved, resolved_via = match, term
                        break
                    elif results and debug:
                        print(f"{BLUE}[DEBUG] Ignored {len(results)} result(s) for '{title}' via {term}: "
                              f"none carry the queried ID{RESET}")
                resolution_cache[cache_key] = (resolved, resolved_via)

            if resolved:
                new_tvdb = str(resolved['tvdbId'])
                if new_tvdb != tvdb_id:
                    print(f"{ORANGE}Corrected trending show '{title}' ({item.get('year')}): "
                          f"TVDB {tvdb_id or 'none'} -> {new_tvdb} "
                          f"'{resolved.get('title', title)}' ({resolved.get('year')}) "
                          f"via {resolved_via}{RESET}")
                item['tvdb_id'] = resolved['tvdbId']
                if resolved.get('year'):
                    item['year'] = resolved['year']
                if resolved.get('imdbId'):
                    item['imdb_id'] = resolved['imdbId']
                item.pop('_id_unresolved', None)
            else:
                item['_id_unresolved'] = True
                unresolved_count += 1
                print(f"{ORANGE}Skipping trending show '{title}' ({item.get('year')}): "
                      f"could not resolve a valid TVDB ID "
                      f"(MDBList gave TVDB {tvdb_id or 'none'}, TMDB {tmdb_id or 'none'}, "
                      f"IMDB {imdb_id or 'none'}){RESET}")

    return unresolved_count


def process_trending_tv(mdblist_items, sonarr_instances_data, debug=False):
    """
    Process trending TV shows from MDBList against ALL Sonarr instances combined.

    sonarr_instances_data: list of dicts, one per instance:
        {'name', 'url', 'api_key', 'timeout', 'all_series'}

    Returns: (monitored_not_available, not_found_or_unmonitored)
    Each item in monitored_not_available carries an 'owner' key:
        {'name', 'url', 'api_key', 'timeout'} identifying the instance whose
        path + Sonarr API to use for placeholder creation.
    """
    monitored_not_available = []
    not_found_or_unmonitored = []

    if debug:
        print(f"{BLUE}[DEBUG] Processing {len(mdblist_items)} trending TV shows across {len(sonarr_instances_data)} Sonarr instance(s){RESET}")

    per_instance_lookups = _build_sonarr_series_lookups(sonarr_instances_data)

    for item in mdblist_items:
        tvdb_id = str(item.get('tvdb_id', '')) if item.get('tvdb_id') else None
        tmdb_id = str(item.get('tmdb_id', '')) if item.get('tmdb_id') else None
        imdb_id = item.get('imdb_id', '')
        title = item.get('title', 'Unknown')
        year = item.get('year')
        rank = item.get('rank')

        if debug:
            print(f"{BLUE}[DEBUG] Processing trending show: {title} ({year}) - TVDB: {tvdb_id}, TMDB: {tmdb_id}, IMDB: {imdb_id}, Rank: {rank}{RESET}")

        # Find matches across all instances
        matches = []  # list of (lookup_entry, series)
        for lookup in per_instance_lookups:
            series = None
            # IMDb before TMDB: MDBList's 'id' field is the less reliable of the
            # two fallbacks, so try the stable identifier first.
            if tvdb_id and tvdb_id in lookup['by_tvdb']:
                series = lookup['by_tvdb'][tvdb_id]
            elif imdb_id and imdb_id in lookup['by_imdb']:
                series = lookup['by_imdb'][imdb_id]
            elif tmdb_id and tmdb_id in lookup['by_tmdb']:
                series = lookup['by_tmdb'][tmdb_id]
            if series:
                matches.append((lookup, series))

        if not matches:
            if debug:
                print(f"{BLUE}[DEBUG] Not found in any Sonarr instance - adding to not_found_or_unmonitored{RESET}")
            not_found_or_unmonitored.append({
                'title': title,
                'tvdbId': int(tvdb_id) if tvdb_id and tvdb_id.isdigit() else None,
                'tmdbId': int(tmdb_id) if tmdb_id and tmdb_id.isdigit() else None,
                'path': None,
                'imdbId': imdb_id,
                'year': year,
                'airDate': None,
                'rank': rank,
                'source_list': item.get('source_list')
            })
            continue

        # Walk matches: short-circuit on first downloaded; otherwise track first monitored owner.
        downloaded_anywhere = False
        owner_lookup = None
        owner_series = None

        for lookup, series in matches:
            inst = lookup['instance']
            try:
                episodes = get_sonarr_episodes(inst['url'], inst['api_key'], series['id'])
            except requests.exceptions.RequestException:
                raise

            if any(ep.get('hasFile', False) for ep in episodes):
                if debug:
                    print(f"{BLUE}[DEBUG] Downloaded episodes in instance '{inst.get('name')}', skipping completely{RESET}")
                downloaded_anywhere = True
                break

            if owner_lookup is None and series.get('monitored', False):
                if any(ep.get('monitored', False) for ep in episodes):
                    owner_lookup = lookup
                    owner_series = series

        if downloaded_anywhere:
            continue

        if owner_lookup is not None:
            inst = owner_lookup['instance']
            if debug:
                print(f"{BLUE}[DEBUG] Monitored in instance '{inst.get('name')}' - adding to monitored_not_available{RESET}")
            monitored_not_available.append({
                'title': owner_series['title'],
                'tvdbId': owner_series.get('tvdbId'),
                'tmdbId': owner_series.get('tmdbId'),
                'path': owner_series.get('path', ''),
                'imdbId': owner_series.get('imdbId', ''),
                'year': owner_series.get('year', None),
                'airDate': None,
                'rank': rank,
                'source_list': item.get('source_list'),
                'owner': {
                    'name': inst.get('name'),
                    'url': inst.get('url'),
                    'api_key': inst.get('api_key'),
                    'timeout': inst.get('timeout'),
                },
            })
        else:
            # Found in at least one instance, but unmonitored everywhere
            ref_series = matches[0][1]
            if debug:
                print(f"{BLUE}[DEBUG] Found but unmonitored everywhere - adding to not_found_or_unmonitored{RESET}")
            not_found_or_unmonitored.append({
                'title': ref_series['title'],
                'tvdbId': ref_series.get('tvdbId'),
                'tmdbId': ref_series.get('tmdbId'),
                'path': ref_series.get('path', ''),
                'imdbId': ref_series.get('imdbId', ''),
                'year': ref_series.get('year', None),
                'airDate': None,
                'rank': rank,
                'source_list': item.get('source_list')
            })

    return monitored_not_available, not_found_or_unmonitored


def process_trending_movies(mdblist_items, radarr_instances_data, debug=False):
    """
    Process trending movies from MDBList against ALL Radarr instances combined.

    radarr_instances_data: list of dicts, one per instance:
        {'name', 'url', 'api_key', 'timeout', 'all_movies'}

    Returns: (monitored_not_available, not_found_or_unmonitored)
    Each item in monitored_not_available carries an 'owner' key:
        {'name', 'url', 'api_key', 'timeout'} identifying the instance whose
        path + Radarr API to use for placeholder creation.
    """
    monitored_not_available = []
    not_found_or_unmonitored = []

    if debug:
        print(f"{BLUE}[DEBUG] Processing {len(mdblist_items)} trending movies across {len(radarr_instances_data)} Radarr instance(s){RESET}")

    # Per-instance lookup tables
    per_instance_lookups = []
    for inst in radarr_instances_data:
        by_tmdb, by_imdb = {}, {}
        for movie in inst.get('all_movies', []):
            if movie.get('tmdbId'):
                by_tmdb[str(movie['tmdbId'])] = movie
            if movie.get('imdbId'):
                by_imdb[movie['imdbId']] = movie
        per_instance_lookups.append({
            'instance': inst,
            'by_tmdb': by_tmdb,
            'by_imdb': by_imdb,
        })

    for item in mdblist_items:
        tmdb_id = str(item.get('tmdb_id', '')) if item.get('tmdb_id') else None
        imdb_id = item.get('imdb_id', '')
        title = item.get('title', 'Unknown')
        year = item.get('year')
        rank = item.get('rank')

        if debug:
            print(f"{BLUE}[DEBUG] Processing trending movie: {title} ({year}) - TMDB: {tmdb_id}, IMDB: {imdb_id}, Rank: {rank}{RESET}")

        # Find matches across all instances
        matches = []  # list of (lookup_entry, movie)
        for lookup in per_instance_lookups:
            movie = None
            if tmdb_id and tmdb_id in lookup['by_tmdb']:
                movie = lookup['by_tmdb'][tmdb_id]
            elif imdb_id and imdb_id in lookup['by_imdb']:
                movie = lookup['by_imdb'][imdb_id]
            if movie:
                matches.append((lookup, movie))

        if not matches:
            if debug:
                print(f"{BLUE}[DEBUG] Not found in any Radarr instance - adding to not_found_or_unmonitored{RESET}")
            not_found_or_unmonitored.append({
                'title': title,
                'tmdbId': int(tmdb_id) if tmdb_id and tmdb_id.isdigit() else None,
                'imdbId': imdb_id,
                'path': None,
                'folderName': None,
                'year': year,
                'releaseDate': None,
                'releaseType': 'Trending',
                'rank': rank,
                'source_list': item.get('source_list')
            })
            continue

        # Short-circuit on first downloaded; track first monitored owner.
        downloaded_anywhere = False
        owner_lookup = None
        owner_movie = None

        for lookup, movie in matches:
            if movie.get('hasFile', False):
                if debug:
                    print(f"{BLUE}[DEBUG] Already downloaded in instance '{lookup['instance'].get('name')}', skipping completely{RESET}")
                downloaded_anywhere = True
                break
            if owner_lookup is None and movie.get('monitored', False):
                owner_lookup = lookup
                owner_movie = movie

        if downloaded_anywhere:
            continue

        if owner_lookup is not None:
            inst = owner_lookup['instance']
            if debug:
                print(f"{BLUE}[DEBUG] Monitored in instance '{inst.get('name')}' - adding to monitored_not_available{RESET}")
            monitored_not_available.append({
                'title': owner_movie['title'],
                'tmdbId': owner_movie.get('tmdbId'),
                'imdbId': owner_movie.get('imdbId'),
                'path': owner_movie.get('path', ''),
                'folderName': owner_movie.get('folderName', ''),
                'year': owner_movie.get('year', None),
                'releaseDate': None,
                'releaseType': 'Trending',
                'rank': rank,
                'source_list': item.get('source_list'),
                'owner': {
                    'name': inst.get('name'),
                    'url': inst.get('url'),
                    'api_key': inst.get('api_key'),
                    'timeout': inst.get('timeout'),
                },
            })
        else:
            ref_movie = matches[0][1]
            if debug:
                print(f"{BLUE}[DEBUG] Found but unmonitored everywhere - adding to not_found_or_unmonitored{RESET}")
            not_found_or_unmonitored.append({
                'title': ref_movie['title'],
                'tmdbId': ref_movie.get('tmdbId'),
                'imdbId': ref_movie.get('imdbId'),
                'path': ref_movie.get('path', ''),
                'folderName': ref_movie.get('folderName', ''),
                'year': ref_movie.get('year', None),
                'releaseDate': None,
                'releaseType': 'Trending',
                'rank': rank,
                'source_list': item.get('source_list')
            })

    return monitored_not_available, not_found_or_unmonitored