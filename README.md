<p align="center">
<img width="567" height="204" alt="UMTK_Logo2" src="https://github.com/user-attachments/assets/78952905-6b14-421e-bd08-9195cda5ba94" /><br>
   <a href="https://github.com/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa/releases"><img alt="GitHub Release" src="https://img.shields.io/github/v/release/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa?style=plastic"></a> <a href="https://hub.docker.com/repository/docker/netplexflix/umtk"><img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/netplexflix/umtk?style=plastic"></a> <a href="https://discord.gg/VBNUJd7tx3"><img alt="Discord" src="https://img.shields.io/discord/1329439972796928041?style=plastic&label=Discord"></a>
</p>

**UMTK** (Upcoming Movies & TV Shows for Kometa) manages your Plex media collections and overlays using [Kometa](https://kometa.wiki/en/latest/) (formerly Plex Meta Manager).<br>
It includes:

- **Coming Soon** — Checks [Radarr](https://radarr.video/) and [Sonarr](https://sonarr.tv/) for upcoming (monitored) content expected to be released/air within x days. Either downloads trailers using [yt-dlp](https://github.com/yt-dlp/yt-dlp) or creates placeholder video files. For movies, Plex's 'editions' feature is used (Plex Pass required for Server admin account). For TV Shows, the trailer or placeholder file is saved as a "special" (S00E00).
- **TV Show Status** (formerly [TSSK](https://github.com/netplexflix/TV-show-status-for-Kometa)) — Checks your Sonarr for TV show statuses and creates `.yml` files for overlays and collections. Categories include: new shows, new seasons, upcoming episodes, upcoming finales, season finales, final episodes, returning, ended, and canceled shows.
- **Trending** — Uses MDBList to create "Trending" categories and creates placeholder files for missing items with an overlay indicating that a request is required. Optionally applies a TOP 10 ranking overlay.

## Examples:
### TV Show Status Overlays:

![Image](https://github.com/user-attachments/assets/e7c517cc-5164-41d9-8e5e-015577aad36e)

### Coming Soon Movies:

<img width="1617" height="303" alt="Image" src="https://github.com/user-attachments/assets/51bdcbb2-1d0a-4d2f-b6ac-662678f54bb5" />

### Coming Soon TV Shows:

<img width="1617" height="303" alt="Image" src="https://github.com/user-attachments/assets/5c0b5f80-329e-4c17-ba1b-cd71f22e9b92" />

### TV Shows Trending TOP 10:

<img width="2000" height="375" alt="Image" src="https://github.com/user-attachments/assets/5559d281-6fc2-4e6a-9c72-1f49f45f5ef6" />

In this example 3 trending shows have not been added to Sonarr (and are not available).
This example uses the Kabeb template + TV Show Status overlays.

---

## 📑 Table of Contents

- [🛠️ Installation](#installation)
  - [Option 1: Docker](#option-1-docker)
    - [Step 1: Install Docker](#step-1-install-docker)
    - [Step 2: Create Docker Compose File](#step-2-create-docker-compose-file)
    - [Step 3: Create Required Directories](#step-3-create-required-directories)
    - [Step 4: Configure Your Settings](#step-4-configure-your-settings)
    - [Step 5: Update Media Paths](#step-5-update-media-paths)
    - [Step 6: Run UMTK](#step-6-run-umtk)
    - [Step 7: Add the yml files to your Kometa config](#step-7-add-the-yml-files-to-your-kometa-config)
  - [Option 2: Manual Installation](#option-2-manual-installation)
    - [Step 1: Clone the repository](#step-1-clone-the-repository)
    - [Step 2: Install Python dependencies](#step-2-install-python-dependencies)
    - [Step 3: Install ffmpeg (for trailer downloads)](#step-3-install-ffmpeg-for-trailer-downloads)
    - [Step 4: Configure Your Config Settings](#2.4)
    - [Step 5: Add the yml files to your Kometa config](#step-5-add-the-yml-files-to-your-kometa-config)
- [🖥️ Web UI](#web-ui)
- [⚙️ Configuration](#️-configuration)
  - [General](#general)
  - [Radarr Configuration (for Movies)](#radarr-configuration-for-movies)
  - [Sonarr Configuration (for TV Shows)](#sonarr-configuration-for-tv-shows)
  - [Plex Configuration (for metadata edits)](#plex-configuration-for-metadata-edits)
  - [Movie Settings](#movie-settings)
  - [TV Show Settings](#tv-show-settings)
  - [Trending](#trending)
  - [Overlay & Collection Settings](#overlay--collection-settings)
  - [TSSK Configuration (TV Show Status)](#tssk-configuration-tv-show-status)
- [🗂️ Create your Coming Soon Collection](#️-create-your-coming-soon-collection)
- [☄️ Add to Kometa Configuration](#️-add-to-kometa-configuration)
- [🍪 Using browser cookies for yt-dlp (Method 1)](#-using-browser-cookies-for-yt-dlp-method-1)
- [📼 Placeholder Video (Method 2)](#-choose-placeholder-video-method-2)
- [🚀 Usage](#-usage)
- [🌐 Localization](#localization)
- [💡 Tips & Best Practices](#-tips--best-practices)
  - [Exclude Upcoming Content from "Recently Added" Sections](#exclude-umtk-content-from-recently-added-sections)
  - [Choosing Between Methods](#choosing-between-methods)
  - [Understanding Movie Release Types](#understanding-movie-release-types)
  - [Scheduling with Cron (Docker)](#scheduling-with-cron-docker)
  - [Prevent Request Platforms from marking coming soon items as available](#prevent-request-platforms)
- [🩺 Troubleshooting Common Issues:](#-troubleshooting-common-issues)
  - [❌ "Connection refused" to Sonarr/Radarr](#-connection-refused-to-sonarrradarr)
  - [❌ "Permission denied" errors](#-permission-denied-errors)
  - [❌ "No config.yml found"](#-no-configyml-found)
  - [❌ yt-dlp fails to download Trailers](#-yt-dlp-fails-to-download-trailers)
  - [❌ A bunch of old movies/shows are being added as Coming Soon](#-a-bunch-of-old-moviesshows-are-being-added-as-coming-soon)

---
<a id="installation"></a>
## 🛠️ Installation

### Option 1: Docker

#### Step 1: Install Docker

1. **Download Docker Desktop** from [docker.com](https://www.docker.com/products/docker-desktop/)
2. **Install and start Docker Desktop** on your computer
3. **Verify installation**: Open a terminal/command prompt and type `docker --version` - you should see a version number

#### Step 2: Create Docker Compose File

1. **Create a new folder** for UMTK on your computer (e.g., `C:\UMTK` or `/home/user/UMTK`)
2. **Create a new file** called `docker-compose.yml` in that folder
3. **Copy and paste this content** into the file:

```yaml
services:
  umtk:
    image: netplexflix/umtk:latest
    container_name: umtk
    ports:
      - "2120:2120" # Web UI
    environment:
      - CRON=0 2 * * * # Run daily at 2am
      - DOCKER=true
      - TZ=America/New_York # Set your timezone
      - PUID=1000 # Set to your user ID (run `id -u` in terminal)
      - PGID=1000 # Set to your group ID (run `id -g` in terminal)
    extra_hosts:
      - "host.docker.internal:host-gateway" # Alternative way to access host
    volumes:
      # Configuration directory (required)
      - ./config:/app/config

      # Video directory for placeholder method (optional - only needed if using method 2)
      - ./video:/video

      # Output directory for generated YAML files (required)
      - ./kometa:/app/kometa

      # UMTK root folders
      - /your/actual/path:/umtkmovies #example: /mnt/media/umtk/movies:/umtkmovies
      - /your/actual/path:/umtktv #example: /mnt/media/umtk/tv:/umtktv

    restart: unless-stopped
```

4. **Update the timezone** in the `TZ` environment variable to [match your location](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) (e.g.: `America/New_York`, `Europe/London`, `Asia/Tokyo`)
5. **Update PUID/PGID** to match your system user (optional - defaults to 1000:1000)

#### Step 3: Create Required Directories

1. **Create the required folders** in your UMTK directory:

   - `config` folder (for configuration files)
   - `video` folder (for placeholder videos)
   - `kometa` folder (for generated YAML files) 

2. **Download the required files**:
   - Go to the [GitHub repository](https://github.com/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa)
   - Download `config/config.sample.yml` and save it as `config/config.yml` in your UMTK folder
   - If using TSSK: Download `config/tssk_config.sample.yml` and save it as `config/tssk_config.yml`
   - Download `video/UMTK.mp4` and save it in your `video` folder (if using placeholder method)
   - You can also use your own video file. Just make sure it is called `UMTK`.

3. **Create your UMTK video file roots**:
   - These will be the folders UMTK creates the trailer or placeholder files in. Make sure it's not within your Arr root path.
   - For example if your Arr roots are `/mnt/media/movies` and `/mnt/media/tv`then you can create `/mnt/media/umtk/movies` and `/mnt/media/umtk/tv`
   - These are the UMTK roots you have to mount in your docker-compose
   
#### Step 4: Configure Your Settings
- You can skip this if you want to edit your settings in the webUI.
- Alternatively you can manually edit your settings in the yml files. See [⚙️ Configuration](#️-configuration)

#### Step 5: Update Media Paths
You must update the media paths in the existing `docker-compose.yml` file.

> [!IMPORTANT]
> **The format is**: `your-actual-path:container-path`

Example:
   - You created `/mnt/media/umtk/movies` and `/mnt/media/umtk/tv`
   - In your config you used `umtk_root_movies: /umtkmovies` and `umtk_root_tv: /umtktv`
   - Then your mounts should look like this:
   ```
         - /mnt/media/umtk/movies:/umtkmovies
         - /mnt/media/umtk/tv:/umtktv
   ```

> [!TIP]
> By default UMTK will output the yml files in a subfolder named `kometa`.<br>
> You can make UMTK output the yml files directly into your `Kometa/config` folder for example by adjusting the volume mount.<br>
> This will make them easily accessible for Kometa.
> e.g.: `/path/to/Kometa/config:/kometa`


#### Step 6: Run UMTK

1. **Open a terminal/command prompt** in your UMTK folder
2. **Type this command** and press Enter:
   ```bash
   docker-compose up -d
   ```
3. **That's it!** UMTK will now run automatically every day at 2 AM

#### Step 7: Add the yml files to your Kometa config
- See [☄️ Add to Kometa Configuration](#️-add-to-kometa-configuration)

---

### Option 2: Manual Installation

#### Step 1: Clone the repository:

```bash
git clone https://github.com/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa.git
cd Upcoming-Movies-TV-Shows-for-Kometa
```

> [!TIP]
> If you don't know what that means, simply download the script by pressing the green 'Code' button above and then 'Download Zip'.  
> Extract the files to your desired folder.

#### Step 2: Install Python dependencies:

- Ensure you have [Python](https://www.python.org/downloads/) installed (`>=3.11`)
- Open a Terminal in the script's directory

> [!TIP]
> Windows Users:  
> Go to the UMTK folder (where UMTK.py is). Right mouse click on an empty space in the folder and click `Open in Windows Terminal`.

- Install the required dependencies:

```sh
pip install -r requirements.txt
```

#### Step 3: Install ffmpeg (for trailer downloads)

[ffmpeg](https://www.ffmpeg.org/) is required by yt-dlp for postprocessing when downloading trailers.
Check [THIS WIKI](https://www.reddit.com/r/youtubedl/wiki/ffmpeg/#wiki_where_do_i_get_ffmpeg.3F) for installation instructions.

<a id="2.4"></a>
#### Step 4: Configure Your Config Settings
- See [⚙️ Configuration](#️-configuration)
  
#### Step 5: Add the yml files to your Kometa config
- See [☄️ Add to Kometa Configuration](#️-add-to-kometa-configuration)

> [!TIP]
> Windows users can create a batch file to quickly launch the script.<br/>
> Type `"[path to your python.exe]" "[path to the script]" -r pause"` into a text editor
>
> For example:
> ```
>"C:\Users\User1\AppData\Local\Programs\Python\Python311\python.exe" "P:\UMTK\UMTK.py" -r
>pause
> ```
> Save as a .bat file. You can now double click this batch file to directly launch the script.<br/>
> You can also use this batch file to [schedule](https://www.windowscentral.com/how-create-automated-task-using-task-scheduler-windows-10) the script to run.

---

<a id="web-ui"></a>
## 🖥️ Web UI
<img src="https://github.com/user-attachments/assets/b8f1d7c7-5dfb-431b-9a30-837272459500" width="15%"></img> <img src="https://github.com/user-attachments/assets/c0a5b354-347b-4d1f-932a-dcf0c71bb2d3" width="15%"></img> <img src="https://github.com/user-attachments/assets/cfea0396-28fa-4bbc-a0a5-2d08127f5d2a" width="15%"></img>

UMTK includes a built-in web interface for configuration and monitoring, accessible at `http://localhost:2120` (or `http://your-ip:2120`).
Features:
- **Configuration**: Edit all UMTK and TSSK settings through the UI. Organized in tabs: Connections (Plex/Radarr/Sonarr), UMTK settings, and TSSK settings.
- **Connection Testing**: Test your Plex, Radarr, and Sonarr connections directly from the UI with response time feedback.
- **Scheduler Control**: View the current status (idle/running/stopped), trigger a "Run Now", pause or resume the schedule, and see next/last run times.
- **Live Logs**: Monitor real-time application logs.
- **Update Checker**: Check for new UMTK versions.

> [!TIP]
> All settings can also be edited manually in the YAML config files if you prefer.

---

## ⚙️ Configuration

Rename `config.sample.yml` to `config.yml` and update your settings:

### General:

- **enable_umtk:** Enable/disable the UMTK module — Coming Soon and Trending (default: `true`)
- **enable_tssk:** Enable/disable the TSSK module — TV Show Status (default: `false`). See [TSSK Configuration](#tssk-configuration-tv-show-status) for settings.
- **movies**: 0 = Don't process, 1 = Download trailers with yt-dlp, 2 = Use placeholder video file
- **tv**: 0 = Don't process, 1 = Download trailers with yt-dlp, 2 = Use placeholder video file
- **method_fallback**: When set to `true`: If trailer downloading fails, UMTK will automatically fallback to using the placeholder method.
- **utc_offset:** Set your [UTC timezone](https://en.wikipedia.org/wiki/List_of_UTC_offsets) offset
  - Examples: LA: `-8`, New York: `-5`, Amsterdam: `+1`, Tokyo: `+9`
- **debug:** Set to `true` to troubleshoot issues
- **cleanup:** Set to `true` (default) to automatically remove trailers/placeholders when actual content is downloaded or no longer valid
- **simplify_next_week_dates:** Set to `true` to simplify dates to `today`, `tomorrow`, `friday` etc if the air date is within the coming week.
- **skip_channels:** Blacklist YouTube channels that create fake trailers

### Radarr Configuration (for Movies):

- **radarr_url:** Your Radarr URL (default: `http://localhost:7878`)
- **radarr_api_key:** Found in Radarr under Settings → General → Security
- **radarr_timeout:** Increase if needed for large libraries

### Sonarr Configuration (for TV Shows):

- **sonarr_url:** Your Sonarr URL (default: `http://localhost:8989`)
- **sonarr_api_key:** Found in Sonarr under Settings → General → Security
- **sonarr_timeout:** Increase if needed for large libraries

### Plex Configuration (for metadata edits):

- **plex_url:** Your Plex URL
- **plex_token:** [How to find your Plex Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
- **movie_libraries:** names of your movie libraries, comma separated
- **tv_libraries:** names of your TV show libraries, comma separated
- **append_dates_to_sort_titles:** Release dates will be added to sort titles so you can sort in order of release date.
- **add_rank_to_sort_title:** Will add the rank in front of the sort title so you can sort in order of rank
- **edit_S00E00_episode_title:** Will name the S00E00 episodes as either `Trailer` or `Coming Soon` depending on whether a trailer was downloaded or placeholder file was used
- **metadata_retry_limit:** How many times to retry metadata edits. This gives Plex some time to pick up the newly created items.

### Movie Settings:

- **future_days_upcoming_movies:** How many days ahead to look for releases (default: `30`)
- **past_days_upcoming_movies:** How many days in the past to look for releases (default: `0` means no limit)
- **include_inCinemas:** Include cinema release dates (default: `false`, only digital/physical)
- **future_only:** `false` (default) will include already-released but not-downloaded movies. `true` only looks at release dates in the future.
- **exclude_radarr_tags**: Skip movies with these tags
- **umtk_root_movies**: Where UMTK will output the movie folders. Docker users: use `/umtkmovies`

### TV Show Settings:

- **future_days_upcoming_shows:** How many days ahead to look for premieres (default: `30`)
- **recent_days_new_show:** How many days back to look for new shows (default: `7`)
- **future_only_tv:** Set to `false` (default) to include already-aired but not-downloaded show premieres
- **exclude_sonarr_tags**: Skip TV Shows with these tags
- **umtk_root_tv**: Where UMTK will output the tv folder. Docker users: use `/umtktv`

> [!IMPORTANT]
> You need to add the `umtk_root` folders to your library folders in Plex (or create separate libraries if you prefer).<br>
> Example for TV:<br>
> <img width="729" height="525" alt="Image" src="https://github.com/user-attachments/assets/8e3e4f4e-b6b7-4ea2-8238-3040a1ff30fe" />

### Trending:
- **trending_movies:** 0 = Don't process, 1 = Download trailers with yt-dlp, 2 = Use placeholder video file
- **trending_tv:** 0 = Don't process, 1 = Download trailers with yt-dlp, 2 = Use placeholder video file
- **label_request_needed:** will add an additional `RequestNeeded` label to trending items not yet monitored in the Arrs
- **mdblist_api_key:** Can be found at https://mdblist.com/preferences/
- **mdblist_movies:** which trending movies list to use. you can create your own.
- **mdblist_movies_limit:** How many items to pull from the trending movies list
- **mdblist_tv:** which trending TV shows list to use. you can create your own.
- **mdblist_tv_limit:** ow many items to pull from the trending TV shows list
> [!TIP]
> With [Pulsarr](https://github.com/jamcalli/Pulsarr) you and your users can easily request missing content by adding it to watchlist in Plex. No external request platforms needed.

### Overlay & Collection Settings:

The remaining settings customize the output .yml files for Kometa.

> [!TIP]
> You can enter any Kometa variables in this block and they will be automatically added in the generated .yml files.</br>

> [!NOTE]
> There are two different overlays:<br>
>
> - One for movies/shows with a release/air date in the future. This overlay will append the release date.<br>
> - One for movies/shows that have already been released/aired but haven't been downloaded yet. Depending on your setup there could be some time between the official release date and when it's actually added to your Plex server. Since the release date is in the past it isn't printed. Instead you can state it's "coming soon". You can disable this category by setting `future_only` to `true`

> [!NOTE] 
> **Date format options:**
>
> - `d`: 1 digit day (1)
> - `dd`: 2 digit day (01)
> - `ddd`: Abbreviated weekday (Mon)
> - `dddd`: Full weekday (Monday)
> - `m`: 1 digit month (1)
> - `mm`: 2 digit month (01)
> - `mmm`: Abbreviated month (Jan)
> - `mmmm`: Full month (January)
> - `yy`: Two digit year (25)
> - `yyyy`: Full year (2025)
>
> Dividers can be `/`, `-` or a space

<a id="tssk-configuration-tv-show-status"></a>
### TSSK Configuration (TV Show Status):

TSSK settings are stored in a separate config file. Rename `tssk_config.sample.yml` to `tssk_config.yml` in your config folder (next to `config.yml`).

> [!NOTE]
> Sonarr/Plex credentials and shared settings (`utc_offset`, `debug`, `simplify_next_week_dates`) are automatically read from the main `config.yml` — you do not need to duplicate them.

#### TSSK General Settings:

- **use_tvdb:** Change to `true` if you prefer TheTVDB statuses for returning and ended. (Note: TheTVDB does not have the 'canceled' status)
- **skip_unmonitored:** Default `true` will skip a show if the upcoming season/episode is unmonitored.
- **edit_sort_titles:** Set to `true` to have TSSK edit sort titles directly in Plex. The air date of the new season premiere will be added to the sort title so you can sort shows by air date.
- **ignore_finales_tags:** Shows with these Sonarr tags will be ignored when checking for finales.

> [!NOTE]
> For some shows, episodes are listed one at a time — usually one week ahead — in TheTVDB/Sonarr. Because of this, TSSK may wrongly think the last episode listed in the season is a finale.
> You can give problematic shows like this a tag in Sonarr (and add that tag to `ignore_finales_tags`) so TSSK will ignore finales for that show and treat the current 'last' episode as a regular episode.

#### TSSK Categories:

Each category can be individually enabled or disabled. Set to `false` to disable:

- **process_new_shows:** New shows that were added in the past x days
- **process_new_season_soon:** Shows for which a new season is airing within x days
- **process_new_season_started:** Shows for which a new season has been added which aired in the past x days
- **process_upcoming_episode:** Shows with upcoming regular episodes within x days
- **process_upcoming_finale:** Shows with upcoming season finales within x days
- **process_season_finale:** Shows for which a season finale was added which aired in the past x days
- **process_final_episode:** Shows for which a final episode was added which aired in the past x days
- **process_returning_shows:** Returning shows
- **process_ended_shows:** Ended shows
- **process_canceled_shows:** Canceled shows

#### TSSK Timeframe Settings:

For each category, you can change the relevant timeframe:

- **recent_days_new_show:** How many days in the past to look for new shows (default: `7`)
- **future_days_new_season:** How many days into the future to look for new seasons (default: `31`)
- **recent_days_new_season_started:** How many days in the past to look for started seasons (default: `7`)
- **future_days_upcoming_episode:** How many days into the future for upcoming episodes (default: `31`)
- **future_days_upcoming_finale:** How many days into the future for upcoming finales (default: `31`)
- **recent_days_season_finale:** How many days in the past for aired season finales (default: `7`)
- **recent_days_final_episode:** How many days in the past for aired final episodes (default: `7`)

#### TSSK Collection & Overlay Settings:

Each category has its own collection and overlay blocks, following the same pattern as the UMTK overlay settings.

- **Collection blocks:** Customize `collection_name`, `item_label`, `build_collection`, `sync_mode`, etc. You can enter any Kometa collection variables.
- **Backdrop blocks:** Enable/disable the backdrop, set colors, size, and positioning. Supports both `back_color` (solid color) and `url` (image) backdrops.
- **Text blocks:** Customize `use_text`, `date_format`, `capitalize_dates`, font color, size, and positioning.

> [!TIP]
> For `New Season Soon`, `New Season Started`, `Upcoming Finale` and `Season Finale` you can use `[#]` in the `use_text` field to display the season number. For example: `"SEASON [#] AIRS"`

> [!TIP]
> `group` and `weight` are used to determine which overlays are applied when multiple are valid for the same show.
> For example: You add a new show, for which season 2 just aired in full yesterday. In this case the following overlays would be valid: `new show`, `new season started` and `season finale`.
> The overlay with the highest `weight` will be applied. If you prefer a different priority, adjust the weights accordingly.
> You can also have multiple overlays applied at the same time by removing `group` and `weight`, in case you position them differently.

> [!NOTE]
> The date format options are the same as listed above in the [Overlay & Collection Settings](#overlay--collection-settings) section.

---

## 🗂️ Create your Coming Soon Collection

In the config example, we use `build_collection: false`.<br>
This will tell Kometa to only apply labels to the content without actually creating the collection directly.<br>
That way we can manually create a smart filter which includes both `Coming Soon` items and `New Season Soon` items from TSSK:<br>
<img width="754" height="198" alt="Image" src="https://github.com/user-attachments/assets/acd4b521-27a8-457f-b056-9f3a8d130442" /><br>
It also makes the collection more flexible allowing filters to be easily added and removed.

You can replace `build_collection: false` with your own [Kometa collection variables](https://metamanager.wiki/en/latest/files/collections/) to have Kometa create the collection directly.

---

## ☄️ Add to Kometa Configuration

Open your **Kometa** config.yml (typically at `Kometa/config/config.yml`) and add the path to the generated .yml files under `collection_files` and `overlay_files`.

Example:

```yaml
TV Shows:
  collection_files:
    # UMTK
    - file: /path/to/UMTK/kometa/UMTK_TV_UPCOMING_SHOWS_COLLECTION.yml
    - file: /path/to/UMTK/kometa/UMTK_TV_TRENDING_COLLECTION.yml
    # TSSK
    - file: /path/to/UMTK/kometa/TSSK_TV_NEW_SHOW_COLLECTION.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_NEW_SEASON_COLLECTION.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_NEW_SEASON_STARTED_COLLECTION.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_UPCOMING_EPISODE_COLLECTION.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_UPCOMING_FINALE_COLLECTION.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_SEASON_FINALE_COLLECTION.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_FINAL_EPISODE_COLLECTION.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_RETURNING_COLLECTION.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_ENDED_COLLECTION.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_CANCELED_COLLECTION.yml
  overlay_files:
    # UMTK
    - file: /path/to/UMTK/kometa/UMTK_TV_UPCOMING_SHOWS_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/UMTK_TV_TOP10_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/UMTK_TV_NEW_SHOWS_OVERLAYS.yml
    # TSSK
    - file: /path/to/UMTK/kometa/TSSK_TV_NEW_SHOW_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_NEW_SEASON_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_NEW_SEASON_STARTED_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_UPCOMING_EPISODE_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_UPCOMING_FINALE_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_SEASON_FINALE_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_FINAL_EPISODE_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_RETURNING_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_ENDED_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/TSSK_TV_CANCELED_OVERLAYS.yml

Movies:
  collection_files:
    - file: /path/to/UMTK/kometa/UMTK_MOVIES_UPCOMING_COLLECTION.yml
    - file: /path/to/UMTK/kometa/UMTK_MOVIES_TRENDING_COLLECTION.yml
  overlay_files:
    - file: /path/to/UMTK/kometa/UMTK_MOVIES_UPCOMING_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/UMTK_MOVIES_TOP10_OVERLAYS.yml
```

> [!TIP]
> Only add the files for the categories you have enabled. All are optional and independently generated based on your config settings.

---

## 🍪 Using browser cookies for yt-dlp (Method 1)

In case you need to use your browser's cookies with method 1, you can pass them along to yt-dlp.<br>
To extract your cookies in Netscape format, you can use an extension:
  * [Firefox](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/)
  * [Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)<br>
Extract the cookies you need and rename the file `cookies.txt`

#### For Docker Users:

Add the path to the folder containing your `cookies.txt` to your docker-compose.yml under `volumes:`:

```yaml
      - /path/to/cookies:/cookies
```

#### For Local Installation

1. Create a `cookies` folder in the same directory as the UMTK script
2. Export your browser cookies to `cookies.txt` within this new subfolder

---

## 📼 Choose Placeholder Video (Method 2)

When using the placeholder method, the script uses the `UMTK` video file in the `video` subfolder.<br>
It's a simple intro video that shows 'coming soon':<br>
![Image](https://github.com/user-attachments/assets/588618dc-86f2-4e0f-9be7-93c5eacef4e7)<br>

You can replace this with one of the other included examples, or with any video you like. Just make sure your chosen video is named `UMTK`.

---

## 🚀 Usage

### Docker:

The container runs automatically based on your CRON schedule. To run manually:

```bash
docker exec umtk python /app/UMTK.py
```

### Manual:

Open a Terminal in your script directory and run:

```bash
python UMTK.py
```

> [!TIP]
> You can also trigger a run from the [Web UI](#web-ui) using the "Run Now" button.

When both modules are enabled, UMTK runs first, followed by TSSK.

---

<a id="localization"></a>
## 🌐 Localization

You can translate weekdays and months by using a localization file. <br>
- Download your language from this repo (`config/localization files`)
- Rename it to `localization.yml` and place it in your config folder (next to `config.yml`).

If your language is missing, simply use one of the templates and edit as needed.


---

## 💡 Tips & Best Practices

### Exclude UMTK Content from Recently Added Sections

Since UMTK adds content before it's actually available, you'll want to exclude it from "Recently Added" sections:

#### Example for TV Shows:

1. Go to your TV show library
2. Sort by "Last Episode Date Added"
3. Click '+' → "Create Smart Collection"
4. Add filter: `Folder Location` `is not` `your umtk_root_tv folder` 
5. Press 'Save As' > 'Save As Smart Collection'
6. Name it something like "New in TV Shows📺"
7. In the new collection click the three dots then "Visible on" > "Home"
8. Go to Settings > under 'manage' click 'Libraries' > Click on "Manage Recommendations" next to your TV library
9. Unpin the default "Recently Added TV" and "Recently Released Episodes" from home, and move your newly made smart collection to the top (or wherever you want it)

### Choosing Between Methods

**Trailer Method (1):**

- ✅ Provides actual trailers for upcoming content
- ❌ May fail if no suitable trailer is found or yt-dlp is currently blocked by YouTube

**Placeholder Method (2):**

- ✅ Always works (no external dependencies)
- ✅ Faster processing
- ❌ Some content may not have a Plex Pass Trailer

### Understanding Movie Release Types

When `include_inCinemas` is enabled, UMTK considers three release types:

- **Digital Release:** Streaming/VOD availability
- **Physical Release:** Blu-ray/DVD release
- **Cinema Release:** Theatrical release

UMTK uses the earliest available date when multiple types exist.
Keep `include_inCinemas` set to `false` to ignore cinema/theater release dates.

### Scheduling with Cron (Docker)

The default schedule is `0 2 * * *` (2 AM daily). Common alternatives:

- `0 */6 * * *` - Every 6 hours
- `0 0 * * 0` - Weekly on Sunday at midnight
- `0 4 * * 1,4` - Monday and Thursday at 4 AM

Use [crontab.guru](https://crontab.guru/) to create custom schedules.

<a id="prevent-request-platforms"></a>
### Prevent Request Platforms from marking coming soon items as available
Request platforms such as Ombi and Overseerr check Plex for availability instead of Radarr/Sonarr. Therefor they will mark 'coming soon' items as available even though Radarr and Sonarr will correctly see them as 'missing'<br>
To avoid this you can choose to create seperate libraries for your 'coming soon' items.

- In Plex, create new Coming Soon Libraries pointed to the umtk_root folder.
- Add these new libraries to your Kometa config and add the collection and overlay .yml files there.
- In Ombi/Overseerr/... unmonitor these libraries
<img width="638" height="191" alt="Image" src="https://github.com/user-attachments/assets/6a7ff130-12dc-42dd-bb50-4686af9e0e28" />

NOTE: You'll have to instruct your users to 'pin' these new libraries. Otherwise they will not see the 'Coming Soon' collections appear on their home screen.

---

## 🩺 Troubleshooting Common Issues:

### ❌ "Connection refused" to Sonarr/Radarr:
- **First**: Make sure Sonarr and Radarr are actually running on your computer.
- Check that the URLs in `config.yml` are correct (e.g., `http://localhost:8989` for Sonarr).
- If using docker, use `ipaddress:8989` or `host.docker.internal:8989`.
- If using IP addresses (e.g., `192.168.1.100`), make sure they're correct and accessible.

### ❌ "Permission denied" errors:
- Check your Docker path mounts in your container or docker-compose.
- Check whether the PGID:PUID you set in docker-compose has the correct permissions .

### ❌ "No config.yml found":
- Make sure you renamed `config.sample.yml` to `config.yml`
- Check that the `config` folder is properly mounted

### ❌ yt-dlp fails to download Trailers:
- There is a constant 'battle' between YouTube and projects like yt-dlp which sporadically 'breaks' the functionality of yt-dlp. An update of yt-dlp may be required. If you manually run the script, you can try updating yt-dlp. Report the issue so the requirements can be updated in the Docker image if needed.
- Make sure you set `method_fallback: true` in config to fallback to the Placeholder video method when trailer downloads fail.

### ❌ A bunch of old movies/shows are being added as Coming Soon
- That means you have those items monitored in Radarr/Sonarr but not downloaded.
- You need to either trigger them to download if you want them, or unmonitor them if you don't. Basically your Arrs needed a cleanup.
- Alternatively, set `future_only` and/or `future_only_tv` to `true` if you don't want any items that have been released to show up as Coming Soon.

---

## ⚠️ Need Help or Have Feedback?

- Join the [Discord](https://discord.gg/VBNUJd7tx3)

---

## ❤️ Support the Project

If you like this project, please ⭐ star the repository and share it with the community!

<br/>

[!["Buy Me A Coffee"](https://github.com/user-attachments/assets/5c30b977-2d31-4266-830e-b8c993996ce7)](https://www.buymeacoffee.com/neekokeen)