# Upcoming Movies & TV Shows for Kometa

**UMTK** (Upcoming Movies & TV Shows for Kometa) creates 'Coming Soon' collections in your Plex server.<br> 
It accomplishes this by:

- Checking [Radarr](https://radarr.video/) and [Sonarr](https://sonarr.tv/) for upcoming (monitored) content expected to be released/air within x days
- Either downloading trailers using [yt-dlp](https://github.com/yt-dlp/yt-dlp) or creating placeholder video files
  - For movies, Plex's 'editions' feature is used (Plex Pass required for Server admin account)
  - For TV Shows, the Trailer or placeholder file is saved as a "special"(S00E00)
- Creating collection and overlay .yml files which can be used with [Kometa](https://kometa.wiki/en/latest/) (formerly Plex Meta Manager)

UMTK can also use MDBList to create "Trending" categories and create placeholder files for missing items with an overlay indicating that a request is required.
Optionally applies a TOP 10 ranking overlay.

## Examples:

### Movies:

<img width="785" height="357" alt="Image" src="https://github.com/user-attachments/assets/bd809972-fa98-4cb5-a64f-d514e75f69e2" /><br>

### TV Shows:

![Image](https://github.com/user-attachments/assets/3f9beeca-2c7e-4c34-bbda-5293c6d45a8c)

### Trending Movies:

<img width="1636" height="372" alt="Image" src="https://github.com/user-attachments/assets/4cc2511a-40aa-4476-9fb2-7f054708e271" />
In this example the movie "Dracula" has not been added to Radarr (and is not available).

---

## 📑 Table of Contents

- [🛠️ Installation](#-installation)
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
    - [Step2: Install Python dependencies](#step-2-install-python-dependencies)
    - [Step3: Install ffmpeg (for trailer downloads)](#step-3-install-ffmpeg-for-trailer-downloads)
    - [Step 4: Configure Your Config Settings](#step-4-configure-your-config-Settings)
    - [Step 5: Add the yml files to your Kometa config](#step-5-add-the-yml-files-to-your-kometa-config)
- [⚙️ Configuration](#️-configuration)
  - [General](#general)
  - [Radarr Configuration (for Movies)](#radarr-configuration-for-movies)
  - [Sonarr Configuration (for TV Shows)](#sonarr-configuration-for-tv-shows)
  - [Movie Settings](#movie-settings)
  - [TV Show Settings](#tv-show-settings)
  - [Trending](#trending)
  - [Overlay & Collection Settings](#overlay--collection-settings)
- [☄️ Add to Kometa Configuration](#️-add-to-kometa-configuration)
- [🍪 Using browser cookies for yt-dlp (Method 1)](#-using-browser-cookies-for-yt-dlp-method-1)
- [📼 Placeholder Video (Method 2)](#-choose-placeholder-video-method-2)
- [🚀 Usage](#-usage)
- [💡 Tips & Best Practices](#-tips--best-practices)
  - [Exclude Upcoming Content from "Recently Added" Sections](#exclude-upcoming-content-from-recently-added-sections)
  - [Choosing Between Methods](#choosing-between-methods)
  - [Understanding Movie Release Types](#understanding-movie-release-types)
  - [Scheduling with Cron (Docker)](#scheduling-with-cron-docker)
  - [Prevent Request Platforms from marking coming soon items as available](#Prevent-Request-Platforms-from-marking-coming-soon-items-as-available)
- [🩺 Troubleshooting Common Issues:](#-troubleshooting-common-issues)

---

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
    network_mode: "host" # Use host network to access localhost services
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

      # Media directories - MUST match your Sonarr/Radarr paths exactly
      - /mnt/media/movies:/media/movies
      - /mnt/media/tv:/media/tv

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
   - Download `video/UMTK.mp4` and save it in your `video` folder (if using placeholder method)
     - You can also use your own video file. Just make sure it is called `UMTK`.

#### Step 4: Configure Your Settings
- See [⚙️ Configuration](#️-configuration)

#### Step 5: Update Media Paths
You must update the media paths in the existing `docker-compose.yml` file to match your Sonarr/Radarr setup.

> [!IMPORTANT]
> **The format is**: `your-actual-path:container-path`
1. **Check your Sonarr/Radarr**
   - To see what paths they use for your media, go to Settings>Media Management>Root Folders
   - Let's say your Radarr Root folder is simply `/movies`, and the actual full path is `/mnt/media/movies`
   - Then you have to mount `/mnt/media/movies:/movies`
   - If you have multiple roots, simply mount all of them.
3. **Edit the volume paths** in `docker-compose.yml`:

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

## ⚙️ Configuration

Rename `config.example.yml` to `config.yml` and update your settings:

### General:

- **movies**: 0 = Don't process, 1 = Download trailers with yt-dlp, 2 = Use placeholder video file
- **tv**: 0 = Don't process, 1 = Download trailers with yt-dlp, 2 = Use placeholder video file
- **method_fallback**: When set to `true`: If trailer downloading fails, UMTK will automatically fallback to using the placeholder method.
- **utc_offset:** Set your [UTC timezone](https://en.wikipedia.org/wiki/List_of_UTC_offsets) offset
  - Examples: LA: `-8`, New York: `-5`, Amsterdam: `+1`, Tokyo: `+9`
- **debug:** Set to `true` to troubleshoot issues
- **cleanup:** Set to `true` (default) to automatically remove trailers/placeholders when actual content is downloaded or no longer valid
- **skip_channels:** Blacklist YouTube channels that create fake trailers

### Radarr Configuration (for Movies):

- **radarr_url:** Your Radarr URL (default: `http://localhost:7878`)
- **radarr_api_key:** Found in Radarr under Settings → General → Security
- **radarr_timeout:** Increase if needed for large libraries

### Sonarr Configuration (for TV Shows):

- **sonarr_url:** Your Sonarr URL (default: `http://localhost:8989`)
- **sonarr_api_key:** Found in Sonarr under Settings → General → Security
- **sonarr_timeout:** Increase if needed for large libraries
  
### Movie Settings:

- **future_days_upcoming_movies:** How many days ahead to look for releases (default: `30`)
- **include_inCinemas:** Include cinema release dates (default: `false`, only digital/physical)
- **future_only:** Set to `false` (default) to include already-released but not-downloaded movies
- **exclude_radarr_tags**: Skip movies with these tags
- **umtk_root_movies**: Leave empty to use the default Radarr root. Enter a custom root if desired. Required for using trending_movies.

### TV Show Settings:

- **future_days_upcoming_shows:** How many days ahead to look for premieres (default: `30`)
- **recent_days_new_show:** How many days back to look for new shows (default: `7`)
- **future_only_tv:** Set to `false` (default) to include already-aired but not-downloaded show premieres
- **exclude_sonarr_tags**: Skip TV Shows with these tags
- **umtk_root_tv**: Leave empty to use the default Sonarr root. Enter a custom root if desired. Required for using trending_tv.

### Trending:
- **trending_movies:** 0 = Don't process, 1 = Download trailers with yt-dlp, 2 = Use placeholder video file
- **trending_tv:** 0 = Don't process, 1 = Download trailers with yt-dlp, 2 = Use placeholder video file
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

> [!NOTE] 
> In the config example, I use `build_collection: false`, only applying labels to the content without having Kometa actually creating the collection.
> I do this because I can then create a smart filter which includes both `Coming Soon` items from UMTK and `New Season Soon` items from TSSK.
> It also makes the collection more flexible allowing me to easily add/remove filters
> You can remove `build_collection: false` if you want Kometa to create the collection directly.

---

## ☄️ Add to Kometa Configuration

Open your **Kometa** config.yml (typically at `Kometa/config/config.yml`) and add the path to the UMFK .yml files under `collection_files` and `overlay_files`.

Example:

```yaml
TV Shows:
  collection_files:
    - file: /path/to/UMTK/kometa/UMTK_TV_UPCOMING_SHOWS_COLLECTION.yml
    - file: /path/to/UMTK/kometa/UMTK_TV_TRENDING_COLLECTION.yml
  overlay_files:
    - file: /path/to/UMTK/kometa/UMTK_TV_UPCOMING_SHOWS_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/UMTK_TV_TOP10_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/UMTK_TV_NEW_SHOWS_OVERLAYS.yml

Movies:
  collection_files:
    - file: /path/to/UMTK/kometa/UMTK_MOVIES_UPCOMING_COLLECTION.yml
    - file: /path/to/UMTK/kometa/UMTK_MOVIES_TRENDING_COLLECTION.yml
  overlay_files:
    - file: /path/to/UMTK/kometa/UMTK_MOVIES_UPCOMING_OVERLAYS.yml
    - file: /path/to/UMTK/kometa/UMTK_MOVIES_TOP10_OVERLAYS.yml
```

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

---

## 💡 Tips & Best Practices

### Exclude UMTK Content from "Recently Added" Sections

Since UMTK adds content before it's actually available, you'll want to exclude it from "Recently Added" sections:

#### Example for TV Shows:

1. Go to your TV show library
2. Sort by "Last Episode Date Added"
3. Click '+' → "Create Smart Collection"
4. Add filter: `Label` `is not` `Coming Soon` (or whatever you used as collection_name. Since the collection yml uses smart_label, Kometa adds that label to the relevant shows, so you can exclude these shows based on that label. The label will be automatically removed by Kometa once the show is no longer 'upcoming' so when the first episode is added, it will show up). If you are using the Trending feature then also add a filter for `folder location` `is not` `your umtk_root_tv folder`.
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


### Prevent Request Platforms from marking coming soon items as available
Request platforms such as Ombi and Overseerr check Plex for availability instead of Radarr/Sonarr. Therefor they will mark 'coming soon' items as available even though Radarr and Sonarr will correctly see them as 'missing'<br>
To avoid this you can choose to create seperate libraries for your 'coming soon' items.

- Use new custom roots for coming soon content under `umtk_root_movies` and `umtk_root_tv`
Examples:

```yaml
umtk_root_movies: P:/umtk movies
umtk_root_tv: P:/umtk tv
```

```yaml
umtk_root_movies: /mnt/media/umtk movies
umtk_root_tv: /mnt/media/umtk tv
```

- In Plex, create new Coming Soon Libraries pointed to these new roots.
- Add these new libraries to your Kometa config and add the collection and overlay .yml files there.
- In Ombi/Overseerr/... unmonitor these libraries
<img width="638" height="191" alt="Image" src="https://github.com/user-attachments/assets/6a7ff130-12dc-42dd-bb50-4686af9e0e28" />

NOTE: You'll have to instruct your users to 'pin' these new libraries. Otherwise they will not see the 'Coming Soon' collections appear on their home screen.

---

## 🩺 Troubleshooting Common Issues:

**❌ "Connection refused" to Sonarr/Radarr:**

- **First**: Make sure Sonarr and Radarr are actually running on your computer
- Check that the URLs in `config.yml` are correct (e.g., `http://localhost:8989` for Sonarr)
- If using `localhost`, make sure the services are running on the same computer as Docker
- If using IP addresses (e.g., `192.168.1.100`), make sure they're correct and accessible
- The container uses `network_mode: "host"` to access localhost services

**❌ "Permission denied" errors:**

- Make sure Docker Desktop is running
- Try running: `docker-compose down && docker-compose up -d`

**❌ "No config.yml found":**

- Make sure you renamed `config.sample.yml` to `config.yml`
- Check that the `config` folder is properly mounted

**❌ Container keeps restarting:**

- Check logs: `docker-compose logs umtk`
- Verify your `config.yml` settings are correct

**❌ yt-dlp fails to download Trailers:**
- There is a constant 'battle' between YouTube and projects like yt-dlp which sporadically 'breaks' the functionality of yt-dlp. An update of yt-dlp may be required. If you manually run the script, you can try updating yt-dlp. Report the issue so the requirements can be updated in the Docker image if needed.
- As a temporary workaround, set `method_fallback: true` in config to fallback to the Placeholder video method if trailer downloads fail.

**❌ A bunch of old movies/shows are being added as Coming Soon**
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