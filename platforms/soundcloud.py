"""SoundCloud media extractor."""
import os
import re
import time
from typing import Any

import requests
import yt_dlp

from core.archive import (
    DEFAULT_OUTPUT_DIR,
    RESULT_DOWNLOADED,
    RESULT_FAILED,
    RESULT_SKIPPED,
    add_to_archive,
    check_disk_presence,
    extract_url_item_id,
    is_archived,
    sanitize_filename,
)
from core.cookies import (
    get_effective_soundcloud_cookie_file,
    verify_soundcloud_session,
)
from core.ytdl_format import (
    get_ydl_format,
)
from platforms.base import (
    filter_playlist_items,
)
from ui.components import (
    ask_input,
)
from ui.theme import console


def process_soundcloud_item(
    url: str,
    output_dir: str,
    ydl: yt_dlp.YoutubeDL,
    session: requests.Session,
    archive_path: str,
    archive_set: set,
    mode: str = "audio",
    audio_format: str = "mp3",
    audio_quality: str = "320",
    delay: float = 2.0,
    smart_filters: dict = None,
    dashboard: Any = None
) -> str:
    """Download SoundCloud track or playlist."""
    plat, track_id = extract_url_item_id(url)
    if track_id and is_archived(archive_set, track_id, "soundcloud", output_dir=output_dir, mode="audio"):
        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (SoundCloud: {track_id})[/bold blue]")
        return RESULT_SKIPPED

    sub_opts = dict(ydl.params)
    sub_opts.pop("cookiesfrombrowser", None)
    if ydl.cookiejar:
        sub_opts["cookiejar"] = ydl.cookiejar

    embed_meta = ydl.params.get("_embed_metadata", True)
    fmt_str, pps = get_ydl_format(mode="audio", audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_meta)
    sub_opts["format"] = fmt_str
    sub_opts["postprocessors"] = pps
    if embed_meta:
        sub_opts["writethumbnail"] = True
    sub_opts["outtmpl"] = os.path.join(output_dir, "%(artist,uploader)s - %(title)s [%(id)s].%(ext)s")

    try:
        info = ydl.extract_info(url, download=False)
        if not info:
            console.print(f"[bold red]  [-] Could not extract SoundCloud info for URL: {url}[/bold red]")
            return RESULT_FAILED

        if info.get("_type") == "playlist" or "entries" in info:
            entries = list(info.get("entries") or [])
            if smart_filters and smart_filters.get("items"):
                entries = filter_playlist_items(entries, smart_filters["items"])
            if smart_filters and smart_filters.get("count_limit"):
                entries = entries[:smart_filters["count_limit"]]
            console.print(f"[bold yellow][*] SoundCloud collection detected ({len(entries)} tracks).[/bold yellow]")
            if dashboard and entries:
                queue_items = [
                    sanitize_filename(e.get("title") or f"Track {i:02d}", max_len=60)
                    for i, e in enumerate(entries, 1) if e
                ]
                dashboard.init_queue(queue_items)
            s_dl, s_skip, s_fail = 0, 0, 0
            for idx, entry in enumerate(entries, 1):
                if not entry:
                    continue
                e_id = entry.get("id") or str(idx)
                if e_id and is_archived(archive_set, str(e_id), "soundcloud", output_dir=output_dir, title=entry.get("title"), mode="audio"):
                    console.print(f"[bold blue]  [>>] [SKIPPED] Track {idx}/{len(entries)} already downloaded ({entry.get('title')})[/bold blue]")
                    s_skip += 1
                    continue
                console.print(f"[dim]--- SoundCloud Track [{idx}/{len(entries)}] ---[/dim]")
                t_opts = dict(sub_opts)
                with yt_dlp.YoutubeDL(t_opts) as t_ydl:
                    t_ydl.process_ie_result(entry, download=True)
                    add_to_archive(archive_path, str(e_id), "soundcloud")
                    archive_set.add(f"soundcloud {str(e_id)}")
                    s_dl += 1
                    if dashboard:
                        dashboard.finish_item(idx, status="DONE", done=s_dl, skip=s_skip, fail=s_fail)
                if delay > 0:
                    time.sleep(delay)
            return RESULT_DOWNLOADED if s_dl > 0 else (RESULT_SKIPPED if s_skip > 0 and s_fail == 0 else RESULT_FAILED)
        else:
            console.print(f"[bold yellow]  [AUDIO] Downloading SoundCloud track ({audio_format.upper()} @ {audio_quality}k)...[/bold yellow]")
            with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                ret = sub_ydl.download([url])
                if ret == 0 or (track_id and check_disk_presence(output_dir, track_id, mode="audio")):
                    if track_id:
                        add_to_archive(archive_path, track_id, "soundcloud")
                        archive_set.add(f"soundcloud {track_id}")
                    return RESULT_DOWNLOADED
                return RESULT_FAILED
    except Exception as e:
        console.print(f"[bold red]  [-] SoundCloud download error: {e}[/bold red]")
        return RESULT_FAILED

def download_soundcloud_liked_tracks(
    username_or_url: str = None,
    cookie_file: str = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    audio_format: str = "mp3",
    audio_quality: str = "320",
    smart_filters: dict = None,
    embed_metadata: bool = True
):
    """Download SoundCloud liked tracks."""
    from features.downloader import download_urls
    target = username_or_url
    c_file = get_effective_soundcloud_cookie_file(cookie_file)
    if not target:
        if c_file:
            ok, msg = verify_soundcloud_session(c_file)
            if ok and "Logged in as " in msg:
                target = msg.replace("Logged in as ", "").strip()
        if not target:
            target = ask_input("[bold cyan]Enter SoundCloud username or profile URL[/bold cyan]")
            if not target:
                console.print("[bold red][-] SoundCloud username or URL required.[/bold red]")
                return

    clean_target = target.strip()
    if clean_target.startswith("http"):
        if not clean_target.endswith("/likes"):
            likes_url = clean_target.rstrip("/") + "/likes"
        else:
            likes_url = clean_target
        m_user = re.search(r"soundcloud\.com/([^/?#]+)", likes_url)
        user_label = m_user.group(1) if m_user else "user"
    else:
        clean_user = clean_target.lstrip("@").strip()
        likes_url = f"https://soundcloud.com/{clean_user}/likes"
        user_label = clean_user

    dest_folder = os.path.join(output_dir, f"soundcloud_{user_label}_likes")
    console.print(f"[bold yellow][*] Fetching SoundCloud Liked Tracks for {user_label}...[/bold yellow]")

    download_urls(
        [likes_url],
        output_dir=dest_folder,
        cookie_file=c_file,
        mode="audio",
        audio_format=audio_format,
        audio_quality=audio_quality,
        smart_filters=smart_filters,
        embed_metadata=embed_metadata,
        is_bulk=True
    )
