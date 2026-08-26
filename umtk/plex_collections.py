"""
Direct Plex collection management for UMTK trending lists.
"""

import requests

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .utils import request_with_retry, dedupe_by_key
from .plex_integration import get_plex_libraries, get_plex_library_items, _plex_item_ids

# Plex library/collection type ids and the 'Collection Order' advanced setting.
PLEX_TYPE_MOVIE = 1
PLEX_TYPE_SHOW = 2
COLLECTION_SORT_CUSTOM = 2


def _headers(plex_token):
    return {"X-Plex-Token": plex_token, "Accept": "application/json"}


def _metadata_uri(machine_id, rating_keys):
    """The server:// uri Plex expects when adding items to a collection."""
    keys = ",".join(str(k) for k in rating_keys)
    return f"server://{machine_id}/com.plexapp.plugins.library/library/metadata/{keys}"


def get_plex_machine_identifier(plex_url, plex_token, debug=False):
    """Fetch the server's machine identifier (needed to build item uris)."""
    try:
        url = f"{plex_url.rstrip('/')}/identity"

        if debug:
            print(f"{BLUE}[DEBUG] Fetching Plex identity from: {url}{RESET}")

        response = request_with_retry('GET', url, headers=_headers(plex_token), timeout=30)
        response.raise_for_status()

        machine_id = response.json().get('MediaContainer', {}).get('machineIdentifier')

        if debug:
            print(f"{BLUE}[DEBUG] Plex machineIdentifier: {machine_id}{RESET}")

        return machine_id
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error fetching Plex identity: {str(e)}{RESET}")
        return None


def get_section_collections(plex_url, plex_token, library_key, debug=False):
    """All collections in a library section as [{'ratingKey', 'title'}]."""
    try:
        url = f"{plex_url.rstrip('/')}/library/sections/{library_key}/collections"

        if debug:
            print(f"{BLUE}[DEBUG] Fetching Plex collections from: {url}{RESET}")

        response = request_with_retry('GET', url, headers=_headers(plex_token), timeout=30)
        response.raise_for_status()

        container = response.json().get('MediaContainer', {})
        # Depending on the PMS version collections come back under Metadata or Directory.
        entries = container.get('Metadata') or container.get('Directory') or []

        collections = [{'ratingKey': str(e.get('ratingKey')), 'title': e.get('title', '')}
                       for e in entries if e.get('ratingKey')]

        if debug:
            print(f"{BLUE}[DEBUG] Found {len(collections)} collections in section {library_key}{RESET}")

        return collections
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error fetching Plex collections: {str(e)}{RESET}")
        return []


def get_collection_items(plex_url, plex_token, collection_rating_key, debug=False):
    """The collection's items as a list of ratingKeys, in their current order."""
    try:
        url = f"{plex_url.rstrip('/')}/library/collections/{collection_rating_key}/children"

        if debug:
            print(f"{BLUE}[DEBUG] Fetching collection items from: {url}{RESET}")

        response = request_with_retry('GET', url, headers=_headers(plex_token), timeout=30)
        response.raise_for_status()

        metadata = response.json().get('MediaContainer', {}).get('Metadata', [])
        return [str(m.get('ratingKey')) for m in metadata if m.get('ratingKey')]
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error fetching collection items: {str(e)}{RESET}")
        return []


def create_collection(plex_url, plex_token, machine_id, library_key, section_type,
                      title, rating_keys, debug=False):
    """Create a collection holding rating_keys. Returns its ratingKey or None."""
    try:
        url = f"{plex_url.rstrip('/')}/library/collections"
        params = {
            "type": PLEX_TYPE_MOVIE if section_type == 'movie' else PLEX_TYPE_SHOW,
            "title": title,
            "smart": 0,
            "sectionId": library_key,
            "uri": _metadata_uri(machine_id, rating_keys),
        }

        if debug:
            print(f"{BLUE}[DEBUG] Creating Plex collection - URL: {url}, params: {params}{RESET}")

        response = request_with_retry('POST', url, headers=_headers(plex_token),
                                      params=params, timeout=30)
        response.raise_for_status()

        container = response.json().get('MediaContainer', {})
        entries = container.get('Metadata') or container.get('Directory') or []
        if entries and entries[0].get('ratingKey'):
            return str(entries[0]['ratingKey'])

        print(f"{ORANGE}Plex did not return a ratingKey for new collection '{title}'{RESET}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error creating Plex collection '{title}': {str(e)}{RESET}")
        return None


def add_collection_items(plex_url, plex_token, machine_id, collection_rating_key,
                         rating_keys, debug=False):
    """Add items to an existing collection in one call."""
    if not rating_keys:
        return True
    try:
        url = f"{plex_url.rstrip('/')}/library/collections/{collection_rating_key}/items"
        params = {"uri": _metadata_uri(machine_id, rating_keys)}

        if debug:
            print(f"{BLUE}[DEBUG] Adding {len(rating_keys)} item(s) - URL: {url}{RESET}")

        response = request_with_retry('PUT', url, headers=_headers(plex_token),
                                      params=params, timeout=30)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error adding items to Plex collection: {str(e)}{RESET}")
        return False


def remove_collection_item(plex_url, plex_token, collection_rating_key, item_rating_key,
                           debug=False):
    """Remove a single item from a collection."""
    try:
        url = (f"{plex_url.rstrip('/')}/library/collections/{collection_rating_key}"
               f"/items/{item_rating_key}")

        if debug:
            print(f"{BLUE}[DEBUG] Removing item {item_rating_key} - URL: {url}{RESET}")

        response = request_with_retry('DELETE', url, headers=_headers(plex_token), timeout=30)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error removing item from Plex collection: {str(e)}{RESET}")
        return False


def move_collection_item(plex_url, plex_token, collection_rating_key, item_rating_key,
                         after_rating_key=None, debug=False):
    """Move an item after another one; omitting 'after' moves it to the front."""
    try:
        url = (f"{plex_url.rstrip('/')}/library/collections/{collection_rating_key}"
               f"/items/{item_rating_key}/move")
        params = {"after": after_rating_key} if after_rating_key else None

        if debug:
            print(f"{BLUE}[DEBUG] Moving item {item_rating_key} after {after_rating_key} "
                  f"- URL: {url}{RESET}")

        response = request_with_retry('PUT', url, headers=_headers(plex_token),
                                      params=params, timeout=30)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error reordering Plex collection item: {str(e)}{RESET}")
        return False


def set_collection_custom_sort(plex_url, plex_token, collection_rating_key, debug=False):
    """Set the collection's 'Collection Order' advanced setting to Custom.

    Both /library/metadata/{key}/prefs and /library/collections/{key}/prefs resolve
    on PMS depending on version, so fall back to the second if the first is refused.
    """
    base = plex_url.rstrip('/')
    params = {"collectionSort": COLLECTION_SORT_CUSTOM}
    paths = [f"{base}/library/metadata/{collection_rating_key}/prefs",
             f"{base}/library/collections/{collection_rating_key}/prefs"]

    for url in paths:
        try:
            if debug:
                print(f"{BLUE}[DEBUG] Setting custom collection order - URL: {url}{RESET}")

            response = request_with_retry('PUT', url, headers=_headers(plex_token),
                                          params=params, timeout=30)
            if response.ok:
                return True
            if debug:
                print(f"{BLUE}[DEBUG] {url} returned {response.status_code}{RESET}")
        except requests.exceptions.RequestException as e:
            if debug:
                print(f"{BLUE}[DEBUG] {url} failed: {str(e)}{RESET}")

    print(f"{ORANGE}Could not set custom collection order for collection "
          f"{collection_rating_key}{RESET}")
    return False


def trending_collection_name(config, lst):
    """The Plex collection name for a trending list.

    Must match the name create_trending_collection_yaml_* writes, otherwise UMTK
    would build a second collection next to the one Kometa manages.
    """
    if lst.get('legacy_filenames'):
        if lst.get('type') == 'movie':
            block, default = 'collection_trending_movies', 'Trending Movies'
        else:
            block, default = 'collection_trending_shows', 'Trending Shows'
        block_config = config.get(block)
        if isinstance(block_config, dict):
            return block_config.get('collection_name') or default
        return default
    return lst.get('name')


def _first_library_name(value):
    """First entry of a comma-separated (or list) library setting."""
    if isinstance(value, str):
        names = [n.strip() for n in value.split(',') if n.strip()]
    elif isinstance(value, (list, tuple)):
        names = [str(n).strip() for n in value if str(n).strip()]
    else:
        names = []
    return names[0] if names else None


def _build_id_index(plex_items):
    """Map every TMDB/TVDB id a library's items carry to their ratingKey."""
    by_tmdb = {}
    by_tvdb = {}
    for plex_item in plex_items:
        rating_key = plex_item.get('ratingKey')
        if not rating_key:
            continue
        for tmdb_id in _plex_item_ids(plex_item, 'tmdbIds', 'tmdbId'):
            by_tmdb.setdefault(tmdb_id, str(rating_key))
        for tvdb_id in _plex_item_ids(plex_item, 'tvdbIds', 'tvdbId'):
            by_tvdb.setdefault(tvdb_id, str(rating_key))
    return by_tmdb, by_tvdb


def _resolve_items(lst, by_tmdb, by_tvdb):
    """Map a list's MDBList items to Plex ratingKeys, preserving rank order.

    Returns (rating_keys, missing_titles). TV prefers TVDB and falls back to
    TMDB, mirroring how create_trending_collection_yaml_tv picks its ids.
    """
    is_tv = lst.get('type') == 'tv'
    rating_keys = []
    seen = set()
    missing = []

    for item in (lst.get('_items') or []):
        if item.get('_id_unresolved'):
            continue

        tmdb_id = item.get('tmdb_id') or item.get('id')
        rating_key = None

        if is_tv:
            if item.get('tvdb_id'):
                rating_key = by_tvdb.get(str(item['tvdb_id']))
            if not rating_key and tmdb_id:
                rating_key = by_tmdb.get(str(tmdb_id))
        elif tmdb_id:
            rating_key = by_tmdb.get(str(tmdb_id))

        if not rating_key:
            missing.append(item.get('title', 'Unknown'))
            continue
        if rating_key in seen:
            continue

        seen.add(rating_key)
        rating_keys.append(rating_key)

    return rating_keys, missing


def _find_collection(collections, title):
    """Locate an existing collection by title, tolerating case differences."""
    matches = [c for c in collections if c['title'] == title]
    if not matches:
        lowered = (title or '').lower()
        matches = [c for c in collections if c['title'].lower() == lowered]
    if len(matches) > 1:
        print(f"{ORANGE}Found {len(matches)} Plex collections named '{title}' — "
              f"updating the first one{RESET}")
    return matches[0] if matches else None


def _reorder(plex_url, plex_token, collection_rating_key, current_order, desired, debug=False):
    """Move items until the collection order matches 'desired'. Returns move count."""
    order = list(current_order)
    moves = 0

    for index, rating_key in enumerate(desired):
        if index < len(order) and order[index] == rating_key:
            continue
        after = desired[index - 1] if index > 0 else None
        if not move_collection_item(plex_url, plex_token, collection_rating_key,
                                    rating_key, after, debug):
            continue
        if rating_key in order:
            order.remove(rating_key)
        order.insert(index, rating_key)
        moves += 1

    return moves


def _apply_order(plex_url, plex_token, collection_rating_key, desired,
                 created=False, debug=False):
    """Put the collection's items in 'desired' order, then confirm they landed.

    Right after a collection is created Plex still serves /children in the
    default (release) order rather than the custom order it actually stored, so
    that read is not a usable baseline: _reorder's "already in place" shortcut
    skips items that are in fact somewhere else, and the collection comes out
    mis-ordered until the next run. Place every item explicitly in that case.

    Re-reading afterwards is cheap insurance. Each move puts desired[i] directly
    after desired[i-1], so replaying moves is idempotent toward the target - a
    stale baseline can only ever make us skip a move, never misplace an item.
    """
    moves = 0

    if created:
        moves += _reorder(plex_url, plex_token, collection_rating_key, [], desired, debug)

    for attempt in range(2):
        current = get_collection_items(plex_url, plex_token, collection_rating_key, debug)
        if current == desired:
            break
        if debug:
            print(f"{BLUE}[DEBUG] Collection order still off after "
                  f"{'creation' if created and not attempt else 'sync'}, correcting{RESET}")
        # Second time around the read has already proved unreliable, so stop
        # diffing against it and place everything explicitly.
        baseline = current if attempt == 0 else []
        moves += _reorder(plex_url, plex_token, collection_rating_key,
                          baseline, desired, debug)

    return moves


def _resolve_library(libraries, library_name, expected_type, label, config, debug=False):
    """Find the Plex library a collection should live in.

    Falls back to the first configured movie/TV library when no name is given.
    Returns (library_name, library_dict) or (None, None) after warning.
    """
    library_name = (library_name or '').strip()
    if not library_name:
        fallback_key = 'tv_libraries' if expected_type == 'show' else 'movie_libraries'
        library_name = _first_library_name(config.get(fallback_key))
    if not library_name:
        print(f"{ORANGE}{label}: no Plex library configured — skipping collection{RESET}")
        return None, None

    library = libraries.get(library_name)
    if not library:
        print(f"{ORANGE}{label}: Plex library '{library_name}' not found — "
              f"skipping collection{RESET}")
        if debug:
            matching = [k for k in libraries if library_name.lower() in k.lower()]
            if matching:
                print(f"{BLUE}[DEBUG] Did you mean one of these? {matching}{RESET}")
        return None, None
    if library.get('type') != expected_type:
        kind_label = 'TV' if expected_type == 'show' else 'movie'
        print(f"{ORANGE}{label}: Plex library '{library_name}' is not a {kind_label} "
              f"library — skipping collection{RESET}")
        return None, None

    return library_name, library


def _library_items(plex_url, plex_token, library_key, library_items_cache, debug=False):
    """A library's items, fetched once per run (the call pulls a whole section)."""
    if library_key not in library_items_cache:
        library_items_cache[library_key] = get_plex_library_items(
            plex_url, plex_token, library_key, debug)
    return library_items_cache[library_key]


def _sync_collection(plex_url, plex_token, machine_id, library_key, library_name,
                     expected_type, collection_name, desired, debug=False):
    """Create the collection or bring an existing one in line with 'desired'.

    'desired' is the wanted ratingKeys in the wanted order. Adds what joined,
    removes what left, forces Custom order and reorders in place.
    """
    collections = get_section_collections(plex_url, plex_token, library_key, debug)
    existing = _find_collection(collections, collection_name)

    added = removed = 0

    created = existing is None

    if created:
        collection_rating_key = create_collection(
            plex_url, plex_token, machine_id, library_key, expected_type,
            collection_name, desired, debug)
        if not collection_rating_key:
            return
        added = len(desired)
        print(f"{GREEN}Created Plex collection '{collection_name}' in '{library_name}'{RESET}")
    else:
        collection_rating_key = existing['ratingKey']
        current = get_collection_items(plex_url, plex_token, collection_rating_key, debug)

        desired_set = set(desired)
        to_add = [rk for rk in desired if rk not in current]
        to_remove = [rk for rk in current if rk not in desired_set]

        if to_add and add_collection_items(plex_url, plex_token, machine_id,
                                           collection_rating_key, to_add, debug):
            added = len(to_add)
        for rating_key in to_remove:
            if remove_collection_item(plex_url, plex_token, collection_rating_key,
                                      rating_key, debug):
                removed += 1

    set_collection_custom_sort(plex_url, plex_token, collection_rating_key, debug)

    moves = _apply_order(plex_url, plex_token, collection_rating_key, desired,
                         created, debug)

    print(f"{GREEN}Plex collection '{collection_name}' ({library_name}): {len(desired)} items, "
          f"+{added} added, -{removed} removed, {moves} reordered{RESET}")


def _sync_one(plex_url, plex_token, machine_id, libraries, library_items_cache,
              lst, config, debug=False):
    """Create or update one trending list's collection in Plex."""
    label = f"Trending list '{lst.get('name') or 'Unnamed list'}'"
    expected_type = 'show' if lst.get('type') == 'tv' else 'movie'

    library_name, library = _resolve_library(
        libraries, lst.get('plex_library'), expected_type, label, config, debug)
    if not library:
        return

    plex_items = _library_items(plex_url, plex_token, library['key'],
                                library_items_cache, debug)
    by_tmdb, by_tvdb = _build_id_index(plex_items)

    desired, missing = _resolve_items(lst, by_tmdb, by_tvdb)

    if missing:
        print(f"{ORANGE}{label}: {len(missing)} item(s) not in Plex "
              f"library '{library_name}' yet:{RESET}")
        for title in missing:
            print(f"  - {title}")

    collection_name = trending_collection_name(config, lst)
    if not desired:
        print(f"{ORANGE}{label}: none of the items are in Plex — "
              f"leaving collection '{collection_name}' untouched{RESET}")
        return

    _sync_collection(plex_url, plex_token, machine_id, library['key'], library_name,
                     expected_type, collection_name, desired, debug)


def sync_trending_collections(plex_url, plex_token, lists, config, debug=False):
    """Build/update the Plex collections of every trending list with build_in_plex."""
    if not lists:
        return

    machine_id = get_plex_machine_identifier(plex_url, plex_token, debug)
    if not machine_id:
        print(f"{RED}Could not determine the Plex machine identifier — "
              f"skipping collection building{RESET}")
        return

    libraries = get_plex_libraries(plex_url, plex_token, debug)
    if not libraries:
        print(f"{RED}Could not fetch Plex libraries — skipping collection building{RESET}")
        return

    # Several lists can target the same library and that fetch pulls a whole
    # section, so keep the results around for the duration of the run.
    library_items_cache = {}

    for lst in lists:
        _sync_one(plex_url, plex_token, machine_id, libraries, library_items_cache,
                  lst, config, debug)


# ── Upcoming (Coming Soon) collections ────────────────────────────────────

# Which collector list each 'include TSSK ...' option pulls in.
TSSK_UPCOMING_SOURCES = (
    ('upcoming_shows_include_new_season_soon', 'tssk_new_season_soon', 'New Season Soon'),
    ('upcoming_shows_include_upcoming_episode', 'tssk_upcoming_episode', 'Upcoming Episode'),
    ('upcoming_shows_include_upcoming_finale', 'tssk_upcoming_finale', 'Upcoming Finale'),
)

# Items with no date sort last rather than jumping to the front.
_NO_DATE = '9999-12-31'


def _is_true(value):
    """Parse a config flag that may be a real bool or a YAML/WebUI string."""
    return str(value).lower() == 'true'


def upcoming_collection_name(config, block_key, default):
    """The collection name create_collection_yaml_* writes for an upcoming block."""
    block = config.get(block_key)
    if isinstance(block, dict):
        return block.get('collection_name') or default
    return default


def _sorted_by_date(items, date_key):
    """Items oldest date first; undated ones last, in their original order."""
    return sorted(items, key=lambda i: str(i.get(date_key) or _NO_DATE))


def _resolve_by_id(items, index, id_key):
    """Map date-sorted item dicts to Plex ratingKeys, preserving order."""
    rating_keys = []
    seen = set()
    missing = []

    for item in items:
        id_value = item.get(id_key)
        rating_key = index.get(str(id_value)) if id_value else None
        if not rating_key:
            missing.append(item.get('title', 'Unknown'))
            continue
        if rating_key in seen:
            continue
        seen.add(rating_key)
        rating_keys.append(rating_key)

    return rating_keys, missing


def _collect_upcoming_shows(config, collector, debug=False):
    """UMTK's upcoming shows plus whichever TSSK categories are switched on.

    Deduped on tvdbId with UMTK's own entry winning, then ordered by air date.
    """
    groups = [collector.get('upcoming_shows') or []]

    for option_key, collector_key, label in TSSK_UPCOMING_SOURCES:
        if not _is_true(config.get(option_key, 'false')):
            continue
        shows = collector.get(collector_key)
        if shows is None:
            print(f"{ORANGE}Coming Soon shows: TSSK '{label}' is switched on but TSSK "
                  f"produced no results this run — skipping that category{RESET}")
            continue
        if debug:
            print(f"{BLUE}[DEBUG] Adding {len(shows)} show(s) from TSSK '{label}'{RESET}")
        groups.append(shows)

    return _sorted_by_date(dedupe_by_key(groups, 'tvdbId'), 'airDate')


def _sync_upcoming(plex_url, plex_token, machine_id, libraries, library_items_cache,
                   config, items, expected_type, id_key, library_option, block_key,
                   default_name, label, debug=False):
    """Build/update one upcoming collection from date-ordered item dicts."""
    library_name, library = _resolve_library(
        libraries, config.get(library_option), expected_type, label, config, debug)
    if not library:
        return

    plex_items = _library_items(plex_url, plex_token, library['key'],
                                library_items_cache, debug)
    by_tmdb, by_tvdb = _build_id_index(plex_items)
    index = by_tvdb if id_key == 'tvdbId' else by_tmdb

    desired, missing = _resolve_by_id(items, index, id_key)

    if missing:
        print(f"{ORANGE}{label}: {len(missing)} item(s) not in Plex library "
              f"'{library_name}' yet:{RESET}")
        for title in missing:
            print(f"  - {title}")

    collection_name = upcoming_collection_name(config, block_key, default_name)
    if not desired:
        print(f"{ORANGE}{label}: none of the items are in Plex — "
              f"leaving collection '{collection_name}' untouched{RESET}")
        return

    _sync_collection(plex_url, plex_token, machine_id, library['key'], library_name,
                     expected_type, collection_name, desired, debug)


def sync_upcoming_collections(plex_url, plex_token, config, collector, debug=False):
    """Build/update the Coming Soon movie and TV collections directly in Plex.

    Ordered by expected release date (movies) / air date (shows). The shows
    collection can also absorb TSSK's upcoming categories - see
    TSSK_UPCOMING_SOURCES.
    """
    do_movies = _is_true(config.get('upcoming_movies_build_in_plex', 'false'))
    do_shows = _is_true(config.get('upcoming_shows_build_in_plex', 'false'))
    if not do_movies and not do_shows:
        return

    print(f"\n{BLUE}{'=' * 50}{RESET}")
    print(f"{BLUE}Building Coming Soon collections in Plex...{RESET}")
    print(f"{BLUE}{'=' * 50}{RESET}\n")

    movies = _sorted_by_date(collector.get('upcoming_movies') or [], 'releaseDate') if do_movies else []
    shows = _collect_upcoming_shows(config, collector, debug) if do_shows else []

    if do_movies and not movies:
        print(f"{ORANGE}Coming Soon movies: nothing to put in the collection this run{RESET}")
    if do_shows and not shows:
        print(f"{ORANGE}Coming Soon shows: nothing to put in the collection this run{RESET}")
    if not movies and not shows:
        return

    machine_id = get_plex_machine_identifier(plex_url, plex_token, debug)
    if not machine_id:
        print(f"{RED}Could not determine the Plex machine identifier — "
              f"skipping collection building{RESET}")
        return

    libraries = get_plex_libraries(plex_url, plex_token, debug)
    if not libraries:
        print(f"{RED}Could not fetch Plex libraries — skipping collection building{RESET}")
        return

    library_items_cache = {}

    if movies:
        _sync_upcoming(plex_url, plex_token, machine_id, libraries, library_items_cache,
                       config, movies, 'movie', 'tmdbId',
                       'upcoming_movies_plex_library', 'collection_upcoming_movies',
                       'Upcoming Movies', 'Coming Soon movies', debug)

    if shows:
        _sync_upcoming(plex_url, plex_token, machine_id, libraries, library_items_cache,
                       config, shows, 'show', 'tvdbId',
                       'upcoming_shows_plex_library', 'collection_upcoming_shows',
                       'Upcoming Shows', 'Coming Soon shows', debug)
