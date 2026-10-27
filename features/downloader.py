"""Batch download pipeline and progress orchestrator."""
import os
import re
import shutil
import sys
import time
from pathlib import Path

import requests
import yt_dlp

from core.archive import (
    DEFAULT_OUTPUT_DIR,
    HISTORY_FILE,
    RESULT_DOWNLOADED,
    RESULT_SKIPPED,
    add_to_archive,
    check_disk_presence,
    extract_url_item_id,
    find_downloaded_media_file,
    get_archive_set,
    is_archived,
    remove_from_failed_urls,
    reset_missing_decision_cache,
    resolve_archive_policy,
)
from core.cookies import (
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
    get_effective_youtube_cookie_file,
    load_cookie_jar,
)
from core.instances import config_mgr, media_maestro
from core.urls import (
    is_facebook_url,
    is_instagram_url,
    is_pinterest_url,
    is_reddit_url,
    is_soundcloud_url,
    is_spotify_url,
    is_threads_url,
    is_tiktok_url,
    is_twitch_url,
    is_x_url,
    is_youtube_url,
)
from core.ytdl_format import (
    get_ydl_format,
)
from platforms.facebook import (
    process_facebook_item,
)
from platforms.instagram import (
    extract_instagram_info,
    process_instagram_post,
)
from platforms.pinterest import (
    process_pinterest_pin,
)
from platforms.reddit import (
    process_reddit_post,
)
from platforms.soundcloud import (
    process_soundcloud_item,
)
from platforms.spotify import (
    process_spotify_item,
)
from platforms.threads import (
    process_threads_item,
)
from platforms.tiktok import (
    process_tiktok_post,
)
from platforms.twitch import (
    process_twitch_item,
)
from platforms.x_twitter import (
    process_x_post,
)
from platforms.youtube import (
    process_youtube_url,
)
from ui.dashboard import (
    RichLiveDownloadDashboard,
    SkipItemRequested,
    YtdlQuietLogger,
    check_cancel_requested,
    interruptible_sleep,
)
from ui.quality import parse_time_range, resolve_embed_metadata
from ui.theme import FFMPEG_EXE, console, print_summary_table


def download_urls(
    urls: list[str],
    output_dir: str = DEFAULT_OUTPUT_DIR,
    browser: str = None,
    cookie_file: str = None,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    use_aria2: bool = False,
    normalize: bool = False,
    transcode: bool = False,
    proxy: str = None,
    smart_filters: dict = None,
    embed_metadata: bool = None,
    is_bulk: bool = False,
    use_archive: bool = None,
    clip_range: str = None,
    subtitles: bool = False,
    initial_skipped: int = 0,
):
    """Batch download URLs across all platforms."""
    cleaned_urls = [u.strip() for u in urls if u.strip() and not u.strip().startswith("#")]
    if not cleaned_urls:
        if initial_skipped > 0:
            print_summary_table(
                total=initial_skipped,
                succeeded=0,
                skipped=initial_skipped,
                failed=0,
                output_dir=output_dir,
                failed_urls_list=[]
            )
            return (0, 0, initial_skipped)
        console.print("[bold red][!] No valid URLs provided for download.[/bold red]")
        return (0, 0, 0)

    if embed_metadata is None:
        embed_metadata = resolve_embed_metadata()

    if use_archive is None:
        use_archive = resolve_archive_policy(is_bulk=is_bulk)

    reset_missing_decision_cache()

    os.makedirs(output_dir, exist_ok=True)
    archive_path = os.path.join(output_dir, HISTORY_FILE)
    if use_archive:
        archive_set = get_archive_set(archive_path)
    else:
        archive_set = set()

    console.print(f"[bold cyan][*] Starting process for {len(cleaned_urls)} URL(s)...[/bold cyan]")
    console.print(f"[dim][FOLDER] Destination Directory:[/dim] [bold white]{os.path.abspath(output_dir)}[/bold white]")
    if use_archive:
        console.print("[dim][ARCHIVE] Download history tracking active[/dim]")
    else:
        console.print("[dim][ARCHIVE] Download history tracking disabled[/dim]")

    if mode == "audio":
        console.print(f"[bold magenta][AUDIO] Mode:[/bold magenta] Audio Only ([bold cyan]{audio_format.upper()} @ {audio_quality}k[/bold cyan])")
    elif video_quality and video_quality != "best":
        console.print(f"[bold green][VIDEO] Mode:[/bold green] Video ([bold cyan]{video_quality}p max cap[/bold cyan])")
    else:
        console.print("[bold green][VIDEO] Mode:[/bold green] Video ([bold cyan]Best Available / Full HD / 4K[/bold cyan])")

    if embed_metadata:
        console.print("[dim][METADATA] Auto-embedding cover art & track metadata active[/dim]")

    cj = None
    if not cookie_file:
        has_ig = any(is_instagram_url(u) for u in cleaned_urls)
        has_tt = any(is_tiktok_url(u) for u in cleaned_urls)
        has_yt = any(is_youtube_url(u) for u in cleaned_urls)
        has_x = any(is_x_url(u) for u in cleaned_urls)
        has_sc = any(is_soundcloud_url(u) for u in cleaned_urls)
        has_rd = any(is_reddit_url(u) for u in cleaned_urls)
        has_fb = any(is_facebook_url(u) for u in cleaned_urls)
        has_pin = any(is_pinterest_url(u) for u in cleaned_urls)
        has_tw = any(is_twitch_url(u) for u in cleaned_urls)
        has_th = any(is_threads_url(u) for u in cleaned_urls)
        has_sp = any(is_spotify_url(u) for u in cleaned_urls)
        if has_yt and not (has_ig or has_tt or has_x or has_sc or has_rd or has_fb or has_pin or has_tw or has_th or has_sp):
            cookie_file = get_effective_youtube_cookie_file()
        elif has_tt and not (has_ig or has_yt or has_x or has_sc or has_rd or has_fb or has_pin or has_tw or has_th or has_sp):
            cookie_file = get_effective_tiktok_cookie_file()
        elif has_x and not (has_ig or has_tt or has_yt or has_sc or has_rd or has_fb or has_pin or has_tw or has_th or has_sp):
            cookie_file = get_effective_x_cookie_file()
        elif has_sc and not (has_ig or has_tt or has_yt or has_x or has_rd or has_fb or has_pin or has_tw or has_th or has_sp):
            cookie_file = get_effective_soundcloud_cookie_file()
        elif has_rd and not (has_ig or has_tt or has_yt or has_x or has_sc or has_fb or has_pin or has_tw or has_th or has_sp):
            cookie_file = get_effective_reddit_cookie_file()
        elif has_fb and not (has_ig or has_tt or has_yt or has_x or has_sc or has_rd or has_pin or has_tw or has_th or has_sp):
            cookie_file = get_effective_facebook_cookie_file()
        elif has_pin and not (has_ig or has_tt or has_yt or has_x or has_sc or has_rd or has_fb or has_tw or has_th or has_sp):
            cookie_file = get_effective_pinterest_cookie_file()
        elif has_tw and not (has_ig or has_tt or has_yt or has_x or has_sc or has_rd or has_fb or has_pin or has_th or has_sp):
            cookie_file = get_effective_twitch_cookie_file()
        elif has_th and not (has_ig or has_tt or has_yt or has_x or has_sc or has_rd or has_fb or has_pin or has_tw or has_sp):
            cookie_file = get_effective_threads_cookie_file()
        elif has_sp and not (has_ig or has_tt or has_yt or has_x or has_sc or has_rd or has_fb or has_pin or has_tw or has_th):
            cookie_file = get_effective_spotify_cookie_file()
        elif has_ig and not (has_tt or has_yt or has_x or has_sc or has_rd or has_fb or has_pin or has_tw or has_th or has_sp):
            cookie_file = get_effective_instagram_cookie_file()

    if cookie_file and os.path.isfile(cookie_file):
        cj = load_cookie_jar(cookie_file)
        if cj:
            console.print(f"[bold green][OK] Loaded cookies from:[/bold green] [dim]{cookie_file}[/dim]")

    fmt_str, pps = get_ydl_format(
        mode=mode, video_quality=video_quality,
        audio_format=audio_format, audio_quality=audio_quality,
        embed_metadata=embed_metadata
    )
    abs_output_dir = os.path.abspath(output_dir)
    os.makedirs(abs_output_dir, exist_ok=True)

    ydl_opts = {
        "format": fmt_str,
        "merge_output_format": "mp4",
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": os.path.join(abs_output_dir, "%(title)s [%(id)s].%(ext)s"),
        "paths": {"temp": abs_output_dir},
        "remote_components": ["ejs:github"],
        "js_runtimes": {"node": {}},
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    ydl_opts["_embed_metadata"] = embed_metadata
    if embed_metadata:
        ydl_opts["writethumbnail"] = True

    if clip_range:
        parsed_clip = parse_time_range(clip_range)
        if parsed_clip:
            start_s, end_s = parsed_clip
            console.print(f"[bold magenta][CLIP] Time-Range Clipping active: {clip_range} ({start_s:.0f}s -> {end_s:.0f}s)[/bold magenta]")
            if hasattr(yt_dlp.utils, "download_range_func"):
                ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(start_s, end_s)])
            ydl_opts["force_keyframes_at_cuts"] = True

    if subtitles:
        console.print("[bold cyan][SUBTITLES] Auto-downloading & embedding subtitles (.srt/.vtt) active[/bold cyan]")
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = True
        ydl_opts["subtitleslangs"] = ["en.*", "ar.*", "all"]
        ydl_opts["subtitlesformat"] = "srt/vtt/best"
        if mode == "video":
            pps = list(pps) + [{"key": "FFmpegEmbedSubtitle"}]

    speed_limit_bytes = config_mgr.get_speed_limit_bytes()
    if speed_limit_bytes:
        ydl_opts["ratelimit"] = speed_limit_bytes
        spd_pref = config_mgr.get_default_speed_limit()
        console.print(f"[bold yellow][SPEED] Bandwidth throttle active: {spd_pref.upper()} max[/bold yellow]")

    if smart_filters:
        if smart_filters.get("count_limit"):
            cnt = smart_filters["count_limit"]
            ydl_opts["max_downloads"] = cnt
            ydl_opts["playlistend"] = cnt
            console.print(f"[bold cyan][FILTER] Item Count Cap: First {cnt} items[/bold cyan]")
            cleaned_urls = cleaned_urls[:cnt]

        if smart_filters.get("date_after"):
            d_after = smart_filters["date_after"]
            ydl_opts["dateafter"] = d_after
            d_lbl = smart_filters.get("date_label", d_after)
            console.print(f"[bold cyan][FILTER] Date Cutoff: {d_lbl}[/bold cyan]")

        if smart_filters.get("shorts_only") or smart_filters.get("max_duration"):
            max_sec = 60 if smart_filters.get("shorts_only") else smart_filters.get("max_duration")
            dur_lbl = smart_filters.get("dur_label", f"<= {max_sec}s")
            console.print(f"[bold cyan][FILTER] Duration Cap: {dur_lbl}[/bold cyan]")
            def _duration_filter(info_dict, *, incomplete=False):
                dur = info_dict.get("duration")
                if dur is not None and dur > max_sec:
                    return f"Duration {dur}s exceeds maximum allowed ({max_sec}s)"
                return None
            ydl_opts["match_filter"] = _duration_filter

    if pps:
        ydl_opts["postprocessors"] = pps

    if FFMPEG_EXE:
        ydl_opts["ffmpeg_location"] = FFMPEG_EXE

    if proxy:
        ydl_opts["proxy"] = proxy

    downloaded_files_batch = []

    def _collect_finished(d):
        if d.get("status") == "finished":
            fn = d.get("filename") or d.get("info_dict", {}).get("_filename") or d.get("info_dict", {}).get("filepath")
            if fn:
                abs_fn = os.path.abspath(fn)
                if abs_fn not in downloaded_files_batch:
                    downloaded_files_batch.append(abs_fn)

    dashboard = RichLiveDownloadDashboard(console)
    dashboard.set_output_dir(abs_output_dir)
    ydl_opts["logger"] = YtdlQuietLogger(dashboard)
    ydl_opts["progress_hooks"] = [dashboard.hook, _collect_finished]
    ydl_opts["postprocessor_hooks"] = [dashboard.postprocessor_hook]

    if use_aria2 and shutil.which("aria2c"):
        console.print("[bold yellow][PERF] aria2c 16-connection acceleration enabled[/bold yellow]")
        ydl_opts["external_downloader"] = "aria2c"
        aria_args = ["-s 16", "-x 16", "-k 1M", "-j 16", "--summary-interval=0", "--console-log-level=error", "--quiet=true"]
        limit_str = config_mgr.get_default_speed_limit()
        if limit_str and limit_str.lower() != "unlimited":
            aria_args.append(f"--max-overall-download-limit={limit_str}")
        ydl_opts["external_downloader_args"] = {
            "default": aria_args
        }

    if cookie_file and os.path.isfile(cookie_file):
        ydl_opts["cookiefile"] = cookie_file
    elif browser:
        ydl_opts["cookiesfrombrowser"] = (browser.lower(),)

    session = requests.Session()
    if cj:
        session.cookies.update(cj)
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}

    successful = 0
    skipped = initial_skipped
    failed = 0
    failed_urls_list = []

    ydl = None
    try:
        ydl = yt_dlp.YoutubeDL(ydl_opts)
        if ydl.cookiejar:
            session.cookies.update(ydl.cookiejar)
    except Exception as e:
        console.print(f"[bold red][-] Error initializing engine: {e}[/bold red]")
        return

    try:
        # Skip already-downloaded items upfront.
        if archive_path and archive_set and len(cleaned_urls) > 1:
            pending_cleaned = []
            upfront_skipped = 0
            for u in cleaned_urls:
                plat, iid = extract_url_item_id(u)
                if iid and is_archived(archive_set, iid, plat or "media", output_dir=abs_output_dir, mode=mode, prompt_missing=False):
                    upfront_skipped += 1
                    skipped += 1
                    remove_from_failed_urls(abs_output_dir, u)
                    remove_from_failed_urls(abs_output_dir, iid)
                else:
                    pending_cleaned.append(u)
            if upfront_skipped > 0:
                console.print(f"[bold blue][ARCHIVE] {upfront_skipped} items already in archive & verified on disk (skipped upfront).[/bold blue]")
                cleaned_urls = pending_cleaned
                if not cleaned_urls:
                    console.print("[bold green][DONE] All items are already downloaded and physically verified on disk![/bold green]")
                    print_summary_table(
                        total=max(len(urls), successful + skipped + failed),
                        succeeded=successful,
                        skipped=skipped,
                        failed=failed,
                        output_dir=output_dir,
                        failed_urls_list=[]
                    )
                    return (successful, skipped, failed)

        dashboard.init_queue(cleaned_urls)
        dashboard.start()
        with ydl:
            for index, url in enumerate(cleaned_urls, 1):
                if check_cancel_requested():
                    break

                plat, item_id = extract_url_item_id(url)
                plat_name = plat.capitalize() if plat else "Media"
                display_name = f"{plat_name} {item_id}" if item_id else url

                dashboard.set_batch(current=index, total=len(cleaned_urls), done=successful, skip=skipped, fail=failed)
                dashboard.start_item(index, title=display_name, platform=plat_name, mode=mode.upper(), quality=video_quality)

                # Check shortcode early to avoid network call.
                if item_id and is_archived(archive_set, item_id, plat or "media", output_dir=output_dir, mode=mode):
                    if not sys.stdout.isatty():
                        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded & verified on disk ({plat.title() if plat else 'Media'} ID: {item_id})[/bold blue]")
                    skipped += 1
                    remove_from_failed_urls(output_dir, url)
                    if item_id:
                        remove_from_failed_urls(output_dir, item_id)
                    dashboard.finish_item(index, status="SKIP", log_msg=f"Skipped: already in archive ({display_name})", done=successful, skip=skipped, fail=failed)
                    continue

                if not sys.stdout.isatty():
                    console.print(f"[bold cyan]{'=' * 60}[/bold cyan]")
                    console.print(f"[bold cyan][{index}/{len(cleaned_urls)}] Processing:[/bold cyan] [bold white]{url}[/bold white]")
                    console.print(f"[bold cyan]{'='*60}[/bold cyan]")
                else:
                    dashboard.refresh(force=True)

                prev_successful = successful
                prev_skipped = skipped
                prev_failed = failed
                max_retries = 3

                for attempt in range(1, max_retries + 1):
                    try:
                        dashboard.poll_live_keys()

                        if is_youtube_url(url):
                            status, s_dl, s_skip, s_fail = process_youtube_url(
                                url, output_dir, ydl, archive_path, archive_set,
                                mode=mode, video_quality=video_quality,
                                audio_format=audio_format, audio_quality=audio_quality,
                                delay=delay, smart_filters=smart_filters,
                                dashboard=dashboard
                            )
                            successful += s_dl
                            skipped += s_skip
                            if s_fail > 0:
                                failed += s_fail
                                if url not in failed_urls_list:
                                    failed_urls_list.append(url)
                            break

                        elif is_tiktok_url(url):
                            if re.search(r"tiktok\.com/@[\w.-]+/?(?:$|[#?])", url):
                                console.print("[cyan][*] TikTok profile detected: extracting all user videos...[/cyan]")
                                info = ydl.extract_info(url, download=False)
                                entries = list(info.get("entries") or [])
                                if smart_filters and smart_filters.get("count_limit"):
                                    entries = entries[:smart_filters["count_limit"]]
                                prof_dl = 0
                                prof_skip = 0
                                prof_fail = 0
                                for p_idx, entry in enumerate(entries, 1):
                                    if not entry:
                                        continue
                                    entry_url = entry.get("url") or entry.get("webpage_url")
                                    if entry_url:
                                        console.print(f"[dim]--- TikTok Profile Item [{p_idx}/{len(entries)}] ---[/dim]")
                                        res = process_tiktok_post(
                                            entry_url, output_dir, ydl, session, archive_path, archive_set,
                                            mode=mode, video_quality=video_quality,
                                            audio_format=audio_format, audio_quality=audio_quality
                                        )
                                        if res == RESULT_DOWNLOADED:
                                            prof_dl += 1
                                        elif res == RESULT_SKIPPED:
                                            prof_skip += 1
                                        else:
                                            prof_fail += 1
                                        if delay > 0:
                                            time.sleep(delay)
                                successful += prof_dl
                                skipped += prof_skip
                                if prof_fail > 0:
                                    failed += prof_fail
                                    if url not in failed_urls_list:
                                        failed_urls_list.append(url)
                                break
                            else:
                                res = process_tiktok_post(
                                    url, output_dir, ydl, session, archive_path, archive_set,
                                    mode=mode, video_quality=video_quality,
                                    audio_format=audio_format, audio_quality=audio_quality
                                )
                                if res == RESULT_DOWNLOADED:
                                    successful += 1
                                elif res == RESULT_SKIPPED:
                                    skipped += 1
                                break

                        elif is_instagram_url(url):
                            info, is_single_post = extract_instagram_info(url, ydl)
                            if not info:
                                console.print(f"[bold yellow]  [!] Instagram post unavailable or deleted on server: {url}[/bold yellow]")
                                dashboard.add_log("[WARN]", f"Post unavailable/deleted: {display_name}")
                                break

                            if is_single_post:
                                res = process_instagram_post(
                                    info, output_dir, ydl, session, archive_path, archive_set,
                                    mode=mode, video_quality=video_quality,
                                    audio_format=audio_format, audio_quality=audio_quality
                                )
                                if res == RESULT_DOWNLOADED:
                                    successful += 1
                                elif res == RESULT_SKIPPED:
                                    skipped += 1
                                break
                            elif info.get("_type") == "playlist" and "entries" in info:
                                all_posts = list(info.get("entries") or [])
                                if smart_filters and smart_filters.get("count_limit"):
                                    all_posts = all_posts[:smart_filters["count_limit"]]
                                console.print(f"[cyan][*] Instagram profile playlist detected: {len(all_posts)} items found.[/cyan]")
                                ig_dl = 0
                                ig_skip = 0
                                ig_fail = 0
                                for p_idx, post_info in enumerate(all_posts, 1):
                                    if not post_info:
                                        continue
                                    console.print(f"[dim]--- Instagram Item [{p_idx}/{len(all_posts)}] ---[/dim]")
                                    res = process_instagram_post(
                                        post_info, output_dir, ydl, session, archive_path, archive_set,
                                        mode=mode, video_quality=video_quality,
                                        audio_format=audio_format, audio_quality=audio_quality
                                    )
                                    if res == RESULT_DOWNLOADED:
                                        ig_dl += 1
                                    elif res == RESULT_SKIPPED:
                                        ig_skip += 1
                                    else:
                                        ig_fail += 1
                                    if delay > 0:
                                        time.sleep(delay)
                                successful += ig_dl
                                skipped += ig_skip
                                if ig_fail > 0:
                                    failed += ig_fail
                                    if url not in failed_urls_list:
                                        failed_urls_list.append(url)
                                break
                            else:
                                res = process_instagram_post(
                                    info, output_dir, ydl, session, archive_path, archive_set,
                                    mode=mode, video_quality=video_quality,
                                    audio_format=audio_format, audio_quality=audio_quality
                                )
                                if res == RESULT_DOWNLOADED:
                                    successful += 1
                                elif res == RESULT_SKIPPED:
                                    skipped += 1
                                break

                        elif is_x_url(url):
                            res = process_x_post(
                                url, output_dir, ydl, session, archive_path, archive_set,
                                mode=mode, video_quality=video_quality,
                                audio_format=audio_format, audio_quality=audio_quality
                            )
                            if res == RESULT_DOWNLOADED:
                                successful += 1
                            elif res == RESULT_SKIPPED:
                                skipped += 1
                            break

                        elif is_soundcloud_url(url):
                            res = process_soundcloud_item(
                                url, output_dir, ydl, session, archive_path, archive_set,
                                mode=mode, audio_format=audio_format, audio_quality=audio_quality,
                                delay=delay, smart_filters=smart_filters,
                                dashboard=dashboard
                            )
                            if res == RESULT_DOWNLOADED:
                                successful += 1
                            elif res == RESULT_SKIPPED:
                                skipped += 1
                            break

                        elif is_reddit_url(url):
                            res = process_reddit_post(
                                url, output_dir, ydl, session, archive_path, archive_set,
                                mode=mode, video_quality=video_quality,
                                audio_format=audio_format, audio_quality=audio_quality
                            )
                            if res == RESULT_DOWNLOADED:
                                successful += 1
                            elif res == RESULT_SKIPPED:
                                skipped += 1
                            break

                        elif is_facebook_url(url):
                            res = process_facebook_item(
                                url, output_dir, ydl, session, archive_path, archive_set,
                                mode=mode, video_quality=video_quality,
                                audio_format=audio_format, audio_quality=audio_quality,
                                delay=delay, smart_filters=smart_filters
                            )
                            if res == RESULT_DOWNLOADED:
                                successful += 1
                            elif res == RESULT_SKIPPED:
                                skipped += 1
                            break

                        elif is_pinterest_url(url):
                            res = process_pinterest_pin(
                                url, output_dir, ydl, session, archive_path, archive_set,
                                mode=mode, video_quality=video_quality,
                                audio_format=audio_format, audio_quality=audio_quality,
                                delay=delay, smart_filters=smart_filters
                            )
                            if res == RESULT_DOWNLOADED:
                                successful += 1
                            elif res == RESULT_SKIPPED:
                                skipped += 1
                            break

                        elif is_twitch_url(url):
                            res = process_twitch_item(
                                url, output_dir, ydl, session, archive_path, archive_set,
                                mode=mode, video_quality=video_quality,
                                audio_format=audio_format, audio_quality=audio_quality,
                                delay=delay, smart_filters=smart_filters
                            )
                            if res == RESULT_DOWNLOADED:
                                successful += 1
                            elif res == RESULT_SKIPPED:
                                skipped += 1
                            break

                        elif is_threads_url(url):
                            res = process_threads_item(
                                url, output_dir, ydl, session, archive_path, archive_set,
                                mode=mode, video_quality=video_quality,
                                audio_format=audio_format, audio_quality=audio_quality,
                                delay=delay, smart_filters=smart_filters
                            )
                            if res == RESULT_DOWNLOADED:
                                successful += 1
                            elif res == RESULT_SKIPPED:
                                skipped += 1
                            break

                        elif is_spotify_url(url):
                            res = process_spotify_item(
                                url, output_dir, ydl, session, archive_path, archive_set,
                                mode=mode, audio_format=audio_format, audio_quality=audio_quality,
                                delay=delay, smart_filters=smart_filters,
                                dashboard=dashboard
                            )
                            if res == RESULT_DOWNLOADED:
                                successful += 1
                            elif res == RESULT_SKIPPED:
                                skipped += 1
                            break

                        else:
                            item_start_t = time.time()
                            ret = ydl.download([url])
                            if ret == 0 and (check_disk_presence(abs_output_dir, item_id, min_mtime=item_start_t, mode=mode) or downloaded_files_batch):
                                successful += 1
                            else:
                                media_f = find_downloaded_media_file(abs_output_dir, item_id)
                                if media_f and os.path.isfile(media_f) and os.path.getsize(media_f) > 0:
                                    successful += 1
                            break

                    except SkipItemRequested:
                        skipped += 1
                        if not sys.stdout.isatty():
                            console.print(f"[bold yellow]  [>>] [SKIPPED] User skipped item: {display_name}[/bold yellow]")
                        break
                    except Exception as e:
                        err_str = str(e).lower()
                        if "skipped by user hotkey" in err_str:
                            skipped += 1
                            break
                        is_net_err = any(k in err_str for k in ("getaddrinfo", "transport", "connection", "timed out", "timeout", "network"))
                        if is_net_err and attempt < max_retries:
                            wait_sec = attempt * 5
                            if not sys.stdout.isatty():
                                console.print(f"[bold yellow]  [!] Network / DNS drop detected. Pausing {wait_sec}s for recovery (Attempt {attempt}/{max_retries})...[/bold yellow]")
                            dashboard.add_log("[WARN]", f"Network pause {wait_sec}s ({attempt}/{max_retries})")
                            dashboard.refresh(force=True)
                            time.sleep(wait_sec)
                        else:
                            if not sys.stdout.isatty():
                                console.print(f"[bold red][-] Error processing {url}: {e}[/bold red]")
                            dashboard.add_log("[FAIL]", f"Error {display_name}: {e}")
                            break

                if successful > prev_successful:
                    st = "DONE"
                    msg = f"Finished: {display_name}"
                    remove_from_failed_urls(output_dir, url)
                    if item_id:
                        remove_from_failed_urls(output_dir, item_id)
                    if archive_path and item_id:
                        add_to_archive(archive_path, item_id, plat or "media")
                        if archive_set is not None:
                            archive_set.add(f"{plat or 'media'} {item_id}")
                    dashboard.finish_item(index, status=st, log_msg=msg, done=successful, skip=skipped, fail=failed)
                elif skipped > prev_skipped and failed == prev_failed:
                    st = "SKIP"
                    msg = f"Skipped: {display_name}"
                    remove_from_failed_urls(output_dir, url)
                    if item_id:
                        remove_from_failed_urls(output_dir, item_id)
                    dashboard.finish_item(index, status=st, log_msg=msg, done=successful, skip=skipped, fail=failed)
                else:
                    if failed == prev_failed:
                        failed += 1
                    if url not in failed_urls_list:
                        failed_urls_list.append(url)
                    dashboard.finish_item(index, status="FAIL", log_msg=f"Failed: {display_name}", done=successful, skip=skipped, fail=failed)

                if index < len(cleaned_urls) and delay > 0:
                    dashboard.add_log("[INFO]", f"Cooldown pause ({delay}s)...")
                    if interruptible_sleep(delay):
                        break
    finally:
        dashboard.stop()

    if (normalize or transcode) and downloaded_files_batch:
        console.print("[bold cyan][*] Running Media Engineering Pipeline on downloaded files...[/bold cyan]")
        for f_path in downloaded_files_batch:
            if not os.path.isfile(f_path):
                continue
            is_vid = f_path.lower().endswith((".mp4", ".mkv", ".webm"))
            is_aud = f_path.lower().endswith((".mp3", ".m4a", ".flac", ".wav", ".opus"))

            if normalize and is_aud:
                console.print(f"[cyan][MEDIA] Normalizing audio (EBU R128 -16 LUFS): {os.path.basename(f_path)}[/cyan]")
                tmp_out = str(Path(f_path).with_name(f"norm_{Path(f_path).name}"))
                if media_maestro.normalize_audio(f_path, tmp_out, audio_format=audio_format, bitrate=audio_quality):
                    os.replace(tmp_out, f_path)

            if transcode and is_vid:
                console.print(f"[cyan][MEDIA] Transcoding video ({media_maestro.hw_accel.upper()} faststart): {os.path.basename(f_path)}[/cyan]")
                tmp_out = str(Path(f_path).with_name(f"opt_{Path(f_path).name}"))
                if media_maestro.transcode_video(f_path, tmp_out):
                    os.replace(tmp_out, f_path)



    print_summary_table(
        total=max(len(cleaned_urls) + initial_skipped, successful + skipped + failed),
        succeeded=successful,
        skipped=skipped,
        failed=failed,
        output_dir=output_dir,
        failed_urls_list=failed_urls_list
    )
    return (successful, skipped, failed)
