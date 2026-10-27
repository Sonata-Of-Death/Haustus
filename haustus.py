"""Haustus CLI entry point."""
import argparse
import os
import sys

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.archive import (
    DEFAULT_OUTPUT_DIR,
)
from core.constants import (
    A7_BRASS,
    A7_MUTED,
    A7_OPUS,
    A7_SIGNAL,
    A7_TEXT,
)
from core.cookies import (
    clean_dummy_cookie_profiles,
    get_effective_facebook_cookie_file,
    get_effective_instagram_cookie_file,
    get_effective_pinterest_cookie_file,
    get_effective_reddit_cookie_file,
    get_effective_soundcloud_cookie_file,
    get_effective_spotify_cookie_file,
    get_effective_threads_cookie_file,
    get_effective_tiktok_cookie_file,
    get_effective_twitch_cookie_file,
    get_effective_x_cookie_file,
    prepare_cookies,
    prepare_facebook_cookies,
    prepare_pinterest_cookies,
    prepare_reddit_cookies,
    prepare_soundcloud_cookies,
    prepare_spotify_cookies,
    prepare_threads_cookies,
    prepare_tiktok_cookies,
    prepare_twitch_cookies,
    prepare_x_cookies,
)
from core.engine import HighThroughputEngine
from features.audio_mode import (
    run_audio_mode_menu,
)
from features.bulk_file import (
    download_from_file,
    run_bulk_file_menu,
)
from features.downloader import (
    download_urls,
)
from features.paste_urls import (
    run_paste_urls_menu,
)
from features.playlist import (
    run_youtube_playlist_menu,
)
from features.profile import (
    download_profile,
    run_profile_menu,
)
from features.reposts import (
    dedicated_reposts_menu,
)
from features.saved_posts import (
    unified_saved_posts_menu,
)
from features.settings import (
    manage_configuration_menu,
)
from features.single_download import (
    run_single_video_menu,
)
from platforms.facebook import (
    download_facebook_saved_videos,
)
from platforms.instagram import (
    download_instagram_reposted_posts,
    download_instagram_saved_posts,
    download_instagram_stories_or_highlights,
    parse_instagram_reposts_json,
)
from platforms.pinterest import (
    download_pinterest_board,
)
from platforms.reddit import (
    download_reddit_feed,
)
from platforms.soundcloud import (
    download_soundcloud_liked_tracks,
)
from platforms.spotify import (
    download_spotify_playlist,
)
from platforms.threads import (
    download_threads_profile,
)
from platforms.tiktok import (
    download_tiktok_reposted_videos,
    download_tiktok_saved_posts,
    parse_tiktok_user_data_json,
)
from platforms.twitch import (
    download_twitch_channel,
)
from platforms.x_twitter import (
    download_x_bookmarks,
    download_x_reposts,
    parse_x_data_archive,
)
from ui.components import (
    MenuItem,
    select_menu,
)
from ui.quality import (
    choose_bulk_quality,
    choose_single_video_quality,
)
from ui.theme import (
    BOX_STYLES,
    PLATFORMS_REGISTRY,
    clear_terminal,
    config_mgr,
    console,
    init_windows_terminal,
    render_banner,
    reset_breadcrumb,
)

clean_dummy_cookie_profiles(config_mgr)

def interactive_menu():
    """Run main interactive menu loop."""
    init_windows_terminal()
    while True:
        clear_terminal()
        reset_breadcrumb("Main Menu")
        banner = render_banner()

        main_items = [
            MenuItem("1", "Single Media / Audio", "Download single video, reel, post, track from 11 platforms or 1000+ sites", group="DOWNLOAD", value="1"),
            MenuItem("2", "Batch Links File (.txt)", "Queue multiple links from a text file with mixed platform detection", group="DOWNLOAD", value="2"),
            MenuItem("3", "Paste URLs Interactively", "Multi-line quick paste buffer for instant ad-hoc batch processing", group="DOWNLOAD", value="3"),
            MenuItem("4", "Download Saved / Bookmarks", "Bulk download saved collections from Instagram, TikTok, Reddit, X", group="LIBRARY", value="4"),
            MenuItem("5", "Audio-Only Suite", "Download tracks, extract high-res audio, EBU R128 loudness normalization", group="DOWNLOAD", value="5"),
            MenuItem("6", "YouTube Playlists & Channels", "Full playlists, watch later, liked videos, creator channel index", group="CHANNELS", value="6"),
            MenuItem("7", "Creator Profiles & Feeds", "Instagram stories, TikTok profiles, X timelines, Threads", group="CHANNELS", value="7"),
            MenuItem("8", "Reposts & Retweets", "TikTok Reposted videos, Instagram Reposts archive, X/Twitter Retweets", group="LIBRARY", value="8"),
            MenuItem("9", "Settings & Accounts", "11 platform credentials, speed limiter, missing file policy, folder presets", group="SYSTEM", value="9"),
            MenuItem("0", "Exit Workstation", "Safely close session checkpoints and exit", group="SYSTEM", danger=True, value="0"),
        ]

        def _main_details(item: MenuItem):
            det = Table.grid(expand=True, padding=(0, 0))
            det.add_column(ratio=1)
            det.add_row(Text(item.label, style=f"bold {A7_TEXT}"))
            det.add_row(Text(item.detail, style=f"dim {A7_MUTED}"))
            det.add_row("")

            spec_map = {
                "1": [("Platforms", "11 Specialized + 1000+ Sites"), ("Engines", "yt-dlp, aria2c, Mutagen, EBU R128"), ("Formats", "MP4, MKV, MP3, FLAC, M4A, WAV")],
                "2": [("Platforms", "Any text file with mixed platform links"), ("Deduplication", "Automatic pre-flight check vs history"), ("Engines", "Parallel aria2c / yt-dlp workers")],
                "3": [("Buffer", "Multi-line paste buffer"), ("Batching", "Instant queue resolution"), ("Detection", "11 Core + 1000+ Universal URLs")],
                "4": [("Feeds", "Instagram, TikTok, Reddit, X, FB, Pinterest"), ("Auth", "Uses saved session cookies"), ("Storage", "Dedicated sub-folders per collection")],
                "5": [("Formats", "MP3, FLAC, M4A, OPUS, WAV"), ("Mastering", "EBU R128 Loudness Normalization (-14 LUFS)"), ("Tagging", "ID3v2.4 Cover Art & Metadata")],
                "6": [("Playlists", "Full playlists, Watch Later, Liked Videos"), ("Channels", "Creator uploads & channel video archives"), ("Indexing", "Ordered batch processing")],
                "7": [("Sources", "Instagram Stories/Highlights, TikTok, X, Threads"), ("Extraction", "Native JSON API & media scrapers"), ("History", "Smart delta skip")],
                "8": [("Supported", "TikTok Reposts, Instagram Reposts, X Retweets"), ("Data", "JSON exports or live session feeds"), ("Deduplication", "Archive-aware incremental sync")],
                "9": [("Sessions", f"11 Platforms ({sum(1 for p in PLATFORMS_REGISTRY if config_mgr.get_cookie_profiles(p['id']))} signed in)"), ("Limiter", config_mgr.get_default_speed_limit() or "Unlimited"), ("Folder", os.path.basename(config_mgr.get_default_output_dir()) or config_mgr.get_default_output_dir())],
                "0": [("Status", "Clean exit"), ("Sessions", "All auth sessions preserved safely"), ("Workstation", f"Haustus Opus #{A7_OPUS}")]
            }
            item_val = str(item.value)
            specs = spec_map.get(item_val, [])
            for k_spec, v_spec in specs:
                det.add_row(Text(f"  {k_spec:<12} {v_spec}", style=f"{A7_BRASS}"))
            det.add_row("")

            m_val = config_mgr.get_default_embed_metadata()
            m_str = "Cover + tags" if m_val is not False else "No metadata"
            mode_str = config_mgr.get_default_mode() or "Prompt each time"
            spd_str = config_mgr.get_default_speed_limit() or "Unlimited"
            out_str = os.path.basename(config_mgr.get_default_output_dir()) or config_mgr.get_default_output_dir()

            sub_t = Table.grid(expand=True, padding=(0, 1))
            sub_t.add_column(style=f"dim {A7_MUTED}", width=12)
            sub_t.add_column(style=f"{A7_TEXT}")
            sub_t.add_row("Folder", out_str)
            sub_t.add_row("Mode", mode_str)
            sub_t.add_row("Metadata", m_str)
            sub_t.add_row("Speed", spd_str)
            det.add_row(sub_t)

            det.add_row("")
            det.add_row(Text(f"  Hotkeys      Press [{item.key}] to trigger instantly", style=f"{A7_SIGNAL}"))

            return Panel(det, title="DETAILS", title_align="left", box=BOX_STYLES["normal"], border_style=A7_SIGNAL)

        choice = select_menu(
            title="MENU (10)",
            items=main_items,
            breadcrumb="Main Menu",
            default_index=0,
            details_generator=_main_details,
            footer_keys="[Up/Down] Move [Enter] Open [1-9] Jump [H/?] Help [Esc] Back [Q] Quit",
            banner=banner,
        )

        if choice in ("0", "exit"):
            clear_terminal()
            console.print(f"[bold {A7_SIGNAL}]Goodbye![/bold {A7_SIGNAL}]\n")
            sys.exit(0)

        if choice in ("cancel", "back", None):
            continue

        choice_up = str(choice).upper()
        if choice_up == "1":
            run_single_video_menu()
        elif choice_up == "2":
            run_bulk_file_menu()
        elif choice_up == "3":
            run_paste_urls_menu()
        elif choice_up == "4":
            unified_saved_posts_menu()
        elif choice_up == "5":
            run_audio_mode_menu()
        elif choice_up == "6":
            run_youtube_playlist_menu()
        elif choice_up == "7":
            run_profile_menu()
        elif choice_up == "8":
            dedicated_reposts_menu()
        elif choice_up == "9":
            manage_configuration_menu(config_mgr)

def main():
    parser = argparse.ArgumentParser(
        description="Haustus: High-performance bulk media downloader supporting 11 specialized platforms (Instagram, TikTok, YouTube, X, SoundCloud, Reddit, Facebook, Pinterest, Twitch, Threads, Spotify) and universal download for 1000+ websites and direct media streams."
    )
    parser.add_argument("-f", "--file", help="Path to links text file (any .txt file supported)")
    parser.add_argument("-u", "--user", help="Username or profile/channel URL (Instagram, TikTok, or YouTube)")
    parser.add_argument("-p", "--playlist", help="YouTube playlist URL to download in bulk")
    parser.add_argument("-q", "--quality", help="Target video quality (e.g. 'best', '2160', '1440', '1080', '720', '480', '360')")
    parser.add_argument("-a", "--audio", action="store_true", help="Download in Audio-Only mode")
    parser.add_argument("-aq", "--audio-quality", default="192", help="Audio bitrate ('320', '256', '192', '128', '64', 'best') (default: 192)")
    parser.add_argument("-af", "--audio-format", default="mp3", help="Audio container format ('mp3', 'm4a', 'flac', 'wav', 'opus') (default: mp3)")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_DIR, help="Destination directory for downloads")
    parser.add_argument("-c", "--cookies", help="Path to cookies.txt or raw cookie string / sessionid")
    parser.add_argument("--clip", help="Download a specific time range only (e.g. '01:20-03:45' or '00:01:20-00:03:45')")
    parser.add_argument("--subtitles", action="store_true", help="Download and embed subtitles (.srt / .vtt)")
    parser.add_argument("--instagram-stories", help="Download active 24h Instagram Stories for @username or URL")
    parser.add_argument("--instagram-highlights", help="Download Instagram Story Highlights for @username or Highlight URL")
    parser.add_argument("--saved", action="store_true", help="Download all saved posts from your authenticated Instagram account")
    parser.add_argument("--instagram-reposts", action="store_true", help="Download all reposted posts and reels from your authenticated Instagram account")
    parser.add_argument("--instagram-json", help="Path to Instagram data export JSON file (e.g. reposts.json)")
    parser.add_argument("--tiktok-saved", action="store_true", help="Download all saved / favorite videos from your authenticated TikTok account")
    parser.add_argument("--tiktok-reposts", action="store_true", help="Download all reposted videos from your authenticated TikTok account")
    parser.add_argument("--tiktok-cookies", help="Path to tiktok_cookies.txt or raw TikTok sessionid")
    parser.add_argument("--tiktok-json", help="Path to TikTok user_data.json data export file")
    parser.add_argument("--tiktok-collection", help="URL of TikTok collection to download in bulk")
    parser.add_argument("--x-bookmarks", action="store_true", help="Download all saved / bookmarked tweets from your authenticated X account")
    parser.add_argument("--x-reposts", action="store_true", help="Download all reposted / retweeted media from your authenticated X account")
    parser.add_argument("--x-cookies", help="Path to x_cookies.txt or raw X auth_token")
    parser.add_argument("--x-json", help="Path to X archive JSON or JS file (bookmarks.json, tweets.json)")
    parser.add_argument("--soundcloud-likes", help="SoundCloud username or URL to download liked tracks in bulk")
    parser.add_argument("--soundcloud-cookies", help="Path to soundcloud_cookies.txt or raw SoundCloud oauth_token")
    parser.add_argument("--reddit-saved", action="store_true", help="Download all saved posts from your authenticated Reddit account")
    parser.add_argument("--reddit-upvoted", action="store_true", help="Download all upvoted posts from your authenticated Reddit account")
    parser.add_argument("--reddit-subreddit", help="Subreddit name or URL to download in bulk (e.g. 'videos' or 'r/wallpapers')")
    parser.add_argument("--reddit-sort", choices=['hot', 'new', 'top', 'rising'], default='hot', help="Subreddit sorting method (default: hot)")
    parser.add_argument("--reddit-timeframe", choices=['hour', 'day', 'week', 'month', 'year', 'all'], default='all', help="Timeframe for top subreddit posts (default: all)")
    parser.add_argument("--reddit-cookies", help="Path to reddit_cookies.txt or raw Reddit session token")
    parser.add_argument("--facebook-saved", action="store_true", help="Download all saved videos from your authenticated Facebook account")
    parser.add_argument("--facebook-cookies", help="Path to facebook_cookies.txt or raw Facebook c_user/xs cookies")
    parser.add_argument("--pinterest-board", help="URL of Pinterest board to download in bulk")
    parser.add_argument("--pinterest-saved", action="store_true", help="Download all saved pins from your authenticated Pinterest account")
    parser.add_argument("--pinterest-cookies", help="Path to pinterest_cookies.txt or raw Pinterest _pinterest_sess cookie")
    parser.add_argument("--twitch-channel", help="Twitch streamer/channel username or URL to download in bulk")
    parser.add_argument("--twitch-cookies", help="Path to twitch_cookies.txt or raw Twitch auth-token")
    parser.add_argument("--threads-profile", help="Threads creator username or profile URL to download in bulk")
    parser.add_argument("--threads-cookies", help="Path to threads_cookies.txt or raw Threads sessionid")
    parser.add_argument("--spotify-playlist", help="Spotify playlist, album, or collection URL to download in bulk")
    parser.add_argument("--spotify-cookies", help="Path to spotify_cookies.txt or raw Spotify sp_dc session token")
    parser.add_argument("--delay", type=float, default=2.0, help="Polite delay in seconds between downloads (default: 2.0)")
    parser.add_argument("--aria2", action="store_true", help="Enable segmented 16-connection multi-stream download via aria2c")
    parser.add_argument("--normalize", action="store_true", help="Enable two-pass EBU R128 (-16 LUFS) loudness normalization")
    parser.add_argument("--transcode", action="store_true", help="Enable GPU-accelerated video transcoding (NVENC/VAAPI/AV1)")
    parser.add_argument("--parallel", action="store_true", help="Enable high-throughput multi-threaded parallel batch execution")
    parser.add_argument("--proxy", help="HTTP/HTTPS/SOCKS5 proxy URI (e.g. http://127.0.0.1:7890)")
    parser.add_argument("--speed-limit", help="Download bandwidth speed limit (e.g. '2M', '5M', '10M', '500K')")
    parser.add_argument("--embed-metadata", action="store_true", default=None, help="Force embedding thumbnail cover art and metadata tags")
    parser.add_argument("--no-embed-metadata", action="store_true", help="Force disabling embedding cover art and metadata")
    parser.add_argument("--count-limit", type=int, help="Cap download batch at maximum number of items")
    parser.add_argument("--date-after", help="Filter items uploaded after date (YYYYMMDD or 'now-7days')")
    parser.add_argument("--shorts-only", action="store_true", help="Download short videos only (<= 60s)")
    parser.add_argument("--items", "--playlist-items", dest="items", help="Specify item indices or range to download (e.g. '1,3,5-8' or exclude '~2,4')")
    parser.add_argument("--archive", action="store_true", default=None, help="Force checking download history archive (skip already downloaded)")
    parser.add_argument("--no-archive", action="store_true", help="Force ignoring download history archive (re-download everything)")
    parser.add_argument("urls", nargs="*", help="Direct media URLs from 1000+ supported sites (YouTube, Instagram, TikTok, Vimeo, etc.) or direct media links")

    args = parser.parse_args()

    if args.speed_limit:
        config_mgr.set_default_speed_limit(args.speed_limit)

    cli_smart_filters = {}
    if args.items:
        cli_smart_filters["items"] = args.items
        cli_smart_filters["items_label"] = args.items
    if args.count_limit:
        cli_smart_filters["count_limit"] = args.count_limit
    if args.date_after:
        cli_smart_filters["date_after"] = args.date_after
    if args.shorts_only:
        cli_smart_filters["shorts_only"] = True
    if not cli_smart_filters:
        cli_smart_filters = None

    cli_use_archive = None
    if args.no_archive:
        cli_use_archive = False
    elif args.archive:
        cli_use_archive = True

    cli_embed_metadata = False if args.no_embed_metadata else (True if args.embed_metadata else None)

    cookie_file = prepare_cookies(args.cookies) if args.cookies else None
    if args.spotify_cookies:
        prepare_spotify_cookies(args.spotify_cookies)

    mode = "audio" if args.audio or str(args.quality).lower() == "audio" else "video"
    video_quality = args.quality or "best"
    audio_format = args.audio_format.lower()
    audio_quality = args.audio_quality

    if args.instagram_stories:
        download_instagram_stories_or_highlights(
            args.instagram_stories,
            output_dir=args.output,
            cookie_file=cookie_file,
            mode=mode,
            video_quality=video_quality,
            audio_format=audio_format,
            audio_quality=audio_quality,
            delay=args.delay,
            embed_metadata=cli_embed_metadata,
            kind="stories",
        )
        return
    if args.instagram_highlights:
        download_instagram_stories_or_highlights(
            args.instagram_highlights,
            output_dir=args.output,
            cookie_file=cookie_file,
            mode=mode,
            video_quality=video_quality,
            audio_format=audio_format,
            audio_quality=audio_quality,
            delay=args.delay,
            embed_metadata=cli_embed_metadata,
            kind="highlights",
        )
        return

    if args.parallel and (args.file or args.urls):
        urls_to_download = []
        if args.file and os.path.isfile(args.file):
            with open(args.file, "r", encoding="utf-8") as f:
                urls_to_download.extend([line.strip() for line in f if line.strip() and not line.strip().startswith("#")])
        if args.urls:
            urls_to_download.extend([u.strip() for u in args.urls if u.strip() and not u.strip().startswith("#")])

        if urls_to_download:
            console.print(f"[bold cyan][*] Launching High-Throughput Parallel Engine for {len(urls_to_download)} items...[/bold cyan]")
            engine = HighThroughputEngine(
                output_dir=args.output,
                cookie_file=cookie_file,
                use_aria2=args.aria2,
                proxy=args.proxy
            )
            res = engine.download_batch_parallel(
                urls=urls_to_download,
                mode=mode,
                video_quality=video_quality,
                audio_format=audio_format,
                audio_quality=audio_quality,
                normalize=args.normalize,
                transcode=args.transcode
            )
            console.print(f"[bold green][OK] Parallel batch finished: {res['succeeded']} succeeded, {res['failed']} failed.[/bold green]")
            return

    if args.saved:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        download_instagram_saved_posts(
            cookie_file=cookie_file, output_dir=args.output,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy
        )
    elif args.instagram_reposts or args.instagram_json:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        ig_c = cookie_file or get_effective_instagram_cookie_file()
        custom_urls = None
        if args.instagram_json:
            custom_urls = parse_instagram_reposts_json(args.instagram_json)
        download_instagram_reposted_posts(
            cookie_file=ig_c, output_dir=args.output,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy,
            custom_urls=custom_urls
        )
    elif args.tiktok_reposts:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        tt_c = prepare_tiktok_cookies(args.tiktok_cookies) if args.tiktok_cookies else (cookie_file or get_effective_tiktok_cookie_file())
        download_tiktok_reposted_videos(
            cookie_file=tt_c, output_dir=args.output,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy
        )
    elif args.tiktok_saved or args.tiktok_json:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        tt_c = prepare_tiktok_cookies(args.tiktok_cookies) if args.tiktok_cookies else (cookie_file or get_effective_tiktok_cookie_file())
        custom_urls = None
        if args.tiktok_json:
            custom_urls = parse_tiktok_user_data_json(args.tiktok_json)
        download_tiktok_saved_posts(
            cookie_file=tt_c, output_dir=args.output,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy,
            custom_urls=custom_urls
        )
    elif args.tiktok_collection:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        download_urls(
            [args.tiktok_collection], output_dir=os.path.join(args.output, "tiktok_collections"),
            cookie_file=args.tiktok_cookies or cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy,
            is_bulk=True, clip_range=args.clip, subtitles=args.subtitles
        )
    elif args.x_reposts:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        x_c = prepare_x_cookies(args.x_cookies) if args.x_cookies else (cookie_file or get_effective_x_cookie_file())
        custom_urls = None
        if args.x_json:
            custom_urls = parse_x_data_archive(args.x_json, kind="reposts")
        download_x_reposts(
            cookie_file=x_c, output_dir=args.output,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy,
            custom_urls=custom_urls
        )
    elif args.x_bookmarks or (args.x_json and not args.tiktok_saved and not args.tiktok_reposts):
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        x_c = prepare_x_cookies(args.x_cookies) if args.x_cookies else (cookie_file or get_effective_x_cookie_file())
        custom_urls = None
        if args.x_json:
            custom_urls = parse_x_data_archive(args.x_json, kind="bookmarks")
        download_x_bookmarks(
            cookie_file=x_c, output_dir=args.output,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy,
            custom_urls=custom_urls
        )
    elif args.soundcloud_likes:
        if not args.audio and sys.stdin.isatty():
            mode = "audio"
        sc_c = prepare_soundcloud_cookies(args.soundcloud_cookies) if args.soundcloud_cookies else (cookie_file or get_effective_soundcloud_cookie_file())
        download_soundcloud_liked_tracks(
            username_or_url=args.soundcloud_likes,
            cookie_file=sc_c,
            output_dir=args.output,
            audio_format=audio_format,
            audio_quality=audio_quality,
            smart_filters=cli_smart_filters,
            embed_metadata=cli_embed_metadata
        )
    elif args.reddit_saved or args.reddit_upvoted or args.reddit_subreddit:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        rd_c = prepare_reddit_cookies(args.reddit_cookies) if args.reddit_cookies else (cookie_file or get_effective_reddit_cookie_file())
        feed_target = "saved" if args.reddit_saved else ("upvoted" if args.reddit_upvoted else args.reddit_subreddit)
        download_reddit_feed(
            feed_target,
            output_dir=args.output,
            sort=args.reddit_sort,
            timeframe=args.reddit_timeframe,
            cookie_file=rd_c,
            mode=mode,
            video_quality=video_quality,
            audio_format=audio_format,
            audio_quality=audio_quality,
            delay=args.delay,
            smart_filters=cli_smart_filters,
            embed_metadata=cli_embed_metadata
        )
    elif args.facebook_saved:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        fb_c = prepare_facebook_cookies(args.facebook_cookies) if args.facebook_cookies else (cookie_file or get_effective_facebook_cookie_file())
        download_facebook_saved_videos(
            cookie_file=fb_c,
            output_dir=args.output,
            mode=mode,
            video_quality=video_quality,
            audio_format=audio_format,
            audio_quality=audio_quality,
            delay=args.delay,
            smart_filters=cli_smart_filters
        )
    elif args.pinterest_board or args.pinterest_saved:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        pin_c = prepare_pinterest_cookies(args.pinterest_cookies) if args.pinterest_cookies else (cookie_file or get_effective_pinterest_cookie_file())
        if args.pinterest_board:
            download_pinterest_board(
                board_url=args.pinterest_board,
                output_dir=args.output,
                cookie_file=pin_c,
                mode=mode,
                video_quality=video_quality,
                audio_format=audio_format,
                audio_quality=audio_quality,
                delay=args.delay,
                smart_filters=cli_smart_filters
            )
        else:
            download_urls(
                ["https://www.pinterest.com/"],
                output_dir=os.path.join(args.output, "pinterest_saved"),
                cookie_file=pin_c,
                mode=mode,
                video_quality=video_quality,
                audio_format=audio_format,
                audio_quality=audio_quality,
                delay=args.delay,
                smart_filters=cli_smart_filters,
                is_bulk=True
            )
    elif args.twitch_channel:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        tw_c = prepare_twitch_cookies(args.twitch_cookies) if args.twitch_cookies else (cookie_file or get_effective_twitch_cookie_file())
        download_twitch_channel(
            channel_url=args.twitch_channel,
            output_dir=args.output,
            cookie_file=tw_c,
            mode=mode,
            video_quality=video_quality,
            audio_format=audio_format,
            audio_quality=audio_quality,
            delay=args.delay,
            smart_filters=cli_smart_filters
        )
    elif args.threads_profile:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        th_c = prepare_threads_cookies(args.threads_cookies) if args.threads_cookies else (cookie_file or get_effective_threads_cookie_file())
        download_threads_profile(
            profile_url_or_user=args.threads_profile,
            output_dir=args.output,
            cookie_file=th_c,
            mode=mode,
            video_quality=video_quality,
            audio_format=audio_format,
            audio_quality=audio_quality,
            delay=args.delay,
            smart_filters=cli_smart_filters
        )
    elif args.spotify_playlist:
        sp_c = prepare_spotify_cookies(args.spotify_cookies) if args.spotify_cookies else (cookie_file or get_effective_spotify_cookie_file())
        download_spotify_playlist(
            url=args.spotify_playlist,
            output_dir=args.output,
            cookie_file=sp_c,
            audio_format=audio_format,
            audio_quality=audio_quality,
            delay=args.delay,
            smart_filters=cli_smart_filters,
            embed_metadata=cli_embed_metadata
        )
    elif args.playlist:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        download_urls(
            [args.playlist], output_dir=args.output, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy,
            smart_filters=cli_smart_filters, embed_metadata=cli_embed_metadata,
            is_bulk=True, clip_range=args.clip, subtitles=args.subtitles,
            use_archive=cli_use_archive
        )
    elif args.file:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        download_from_file(
            args.file, output_dir=args.output, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy,
            smart_filters=cli_smart_filters, embed_metadata=cli_embed_metadata,
            use_archive=cli_use_archive
        )
    elif args.user:
        if not args.quality and not args.audio and sys.stdin.isatty():
            mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        download_profile(
            args.user, output_dir=args.output, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy,
            smart_filters=cli_smart_filters, embed_metadata=cli_embed_metadata,
            clip_range=args.clip, subtitles=args.subtitles,
            use_archive=cli_use_archive
        )
    elif args.urls:
        if not args.quality and not args.audio and sys.stdin.isatty():
            if len(args.urls) == 1:
                mode, video_quality, audio_format, audio_quality = choose_single_video_quality(args.urls[0], cookie_file=cookie_file)
            else:
                mode, video_quality, audio_format, audio_quality = choose_bulk_quality()
        download_urls(
            args.urls, output_dir=args.output, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=args.delay,
            use_aria2=args.aria2, normalize=args.normalize,
            transcode=args.transcode, proxy=args.proxy,
            smart_filters=cli_smart_filters, embed_metadata=cli_embed_metadata,
            clip_range=args.clip, subtitles=args.subtitles,
            use_archive=cli_use_archive
        )
    else:
        interactive_menu()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("[bold yellow][!] Operation interrupted by user. Exiting...[/bold yellow]")
        sys.exit(0)
