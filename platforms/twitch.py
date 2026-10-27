"""Twitch media extractor."""
import os
import re
import time

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
)
from core.cookies import get_effective_twitch_cookie_file
from core.ytdl_format import (
    get_ydl_format,
)
from ui.theme import console


def resolve_twitch_url(url: str) -> str:
    """Resolve Twitch short links or tracking parameters to canonical URL."""
    clean_url = url.strip()
    return clean_url

def process_twitch_item(
    url: str,
    output_dir: str,
    ydl: yt_dlp.YoutubeDL,
    session: requests.Session,
    archive_path: str,
    archive_set: set,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    smart_filters: dict = None
) -> str:
    """Download Twitch clip, VOD, or stream."""
    canonical_url = resolve_twitch_url(url)
    plat, item_id = extract_url_item_id(canonical_url)

    if item_id and is_archived(archive_set, item_id, "twitch", output_dir=output_dir):
        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (Twitch ID: {item_id})[/bold blue]")
        return RESULT_SKIPPED

    sub_opts = dict(ydl.params)
    sub_opts.pop("cookiesfrombrowser", None)
    if ydl.cookiejar:
        sub_opts["cookiejar"] = ydl.cookiejar

    tw_cookie_file = get_effective_twitch_cookie_file()
    if tw_cookie_file and os.path.isfile(tw_cookie_file):
        sub_opts["cookiefile"] = tw_cookie_file

    embed_meta = ydl.params.get("_embed_metadata", True)
    if mode == "audio":
        fmt_str, pps = get_ydl_format(mode="audio", audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_meta)
        sub_opts["format"] = fmt_str
        sub_opts["postprocessors"] = pps
        if embed_meta:
            sub_opts["writethumbnail"] = True
        sub_opts["outtmpl"] = os.path.join(output_dir, f"twitch_%(creator,uploader,channel)s_{item_id or '%(id)s'}_%(title)s.%(ext)s")
        console.print(f"[bold magenta]  [AUDIO] Downloading Twitch audio ({audio_format.upper()} @ {audio_quality}k)...[/bold magenta]")
    else:
        fmt_str, pps = get_ydl_format(mode="video", video_quality=video_quality, embed_metadata=embed_meta)
        sub_opts["format"] = fmt_str
        if pps:
            sub_opts["postprocessors"] = pps
        if embed_meta:
            sub_opts["writethumbnail"] = True
        sub_opts["outtmpl"] = os.path.join(output_dir, f"twitch_%(creator,uploader,channel)s_{item_id or '%(id)s'}_%(title)s.%(ext)s")
        q_label = f"({video_quality}p)" if video_quality and video_quality != "best" else "(best available)"
        console.print(f"[bold green]  [VIDEO] Downloading Twitch video {q_label}...[/bold green]")

    try:
        info = ydl.extract_info(canonical_url, download=False)
        if not info:
            console.print(f"[bold red]  [-] Could not extract Twitch info for URL: {canonical_url}[/bold red]")
            return RESULT_FAILED

        if info.get("_type") == "playlist" or "entries" in info:
            entries = list(info.get("entries") or [])
            if smart_filters and smart_filters.get("count_limit"):
                entries = entries[:smart_filters["count_limit"]]
            console.print(f"[bold yellow][*] Twitch video collection detected ({len(entries)} items).[/bold yellow]")
            s_dl, s_skip, s_fail = 0, 0, 0
            for idx, entry in enumerate(entries, 1):
                if not entry:
                    continue
                e_id = entry.get("id") or str(idx)
                if e_id and is_archived(archive_set, str(e_id), "twitch", output_dir=output_dir):
                    console.print(f"[bold blue]  [>>] [SKIPPED] Item {idx}/{len(entries)} already downloaded ({entry.get('title')})[/bold blue]")
                    s_skip += 1
                    continue
                console.print(f"[dim]--- Twitch Item [{idx}/{len(entries)}] ---[/dim]")
                t_opts = dict(sub_opts)
                with yt_dlp.YoutubeDL(t_opts) as t_ydl:
                    t_ydl.process_ie_result(entry, download=True)
                    add_to_archive(archive_path, str(e_id), "twitch")
                    archive_set.add(f"twitch {str(e_id)}")
                    s_dl += 1
                if delay > 0:
                    time.sleep(delay)
            return RESULT_DOWNLOADED if s_dl > 0 else (RESULT_SKIPPED if s_skip > 0 and s_fail == 0 else RESULT_FAILED)
        else:
            with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                ret = sub_ydl.download([canonical_url])
                if ret == 0 or (item_id and check_disk_presence(output_dir, item_id)):
                    if item_id:
                        add_to_archive(archive_path, item_id, "twitch")
                        archive_set.add(f"twitch {item_id}")
                    return RESULT_DOWNLOADED
                return RESULT_FAILED
    except Exception as e:
        console.print(f"[bold red]  [-] Twitch download error: {e}[/bold red]")
        return RESULT_FAILED

def download_twitch_channel(
    channel_url: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    cookie_file: str = None,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    smart_filters: dict = None
) -> int:
    """Download clips or past broadcasts from a Twitch streamer/channel."""
    from features.downloader import download_urls
    canonical_url = resolve_twitch_url(channel_url)
    m = re.search(r"twitch\.tv/([A-Za-z0-9_]+)", canonical_url)
    streamer = m.group(1) if m else "streamer"
    target_dir = os.path.join(output_dir, f"twitch_{streamer}")
    os.makedirs(target_dir, exist_ok=True)

    console.print(f"[bold magenta][*] Downloading Twitch Channel / Streamer: {canonical_url}[/bold magenta]")
    console.print(f"[dim][FOLDER] Destination: {os.path.abspath(target_dir)}[/dim]")
    return download_urls(
        [canonical_url], output_dir=target_dir, cookie_file=cookie_file,
        mode=mode, video_quality=video_quality,
        audio_format=audio_format, audio_quality=audio_quality,
        delay=delay, smart_filters=smart_filters, is_bulk=True
    )
