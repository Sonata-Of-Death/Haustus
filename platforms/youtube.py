"""YouTube media extractor."""
import os
import time
from typing import Any

import yt_dlp

from core.archive import (
    HISTORY_FILE,
    RESULT_DOWNLOADED,
    RESULT_FAILED,
    RESULT_SKIPPED,
    add_to_archive,
    check_disk_presence,
    find_downloaded_media_file,
    get_archive_set,
    is_archived,
    sanitize_filename,
    tag_audio_metadata,
)
from core.instances import config_mgr
from core.ytdl_format import (
    get_ydl_format,
)
from platforms.base import (
    filter_playlist_items,
)
from ui.components import ask_input, interactive_select
from ui.theme import console


def process_youtube_url(
    url: str,
    output_dir: str,
    ydl: yt_dlp.YoutubeDL,
    archive_path: str,
    archive_set: set,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    smart_filters: dict = None,
    dashboard: Any = None
) -> tuple[str, int, int, int]:
    """Download YouTube video, short, or audio."""
    try:
        console.print(f"[cyan]  [*] Inspecting YouTube media information: {url}[/cyan]")
        info = ydl.extract_info(url, download=False)
        if not info:
            console.print("[bold red]  [-] Could not retrieve YouTube video info.[/bold red]")
            return (RESULT_FAILED, 0, 0, 1)

        if info.get("_type") == "playlist" and "entries" in info:
            entries = list(info.get("entries") or [])
            if smart_filters:
                if smart_filters.get("items"):
                    entries = filter_playlist_items(entries, smart_filters["items"])
                if smart_filters.get("count_limit"):
                    entries = entries[:smart_filters["count_limit"]]
                if smart_filters.get("date_after"):
                    d_after = smart_filters["date_after"]
                    entries = [e for e in entries if not (e and e.get("upload_date") and e.get("upload_date") < d_after)]
                if smart_filters.get("shorts_only") or smart_filters.get("max_duration"):
                    max_sec = 60 if smart_filters.get("shorts_only") else smart_filters.get("max_duration")
                    entries = [e for e in entries if not (e and e.get("duration") and e.get("duration") > max_sec)]

            playlist_title = sanitize_filename(info.get("title") or "youtube_playlist")
            console.print(f"[bold cyan]  [PLAYLIST] YouTube Playlist/Channel detected: '{playlist_title}' ({len(entries)} items).[/bold cyan]")

            playlist_dir = os.path.join(output_dir, playlist_title)
            os.makedirs(playlist_dir, exist_ok=True)
            pl_archive_path = os.path.join(playlist_dir, HISTORY_FILE)
            pl_archive_set = get_archive_set(pl_archive_path)

            if dashboard and entries:
                dashboard.set_output_dir(playlist_dir)
                queue_items = [
                    sanitize_filename(e.get("title") or f"Video {i:02d}", max_len=60)
                    for i, e in enumerate(entries, 1) if e
                ]
                dashboard.init_queue(queue_items)

            pl_dl = 0
            pl_skip = 0
            pl_fail = 0

            embed_meta = ydl.params.get("_embed_metadata", True)

            for p_idx, entry in enumerate(entries, 1):
                if not entry:
                    continue
                entry_id = entry.get("id")
                entry_title = sanitize_filename(entry.get("title") or f"video_{p_idx}", max_len=140)
                uploader = sanitize_filename(entry.get("uploader") or entry.get("channel") or "youtube_user", max_len=60)

                if dashboard:
                    dashboard.set_batch(current=p_idx, total=len(entries), done=pl_dl, skip=pl_skip, fail=pl_fail)
                    dashboard.start_item(p_idx, title=entry_title, platform="YouTube", mode=mode.upper(), quality=video_quality)

                if entry_id and (is_archived(pl_archive_set, entry_id, "youtube", output_dir=playlist_dir, title=entry_title, mode=mode) or is_archived(archive_set, entry_id, "youtube", output_dir=playlist_dir, title=entry_title, mode=mode)):
                    console.print(f"[bold blue]  [>>] [{p_idx}/{len(entries)}] [SKIPPED] Already downloaded: {entry_title} (ID: {entry_id})[/bold blue]")
                    pl_skip += 1
                    if dashboard:
                        dashboard.finish_item(p_idx, status="SKIP", done=pl_dl, skip=pl_skip, fail=pl_fail)
                    continue

                console.print(f"[bold cyan]--- [{p_idx}/{len(entries)}] YouTube Item: {entry_title} ---[/bold cyan]")
                entry_url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry_id}"

                sub_opts = dict(ydl.params)
                sub_opts.pop("cookiesfrombrowser", None)
                if ydl.cookiejar:
                    sub_opts["cookiejar"] = ydl.cookiejar

                sub_opts["outtmpl"] = os.path.join(playlist_dir, f"{p_idx:03d}_{uploader}_{entry_id}_{entry_title}.%(ext)s")
                fmt_str, pps = get_ydl_format(mode=mode, video_quality=video_quality, audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_meta)
                sub_opts["format"] = fmt_str
                if pps:
                    sub_opts["postprocessors"] = pps
                else:
                    sub_opts.pop("postprocessors", None)
                if embed_meta:
                    sub_opts["writethumbnail"] = True

                with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                    ret = sub_ydl.download([entry_url])
                    if ret != 0 and sub_opts.get("cookiejar"):
                        console.print("[yellow]  [!] Item failed with cookies (HTTP 403 or session error). Retrying anonymously...[/yellow]")
                        anon_opts = dict(sub_opts)
                        anon_opts.pop("cookiejar", None)
                        anon_opts.pop("cookiefile", None)
                        with yt_dlp.YoutubeDL(anon_opts) as anon_ydl:
                            ret = anon_ydl.download([entry_url])
                    if ret == 0 and (not entry_id or check_disk_presence(playlist_dir, entry_id)):
                        if mode == "audio" and embed_meta:
                            media_f = find_downloaded_media_file(playlist_dir, entry_id)
                            if media_f:
                                tag_audio_metadata(
                                    media_f,
                                    title=entry.get("title") or entry_title,
                                    artist=entry.get("uploader") or entry.get("channel") or uploader,
                                    album=playlist_title,
                                    date=entry.get("upload_date"),
                                    cover_url=entry.get("thumbnail")
                                )
                        if entry_id:
                            add_to_archive(pl_archive_path, entry_id, "youtube")
                            add_to_archive(archive_path, entry_id, "youtube")
                            pl_archive_set.add(f"youtube {entry_id}")
                            archive_set.add(f"youtube {entry_id}")
                        pl_dl += 1
                        if dashboard:
                            dashboard.finish_item(p_idx, status="DONE", done=pl_dl, skip=pl_skip, fail=pl_fail)
                    else:
                        pl_fail += 1
                        if dashboard:
                            dashboard.finish_item(p_idx, status="FAIL", done=pl_dl, skip=pl_skip, fail=pl_fail)
                        pl_fail += 1

                if delay > 0:
                    time.sleep(delay)

            status = RESULT_DOWNLOADED if pl_dl > 0 else (RESULT_SKIPPED if pl_skip > 0 and pl_fail == 0 else RESULT_FAILED)
            return (status, pl_dl, pl_skip, pl_fail)

        else:
            video_id = info.get("id") or str(int(time.time()))
            title = sanitize_filename(info.get("title") or "youtube_video")
            uploader = sanitize_filename(info.get("uploader") or info.get("channel") or "youtube_user")

            if is_archived(archive_set, video_id, "youtube", output_dir=output_dir, title=title, mode=mode):
                console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (YouTube ID: {video_id})[/bold blue]")
                return (RESULT_SKIPPED, 0, 1, 0)

            sub_opts = dict(ydl.params)
            sub_opts.pop("cookiesfrombrowser", None)
            if ydl.cookiejar:
                sub_opts["cookiejar"] = ydl.cookiejar

            embed_meta = ydl.params.get("_embed_metadata", True)
            clean_title = sanitize_filename(info.get("title") or "youtube_video", max_len=140)
            sub_opts["outtmpl"] = os.path.join(output_dir, f"youtube_{uploader}_{video_id}_{clean_title}.%(ext)s")
            fmt_str, pps = get_ydl_format(mode=mode, video_quality=video_quality, audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_meta)
            sub_opts["format"] = fmt_str
            if pps:
                sub_opts["postprocessors"] = pps
            else:
                sub_opts.pop("postprocessors", None)
            if embed_meta:
                sub_opts["writethumbnail"] = True

            if mode == "audio":
                console.print(f"[bold magenta]  [AUDIO] Downloading YouTube audio as {audio_format.upper()} ({audio_quality}k): {clean_title}[/bold magenta]")
            else:
                q_label = f"({video_quality}p with merged audio)" if video_quality and video_quality != "best" else "(Full HD/Best with merged audio)"
                console.print(f"[bold green]  [VIDEO] Downloading YouTube video {q_label}: {clean_title}[/bold green]")

            with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                ret = sub_ydl.download([url])
                if ret == 0 and check_disk_presence(output_dir, video_id):
                    if mode == "audio" and embed_meta:
                        media_f = find_downloaded_media_file(output_dir, video_id)
                        if media_f:
                            tag_audio_metadata(
                                media_f,
                                title=info.get("title") or clean_title,
                                artist=info.get("uploader") or info.get("channel") or uploader,
                                album=info.get("album") or info.get("playlist_title") or f"{uploader} - YouTube",
                                date=info.get("upload_date"),
                                cover_url=info.get("thumbnail")
                            )
                    add_to_archive(archive_path, video_id, "youtube")
                    archive_set.add(f"youtube {video_id}")
                    return (RESULT_DOWNLOADED, 1, 0, 0)

                # Retry without cookies if authenticated session encounters HTTP 403 or stream error.
                if ret != 0 and sub_opts.get("cookiejar"):
                    console.print("[yellow]  [!] YouTube download failed with cookies (HTTP 403 or session error). Retrying anonymously...[/yellow]")
                    anon_opts = dict(sub_opts)
                    anon_opts.pop("cookiejar", None)
                    anon_opts.pop("cookiefile", None)
                    with yt_dlp.YoutubeDL(anon_opts) as anon_ydl:
                        ret_anon = anon_ydl.download([url])
                        if ret_anon == 0 and check_disk_presence(output_dir, video_id):
                            add_to_archive(archive_path, video_id, "youtube")
                            archive_set.add(f"youtube {video_id}")
                            return (RESULT_DOWNLOADED, 1, 0, 0)

                return (RESULT_FAILED, 0, 0, 1)

    except Exception as e:
        console.print(f"[bold red]  [-] Error downloading YouTube media:[/bold red] {e}")
        return (RESULT_FAILED, 0, 0, 1)

def fetch_youtube_user_playlists(cookie_file: str = None) -> list[dict]:
    """Fetch playlists from authenticated YouTube account."""
    playlists = [
        {"id": "WL", "title": "Watch Later (WL)", "desc": "Official YouTube Watch Later queue", "url": "https://www.youtube.com/playlist?list=WL"},
        {"id": "LL", "title": "Liked Videos (LL)", "desc": "All videos you have liked on YouTube", "url": "https://www.youtube.com/playlist?list=LL"},
    ]

    effective_cookie = cookie_file or config_mgr.get_effective_cookie_file("youtube")
    if not effective_cookie or not os.path.isfile(effective_cookie):
        return playlists

    try:
        console.print("[dim][*] Fetching user playlists from YouTube account...[/dim]")
        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "cookiefile": effective_cookie,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info("https://www.youtube.com/feed/playlists", download=False)
            if info:
                entries = info.get("entries", [])
                for e in entries:
                    pl_id = e.get("id")
                    pl_title = e.get("title") or f"Playlist {pl_id}"
                    pl_url = e.get("url") or f"https://www.youtube.com/playlist?list={pl_id}"
                    item_count = e.get("playlist_count") or e.get("item_count")
                    desc = f"{item_count} items" if item_count else "User playlist"
                    if pl_id and pl_id not in ("WL", "LL"):
                        playlists.append({
                            "id": pl_id,
                            "title": pl_title,
                            "desc": desc,
                            "url": pl_url
                        })
    except Exception:
        pass

    return playlists

def choose_youtube_playlist_to_download(cookie_file: str = None) -> str | None:
    """Prompt user to select YouTube playlist."""
    playlists = fetch_youtube_user_playlists(cookie_file=cookie_file)
    opts = []
    for i, pl in enumerate(playlists, 1):
        opts.append({
            "key": str(i),
            "title": pl["title"],
            "desc": pl["desc"],
            "value": pl["url"]
        })
    opts.append({
        "key": str(len(opts) + 1),
        "title": "[CUSTOM] Enter Playlist URL Manually",
        "desc": "Paste any public, unlisted, or private playlist URL",
        "value": "custom"
    })
    opts.append({
        "key": "0",
        "title": "[BACK] Cancel",
        "desc": "Return to previous menu",
        "value": "cancel"
    })

    chosen = interactive_select("SELECT YOUTUBE PLAYLIST", opts, default_index=0, border_style="red")
    if chosen in ("cancel", "0"):
        return None
    if chosen == "custom":
        url = ask_input("[bold green]Enter YouTube Playlist URL[/bold green]")
        return url.strip() if url else None
    return chosen
