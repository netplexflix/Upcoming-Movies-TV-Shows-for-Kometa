"""
Direct Plex collection management for UMTK trending lists.
"""

import time

import requests

from .constants import GREEN, ORANGE, RED, BLUE, RESET
from .utils import request_with_retry, dedupe_by_key
from .plex_integration import get_plex_libraries, get_plex_library_items, _plex_item_ids

# Plex library/collection type ids and the 'Collection Order' advanced setting.
PLEX_TYPE_MOVIE = 1
PLEX_TYPE_SHOW = 2
COLLECTION_SORT_CUSTOM = 2

# Plex needs a moment to index placeholders/trailers UMTK just wrote, so items
# can be missing on the first look. Same wait as the sort-title pass in
# plex_integration.py, driven by the same metadata_retry_limit setting.
PLEX_ITEM_RETRY_WAIT = 60


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


def _resolve_targets(libraries, config, specs, debug=False):
    """Pair every spec with each Plex library it builds in.

    Done once, before any waiting: which libraries exist cannot change while we
    wait for Plex to index, and this keeps the warnings to a single printing.
    """
    targets = []
    for spec in specs:
        for library_name in spec['library_names']:
            resolved_name, library = _resolve_library(
                libraries, library_name, spec['type'],
                spec['label'](library_name), config, debug)
            if library:
                targets.append({'spec': spec, 'library': library,
                                'library_name': resolved_name})
    return targets


def _sync_specs(plex_url, plex_token, machine_id, libraries, config, specs,
                wait_for_items=False, debug=False):
    """Resolve every spec against Plex and sync the resulting collections.

    Items UMTK wrote this run may not be indexed by Plex yet. When that is
    possible (wait_for_items), retry the lookup the way the sort-title pass does
    - up to metadata_retry_limit times, a minute apart - so a placeholder that
    lands late still makes it into the collection on this run. One shared wait
    covers every collection rather than one wait each.
    """
    targets = _resolve_targets(libraries, config, specs, debug)
    if not targets:
        return

    try:
        max_retries = int(config.get('metadata_retry_limit', 4))
    except (TypeError, ValueError):
        max_retries = 4

    # Several targets can share a library and that fetch pulls a whole section,
    # so cache it - and drop the cache between attempts to force a fresh read.
    library_items_cache = {}
    attempt = 0

    while True:
        for target in targets:
            plex_items = _library_items(plex_url, plex_token, target['library']['key'],
                                        library_items_cache, debug)
            by_tmdb, by_tvdb = _build_id_index(plex_items)
            target['desired'], target['missing'] = target['spec']['resolve'](by_tmdb, by_tvdb)

        missing = [(t['spec']['label'](t['library_name']), title)
                   for t in targets for title in t['missing']]
        if not missing:
            break

        if not wait_for_items:
            if debug:
                print(f"{BLUE}[DEBUG] Not waiting for Plex to index - no new files "
                      f"were written this run{RESET}")
            break

        if attempt >= max_retries:
            print(f"{RED}The following item(s) could not be found in Plex after "
                  f"{max_retries + 1} attempts:{RESET}")
            for label, title in missing:
                print(f"  - {title} ({label})")
            break

        attempt += 1
        print(f"{ORANGE}The following {len(missing)} item(s) are not yet present in Plex:{RESET}")
        for label, title in missing:
            print(f"  - {title} ({label})")
        print(f"{ORANGE}Waiting 1 minute before retry ({attempt}/{max_retries})...{RESET}",
              flush=True)
        time.sleep(PLEX_ITEM_RETRY_WAIT)
        library_items_cache.clear()

    for target in targets:
        spec = target['spec']
        label = spec['label'](target['library_name'])

        # Already listed above when we waited for them.
        if target['missing'] and not wait_for_items:
            print(f"{ORANGE}{label}: {len(target['missing'])} item(s) not in this "
                  f"library yet:{RESET}")
            for title in target['missing']:
                print(f"  - {title}")

        if not target['desired']:
            print(f"{ORANGE}{label}: none of the items are in this library - "
                  f"leaving collection '{spec['name']}' untouched{RESET}")
            continue

        _sync_collection(plex_url, plex_token, machine_id, target['library']['key'],
                         target['library_name'], spec['type'], spec['name'],
                         target['desired'], debug)


def _trending_spec(lst, config):
    """Turn a trending list into a spec for _sync_specs."""
    list_name = lst.get('name') or 'Unnamed list'
    expected_type = 'show' if lst.get('type') == 'tv' else 'movie'

    return {
        'name': trending_collection_name(config, lst),
        'type': expected_type,
        'library_names': [(lst.get('plex_library') or '').strip()],
        'label': lambda _library_name, n=list_name: f"Trending list '{n}'",
        'resolve': lambda by_tmdb, by_tvdb, l=lst: _resolve_items(l, by_tmdb, by_tvdb),
    }


def sync_trending_collections(plex_url, plex_token, lists, config, debug=False,
                              wait_for_items=False):
    """Build/update the Plex collections of every trending list with build_in_plex."""
    if not lists:
        return

    machine_id = get_plex_machine_identifier(plex_url, plex_token, debug)
    if not machine_id:
        print(f"{RED}Could not determine the Plex machine identifier - "
              f"skipping collection building{RESET}")
        return

    libraries = get_plex_libraries(plex_url, plex_token, debug)
    if not libraries:
        print(f"{RED}Could not fetch Plex libraries - skipping collection building{RESET}")
        return

    specs = [_trending_spec(lst, config) for lst in lists]
    _sync_specs(plex_url, plex_token, machine_id, libraries, config, specs,
                wait_for_items, debug)


# ── Coming Soon collections ───────────────────────────────────────────────

# Per-collection option -> the collector key it pulls in, and its label.
TSSK_INCLUDE_SOURCES = (
    ('include_new_season_soon', 'tssk_new_season_soon', 'New Season Soon'),
    ('include_upcoming_episode', 'tssk_upcoming_episode', 'Upcoming Episode'),
    ('include_upcoming_finale', 'tssk_upcoming_finale', 'Upcoming Finale'),
)

# Items with no date sort last rather than jumping to the front.
_NO_DATE = '9999-12-31'


def _is_true(value):
    """Parse a config flag that may be a real bool or a YAML/WebUI string."""
    return str(value).lower() == 'true'


def _name_list(value):
    """A YAML list / comma-separated string as a list of names."""
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [n.strip() for n in str(value or '').split(',') if n.strip()]


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


def _instance_items(groups, instances):
    """Items from the named instances; an empty 'instances' means all of them.

    'groups' is the per-instance shape the collector carries:
    [{'instance': name, 'items': [...]}, ...]. Names are only guaranteed unique
    by the WebUI's save validation, so match on them without building a
    name-keyed dict that would silently drop a duplicate.
    """
    wanted = set(instances or ())
    return [group.get('items') or [] for group in (groups or [])
            if not wanted or group.get('instance') in wanted]


def _collection_items(entry, collector, debug=False):
    """One entry's deduped, date-ordered item list."""
    is_tv = entry.get('type') == 'tv'
    source_key = 'upcoming_shows' if is_tv else 'upcoming_movies'
    id_key = 'tvdbId' if is_tv else 'tmdbId'
    date_key = 'airDate' if is_tv else 'releaseDate'
    instances = entry.get('instances') or []
    name = entry.get('name')

    groups = _instance_items(collector.get(source_key), instances)

    if is_tv:
        for option_key, collector_key, label in TSSK_INCLUDE_SOURCES:
            if not _is_true(entry.get(option_key, False)):
                continue
            available = collector.get(collector_key)
            if available is None:
                print(f"{ORANGE}Coming Soon '{name}': TSSK '{label}' is switched on but TSSK "
                      f"produced no results this run — skipping that category{RESET}")
                continue
            extra = _instance_items(available, instances)
            if debug:
                print(f"{BLUE}[DEBUG] Coming Soon '{name}': adding "
                      f"{sum(len(g) for g in extra)} show(s) from TSSK '{label}'{RESET}")
            groups.extend(extra)

    # UMTK's own entry wins for a show that is also in a TSSK category.
    return _sorted_by_date(dedupe_by_key(groups, id_key), date_key)


def _entry_libraries(entry, config):
    """The libraries an entry builds in, falling back to the first configured one."""
    libraries = _name_list(entry.get('libraries'))
    if libraries:
        return libraries
    fallback_key = 'tv_libraries' if entry.get('type') == 'tv' else 'movie_libraries'
    fallback = _first_library_name(config.get(fallback_key))
    return [fallback] if fallback else []


def _coming_soon_spec(entry, config, collector, debug=False):
    """Turn one coming_soon_collections entry into a spec for _sync_specs."""
    name = entry.get('name')
    expected_type = 'show' if entry.get('type') == 'tv' else 'movie'
    id_key = 'tvdbId' if expected_type == 'show' else 'tmdbId'

    if not name:
        print(f"{ORANGE}Coming Soon collection without a name - skipping{RESET}")
        return None

    items = _collection_items(entry, collector, debug)
    if not items:
        print(f"{ORANGE}Coming Soon '{name}': nothing to put in the collection this run{RESET}")
        return None

    library_names = _entry_libraries(entry, config)
    if not library_names:
        print(f"{ORANGE}Coming Soon '{name}': no Plex library configured - "
              f"skipping collection{RESET}")
        return None

    def resolve(by_tmdb, by_tvdb):
        # ratingKeys are per library, so this runs once per target library.
        index = by_tvdb if id_key == 'tvdbId' else by_tmdb
        return _resolve_by_id(items, index, id_key)

    return {
        'name': name,
        'type': expected_type,
        'library_names': library_names,
        'label': lambda library_name, n=name: f"Coming Soon '{n}' ({library_name})",
        'resolve': resolve,
    }


def sync_upcoming_collections(plex_url, plex_token, config, collector, debug=False,
                              wait_for_items=False):
    """Build/update every configured Coming Soon collection directly in Plex.

    Each coming_soon_collections entry names its own collection, the libraries to
    build it in and the Radarr/Sonarr instances to draw from. Items are ordered by
    expected release date (movies) / air date (shows); a TV entry can also absorb
    TSSK's upcoming categories - see TSSK_INCLUDE_SOURCES.
    """
    entries = [e for e in (config.get('coming_soon_collections') or [])
               if isinstance(e, dict)]
    if not entries:
        return

    print(f"\n{BLUE}{'=' * 50}{RESET}")
    print(f"{BLUE}Building Coming Soon collections in Plex...{RESET}")
    print(f"{BLUE}{'=' * 50}{RESET}\n")

    machine_id = get_plex_machine_identifier(plex_url, plex_token, debug)
    if not machine_id:
        print(f"{RED}Could not determine the Plex machine identifier - "
              f"skipping collection building{RESET}")
        return

    libraries = get_plex_libraries(plex_url, plex_token, debug)
    if not libraries:
        print(f"{RED}Could not fetch Plex libraries - skipping collection building{RESET}")
        return

    specs = [spec for spec in
             (_coming_soon_spec(e, config, collector, debug) for e in entries)
             if spec]
    _sync_specs(plex_url, plex_token, machine_id, libraries, config, specs,
                wait_for_items, debug)
