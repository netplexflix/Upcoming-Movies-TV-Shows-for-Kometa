"""
TSSK - TV Show Status for Kometa
Main execution logic, callable from UMTK orchestrator.
"""

from datetime import datetime

from umtk.constants import VERSION
from umtk.utils import dedupe_by_key, sanitize_instance_name
from .constants import IS_DOCKER, GREEN, ORANGE, BLUE, RED, RESET
from .config_loader import (
    ensure_output_directory,
    get_config_section
)
from .sonarr import (
    process_sonarr_url,
    get_sonarr_series_and_tags
)
from .finders import (
    find_new_season_shows,
    find_upcoming_regular_episodes,
    find_upcoming_finales,
    find_recent_season_finales,
    find_recent_final_episodes,
    find_new_season_started
)
from .yaml_generators import (
    create_collection_yaml,
    create_overlay_yaml,
    create_new_show_collection_yaml,
    create_new_show_overlay_yaml,
    create_returning_show_collection_yaml,
    create_returning_show_overlay_yaml,
    create_ended_show_collection_yaml,
    create_ended_show_overlay_yaml,
    create_canceled_show_collection_yaml,
    create_canceled_show_overlay_yaml
)
from .plex_integration import update_plex_sort_titles


def run_tssk(config, localization=None):
    """
    Run TSSK processing with the given config dict.

    Config should contain both TSSK-specific settings and shared credentials
    (sonarr_instances, plex_url, plex_token, etc.) already merged in.

    Args:
        config: dict with all TSSK settings + shared credentials
        localization: dict with localization settings (or None for English defaults)
    """
    start_time = datetime.now()
    print(f"\n{BLUE}{'*' * 40}\n{'*' * 8} TSSK (via UMTK {VERSION}) {'*' * 2}\n{'*' * 40}{RESET}")

    # Verify output directory
    output_dir = ensure_output_directory()
    print(f"Output directory: {output_dir}\n")

    # Load localization if not provided
    if localization is None:
        from .config_loader import load_localization
        localization = load_localization()

    # Get ignore_finales_tags configuration
    ignore_finales_tags_config = config.get('ignore_finales_tags', '')
    ignore_finales_tags = []
    if ignore_finales_tags_config:
        ignore_finales_tags = [tag.strip() for tag in str(ignore_finales_tags_config).split(',') if tag.strip()]

    # Get use_tvdb configuration
    use_tvdb = config.get('use_tvdb', False)

    # Get category-specific future_days values, with fallback to main future_days
    future_days = config.get('future_days', 14)
    future_days_new_season = config.get('future_days_new_season', future_days)
    future_days_upcoming_episode = config.get('future_days_upcoming_episode', future_days)
    future_days_upcoming_finale = config.get('future_days_upcoming_finale', future_days)

    # Get recent days values
    recent_days_season_finale = config.get('recent_days_season_finale', 14)
    recent_days_final_episode = config.get('recent_days_final_episode', 14)
    recent_days_new_season_started = config.get('recent_days_new_season_started', 7)
    recent_days_new_show = config.get('recent_days_new_show', 7)
    debug = config.get('debug', False)

    utc_offset = float(config.get('utc_offset', 0))
    skip_unmonitored = str(config.get("skip_unmonitored", "false")).lower() == "true"

    # Get process flags for each category (default to True if not specified)
    process_new_shows = str(config.get('process_new_shows', 'true')).lower() == 'true'
    process_new_season_soon = str(config.get('process_new_season_soon', 'true')).lower() == 'true'
    process_new_season_started = str(config.get('process_new_season_started', 'true')).lower() == 'true'
    process_upcoming_episode = str(config.get('process_upcoming_episode', 'true')).lower() == 'true'
    process_upcoming_finale = str(config.get('process_upcoming_finale', 'true')).lower() == 'true'
    process_season_finale = str(config.get('process_season_finale', 'true')).lower() == 'true'
    process_final_episode = str(config.get('process_final_episode', 'true')).lower() == 'true'
    process_returning_shows = str(config.get('process_returning_shows', 'true')).lower() == 'true'
    process_ended_shows = str(config.get('process_ended_shows', 'true')).lower() == 'true'
    process_canceled_shows = str(config.get('process_canceled_shows', 'true')).lower() == 'true'

    # Print chosen values
    print(f"future_days_new_season: {future_days_new_season}")
    print(f"recent_days_new_season_started: {recent_days_new_season_started}")
    print(f"future_days_upcoming_episode: {future_days_upcoming_episode}")
    print(f"future_days_upcoming_finale: {future_days_upcoming_finale}")
    print(f"recent_days_season_finale: {recent_days_season_finale}")
    print(f"recent_days_final_episode: {recent_days_final_episode}")
    print(f"recent_days_new_show: {recent_days_new_show}")
    print(f"skip_unmonitored: {skip_unmonitored}")
    print(f"ignore_finales_tags: {ignore_finales_tags}\n")
    print(f"UTC offset: {utc_offset} hours\n")

    # Plex configuration
    plex_url = config.get('plex_url', '')
    plex_token = config.get('plex_token', '')
    tv_libraries = config.get('tv_libraries', '')
    edit_sort_titles = str(config.get('edit_sort_titles', 'false')).lower() == 'true'
    edit_sort_titles_new_season_soon = str(config.get('edit_sort_titles_new_season_soon', 'true')).lower() == 'true'
    edit_sort_titles_upcoming_episode = str(config.get('edit_sort_titles_upcoming_episode', 'false')).lower() == 'true'
    edit_sort_titles_upcoming_finale = str(config.get('edit_sort_titles_upcoming_finale', 'false')).lower() == 'true'

    if edit_sort_titles:
        if not plex_url or not plex_token or not tv_libraries:
            print(f"{ORANGE}edit_sort_titles is enabled but plex_url, plex_token, or tv_libraries is not configured{RESET}")
            edit_sort_titles = False
        else:
            print(f"Edit sort titles: {edit_sort_titles}")
            print(f"  TV libraries: {tv_libraries}")
            print(f"  New Season Soon: {edit_sort_titles_new_season_soon}")
            print(f"  Upcoming Episode: {edit_sort_titles_upcoming_episode}")
            print(f"  Upcoming Finale: {edit_sort_titles_upcoming_finale}")

    # Multi-instance support
    sonarr_instances = config.get('sonarr_instances', [])
    output_mode = config.get('instance_output_mode', 'combined')

    instance_warnings = []

    if not sonarr_instances:
        print(f"{RED}No Sonarr instances configured. TSSK cannot run.{RESET}")
        return instance_warnings

    # Per-instance result accumulators
    instance_results = []

    for instance in sonarr_instances:
        instance_name = instance.get('name', 'Sonarr')
        sonarr_timeout = int(instance.get('timeout', 90))

        if len(sonarr_instances) > 1:
            print(f"\n{BLUE}--- Sonarr Instance: {instance_name} ---{RESET}")

        try:
            sonarr_url = process_sonarr_url(instance['url'], instance['api_key'], sonarr_timeout)
            sonarr_api_key = instance['api_key']
        except (ConnectionError, Exception) as e:
            print(f"{RED}Error connecting to Sonarr instance '{instance_name}': {str(e)}{RESET}")
            instance_warnings.append(f"Sonarr instance '{instance_name}': {str(e)}")
            if len(sonarr_instances) > 1:
                print(f"{ORANGE}Continuing with next instance...{RESET}")
            continue

        # Get series and tags from Sonarr in one call
        all_series, tag_mapping = get_sonarr_series_and_tags(sonarr_url, sonarr_api_key, sonarr_timeout)

        # Track all tvdbIds to exclude from other categories
        all_excluded_tvdb_ids = set()

        matched_shows = []
        skipped_shows = []
        new_season_started_shows = []
        upcoming_eps = []
        finale_eps = []
        season_finale_shows = []
        final_episode_shows = []

        # ---- New Season Soon ----
        if process_new_season_soon:
            matched_shows, skipped_shows = find_new_season_shows(
                sonarr_url, sonarr_api_key, all_series, tag_mapping, future_days_new_season, utc_offset, skip_unmonitored
            )

            if matched_shows:
                print(f"\n{GREEN}Shows with a new season starting within {future_days_new_season} days:{RESET}")
                for show in matched_shows:
                    print(f"- {show['title']} (Season {show['seasonNumber']}) airs on {show['airDate']}")
            else:
                print(f"\n{RED}No shows with new seasons starting within {future_days_new_season} days.{RESET}")

        # ---- New Season Started ----
        if process_new_season_started:
            new_season_started_shows = find_new_season_started(
                sonarr_url, sonarr_api_key, all_series, recent_days_new_season_started, utc_offset, skip_unmonitored
            )

            for show in new_season_started_shows:
                if show.get('tvdbId'):
                    all_excluded_tvdb_ids.add(show['tvdbId'])

            if new_season_started_shows:
                print(f"\n{GREEN}Shows with a new season that started within the past {recent_days_new_season_started} days:{RESET}")
                for show in new_season_started_shows:
                    print(f"- {show['title']} (Season {show['seasonNumber']}) started on {show['airDate']}")

        # ---- Upcoming Regular Episodes ----
        if process_upcoming_episode:
            upcoming_eps, skipped_eps = find_upcoming_regular_episodes(
                sonarr_url, sonarr_api_key, all_series, future_days_upcoming_episode, utc_offset, skip_unmonitored, ignore_finales_tags, tag_mapping
            )

            upcoming_eps = [show for show in upcoming_eps if show.get('tvdbId') not in all_excluded_tvdb_ids]

            if upcoming_eps:
                print(f"\n{GREEN}Shows with upcoming non-finale episodes within {future_days_upcoming_episode} days:{RESET}")
                for show in upcoming_eps:
                    print(f"- {show['title']} (S{show['seasonNumber']}E{show['episodeNumber']}) airs on {show['airDate']}")

        # ---- Upcoming Finale Episodes ----
        if process_upcoming_finale:
            finale_eps, skipped_finales = find_upcoming_finales(
                sonarr_url, sonarr_api_key, all_series, future_days_upcoming_finale, utc_offset, skip_unmonitored, ignore_finales_tags, tag_mapping
            )

            if finale_eps:
                print(f"\n{GREEN}Shows with upcoming season finales within {future_days_upcoming_finale} days:{RESET}")
                for show in finale_eps:
                    print(f"- {show['title']} (S{show['seasonNumber']}E{show['episodeNumber']}) airs on {show['airDate']}")

        # ---- Recent Season Finales ----
        if process_season_finale:
            season_finale_shows = find_recent_season_finales(
                sonarr_url, sonarr_api_key, all_series, recent_days_season_finale, utc_offset, skip_unmonitored, ignore_finales_tags, tag_mapping
            )

            for show in season_finale_shows:
                if show.get('tvdbId'):
                    all_excluded_tvdb_ids.add(show['tvdbId'])

            if season_finale_shows:
                print(f"\n{GREEN}Shows with a season finale that aired within the past {recent_days_season_finale} days:{RESET}")
                for show in season_finale_shows:
                    print(f"- {show['title']} (S{show['seasonNumber']}E{show['episodeNumber']}) aired on {show['airDate']}")

        # ---- Recent Final Episodes ----
        if process_final_episode:
            final_episode_shows = find_recent_final_episodes(
                sonarr_url, sonarr_api_key, all_series, recent_days_final_episode, utc_offset, skip_unmonitored, ignore_finales_tags, tag_mapping
            )

            for show in final_episode_shows:
                if show.get('tvdbId'):
                    all_excluded_tvdb_ids.add(show['tvdbId'])

            if final_episode_shows:
                print(f"\n{GREEN}Shows with a final episode that aired within the past {recent_days_final_episode} days:{RESET}")
                for show in final_episode_shows:
                    print(f"- {show['title']} (S{show['seasonNumber']}E{show['episodeNumber']}) aired on {show['airDate']}")

        instance_results.append({
            'name': instance_name,
            'matched_shows': matched_shows,
            'skipped_shows': skipped_shows,
            'new_season_started_shows': new_season_started_shows,
            'upcoming_eps': upcoming_eps,
            'finale_eps': finale_eps,
            'season_finale_shows': season_finale_shows,
            'final_episode_shows': final_episode_shows,
            'all_series': all_series,
        })

    if not instance_results:
        print(f"{RED}No Sonarr instances connected successfully. TSSK cannot generate YMLs.{RESET}")
        return instance_warnings

    # ---- Generate YML files ----
    # Plex-based generators (don't depend on Sonarr data, always single output)
    if process_new_shows:
        create_new_show_overlay_yaml("TSSK_TV_NEW_SHOW_OVERLAYS.yml",
                                     {"backdrop": get_config_section(config, "backdrop_new_show"),
                                      "text": get_config_section(config, "text_new_show")},
                                     recent_days_new_show, config, "backdrop_new_show")

        create_new_show_collection_yaml("TSSK_TV_NEW_SHOW_COLLECTION.yml", config, recent_days_new_show)
        print(f"\n'New shows' overlay and collection .ymls created for shows added within the past {GREEN}{recent_days_new_show}{RESET} days")

    if process_returning_shows:
        create_returning_show_overlay_yaml("TSSK_TV_RETURNING_OVERLAYS.yml",
                                          {"backdrop": config.get("backdrop_returning", {}),
                                           "text": config.get("text_returning", {})}, use_tvdb, config, "backdrop_returning")

        create_returning_show_collection_yaml("TSSK_TV_RETURNING_COLLECTION.yml", config, use_tvdb)
        print(f"\n'Returning shows' overlay and collection .ymls created using {'TVDB' if use_tvdb else 'TMDB'} status filtering")

    if process_ended_shows:
        create_ended_show_overlay_yaml("TSSK_TV_ENDED_OVERLAYS.yml",
                                     {"backdrop": config.get("backdrop_ended", {}),
                                      "text": config.get("text_ended", {})}, use_tvdb, config, "backdrop_ended")

        create_ended_show_collection_yaml("TSSK_TV_ENDED_COLLECTION.yml", config, use_tvdb)
        print(f"'Ended shows' overlay and collection .ymls created using {'TVDB' if use_tvdb else 'TMDB'} status filtering")

    if process_canceled_shows:
        create_canceled_show_overlay_yaml("TSSK_TV_CANCELED_OVERLAYS.yml",
                                         {"backdrop": config.get("backdrop_canceled", {}),
                                          "text": config.get("text_canceled", {})}, use_tvdb, config, "backdrop_canceled")

        create_canceled_show_collection_yaml("TSSK_TV_CANCELED_COLLECTION.yml", config, use_tvdb)
        print(f"'Canceled shows' overlay and collection .ymls created using {'TVDB' if use_tvdb else 'TMDB'} status filtering")

    # Sonarr-data generators: combined or split mode
    def _generate_sonarr_ymls(suffix, matched_shows, new_season_started_shows,
                               upcoming_eps, finale_eps, season_finale_shows, final_episode_shows):
        """Generate the Sonarr-data-based YML files with optional filename suffix."""
        if process_new_season_soon:
            create_overlay_yaml(f"TSSK_TV_NEW_SEASON_OVERLAYS{suffix}.yml", matched_shows,
                               {"backdrop": config.get("backdrop_new_season", config.get("backdrop", {})),
                                "text": config.get("text_new_season", config.get("text", {}))}, config, "backdrop_new_season", localization)
            create_collection_yaml(f"TSSK_TV_NEW_SEASON_COLLECTION{suffix}.yml", matched_shows, config)

        if process_new_season_started:
            create_overlay_yaml(f"TSSK_TV_NEW_SEASON_STARTED_OVERLAYS{suffix}.yml", new_season_started_shows,
                               {"backdrop": config.get("backdrop_new_season_started", {}),
                                "text": config.get("text_new_season_started", {})}, config, "backdrop_new_season_started", localization)
            create_collection_yaml(f"TSSK_TV_NEW_SEASON_STARTED_COLLECTION{suffix}.yml", new_season_started_shows, config)

        if process_upcoming_episode:
            create_overlay_yaml(f"TSSK_TV_UPCOMING_EPISODE_OVERLAYS{suffix}.yml", upcoming_eps,
                               {"backdrop": config.get("backdrop_upcoming_episode", {}),
                                "text": config.get("text_upcoming_episode", {})}, config, "backdrop_upcoming_episode", localization)
            create_collection_yaml(f"TSSK_TV_UPCOMING_EPISODE_COLLECTION{suffix}.yml", upcoming_eps, config)

        if process_upcoming_finale:
            create_overlay_yaml(f"TSSK_TV_UPCOMING_FINALE_OVERLAYS{suffix}.yml", finale_eps,
                               {"backdrop": config.get("backdrop_upcoming_finale", {}),
                                "text": config.get("text_upcoming_finale", {})}, config, "backdrop_upcoming_finale", localization)
            create_collection_yaml(f"TSSK_TV_UPCOMING_FINALE_COLLECTION{suffix}.yml", finale_eps, config)

        if process_season_finale:
            create_overlay_yaml(f"TSSK_TV_SEASON_FINALE_OVERLAYS{suffix}.yml", season_finale_shows,
                               {"backdrop": config.get("backdrop_season_finale", {}),
                                "text": config.get("text_season_finale", {})}, config, "backdrop_season_finale", localization)
            create_collection_yaml(f"TSSK_TV_SEASON_FINALE_COLLECTION{suffix}.yml", season_finale_shows, config)

        if process_final_episode:
            create_overlay_yaml(f"TSSK_TV_FINAL_EPISODE_OVERLAYS{suffix}.yml", final_episode_shows,
                               {"backdrop": config.get("backdrop_final_episode", {}),
                                "text": config.get("text_final_episode", {})}, config, "backdrop_final_episode", localization)
            create_collection_yaml(f"TSSK_TV_FINAL_EPISODE_COLLECTION{suffix}.yml", final_episode_shows, config)

    if output_mode == 'combined' or len(instance_results) == 1:
        # Merge results from all instances
        merged_matched = dedupe_by_key([r['matched_shows'] for r in instance_results], 'tvdbId')
        merged_new_season_started = dedupe_by_key([r['new_season_started_shows'] for r in instance_results], 'tvdbId')
        merged_upcoming = dedupe_by_key([r['upcoming_eps'] for r in instance_results], 'tvdbId')
        merged_finales = dedupe_by_key([r['finale_eps'] for r in instance_results], 'tvdbId')
        merged_season_finales = dedupe_by_key([r['season_finale_shows'] for r in instance_results], 'tvdbId')
        merged_final_eps = dedupe_by_key([r['final_episode_shows'] for r in instance_results], 'tvdbId')

        _generate_sonarr_ymls("", merged_matched, merged_new_season_started,
                              merged_upcoming, merged_finales, merged_season_finales, merged_final_eps)
    else:
        # Split mode: per-instance YML files
        for result in instance_results:
            suffix = f"_{sanitize_instance_name(result['name'])}"
            _generate_sonarr_ymls(suffix, result['matched_shows'], result['new_season_started_shows'],
                                  result['upcoming_eps'], result['finale_eps'],
                                  result['season_finale_shows'], result['final_episode_shows'])
            print(f"{GREEN}TSSK YAML files created for instance '{result['name']}'{RESET}")

    # Update Plex sort titles (uses merged data from all instances)
    merged_all_series_for_plex = dedupe_by_key([r['all_series'] for r in instance_results], 'tvdbId')
    if edit_sort_titles:
        shows_to_update = []
        if edit_sort_titles_new_season_soon:
            shows_to_update.extend(dedupe_by_key([r['matched_shows'] for r in instance_results], 'tvdbId'))
        if edit_sort_titles_upcoming_episode:
            shows_to_update.extend(dedupe_by_key([r['upcoming_eps'] for r in instance_results], 'tvdbId'))
        if edit_sort_titles_upcoming_finale:
            shows_to_update.extend(dedupe_by_key([r['finale_eps'] for r in instance_results], 'tvdbId'))
        shows_to_update = dedupe_by_key([shows_to_update], 'tvdbId')
        update_plex_sort_titles(plex_url, plex_token, tv_libraries, shows_to_update, merged_all_series_for_plex, config)

    # ---- Skipped Shows ----
    if process_new_season_soon:
        all_skipped = []
        for r in instance_results:
            all_skipped.extend(r['skipped_shows'])
        if all_skipped:
            print(f"\n{ORANGE}Skipped shows (unmonitored or new show):{RESET}")
            for show in all_skipped:
                print(f"- {show['title']} (Season {show['seasonNumber']}) airs on {show['airDate']}")

    # Print processing summary
    print(f"\n{BLUE}{'=' * 40}")
    print("TSSK Processing Summary:")
    print(f"{'=' * 40}{RESET}")
    categories = [
        ("New Shows", process_new_shows),
        ("New Season Soon", process_new_season_soon),
        ("New Season Started", process_new_season_started),
        ("Upcoming Episode", process_upcoming_episode),
        ("Upcoming Finale", process_upcoming_finale),
        ("Season Finale", process_season_finale),
        ("Final Episode", process_final_episode),
        ("Returning Shows", process_returning_shows),
        ("Ended Shows", process_ended_shows),
        ("Canceled Shows", process_canceled_shows)
    ]

    for category, enabled in categories:
        status = f"{GREEN}✓ Processed{RESET}" if enabled else f"{ORANGE}✗ Skipped{RESET}"
        print(f"{category:.<30} {status}")

    # Calculate and display runtime
    end_time = datetime.now()
    runtime = end_time - start_time
    hours, remainder = divmod(runtime.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    runtime_formatted = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

    print(f"\nTSSK run completed. Runtime: {runtime_formatted}")

    return instance_warnings
