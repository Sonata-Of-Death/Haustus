"""Download history archive and disk verification."""
import os
import re
import time

import requests

from core.instances import config_mgr
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
from ui.theme import console

DEFAULT_OUTPUT_DIR = config_mgr.get_default_output_dir()
DEFAULT_INSTAGRAM_SAVED_DIR = "my_saved_posts"
DEFAULT_INSTAGRAM_REPOSTS_DIR = "my_instagram_reposts"
DEFAULT_TIKTOK_SAVED_DIR = "my_tiktok_saved"
DEFAULT_TIKTOK_REPOSTS_DIR = "my_tiktok_reposts"
DEFAULT_X_SAVED_DIR = "my_x_bookmarks"
DEFAULT_X_REPOSTS_DIR = "my_x_reposts"
HISTORY_FILE = ".download_history.txt"

RESULT_DOWNLOADED = "DOWNLOADED"
RESULT_SKIPPED = "SKIPPED"
RESULT_FAILED = "FAILED"

_missing_file_session_decision = None
_missing_file_decisions = {}

def sanitize_filename(name: str, max_len: int = 180) -> str:
    """Sanitize string for safe cross-platform file naming."""
    if not name:
        return "unnamed"
    clean = re.sub(r'[\\/*?:"<>|]', "_", str(name)).strip(" .\t\r\n")
    if not clean or clean in (".", ".."):
        return "unnamed"
    stem = clean.split(".")[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}:
        clean = f"_{clean}"
    return clean[:max_len].strip(" .") if len(clean) > max_len else clean

def get_archive_set(archive_path: str) -> set:
    """Load downloaded item IDs from history archive."""
    if not os.path.exists(archive_path):
        return set()
    try:
        with open(archive_path, "r", encoding="utf-8", errors="ignore") as f:
            return {line.strip() for line in f if line.strip()}
    except (IOError, OSError):
        return set()

def remove_from_failed_urls(output_dir: str, url_or_item_id: str) -> None:
    """Remove item from failed URLs file."""
    if not output_dir or not url_or_item_id:
        return

    clean_target = str(url_or_item_id).strip()
    plat, iid = extract_url_item_id(clean_target)
    match_tokens = {clean_target}
    if iid:
        match_tokens.add(iid)

    candidate_dirs = [output_dir]
    parent_dir = os.path.dirname(os.path.abspath(output_dir))
    if parent_dir and os.path.isdir(parent_dir):
        candidate_dirs.append(parent_dir)
    for sub in (DEFAULT_INSTAGRAM_SAVED_DIR, DEFAULT_INSTAGRAM_REPOSTS_DIR,
                DEFAULT_TIKTOK_SAVED_DIR, DEFAULT_TIKTOK_REPOSTS_DIR,
                DEFAULT_X_SAVED_DIR, DEFAULT_X_REPOSTS_DIR):
        s_path = os.path.join(output_dir, sub)
        if os.path.isdir(s_path):
            candidate_dirs.append(s_path)

    for c_dir in set(candidate_dirs):
        failed_path = os.path.join(c_dir, "failed_urls.txt")
        if not os.path.isfile(failed_path):
            continue
        try:
            with open(failed_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f if line.strip()]

            remaining = []
            removed = False
            for line in lines:
                l_plat, l_id = extract_url_item_id(line)
                matched = (
                    line in match_tokens or
                    (iid and l_id == iid) or
                    (iid and iid in line) or
                    any(tok in line for tok in match_tokens if len(tok) >= 5)
                )
                if matched:
                    removed = True
                else:
                    remaining.append(line)

            if removed:
                if remaining:
                    with open(failed_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(remaining) + "\n")
                else:
                    try:
                        os.remove(failed_path)
                    except OSError:
                        pass
        except (IOError, OSError):
            pass

def add_to_archive(archive_path: str, item_id: str, platform: str = "media"):
    """Append an item ID to the archive file to prevent future re-downloads."""
    if not item_id:
        return
    try:
        with open(archive_path, "a", encoding="utf-8") as f:
            f.write(f"{platform} {item_id}\n")
    except (IOError, OSError):
        pass
    if archive_path:
        out_dir = os.path.dirname(os.path.abspath(archive_path))
        remove_from_failed_urls(out_dir, item_id)

VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv")
AUDIO_EXTS = (".mp3", ".m4a", ".flac", ".wav", ".opus", ".ogg", ".aac")
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
ALL_MEDIA_EXTS = VIDEO_EXTS + AUDIO_EXTS + PHOTO_EXTS

def check_disk_presence(
    output_dir: str,
    item_id: str = None,
    min_mtime: float = None,
    mode: str = None,
    title: str = None
) -> bool:
    """Verify if downloaded media file exists on disk."""
    if not output_dir or not os.path.isdir(output_dir):
        return False

    target_mode = (mode or "").lower()
    if target_mode == "video":
        valid_exts = VIDEO_EXTS
        check_dirs = True
    elif target_mode == "audio":
        valid_exts = AUDIO_EXTS
        check_dirs = False
    elif target_mode == "photo":
        valid_exts = PHOTO_EXTS
        check_dirs = True
    else:
        valid_exts = ALL_MEDIA_EXTS
        check_dirs = True

    clean_item_id = item_id.strip().lower() if item_id else None
    clean_title = sanitize_filename(title, max_len=50).strip().lower() if title else None

    try:
        with os.scandir(output_dir) as entries:
            for entry in entries:
                entry_name_lower = entry.name.lower()
                matches_id = False
                if clean_item_id:
                    if clean_item_id in entry_name_lower:
                        matches_id = True
                    elif "_" in clean_item_id:
                        parts = [p.strip() for p in clean_item_id.split("_") if len(p.strip()) > 2]
                        if parts and all(p in entry_name_lower for p in parts):
                            matches_id = True
                matches_title = clean_title and (clean_title in entry_name_lower)

                if matches_id or matches_title:
                    if entry.is_file():
                        ext = os.path.splitext(entry_name_lower)[1]
                        if ext in valid_exts and entry.stat().st_size > 0:
                            return True
                    elif entry.is_dir() and check_dirs:
                        try:
                            with os.scandir(entry.path) as sub_entries:
                                if any(sub_entries):
                                    return True
                        except (IOError, OSError):
                            pass
                elif min_mtime and entry.is_file():
                    ext = os.path.splitext(entry_name_lower)[1]
                    if ext in valid_exts:
                        st = entry.stat()
                        if st.st_size > 0 and st.st_mtime >= min_mtime:
                            return True
    except (IOError, OSError):
        pass
    return False

def extract_url_item_id(url: str) -> tuple[str | None, str | None]:
    """Extract platform and item ID from URL."""
    if not url:
        return None, None
    clean = url.strip()
    if is_instagram_url(clean):
        m = re.search(r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", clean)
        if m:
            return "instagram", m.group(1)
    elif is_youtube_url(clean):
        m = re.search(r"(?:v=|\/|youtu\.be\/|shorts\/)([a-zA-Z0-9_-]{11})", clean)
        if m:
            return "youtube", m.group(1)
    elif is_tiktok_url(clean):
        m = re.search(r"/(?:video|photo)/(\d+)", clean)
        if m:
            return "tiktok", m.group(1)
    elif is_x_url(clean):
        m = re.search(r"(?:x\.com|twitter\.com)/(?:[^/]+)/status/(\d+)", clean)
        if m:
            return "x", m.group(1)
    elif is_soundcloud_url(clean):
        m = re.search(r"soundcloud\.com/([^/?#]+/[^/?#]+)", clean)
        if m:
            return "soundcloud", m.group(1).replace("/", "_")
        m2 = re.search(r"snd\.sc/([^/?#]+)", clean)
        if m2:
            return "soundcloud", m2.group(1)
    elif is_reddit_url(clean):
        m = re.search(r"comments/([a-zA-Z0-9]+)", clean)
        if m:
            return "reddit", m.group(1)
        m2 = re.search(r"redd\.it/([a-zA-Z0-9]+)", clean)
        if m2:
            return "reddit", m2.group(1)
    elif is_facebook_url(clean):
        m = re.search(r"/(?:reel|reels)/(\d+)", clean)
        if m:
            return "facebook", m.group(1)
        m = re.search(r"[?&]v=(\d+)", clean)
        if m:
            return "facebook", m.group(1)
        m = re.search(r"/videos/(\d+)", clean)
        if m:
            return "facebook", m.group(1)
        m = re.search(r"/share/[rvp]/([A-Za-z0-9_-]+)", clean)
        if m:
            return "facebook", m.group(1)
        m = re.search(r"fb\.watch/([A-Za-z0-9_-]+)", clean)
        if m:
            return "facebook", m.group(1)
    elif is_pinterest_url(clean):
        m = re.search(r"/pin/(?:[\w-]+--)?(\d+)", clean)
        if m:
            return "pinterest", m.group(1)
        m2 = re.search(r"pin\.it/([A-Za-z0-9_-]+)", clean)
        if m2:
            return "pinterest", m2.group(1)
        m3 = re.search(r"/pin/([A-Za-z0-9_-]+)", clean)
        if m3:
            return "pinterest", m3.group(1)
    elif is_twitch_url(clean):
        m = re.search(r"(?:clips\.twitch\.tv/|/clip/)([A-Za-z0-9_-]+)", clean)
        if m:
            return "twitch", m.group(1)
        m2 = re.search(r"/(?:videos|video)/(\d+)", clean)
        if m2:
            return "twitch", m2.group(1)
        m3 = re.search(r"twitch\.tv/([A-Za-z0-9_]+)", clean)
        if m3 and m3.group(1).lower() not in ("directory", "downloads", "p", "search"):
            return "twitch", m3.group(1)
    elif is_threads_url(clean):
        m = re.search(r"/post/([A-Za-z0-9_-]+)", clean)
        if m:
            return "threads", m.group(1)
        m2 = re.search(r"/t/([A-Za-z0-9_-]+)", clean)
        if m2:
            return "threads", m2.group(1)
    elif is_spotify_url(clean):
        m = re.search(r"/(?:track|album|playlist|artist|episode|show)/([A-Za-z0-9]+)", clean)
        if m:
            return "spotify", m.group(1)
        m2 = re.search(r"spotify:(?:track|album|playlist|artist|episode|show):([A-Za-z0-9]+)", clean)
        if m2:
            return "spotify", m2.group(1)
    return None, None

def is_archived(
    archive_set: set,
    item_id: str,
    platform: str = "media",
    output_dir: str = None,
    title: str = None,
    prompt_missing: bool = True,
    mode: str = None
) -> bool:
    """Check if item is recorded in history and exists on disk."""
    if not item_id or not archive_set:
        return False

    in_archive = (
        f"{platform} {item_id}" in archive_set
        or f"instagram {item_id}" in archive_set
        or f"tiktok {item_id}" in archive_set
        or f"youtube {item_id}" in archive_set
        or f"x {item_id}" in archive_set
        or f"twitter {item_id}" in archive_set
        or f"soundcloud {item_id}" in archive_set
        or f"reddit {item_id}" in archive_set
        or f"facebook {item_id}" in archive_set
        or f"pinterest {item_id}" in archive_set
        or f"twitch {item_id}" in archive_set
        or f"threads {item_id}" in archive_set
        or f"spotify {item_id}" in archive_set
        or item_id in archive_set
    )
    if not in_archive:
        return False

    if output_dir and os.path.isdir(output_dir):
        exists_on_disk = check_disk_presence(output_dir, item_id, mode=mode, title=title)
        if exists_on_disk:
            return True

        # Check whether media exists in another format before treating as missing.
        if mode:
            other_mode_present = check_disk_presence(output_dir, item_id, mode=None, title=title)
            if other_mode_present:
                return False

        # File is recorded in history but absent from disk.
        if not prompt_missing:
            return False

        global _missing_file_session_decision, _missing_file_decisions
        if _missing_file_session_decision == "skip_all":
            return True
        elif _missing_file_session_decision == "redownload_all":
            return False

        if item_id in _missing_file_decisions:
            dec = _missing_file_decisions[item_id]
            return dec in ("skip", "skip_all")

        policy = config_mgr.get_archive_missing_policy()
        if policy == "skip":
            _missing_file_decisions[item_id] = "skip"
            console.print(f"[bold yellow]  [!] [ARCHIVE] '{platform.title()} ID: {item_id}' found in history but missing from disk. Keeping deleted (skipped) per policy.[/bold yellow]")
            return True
        elif policy == "redownload":
            _missing_file_decisions[item_id] = "redownload"
            console.print(f"[bold yellow]  [!] [ARCHIVE] '{platform.title()} ID: {item_id}' found in history but missing from disk. Re-downloading per policy.[/bold yellow]")
            return False

        # Prompt user when no automated policy is configured.
        label = f"'{title}'" if title else f"ID: {item_id}"
        console.print(f"[bold yellow][!] File missing from disk: {label} was previously downloaded but is missing from '{output_dir}'.[/bold yellow]")
        opts = [
            {"key": "1", "title": "Keep Deleted (Skip)", "desc": "Do not download again; preserve history archive", "value": "skip"},
            {"key": "2", "title": "Re-download Media", "desc": "Download file again to restore it to disk", "value": "redownload"},
            {"key": "3", "title": "Skip All Missing (This Session)", "desc": "Skip all deleted files encountered during this run", "value": "skip_all"},
            {"key": "4", "title": "Re-download All Missing (This Session)", "desc": "Re-download all deleted files encountered during this run", "value": "redownload_all"},
        ]
        from ui.components import interactive_select
        choice = interactive_select("MISSING ARCHIVED FILE ACTION", opts, default_index=0, border_style="yellow")
        if choice in ("skip_all", "redownload_all"):
            _missing_file_session_decision = choice
        _missing_file_decisions[item_id] = choice
        return choice in ("skip", "skip_all")

    return True

def reset_missing_decision_cache():
    """Reset session cache for missing file decisions at the start of a download task."""
    global _missing_file_session_decision, _missing_file_decisions
    _missing_file_session_decision = None
    _missing_file_decisions = {}

def resolve_archive_policy(is_bulk: bool = False) -> bool:
    """Determine if archive check should run for task."""
    if is_bulk:
        mode = config_mgr.get_archive_bulk_mode()
        if mode == "always":
            return True
        elif mode == "disabled":
            return False
        opts = [
            {"key": "1", "title": "Yes - Use Download History Archive [Recommended]", "desc": "Skip items already downloaded in previous sessions", "value": "yes"},
            {"key": "2", "title": "No - Ignore Archive History", "desc": "Download everything without skipping previous items", "value": "no"},
        ]
        from ui.components import interactive_select
        res = interactive_select("USE DOWNLOAD HISTORY ARCHIVE?", opts, default_index=0, border_style="cyan")
        return res == "yes"
    else:
        mode = config_mgr.get_archive_single_mode()
        if mode == "always":
            return True
        elif mode == "disabled":
            return False
        opts = [
            {"key": "1", "title": "No - Download Directly (Ignore History) [Default]", "desc": "Process file even if downloaded previously", "value": "no"},
            {"key": "2", "title": "Yes - Check & Update History Archive", "desc": "Skip if already recorded in history", "value": "yes"},
        ]
        from ui.components import interactive_select
        res = interactive_select("CHECK DOWNLOAD HISTORY ARCHIVE?", opts, default_index=0, border_style="cyan")
        return res == "yes"

def download_file(url: str, save_path: str, session: requests.Session, progress_callback=None) -> bool:
    """Download binary file with progress updates."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.tiktok.com/",
    }
    try:
        resp = session.get(url, headers=headers, stream=True, timeout=30)
        if resp.status_code == 200:
            total_bytes = None
            try:
                headers_dict = getattr(resp, "headers", None)
                if headers_dict and hasattr(headers_dict, "get"):
                    cl = headers_dict.get("Content-Length")
                    if cl:
                        total_bytes = int(cl)
            except (ValueError, TypeError):
                total_bytes = None

            downloaded = 0
            start_t = time.time()
            last_hook_t = start_t
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=16384):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if progress_callback and (now - last_hook_t >= 0.1 or (total_bytes and downloaded >= total_bytes)):
                        dt = now - start_t
                        speed = downloaded / dt if dt > 0 else 0
                        eta = (total_bytes - downloaded) / speed if (total_bytes and speed > 0 and total_bytes > downloaded) else None
                        progress_callback({
                            "status": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": total_bytes,
                            "speed": speed,
                            "eta": eta,
                            "filename": save_path,
                        })
                        last_hook_t = now

            if progress_callback:
                progress_callback({
                    "status": "finished",
                    "filename": save_path,
                    "downloaded_bytes": downloaded,
                    "total_bytes": downloaded,
                })
            return True
        else:
            console.print(f"[bold yellow]    [!] Failed download (HTTP {resp.status_code})[/bold yellow]")
            return False
    except Exception as e:
        console.print(f"[bold red]    [-] File download error: {e}[/bold red]")
        return False

def find_downloaded_media_file(output_dir: str, item_id: str = None) -> str | None:
    """Find downloaded media file path in directory."""
    if not output_dir or not os.path.isdir(output_dir):
        return None
    try:
        cand_list = []
        with os.scandir(output_dir) as entries:
            for entry in entries:
                if entry.is_file() and entry.stat().st_size > 0:
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in (".mp3", ".m4a", ".mp4", ".flac", ".wav", ".opus", ".ogg", ".mkv", ".webm"):
                        if item_id and item_id in entry.name:
                            return entry.path
                        cand_list.append(entry)
        if cand_list:
            cand_list.sort(key=lambda e: e.stat().st_mtime, reverse=True)
            return cand_list[0].path
    except Exception:
        pass
    return None

def tag_audio_metadata(
    file_path: str,
    title: str = None,
    artist: str = None,
    album: str = None,
    date: str = None,
    cover_url: str = None,
    comment: str = None
):
    """Tag audio file with metadata and cover art."""
    if not file_path or not os.path.isfile(file_path):
        return
    ext = os.path.splitext(file_path)[1].lower()
    cover_bytes = None
    if cover_url:
        if os.path.isfile(cover_url):
            try:
                with open(cover_url, "rb") as cf:
                    cover_bytes = cf.read()
            except Exception:
                cover_bytes = None
        elif str(cover_url).startswith(("http://", "https://")):
            try:
                r = requests.get(cover_url, timeout=12)
                if r.status_code == 200:
                    cover_bytes = r.content
            except Exception:
                cover_bytes = None

    sibling_thumb_to_clean = None
    if not cover_bytes and file_path:
        base_no_ext = os.path.splitext(file_path)[0]
        for img_ext in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = base_no_ext + img_ext
            if os.path.isfile(candidate) and os.path.getsize(candidate) > 100:
                try:
                    with open(candidate, "rb") as cf:
                        cover_bytes = cf.read()
                    sibling_thumb_to_clean = candidate
                    break
                except Exception:
                    pass

    mime_type = "image/png" if (cover_bytes and cover_bytes.startswith(b"\x89PNG")) else "image/jpeg"

    try:
        if ext == ".mp3":
            try:
                from mutagen.id3 import APIC, COMM, ID3, TALB, TDRC, TIT2, TPE1, ID3NoHeaderError
                try:
                    id3 = ID3(file_path)
                except ID3NoHeaderError:
                    id3 = ID3()
                if title:
                    id3["TIT2"] = TIT2(encoding=3, text=str(title))
                if artist:
                    id3["TPE1"] = TPE1(encoding=3, text=str(artist))
                if album:
                    id3["TALB"] = TALB(encoding=3, text=str(album))
                if date:
                    id3["TDRC"] = TDRC(encoding=3, text=str(date)[:10])
                if comment:
                    id3["COMM"] = COMM(encoding=3, lang="eng", desc="Comment", text=str(comment))
                if cover_bytes:
                    id3.delall("APIC")
                    id3.add(APIC(
                        encoding=3,
                        mime=mime_type,
                        type=3,
                        desc="Cover",
                        data=cover_bytes
                    ))
                id3.save(file_path, v2_version=4)
            except Exception:
                pass
        elif ext in (".m4a", ".mp4"):
            try:
                from mutagen.mp4 import MP4, MP4Cover
                mp4 = MP4(file_path)
                if title:
                    mp4["\xa9nam"] = [str(title)]
                if artist:
                    mp4["\xa9ART"] = [str(artist)]
                if album:
                    mp4["\xa9alb"] = [str(album)]
                if date:
                    mp4["\xa9day"] = [str(date)[:10]]
                if comment:
                    mp4["\xa9cmt"] = [str(comment)]
                if cover_bytes:
                    fmt = MP4Cover.FORMAT_PNG if mime_type == "image/png" else MP4Cover.FORMAT_JPEG
                    mp4["covr"] = [MP4Cover(cover_bytes, imageformat=fmt)]
                mp4.save()
            except Exception:
                pass
        elif ext == ".flac":
            try:
                from mutagen.flac import FLAC, Picture
                flac = FLAC(file_path)
                if title:
                    flac["title"] = str(title)
                if artist:
                    flac["artist"] = str(artist)
                if album:
                    flac["album"] = str(album)
                if date:
                    flac["date"] = str(date)[:10]
                if comment:
                    flac["comment"] = str(comment)
                if cover_bytes:
                    pic = Picture()
                    pic.type = 3
                    pic.mime = mime_type
                    pic.desc = "Cover"
                    pic.data = cover_bytes
                    flac.clear_pictures()
                    flac.add_picture(pic)
                flac.save()
            except Exception:
                pass
        elif ext in (".ogg", ".opus"):
            try:
                import base64

                from mutagen.flac import Picture
                if ext == ".opus":
                    from mutagen.oggopus import OggOpus
                    audio = OggOpus(file_path)
                else:
                    from mutagen.oggvorbis import OggVorbis
                    audio = OggVorbis(file_path)
                if title:
                    audio["title"] = [str(title)]
                if artist:
                    audio["artist"] = [str(artist)]
                if album:
                    audio["album"] = [str(album)]
                if date:
                    audio["date"] = [str(date)[:10]]
                if comment:
                    audio["comment"] = [str(comment)]
                if cover_bytes:
                    pic = Picture()
                    pic.type = 3
                    pic.mime = mime_type
                    pic.desc = "Cover"
                    pic.data = cover_bytes
                    audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
                audio.save()
            except Exception:
                pass
    except Exception:
        pass

    if sibling_thumb_to_clean and os.path.isfile(sibling_thumb_to_clean):
        try:
            os.remove(sibling_thumb_to_clean)
        except Exception:
            pass
