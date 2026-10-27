"""Pinterest media extractor."""
import json
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
    download_file,
    extract_url_item_id,
    is_archived,
    sanitize_filename,
)
from core.cookies import get_effective_pinterest_cookie_file
from core.ytdl_format import (
    get_ydl_format,
)
from ui.theme import console


def resolve_pinterest_url(url: str) -> str:
    """Resolve Pinterest short links (pin.it/...) to canonical pin or board URL."""
    clean_url = url.strip()
    if "pin.it" in clean_url.lower():
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

def process_pinterest_pin(
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
    """Download Pinterest pin or video."""
    canonical_url = resolve_pinterest_url(url)
    plat, pin_id = extract_url_item_id(canonical_url)
    if not pin_id:
        m = re.search(r"/pin/(?:[\w-]+--)?(\d+)", canonical_url)
        if m:
            pin_id = m.group(1)

    if pin_id and is_archived(archive_set, pin_id, "pinterest", output_dir=output_dir):
        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (Pinterest ID: {pin_id})[/bold blue]")
        return RESULT_SKIPPED

    sub_opts = dict(ydl.params)
    sub_opts.pop("cookiesfrombrowser", None)
    if ydl.cookiejar:
        sub_opts["cookiejar"] = ydl.cookiejar

    pin_cookie_file = get_effective_pinterest_cookie_file()
    if pin_cookie_file and os.path.isfile(pin_cookie_file):
        sub_opts["cookiefile"] = pin_cookie_file

    embed_meta = ydl.params.get("_embed_metadata", True)

    try:
        info = ydl.extract_info(canonical_url, download=False)

        if not info:
            console.print(f"[bold red]  [-] Could not extract Pinterest info for URL: {canonical_url}[/bold red]")
            return RESULT_FAILED

        # Handle multi-item collection or board.
        if info.get("_type") == "playlist" or "entries" in info:
            entries = list(info.get("entries") or [])
            if smart_filters and smart_filters.get("count_limit"):
                entries = entries[:smart_filters["count_limit"]]
            board_title = info.get("title") or "Pinterest Collection"
            console.print(f"[bold yellow][*] Pinterest collection detected: '{board_title}' ({len(entries)} items).[/bold yellow]")
            p_dl, p_skip, p_fail = 0, 0, 0
            for idx, entry in enumerate(entries, 1):
                if not entry:
                    continue
                e_id = entry.get("id") or str(idx)
                if e_id and is_archived(archive_set, str(e_id), "pinterest", output_dir=output_dir):
                    console.print(f"[bold blue]  [>>] [SKIPPED] Pin {idx}/{len(entries)} already downloaded ({entry.get('title') or e_id})[/bold blue]")
                    p_skip += 1
                    continue
                console.print(f"[dim]--- Pinterest Pin [{idx}/{len(entries)}] ---[/dim]")
                entry_url = entry.get("webpage_url") or f"https://www.pinterest.com/pin/{e_id}/"
                res = process_pinterest_pin(
                    entry_url, output_dir, ydl, session, archive_path, archive_set,
                    mode=mode, video_quality=video_quality,
                    audio_format=audio_format, audio_quality=audio_quality,
                    delay=delay, smart_filters=smart_filters
                )
                if res == RESULT_DOWNLOADED:
                    p_dl += 1
                elif res == RESULT_SKIPPED:
                    p_skip += 1
                else:
                    p_fail += 1
                if delay > 0:
                    time.sleep(delay)
            return RESULT_DOWNLOADED if p_dl > 0 else (RESULT_SKIPPED if p_skip > 0 and p_fail == 0 else RESULT_FAILED)

        # Handle video pin.
        formats = info.get("formats") or []
        has_video_formats = any(f.get("url") and f.get("vcodec") != "none" for f in formats)

        if has_video_formats:
            if mode == "audio":
                fmt_str, pps = get_ydl_format(mode="audio", audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_meta)
                sub_opts["format"] = fmt_str
                sub_opts["postprocessors"] = pps
                if embed_meta:
                    sub_opts["writethumbnail"] = True
                sub_opts["outtmpl"] = os.path.join(output_dir, f"pinterest_%(uploader,uploader_id)s_{pin_id or '%(id)s'}_%(title)s.%(ext)s")
                console.print(f"[bold magenta]  [AUDIO] Downloading Pinterest video audio ({audio_format.upper()} @ {audio_quality}k)...[/bold magenta]")
            else:
                fmt_str, pps = get_ydl_format(mode="video", video_quality=video_quality, embed_metadata=embed_meta)
                sub_opts["format"] = fmt_str
                if pps:
                    sub_opts["postprocessors"] = pps
                if embed_meta:
                    sub_opts["writethumbnail"] = True
                sub_opts["outtmpl"] = os.path.join(output_dir, f"pinterest_%(uploader,uploader_id)s_{pin_id or '%(id)s'}_%(title)s.%(ext)s")
                q_label = f"({video_quality}p)" if video_quality and video_quality != "best" else "(best available)"
                console.print(f"[bold green]  [VIDEO] Downloading Pinterest video {q_label}...[/bold green]")

            with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                ret = sub_ydl.download([canonical_url])
                if ret == 0 or (pin_id and check_disk_presence(output_dir, pin_id)):
                    if pin_id:
                        add_to_archive(archive_path, pin_id, "pinterest")
                        archive_set.add(f"pinterest {pin_id}")
                    return RESULT_DOWNLOADED
                return RESULT_FAILED

        # Extract full-resolution image.
        best_img_url = None
        thumbnails = info.get("thumbnails") or []
        if isinstance(thumbnails, list) and thumbnails:
            sorted_thumbs = sorted(
                thumbnails,
                key=lambda t: (t.get("width") or 0) * (t.get("height") or 0) if isinstance(t, dict) else 0,
                reverse=True
            )
            if sorted_thumbs and isinstance(sorted_thumbs[0], dict):
                best_img_url = sorted_thumbs[0].get("url")

        if best_img_url:
            best_img_url = re.sub(r"/\d+x(?:\d+)?/", "/originals/", best_img_url)

        if not best_img_url:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            }
            resp = session.get(canonical_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                m_img = re.search(r'property="og:image"\s+content="([^"]+)"', resp.text)
                if m_img:
                    best_img_url = re.sub(r"/\d+x(?:\d+)?/", "/originals/", m_img.group(1))

        if best_img_url:
            raw_title = info.get("title") or info.get("description") or f"pin_{pin_id}"
            clean_title = sanitize_filename(raw_title)[:45].strip()
            ext = "png" if ".png" in best_img_url.lower() else "jpg"
            filename = f"pinterest_{pin_id}_{clean_title}.{ext}" if pin_id else f"pinterest_{clean_title}.{ext}"
            save_path = os.path.join(output_dir, filename)

            console.print(f"[bold cyan]  [PHOTO] Downloading Pinterest original image: {filename}...[/bold cyan]")
            if download_file(best_img_url, save_path, session):
                meta_file = os.path.join(output_dir, f"pinterest_{pin_id}_metadata.json") if pin_id else os.path.join(output_dir, f"{os.path.splitext(filename)[0]}_metadata.json")
                try:
                    with open(meta_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "id": pin_id,
                            "title": info.get("title", ""),
                            "description": info.get("description", ""),
                            "uploader": info.get("uploader", ""),
                            "url": canonical_url,
                            "image_url": best_img_url,
                        }, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

                if pin_id:
                    add_to_archive(archive_path, pin_id, "pinterest")
                    archive_set.add(f"pinterest {pin_id}")
                console.print(f"[bold green]  [OK] Pinterest photo saved: {filename}[/bold green]")
                return RESULT_DOWNLOADED

        console.print(f"[bold red]  [-] Could not retrieve video or image for Pinterest pin: {canonical_url}[/bold red]")
        return RESULT_FAILED

    except Exception as e:
        console.print(f"[bold red]  [-] Pinterest processing error: {e}[/bold red]")
        return RESULT_FAILED

def download_pinterest_board(
    board_url: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    cookie_file: str = None,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    smart_filters: dict = None
) -> int:
    """Download an entire Pinterest board / collection into a dedicated folder."""
    from features.downloader import download_urls
    canonical_url = resolve_pinterest_url(board_url)
    m = re.search(r"pinterest\.[a-z.]+/([^/]+)/([^/?#]+)", canonical_url)
    user_tag = m.group(1) if m else "user"
    board_tag = m.group(2) if m else "board"
    folder_name = sanitize_filename(f"pinterest_{user_tag}_{board_tag}")
    board_dir = os.path.join(output_dir, folder_name)
    os.makedirs(board_dir, exist_ok=True)

    console.print(f"[bold cyan][*] Downloading Pinterest Board: {canonical_url}[/bold cyan]")
    console.print(f"[dim][FOLDER] Destination: {os.path.abspath(board_dir)}[/dim]")
    return download_urls(
        [canonical_url], output_dir=board_dir, cookie_file=cookie_file,
        mode=mode, video_quality=video_quality,
        audio_format=audio_format, audio_quality=audio_quality,
        delay=delay, smart_filters=smart_filters, is_bulk=True
    )
