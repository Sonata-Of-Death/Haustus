"""Facebook media extractor."""
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
from core.cookies import get_effective_facebook_cookie_file
from core.ytdl_format import (
    get_ydl_format,
)
from ui.theme import console


def resolve_facebook_url(url: str) -> str:
    """Resolve canonical Facebook URL."""
    clean_url = url.strip()
    if any(k in clean_url.lower() for k in ("fb.watch", "/share/r/", "/share/v/", "/share/p/")):
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                )
            }
            resp = requests.head(clean_url, headers=headers, allow_redirects=True, timeout=8)
            if resp.url and resp.url != clean_url:
                return resp.url
        except Exception:
            try:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    )
                }
                resp = requests.get(clean_url, headers=headers, allow_redirects=True, stream=True, timeout=8)
                if resp.url and resp.url != clean_url:
                    return resp.url
            except Exception:
                pass
    return clean_url

def process_facebook_item(
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
    """Download Facebook video or reel."""
    canonical_url = resolve_facebook_url(url)
    plat, item_id = extract_url_item_id(canonical_url)
    if not item_id:
        m = re.search(r"/(?:videos|reel|posts)/([0-9]+)", canonical_url)
        if m:
            item_id = m.group(1)

    if item_id and is_archived(archive_set, item_id, "facebook", output_dir=output_dir):
        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (Facebook ID: {item_id})[/bold blue]")
        return RESULT_SKIPPED

    sub_opts = dict(ydl.params)
    sub_opts.pop("cookiesfrombrowser", None)
    if ydl.cookiejar:
        sub_opts["cookiejar"] = ydl.cookiejar

    fb_cookie_file = get_effective_facebook_cookie_file()
    if fb_cookie_file and os.path.isfile(fb_cookie_file):
        sub_opts["cookiefile"] = fb_cookie_file

    embed_meta = ydl.params.get("_embed_metadata", True)
    if mode == "audio":
        fmt_str, pps = get_ydl_format(mode="audio", audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_meta)
        sub_opts["format"] = fmt_str
        sub_opts["postprocessors"] = pps
        if embed_meta:
            sub_opts["writethumbnail"] = True
        sub_opts["outtmpl"] = os.path.join(output_dir, f"facebook_%(uploader,channel,id)s_{item_id or '%(id)s'}_%(title)s.%(ext)s")
        console.print(f"[bold magenta]  [AUDIO] Downloading Facebook audio ({audio_format.upper()} @ {audio_quality}k)...[/bold magenta]")
    else:
        fmt_str, pps = get_ydl_format(mode="video", video_quality=video_quality, embed_metadata=embed_meta)
        sub_opts["format"] = fmt_str
        if pps:
            sub_opts["postprocessors"] = pps
        if embed_meta:
            sub_opts["writethumbnail"] = True
        sub_opts["outtmpl"] = os.path.join(output_dir, f"facebook_%(uploader,channel,id)s_{item_id or '%(id)s'}_%(title)s.%(ext)s")
        q_label = f"({video_quality}p)" if video_quality and video_quality != "best" else "(best available)"
        console.print(f"[bold green]  [VIDEO] Downloading Facebook video {q_label}...[/bold green]")

    try:
        info = ydl.extract_info(canonical_url, download=False)
        if not info:
            console.print(f"[bold red]  [-] Could not extract Facebook info for URL: {canonical_url}[/bold red]")
            return RESULT_FAILED

        if info.get("_type") == "playlist" or "entries" in info:
            entries = list(info.get("entries") or [])
            if smart_filters and smart_filters.get("count_limit"):
                entries = entries[:smart_filters["count_limit"]]
            console.print(f"[bold yellow][*] Facebook video collection detected ({len(entries)} items).[/bold yellow]")
            s_dl, s_skip, s_fail = 0, 0, 0
            for idx, entry in enumerate(entries, 1):
                if not entry:
                    continue
                e_id = entry.get("id") or str(idx)
                if e_id and is_archived(archive_set, str(e_id), "facebook", output_dir=output_dir):
                    console.print(f"[bold blue]  [>>] [SKIPPED] Item {idx}/{len(entries)} already downloaded ({entry.get('title')})[/bold blue]")
                    s_skip += 1
                    continue
                console.print(f"[dim]--- Facebook Video [{idx}/{len(entries)}] ---[/dim]")
                t_opts = dict(sub_opts)
                with yt_dlp.YoutubeDL(t_opts) as t_ydl:
                    t_ydl.process_ie_result(entry, download=True)
                    add_to_archive(archive_path, str(e_id), "facebook")
                    archive_set.add(f"facebook {str(e_id)}")
                    s_dl += 1
                if delay > 0:
                    time.sleep(delay)
            return RESULT_DOWNLOADED if s_dl > 0 else (RESULT_SKIPPED if s_skip > 0 and s_fail == 0 else RESULT_FAILED)
        else:
            with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                ret = sub_ydl.download([canonical_url])
                if ret == 0 or (item_id and check_disk_presence(output_dir, item_id)):
                    if item_id:
                        add_to_archive(archive_path, item_id, "facebook")
                        archive_set.add(f"facebook {item_id}")
                    return RESULT_DOWNLOADED
                return RESULT_FAILED
    except Exception as e:
        console.print(f"[bold red]  [-] Facebook download error: {e}[/bold red]")
        return RESULT_FAILED

def download_facebook_saved_videos(
    cookie_file: str = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    custom_urls: list = None,
    smart_filters: dict = None
) -> int:
    """Download saved videos or video collection from authenticated Facebook account."""
    from features.downloader import download_urls
    if custom_urls:
        urls_to_download = custom_urls
    else:
        c_file = cookie_file or get_effective_facebook_cookie_file()
        if not c_file:
            console.print("[bold red][-] Error: Facebook cookies (c_user/xs) are required to access saved items.[/bold red]")
            return 0
        urls_to_download = ["https://www.facebook.com/saved/"]

    save_dir = os.path.join(output_dir, "facebook_saved")
    os.makedirs(save_dir, exist_ok=True)
    console.print(f"[bold cyan][*] Processing Facebook Saved Videos ({len(urls_to_download)} items)...[/bold cyan]")
    return download_urls(
        urls_to_download, output_dir=save_dir, cookie_file=cookie_file,
        mode=mode, video_quality=video_quality,
        audio_format=audio_format, audio_quality=audio_quality,
        delay=delay, smart_filters=smart_filters, is_bulk=True
    )
