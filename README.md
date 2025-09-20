# IN DEVELOPMENT! Please join the Discord for testing feedback

# 🎬📺 Upcoming Movies & TV Shows for Kometa

**UMTK** (Upcoming Movies & TV Shows for Kometa) creates 'coming soon' collections in your Plex server. It accomplishes this by:

- Checking [Radarr](https://radarr.video/) and [Sonarr](https://sonarr.tv/) for upcoming (monitored) content within x days
- Either downloading trailers using [yt-dlp](https://github.com/yt-dlp/yt-dlp) or creating placeholder video files
- Creating collection and overlay .yml files which can be used with [Kometa](https://kometa.wiki/en/latest/) (formerly Plex Meta Manager)

This combines the functionality of both [UTSK](https://github.com/netplexflix/Upcoming-TV-Shows-for-Kometa) and [UMFK](https://github.com/netplexflix/Upcoming-Movies-for-Kometa) into a single, unified solution.

> [!note]
> For movies, Plex's 'editions' feature is used which requires a Plex Pass subscription for Server admin account.

## Examples:

### Movies:

<img width="777" height="356" alt="Image" src="https://github.com/user-attachments/assets/588ff92e-ac42-4d80-9d3a-31eac52a7961" /><br>

### TV Shows:

<img width="1303" height="495" alt="TV Shows Example" src="https://github.com/user-attachments/assets/bd2718b0-2437-44f7-8da6-2b819dece7b7" />

---

## 🛠️ Installation

### Option 1: Docker (Recommended for Beginners)

Docker is the easiest way to run UMTK. It automatically handles all the technical setup for you.

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
      # Example 1: If your Sonarr/Radarr use /data/media paths
      # - /mnt/media/movies:/data/media/movies
      # - /mnt/media/tv:/data/media/tv

      # Example 2: If your Sonarr/Radarr use /media paths
      # - /mnt/media/movies:/media/movies
      # - /mnt/media/tv:/media/tv

      # Example 3: If your Sonarr/Radarr use /mnt/media paths
      # - /mnt/media/movies:/mnt/media/movies
      # - /mnt/media/tv:/mnt/media/tv
    restart: unless-stopped
```

4. **Update the timezone** in the `TZ` environment variable to match your location (e.g., `America/New_York`, `Europe/London`, `Asia/Tokyo`)

#### Step 3: Create Required Directories

1. **Create the required folders** in your UMTK directory:

   - `config` folder (for configuration files)
   - `video` folder (for placeholder videos)
   - `kometa` folder (for generated YAML files)

2. **Download the required files**:
   - Go to the [GitHub repository](https://github.com/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa)
   - Download `config/config.sample.yml` and save it as `config/config.yml` in your UMTK folder
   - Download `video/UMTK.mp4` and save it in your `video` folder (if using placeholder method)

#### Step 4: Configure Your Settings

1. **Open the `config.yml` file** you just downloaded
2. **Update these important settings**:
   - `radarr_url`: Your Radarr web address (e.g., `http://localhost:7878` or `http://192.168.1.100:7878`)
   - `radarr_api_key`: Your Radarr API key (found in Radarr Settings → General → Security)
   - `sonarr_url`: Your Sonarr web address (e.g., `http://localhost:8989` or `http://192.168.1.100:8989`)
   - `sonarr_api_key`: Your Sonarr API key (found in Sonarr Settings → General → Security)
   - `utc_offset`: Your timezone (e.g., `-5` for New York, `+1` for London)

> [!IMPORTANT] > **Make sure Sonarr and Radarr are running** before starting UMTK! The container needs to connect to these services.

#### Step 5: Update Media Paths

**IMPORTANT**: You must update the media paths in the existing `docker-compose.yml` file to match your Sonarr/Radarr setup:

1. **Check your Sonarr/Radarr** to see what paths they use for your media
2. **Edit the volume paths** in `docker-compose.yml` (uncomment and modify the appropriate lines):
   - If Sonarr uses `/media/movies`, uncomment and modify: `- /media/movies:/media/movies`
   - If Radarr uses `/data/media/movies`, uncomment and modify: `- /mnt/media/movies:/data/media/movies`
   - **The format is**: `your-actual-path:container-path`

#### Step 6: Run UMTK

1. **Open a terminal/command prompt** in your UMTK folder
2. **Type this command** and press Enter:
   ```bash
   docker-compose up -d
   ```
3. **That's it!** UMTK will now run automatically every day at 2 AM

#### What Happens Next?

- UMTK will create YAML files in the `kometa` folder
- These files can be used with Kometa to create collections in Plex
- You can check the logs anytime with: `docker-compose logs -f`

> [!TIP] > **Need Help?** If something goes wrong, check the logs with `docker-compose logs` to see what's happening.

#### Troubleshooting Common Issues:

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

### Option 2: Manual Installation

#### 1️⃣ Clone the repository:

```bash
git clone https://github.com/netplexflix/Upcoming-Movies-TV-Shows-for-Kometa.git
cd Upcoming-Movies-TV-Shows-for-Kometa
```

> [!TIP]
> If you don't know what that means, simply download the script by pressing the green 'Code' button above and then 'Download Zip'.  
> Extract the files to your desired folder.

#### 2️⃣ Install Python dependencies:

- Ensure you have [Python](https://www.python.org/downloads/) installed (`>=3.11`)
- Open a Terminal in the script's directory

> [!TIP]
> Windows Users:  
> Go to the UMTK folder (where UMTK.py is). Right mouse click on an empty space in the folder and click `Open in Windows Terminal`.

- Install the required dependencies:

```sh
pip install -r requirements.txt
```

#### 3️⃣ Install ffmpeg (for trailer downloads)

[ffmpeg](https://www.ffmpeg.org/) is required by yt-dlp for postprocessing when downloading trailers.
Check [THIS WIKI](https://www.reddit.com/r/youtubedl/wiki/ffmpeg/#wiki_where_do_i_get_ffmpeg.3F) for installation instructions.

---

## ⚙️ Configuration

Rename `config.example.yml` to `config.yml` and update your settings:

### General:

- **movies**: 2 #0 = Don't process, 1 = Download trailers with yt-dlp, 2 = Use placeholder video file
- **tv**: 1 #0 = Don't process, 1 = Download trailers with yt-dlp, 2 = Use placeholder video file
- **utc_offset:** Set your [UTC timezone](https://en.wikipedia.org/wiki/List_of_UTC_offsets) offset
  - Examples: LA: `-8`, New York: `-5`, Amsterdam: `+1`, Tokyo: `+9`
- **debug:** Set to `true` to troubleshoot issues
- **cleanup:** Set to `true` (default) to automatically remove trailers/placeholders when actual content is downloaded or no longer valid
- **skip_channels:** Blacklist YouTube channels that create fake trailers

### Movie Settings:

- **future_days_upcoming_movies:** How many days ahead to look for releases (default: `30`)
- **include_inCinemas:** Include cinema release dates (default: `false`, only digital/physical)
- **future_only:** Set to `false` (default) to include already-released but not-downloaded movies
- **exclude_radarr_tags**: Skip movies with these tags

### TV Show Settings:

- **future_days_upcoming_shows:** How many days ahead to look for premieres (default: `30`)
- **recent_days_new_show:** How many days back to look for new shows (default: `7`)
- **exclude_sonarr_tags**: Skip TV Shows with these tags

### Radarr Configuration (for Movies):

- **radarr_url:** Your Radarr URL (default: `http://localhost:7878`)
- **radarr_api_key:** Found in Radarr under Settings → General → Security

### Sonarr Configuration (for TV Shows):

- **sonarr_url:** Your Sonarr URL (default: `http://localhost:8989`)
- **sonarr_api_key:** Found in Sonarr under Settings → General → Security

### Overlay & Collection Settings:

The remaining settings customize the output .yml files for Kometa.

> [!TIP]
> You can enter any Kometa variables in this block and they will be automatically added in the generated .yml files.</br>

> [!NOTE]
> There are two different overlays for Movies:<br>
>
> - One for movies with a release date in the future. This overlay will append the release date.<br>
> - One for movies that have already been released but haven't been downloaded yet. Depending on your setup there could be some time between the official release date and when it's actually added to your Plex server. Since the release date is in the past it isn't printed. Instead you can state it's "coming soon". You can disable this category by setting `future_only` to `true`

> [!NOTE] > **Date format options:**
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

---

## 📼 Placeholder Video (Method 2)

When using the placeholder method, the script uses the `UMTK` video file in the `video` subfolder.<br>
It's a simple intro video that shows 'coming soon':<br>
![Image](https://github.com/user-attachments/assets/588618dc-86f2-4e0f-9be7-93c5eacef4e7)<br>
You can replace this with any video you like, as long as it is named `UMTK`.

---

## ☄️ Add to Kometa Configuration

Open your **Kometa** config.yml (typically at `Kometa/config/config.yml`) and add the path to the UMFK .yml files under `collection_files` and `overlay_files`.

Example:

```yaml
TV Shows:
  collection_files:
    - file: /path/to/UMTK/Kometa/UMTK_TV_UPCOMING_SHOWS_COLLECTION.yml
  overlay_files:
    - file: /path/to/UMTK/Kometa/UMTK_TV_UPCOMING_SHOWS_OVERLAYS.yml
    - file: /path/to/UMTK/Kometa/UMTK_TV_NEW_SHOWS_OVERLAYS.yml

Movies:
  collection_files:
    - file: /path/to/UMTK/Kometa/UMTK_MOVIES_UPCOMING_COLLECTION.yml
  overlay_files:
    - file: /path/to/UMTK/Kometa/UMTK_MOVIES_UPCOMING_OVERLAYS.yml
```

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

### Prevent Upcoming Content from "Recently Added" Sections

Since UMTK adds content before it's actually available, you'll want to exclude it from "Recently Added" sections:

#### Example for TV Shows:

1. Go to your TV show library
2. Sort by "Last Episode Date Added"
3. Click '+' → "Create Smart Collection"
4. Add filter: `Label` `is not` `Coming Soon` (or whatever you used as collection_name. Since the collection yml uses smart_label, Kometa adds that label to the relevant shows, so you can exclude these shows based on that label. The label will be automatically removed by Kometa once the show is no longer 'upcoming' so when the first episode is added, it will show up)
5. Press 'Save As' > 'Save As Smart Collection'
6. Name it something like "New in TV Shows📺"
7. In the new collection click the three dots then "Visible on" > "Home"
8. Go to Settings > under 'manage' click 'Libraries' > Click on "Manage Recommendations" next to your TV library
9. Unpin the default "Recently Added TV" and "Recently Released Episodes" from home, and move your newly made smart collection to the top (or wherever you want it)

### Choosing Between Methods

**Trailer Method (1):**

- ✅ Provides actual trailers for upcoming content
- ❌ May fail if no suitable trailer is found

**Placeholder Method (2):**

- ✅ Always works (no external dependencies)
- ✅ Faster processing
- ❌ Some TV Shows may not have a Plex Pass Trailer

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

---

## ⚠️ Need Help or Have Feedback?

- Join the [Discord](https://discord.gg/VBNUJd7tx3)

---

## ❤️ Support the Project

If you like this project, please ⭐ star the repository and share it with the community!

<br/>

[!["Buy Me A Coffee"](https://github.com/user-attachments/assets/5c30b977-2d31-4266-830e-b8c993996ce7)](https://www.buymeacoffee.com/neekokeen)
