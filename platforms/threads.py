"""Threads media extractor."""
import html
import json
import os
import re

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
from core.cookies import get_effective_threads_cookie_file
from core.ytdl_format import (
    get_ydl_format,
)
from ui.theme import console


def resolve_threads_url(url: str) -> str:
    """Resolve Threads short links or tracking parameters to canonical URL."""
    clean_url = url.strip()
    if "?" in clean_url:
        clean_url = clean_url.split("?")[0]
    return clean_url

def process_threads_item(
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
    """Download Threads post media."""
    canonical_url = resolve_threads_url(url)
    plat, post_id = extract_url_item_id(canonical_url)
    if not post_id:
        m = re.search(r"/post/([A-Za-z0-9_-]+)", canonical_url)
        if m:
            post_id = m.group(1)

    if post_id and is_archived(archive_set, post_id, "threads", output_dir=output_dir):
        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (Threads ID: {post_id})[/bold blue]")
        return RESULT_SKIPPED

    sub_opts = dict(ydl.params)
    sub_opts.pop("cookiesfrombrowser", None)
    if ydl.cookiejar:
        sub_opts["cookiejar"] = ydl.cookiejar

    th_cookie_file = get_effective_threads_cookie_file()
    if th_cookie_file and os.path.isfile(th_cookie_file):
        sub_opts["cookiefile"] = th_cookie_file

    embed_meta = ydl.params.get("_embed_metadata", True)

    try:
        info = ydl.extract_info(canonical_url, download=False)
        if not info:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = session.get(canonical_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                m_vid = re.search(r'property="og:video"\s+content="([^"]+)"', resp.text)
                if m_vid:
                    vid_url = html.unescape(m_vid.group(1))
                    filename = f"threads_{post_id or 'post'}.mp4"
                    save_path = os.path.join(output_dir, filename)
                    console.print(f"[bold green]  [VIDEO] Downloading Threads video: {filename}...[/bold green]")
                    if download_file(vid_url, save_path, session):
                        if post_id:
                            add_to_archive(archive_path, post_id, "threads")
                            archive_set.add(f"threads {post_id}")
                        return RESULT_DOWNLOADED

                m_img = re.search(r'property="og:image"\s+content="([^"]+)"', resp.text)
                if m_img:
                    img_url = html.unescape(m_img.group(1))
                    filename = f"threads_{post_id or 'post'}.jpg"
                    save_path = os.path.join(output_dir, filename)
                    console.print(f"[bold cyan]  [PHOTO] Downloading Threads photo: {filename}...[/bold cyan]")
                    if download_file(img_url, save_path, session):
                        if post_id:
                            add_to_archive(archive_path, post_id, "threads")
                            archive_set.add(f"threads {post_id}")
                        return RESULT_DOWNLOADED

            console.print(f"[bold red]  [-] Could not extract Threads info for URL: {canonical_url}[/bold red]")
            return RESULT_FAILED

        formats = info.get("formats") or []
        has_video = any(f.get("url") and f.get("vcodec") != "none" for f in formats)

        if has_video:
            if mode == "audio":
                fmt_str, pps = get_ydl_format(mode="audio", audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_meta)
                sub_opts["format"] = fmt_str
                sub_opts["postprocessors"] = pps
                if embed_meta:
                    sub_opts["writethumbnail"] = True
                sub_opts["outtmpl"] = os.path.join(output_dir, f"threads_%(uploader,uploader_id)s_{post_id or '%(id)s'}_%(title)s.%(ext)s")
                console.print(f"[bold magenta]  [AUDIO] Downloading Threads video audio ({audio_format.upper()} @ {audio_quality}k)...[/bold magenta]")
            else:
                fmt_str, pps = get_ydl_format(mode="video", video_quality=video_quality, embed_metadata=embed_meta)
                sub_opts["format"] = fmt_str
                if pps:
                    sub_opts["postprocessors"] = pps
                if embed_meta:
                    sub_opts["writethumbnail"] = True
                sub_opts["outtmpl"] = os.path.join(output_dir, f"threads_%(uploader,uploader_id)s_{post_id or '%(id)s'}_%(title)s.%(ext)s")
                q_label = f"({video_quality}p)" if video_quality and video_quality != "best" else "(best available)"
                console.print(f"[bold green]  [VIDEO] Downloading Threads video {q_label}...[/bold green]")

            with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                ret = sub_ydl.download([canonical_url])
                if ret == 0 or (post_id and check_disk_presence(output_dir, post_id)):
                    if post_id:
                        add_to_archive(archive_path, post_id, "threads")
                        archive_set.add(f"threads {post_id}")
                    return RESULT_DOWNLOADED
                return RESULT_FAILED

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

        if not best_img_url and info.get("url"):
            best_img_url = info.get("url")

        if best_img_url:
            uploader = info.get("uploader") or info.get("uploader_id") or "user"
            clean_title = sanitize_filename(info.get("title") or f"post_{post_id}")[:35].strip()
            ext = "png" if ".png" in best_img_url.lower() else "jpg"
            filename = f"threads_{uploader}_{post_id}_{clean_title}.{ext}" if post_id else f"threads_{uploader}_{clean_title}.{ext}"
            save_path = os.path.join(output_dir, filename)

            console.print(f"[bold cyan]  [PHOTO] Downloading Threads image: {filename}...[/bold cyan]")
            if download_file(best_img_url, save_path, session):
                meta_file = os.path.join(output_dir, f"threads_{post_id}_metadata.json") if post_id else os.path.join(output_dir, f"{os.path.splitext(filename)[0]}_metadata.json")
                try:
                    with open(meta_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "id": post_id,
                            "uploader": uploader,
                            "title": info.get("title", ""),
                            "description": info.get("description", ""),
                            "url": canonical_url,
                            "image_url": best_img_url,
                        }, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

                if post_id:
                    add_to_archive(archive_path, post_id, "threads")
                    archive_set.add(f"threads {post_id}")
                console.print(f"[bold green]  [OK] Threads photo saved: {filename}[/bold green]")
                return RESULT_DOWNLOADED

        console.print(f"[bold red]  [-] Could not retrieve video or photo for Threads post: {canonical_url}[/bold red]")
        return RESULT_FAILED

    except Exception as e:
        console.print(f"[bold red]  [-] Threads processing error: {e}[/bold red]")
        return RESULT_FAILED

def download_threads_profile(
    profile_url_or_user: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    cookie_file: str = None,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    smart_filters: dict = None
) -> int:
    """Download media from a user's Threads profile."""
    from features.downloader import download_urls
    target = profile_url_or_user.strip()
    if not target.startswith("http"):
        clean_user = target.lstrip("@").strip()
        url = f"https://www.threads.net/@{clean_user}"
        profile_dir = os.path.join(output_dir, f"threads_{clean_user}")
    else:
        url = resolve_threads_url(target)
        m = re.search(r"threads\.[a-z.]+/@([^/?#]+)", url)
        clean_user = m.group(1) if m else "user"
        profile_dir = os.path.join(output_dir, f"threads_{clean_user}")

    os.makedirs(profile_dir, exist_ok=True)
    console.print(f"[bold cyan][*] Downloading Threads Profile: {url}[/bold cyan]")
    console.print(f"[dim][FOLDER] Destination: {os.path.abspath(profile_dir)}[/dim]")
    return download_urls(
        [url], output_dir=profile_dir, cookie_file=cookie_file,
        mode=mode, video_quality=video_quality,
        audio_format=audio_format, audio_quality=audio_quality,
        delay=delay, smart_filters=smart_filters, is_bulk=True
    )
