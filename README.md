<h1>
  <img alt="Haustus" src="https://raw.githubusercontent.com/Sonata-Of-Death/Haustus/main/assets/haustus-dark.svg#gh-dark-mode-only" height="96">
  <img alt="Haustus" src="https://raw.githubusercontent.com/Sonata-Of-Death/Haustus/main/assets/haustus-light.svg#gh-light-mode-only" height="96">
</h1>

### Terminal Media Downloader, Audio Mastering & Transcoding Workstation

**Haustus** is a high-throughput CLI and TUI media workstation supporting **11 Dedicated Platforms** and **Universal Ingestion for 1000+ Websites** (via yt-dlp) and direct media streams. Built with Python, yt-dlp, Rich, Mutagen, and imageio-ffmpeg.

<p align="center">
  <a href="https://github.com/Sonata-Of-Death/Haustus/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/Sonata-Of-Death/Haustus/ci.yml?branch=main&label=CI&labelColor=1B1917&style=for-the-badge" height="28"></a>
  <img alt="license" src="https://img.shields.io/badge/license-MIT-E87A24?labelColor=1B1917&style=for-the-badge" height="28">
  <img alt="version" src="https://img.shields.io/badge/version-1.0.0-C8A96E?labelColor=1B1917&style=for-the-badge" height="28">
  <img alt="python" src="https://img.shields.io/badge/python-3.10+-C8A96E?labelColor=1B1917&style=for-the-badge" height="28">
</p>

---

## Quick Start

### 1. Install
```bash
pip install haustus
```
Or from source:
```bash
git clone https://github.com/Sonata-Of-Death/Haustus.git
cd Haustus
pip install -e .
```

### 2. Run
```bash
# Interactive Arrow-Key Menu
haustus

# Or download any media link directly in best quality
haustus "https://www.youtube.com/watch?v=..."
```

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            USER INTERFACE (TUI / CLI)                       │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Interactive Arrow-Key Menu (Single Enter, Instant [Esc] Return)       │  │
│  │ Fast Terminal Navigation, Multi-Profile Sessions & Preset Defaults    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                     CORE INGESTION & NETWORK RESILIENCE                     │
│  ┌──────────────────────────┐  ┌───────────────────┐  ┌───────────────────┐ │
│  │ Multi-Profile Sessions   │  │ Adaptive Network  │  │ Session Ledger    │ │
│  │ Isolated Temp Storage    │  │ Full Jitter + CB  │  │ Atomic Checkpoint │ │
│  └──────────────────────────┘  └───────────────────┘  └───────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ High-Throughput Engine: 16-Stream aria2c + Token-Bucket Pacing         │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Rich Live Dashboard: Real-time Speed, ETA, Percentage, Size            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Smart History & Missing File Ledger (Atomic Verification)              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    STUDIO MEDIA POST-PROCESSING                             │
│  ┌──────────────────────────┐  ┌───────────────────┐  ┌───────────────────┐ │
│  │ GPU Video Transcoding    │  │ EBU R128 Audio    │  │ Subtitle Embedder │ │
│  │ NVENC / VAAPI / SVT-AV1  │  │ Two-Pass -16 LUFS │  │ Soft Mux (.srt)   │ │
│  └──────────────────────────┘  └───────────────────┘  └───────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Mutagen ID3v2.4 & MP4 Cover Art / Metadata Atom Injection              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Supported Platforms

| Platform | Supported Media | Requires Cookies? |
| :--- | :--- | :--- |
| **Instagram** | Full HD Reels, Photo Carousels in subfolders, 24h Stories, Story Highlights, Saved Posts, Reposts | Optional (Required for Stories & Saved) |
| **TikTok** | Watermark-free HD Videos, Photo Slideshow albums, Original Music, Saved / Favorites, Collections, Reposts | Optional (Required for Favorites) |
| **YouTube** | Up to 4K/1080p with audio, Shorts, Interactive Playlist picker (Watch Later, Liked), Full Channels | Optional (Age-gate / Private) |
| **X (Twitter)** | Full HD media tweets, video broadcasts, photo sets, Bookmarks, Retweets, Archive ingestion (`bookmarks.json`) | Optional (Required for Bookmarks) |
| **SoundCloud** | Audio tracks, sets, artist discographies, user liked tracks with cover art embedding | Optional (Required for Liked) |
| **Reddit** | DASH video with merged audio, multi-image galleries, Subreddit feeds (Hot/Top/New), Saved / Upvoted | Optional (Required for Saved / Upvoted) |
| **Facebook** | Full HD/SD Reels, Public video posts, Watch URLs, short links (`fb.watch`), Saved collections | Optional (Required for Saved) |
| **Pinterest** | Video pins, original uncompressed images (`/originals/` CDN pattern) with metadata JSON, full Boards | Optional (Required for Saved Boards) |
| **Twitch** | Stream clips (`clips.twitch.tv`), past broadcasts (VODs), channel archives, audio extraction | Optional (Required for Sub-only VODs) |
| **Threads** | Single post videos, original high-resolution photo carousels with `metadata.json`, creator profiles | Optional |
| **Spotify** | Track/Album/Playlist metadata & cover art resolution with high-fidelity audio discovery | Optional (Session via `sp_dc`) |
| **1000+ Universal Sites** | Vimeo, Bilibili, Dailymotion, Loom, Streamable, Rumble, Bandcamp, and direct media URLs | No |

> [!NOTE]
> Third-party platforms frequently update their web interfaces, layout APIs, and anti-scraping mechanisms. Features like watermark-free extraction, Spotify track resolution, and authenticated bookmarks rely on upstream availability.

---

## System Requirements

- **Python**: `>= 3.10`
- **FFmpeg**: Handled automatically via `imageio-ffmpeg` or discovered from system PATH.
- **aria2c** *(Optional)*: Required only when passing the `--aria2` multi-stream acceleration flag. Install via your package manager:
  - Windows: `winget install aria2` or `choco install aria2`
  - macOS: `brew install aria2`
  - Linux: `sudo apt install aria2`

---

## Usage

### 1. Interactive Menu (TUI)
Run without arguments to launch the interactive arrow-key interface:
```bash
haustus
```
- **Arrow Keys (`Up` / `Down`)** or **`W` / `S`**: Move selection.
- **Single Enter**: Confirm selection.
- **Number Keys (`0` - `9`)**: Quick jump to numbered item.
- **`[H]` or `[?]`**: Open / close keyboard shortcuts help overlay.
- **`[Esc]`**: Return to previous menu or abort prompt.

### 2. Common CLI Commands

#### Single Media Downloads
```bash
# 1080p Video
haustus "https://www.youtube.com/watch?v=..." -q 1080

# 320 kbps Audiophile MP3 with Embedded Cover Art & ID3 Tags
haustus "https://www.youtube.com/watch?v=..." -a -aq 320 -af mp3 --embed-metadata

# Specific Clip Range (HH:MM:SS format)
haustus "https://www.youtube.com/watch?v=..." --clip "01:20-03:45"

# Bandwidth Speed Limit Capped at 2 MB/s
haustus "https://www.youtube.com/watch?v=..." --speed-limit 2M
```

#### Batch & Smart Filters
```bash
# Batch download from text file (one URL per line)
haustus -f links.txt

# Cap playlist download at first 20 items uploaded in the last 7 days
haustus -p "https://www.youtube.com/playlist?list=..." --count-limit 20 --date-after now-7days

# Shorts only under 60 seconds
haustus -u "@channel" --shorts-only

# Specific items in a playlist
haustus -p "https://www.youtube.com/playlist?list=..." --items "1,3,5-10"
```

#### Authenticated Collections
```bash
# Instagram Saved Posts & Stories
haustus --saved
haustus --instagram-stories "@creator"

# TikTok Saved Favorites & Reposts
haustus --tiktok-saved
haustus --tiktok-reposts

# X (Twitter) Bookmarks
haustus --x-bookmarks

# Reddit Subreddit Feed Batch
haustus --reddit-subreddit "EarthPorn" --reddit-sort top --reddit-timeframe week

# Spotify Playlist to 320k Tagged MP3s
haustus --spotify-playlist "https://open.spotify.com/playlist/..." --audio-quality 320
```

---

## Command Line Arguments Reference

| Flag | Long Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `urls` | | Positional URL(s) from 11 platforms or 1000+ universal sites | None |
| `-f` | `--file` | Path to text file containing URLs (one per line) | None |
| `-u` | `--user` | Username or profile/channel URL | None |
| `-p` | `--playlist` | YouTube playlist URL | None |
| `-q` | `--quality` | Target video resolution (`best`, `2160`, `1440`, `1080`, `720`, `480`, `360`) | `best` |
| `-a` | `--audio` | Enable Audio-Only extraction mode | `False` |
| `-aq`| `--audio-quality` | Audio bitrate (`320`, `256`, `192`, `128`, `64`, `best`) | `192` |
| `-af`| `--audio-format` | Audio container format (`mp3`, `m4a`, `flac`, `wav`, `opus`) | `mp3` |
| `-o` | `--output` | Destination directory for downloaded media | `~/Desktop/HaustusDownloads` |
| `-c` | `--cookies` | Path to Netscape `cookies.txt` or raw cookie token string | None |
| | `--clip` | Download specific time range only (e.g. `01:20-03:45`) | None |
| | `--subtitles` | Download and embed subtitles (.srt / .vtt) into media container | `False` |
| | `--speed-limit` | Download bandwidth rate limit (e.g. `2M`, `5M`, `10M`, `500K`) | None |
| | `--embed-metadata` | Force embedding thumbnail cover art and metadata tags | None |
| | `--no-embed-metadata`| Force disabling embedding cover art and metadata tags | None |
| | `--count-limit` | Cap download batch at maximum number of items | None |
| | `--date-after` | Filter items uploaded after date (`YYYYMMDD` or `now-7days`) | None |
| | `--shorts-only` | Download short videos only (`<= 60s`) | `False` |
| | `--items` | Specify playlist item indices or range (e.g. `1,3,5-10`) | None |
| | `--archive` | Force checking download history archive | None |
| | `--no-archive` | Force ignoring download history archive | None |
| | `--saved` | Download all saved posts from authenticated Instagram account | `False` |
| | `--instagram-stories` | Download active 24h Instagram Stories for username | None |
| | `--instagram-highlights` | Download Instagram Story Highlights for username | None |
| | `--instagram-reposts`| Download reposted posts and reels from Instagram account | `False` |
| | `--instagram-json` | Path to Instagram data export JSON file | None |
| | `--tiktok-saved` | Download favorite videos from authenticated TikTok account | `False` |
| | `--tiktok-reposts`| Download reposted videos from authenticated TikTok account | `False` |
| | `--tiktok-cookies` | Netscape cookies file or raw TikTok sessionid | None |
| | `--tiktok-collection` | URL of TikTok collection to batch download | None |
| | `--tiktok-json` | Path to TikTok user_data.json data export file | None |
| | `--x-bookmarks` | Download saved bookmarks from authenticated X account | `False` |
| | `--x-reposts` | Download reposted tweets/media from authenticated X account | `False` |
| | `--x-cookies` | Netscape cookies file or raw X auth_token | None |
| | `--x-json` | Path to X archive JSON or JS file (bookmarks.json, tweets.json) | None |
| | `--soundcloud-likes` | Download liked tracks for SoundCloud username or URL | None |
| | `--soundcloud-cookies` | Netscape cookies file or raw SoundCloud oauth_token | None |
| | `--reddit-saved` | Download saved posts from authenticated Reddit account | `False` |
| | `--reddit-upvoted` | Download upvoted posts from authenticated Reddit account | `False` |
| | `--reddit-subreddit` | Subreddit name or URL to download in bulk | None |
| | `--reddit-sort` | Subreddit sorting order (`hot`, `new`, `top`, `rising`) | `hot` |
| | `--reddit-timeframe` | Subreddit time window (`hour`, `day`, `week`, `month`, `year`, `all`) | `day` |
| | `--reddit-cookies` | Netscape cookies file or raw Reddit session token | None |
| | `--facebook-saved` | Download saved videos from authenticated Facebook account | `False` |
| | `--facebook-cookies` | Netscape cookies file or raw Facebook c_user/xs cookie string | None |
| | `--pinterest-board` | URL of Pinterest board to batch download | None |
| | `--pinterest-saved` | Download saved pins and boards from authenticated Pinterest account | `False` |
| | `--pinterest-cookies`| Netscape cookies file or raw Pinterest _pinterest_sess token | None |
| | `--twitch-channel` | Twitch streamer/channel URL to batch download clips/VODs | None |
| | `--twitch-cookies` | Netscape cookies file or raw auth-token for Twitch | None |
| | `--threads-profile` | Threads username or profile URL to batch download | None |
| | `--threads-cookies` | Netscape cookies file or raw sessionid for Threads | None |
| | `--spotify-playlist`| Spotify playlist, album, or collection URL to batch download | None |
| | `--spotify-cookies` | Netscape cookies file or raw sp_dc token for Spotify | None |
| | `--aria2` | Enable 16-connection segmented multi-stream download via aria2c | `False` |
| | `--normalize` | Enable two-pass EBU R128 (-16 LUFS) loudness normalization | `False` |
| | `--transcode` | Enable GPU-accelerated video transcoding (NVENC/VAAPI/AV1) | `False` |
| | `--parallel` | Enable high-throughput multi-threaded parallel batch execution | `False` |
| | `--delay` | Polite delay in seconds between download requests | `2.0` |
| | `--proxy` | HTTP/HTTPS/SOCKS5 proxy URI (e.g. `http://127.0.0.1:7890`) | None |

---

## Troubleshooting

- **HTTP 429 Too Many Requests**: The platform is rate-limiting your IP. Use `--delay 5.0` to throttle requests, or configure a proxy with `--proxy`.
- **Session Expired / Authentication Failed**: Cookies expire over time. Open `haustus` -> Settings -> Accounts and re-enter your updated session token or Netscape cookies file.
- **aria2c executable not found**: Ensure `aria2c` is installed and reachable on your system PATH before using `--aria2`.
- **Unclosed Terminal Buffers on Windows**: Haustus automatically configures UTF-8 and ANSI escape sequence processing on Windows terminals. If running in legacy cmd.exe, prefer Windows Terminal or PowerShell 7+.

---

## Testing

The test suite covers configuration persistence, cookie isolation, network resilience backoff, format extraction, platform dispatchers, and UI components:

```bash
python -m unittest discover -s tests
```

---

## Disclaimer & Legal Notice

Haustus is designed and intended strictly for personal, educational, and backup archiving purposes. Users are solely responsible for ensuring that their media downloads comply with the Terms of Service of each respective platform and respect the copyrights and intellectual property rights of content creators. The developers assume no liability for misuse.

---

## License

Released under the MIT License. Copyright (c) 2026 Adham Mohamed (Sonata-Of-Death).

> **Third-Party Notice**: Haustus utilizes open-source libraries including `yt-dlp` (Unlicense), `requests` (Apache-2.0), `rich` (MIT), and `imageio-ffmpeg` (BSD-2-Clause).
> - `mutagen` is licensed under GPL-2.0-or-later; it is installed separately from PyPI as an external dependency and is not bundled or distributed with this source code repository.
> - `imageio-ffmpeg` downloads or uses an external FFmpeg binary build which may be compiled under GPL (or LGPL depending on enabled codecs and build flags), which is also retrieved independently at runtime and is not distributed as part of this codebase.
