"""TikTok media extractor."""
import json
import os
import re
import time
import urllib.parse

import requests
import yt_dlp

from core.archive import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TIKTOK_REPOSTS_DIR,
    DEFAULT_TIKTOK_SAVED_DIR,
    RESULT_DOWNLOADED,
    RESULT_FAILED,
    RESULT_SKIPPED,
    add_to_archive,
    check_disk_presence,
    download_file,
    find_downloaded_media_file,
    is_archived,
    sanitize_filename,
    tag_audio_metadata,
)
from core.cookies import get_effective_tiktok_cookie_file, load_cookie_jar, prepare_tiktok_cookies
from core.ytdl_format import (
    get_ydl_format,
)
from platforms.base import resolve_collection_target_dir, run_collection_inventory
from ui.components import ask_input
from ui.theme import console


def fetch_tiktok_api_data(url: str) -> dict | None:
    """Fetch unwatermarked media data from TikTok via high-speed API."""
    api_endpoint = f"https://www.tikwm.com/api/?url={urllib.parse.quote(url)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(api_endpoint, headers=headers, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0 and data.get("data"):
                return data.get("data")
    except Exception:
        pass
    return None

def process_tiktok_post(
    url: str,
    output_dir: str,
    ydl: yt_dlp.YoutubeDL,
    session: requests.Session,
    archive_path: str,
    archive_set: set,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192"
) -> str:
    """Download TikTok video or slideshow."""
    data = fetch_tiktok_api_data(url)
    post_id = None
    uploader = "tiktok_user"
    title = ""

    if data:
        post_id = str(data.get("id") or "")
        uploader = sanitize_filename(data.get("author", {}).get("unique_id") or "tiktok_user")
        title = sanitize_filename(data.get("title") or "")
    else:
        match = re.search(r"/(?:video|photo)/(\d+)", url)
        if match:
            post_id = match.group(1)

    if post_id and is_archived(archive_set, post_id, "tiktok", output_dir=output_dir):
        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (TikTok ID: {post_id})[/bold blue]")
        return RESULT_SKIPPED

    images = data.get("images") if data else None
    prog_cb = (ydl.params.get("progress_hooks") or [None])[0]

    embed_meta = ydl.params.get("_embed_metadata", True)
    clean_title = sanitize_filename(title, max_len=140) if title else (post_id or "tiktok_audio")
    if mode == "audio":
        if images and isinstance(images, list) and len(images) > 0:
            music_url = data.get("music")
            if music_url:
                music_file = os.path.join(output_dir, f"tiktok_{uploader}_{post_id}_{clean_title}.{audio_format}")
                console.print(f"[bold magenta]  [AUDIO] Downloading TikTok background music ({audio_format.upper()})...[/bold magenta]")
                if download_file(music_url, music_file, session, progress_callback=prog_cb) and (not post_id or check_disk_presence(output_dir, post_id)):
                    if embed_meta:
                        tag_audio_metadata(
                            music_file,
                            title=title or f"TikTok_{post_id}",
                            artist=uploader,
                            album=f"{uploader} - TikTok",
                            cover_url=images[0] if images else None
                        )
                    if post_id:
                        add_to_archive(archive_path, post_id, "tiktok")
                        archive_set.add(f"tiktok {post_id}")
                    return RESULT_DOWNLOADED
                return RESULT_FAILED

        console.print(f"[bold magenta]  [AUDIO] Extracting TikTok audio ({audio_format.upper()} @ {audio_quality}k)...[/bold magenta]")
        video_outtmpl = os.path.join(output_dir, f"tiktok_{uploader}_{post_id or '%(id)s'}_{clean_title}.%(ext)s")
        sub_opts = dict(ydl.params)
        sub_opts.pop("cookiesfrombrowser", None)
        if ydl.cookiejar:
            sub_opts["cookiejar"] = ydl.cookiejar
        fmt_str, pps = get_ydl_format(mode="audio", audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_meta)
        sub_opts["format"] = fmt_str
        sub_opts["postprocessors"] = pps
        if embed_meta:
            sub_opts["writethumbnail"] = True
        sub_opts["outtmpl"] = video_outtmpl

        with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
            ret = sub_ydl.download([url])
            if ret == 0 and (not post_id or check_disk_presence(output_dir, post_id)):
                if embed_meta:
                    media_f = find_downloaded_media_file(output_dir, post_id)
                    if media_f:
                        tag_audio_metadata(
                            media_f,
                            title=title or f"TikTok_{post_id}",
                            artist=uploader,
                            album=f"{uploader} - TikTok",
                            cover_url=data.get("cover") if data else None
                        )
                if post_id:
                    add_to_archive(archive_path, post_id, "tiktok")
                    archive_set.add(f"tiktok {post_id}")
                return RESULT_DOWNLOADED
        return RESULT_FAILED

    # Handle photo slideshow posts.
    if images and isinstance(images, list) and len(images) > 0:
        folder_name = sanitize_filename(f"tiktok_{uploader}_{post_id}_photos")
        post_folder = os.path.join(output_dir, folder_name)
        os.makedirs(post_folder, exist_ok=True)

        console.print(f"[bold blue]  [FOLDER] Detected TikTok Photo Slideshow ({len(images)} photos). Folder: {folder_name}/[/bold blue]")

        if title.strip():
            try:
                with open(os.path.join(post_folder, "caption.txt"), "w", encoding="utf-8") as f:
                    f.write(data.get("title") or "")
            except Exception:
                pass

        saved_imgs = 0
        for idx, img_url in enumerate(images, 1):
            img_path = os.path.join(post_folder, f"{idx:02d}.jpg")
            console.print(f"    [>] [{idx}/{len(images)}] Downloading TikTok photo {idx:02d}.jpg...")
            if download_file(img_url, img_path, session, progress_callback=prog_cb):
                saved_imgs += 1

        music_url = data.get("music")
        if music_url:
            music_path = os.path.join(post_folder, "audio_track.mp3")
            console.print("    [AUDIO] Downloading background music track...")
            download_file(music_url, music_path, session, progress_callback=prog_cb)

        if (saved_imgs > 0 or not images) and (not post_id or check_disk_presence(output_dir, post_id) or any(os.scandir(post_folder))):
            if post_id:
                add_to_archive(archive_path, post_id, "tiktok")
                archive_set.add(f"tiktok {post_id}")
            console.print(f"[bold green]  [OK] All TikTok photos & audio saved in: {folder_name}/[/bold green]")
            return RESULT_DOWNLOADED
        return RESULT_FAILED

    # Fetch video stream when post contains video content.
    q_label = f"({video_quality}p with audio)" if video_quality and video_quality != "best" else "(unwatermarked HD with audio)"
    console.print(f"[bold green]  [VIDEO] Downloading TikTok video {q_label}: {title}[/bold green]")

    video_downloaded = False
    try:
        clean_title = sanitize_filename(title, max_len=140) if title else (post_id or "tiktok_video")
        video_outtmpl = os.path.join(output_dir, f"tiktok_{uploader}_{post_id or '%(id)s'}_{clean_title}.%(ext)s")
        sub_opts = dict(ydl.params)
        sub_opts.pop("cookiesfrombrowser", None)
        if ydl.cookiejar:
            sub_opts["cookiejar"] = ydl.cookiejar
        fmt_str, pps = get_ydl_format(mode="video", video_quality=video_quality, embed_metadata=embed_meta)
        sub_opts["format"] = fmt_str
        if pps:
            sub_opts["postprocessors"] = pps
        else:
            sub_opts.pop("postprocessors", None)
        if embed_meta:
            sub_opts["writethumbnail"] = True
        sub_opts["outtmpl"] = video_outtmpl
        with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
            ret = sub_ydl.download([url])
            if ret == 0:
                video_downloaded = True
    except Exception as e:
        console.print(f"    [dim][!] yt-dlp direct download warning: {e}. Trying fallback...[/dim]")

    if not video_downloaded and data and data.get("play"):
        play_url = data.get("play")
        video_file = os.path.join(output_dir, f"tiktok_{uploader}_{post_id}_{clean_title}.mp4")
        console.print("    [>] Downloading unwatermarked video via high-speed stream...")
        if download_file(play_url, video_file, session, progress_callback=prog_cb):
            video_downloaded = True

    if video_downloaded and (not post_id or check_disk_presence(output_dir, post_id)):
        if post_id:
            add_to_archive(archive_path, post_id, "tiktok")
            archive_set.add(f"tiktok {post_id}")
        return RESULT_DOWNLOADED

    return RESULT_FAILED

def fetch_tiktok_saved_videos_urls(session: requests.Session) -> list[str]:
    """Fetch all saved / bookmarked video URLs directly from TikTok's Web Feed API."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.tiktok.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    console.print("[bold cyan][*] Fetching saved / favorite videos from your TikTok account...[/bold cyan]")

    sec_uid = None
    try:
        acc_resp = session.get("https://www.tiktok.com/passport/web/account/info/", headers=headers, timeout=12)
        if acc_resp.status_code == 200:
            acc_data = acc_resp.json()
            if acc_data.get("message") == "success" and acc_data.get("data"):
                u_info = acc_data["data"]
                u_name = u_info.get("username") or u_info.get("screen_name") or "User"
                sec_uid = u_info.get("sec_user_id") or u_info.get("sec_uid")
                console.print(f"  [bold green][OK] Connected to TikTok account:[/bold green] [bold cyan]@{u_name}[/bold cyan]")
    except Exception:
        pass

    saved_urls = []
    seen_ids = set()

    # Query user collect API for bookmarked videos.
    cursor = 0
    page = 1
    while True:
        params = {
            "aid": "1988",
            "app_name": "tiktok_web",
            "device_platform": "web_pc",
            "count": 30,
            "cursor": cursor,
            "coverFormat": 2,
        }
        if sec_uid:
            params["secUid"] = sec_uid

        try:
            resp = session.get("https://www.tiktok.com/api/user/collect/item_list/", headers=headers, params=params, timeout=25)
            if resp.status_code != 200:
                console.print(f"[bold yellow][!] HTTP {resp.status_code} from TikTok collect API.[/bold yellow]")
                break

            data = resp.json()
            if data.get("status_code", 0) != 0 and data.get("statusCode", 0) != 0:
                err_msg = data.get("status_msg") or data.get("statusMsg") or "Login expired or restricted"
                console.print(f"[bold yellow][!] TikTok API Response: {err_msg}[/bold yellow]")
                break

            items = data.get("itemList") or data.get("items") or data.get("collectorItemVoList") or []
            if not items:
                break

            for item in items:
                item_id = str(item.get("id") or item.get("aweme_id") or item.get("itemId") or "")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    author = item.get("author", {})
                    author_id = author.get("uniqueId") or author.get("unique_id") or "video"
                    post_url = f"https://www.tiktok.com/@{author_id}/video/{item_id}"
                    saved_urls.append(post_url)

            console.print(f"  [bold green][OK] Page {page}:[/bold green] Found {len(saved_urls)} saved videos so far...", end="\r")

            has_more = data.get("hasMore") or data.get("has_more")
            next_cursor = data.get("cursor")
            if not has_more or next_cursor is None or str(next_cursor) == str(cursor) or str(next_cursor) == "0":
                break

            cursor = next_cursor
            page += 1
            time.sleep(1.0)
        except Exception as e:
            console.print(f"[bold red][-] Error during TikTok collect pagination:[/bold red] {e}")
            break

    # Fall back to favorite items endpoint if collection query returned no items.
    if not saved_urls:
        cursor = 0
        page = 1
        while True:
            params = {
                "aid": "1988",
                "app_name": "tiktok_web",
                "device_platform": "web_pc",
                "count": 30,
                "cursor": cursor,
                "coverFormat": 2,
            }
            if sec_uid:
                params["secUid"] = sec_uid

            try:
                resp = session.get("https://www.tiktok.com/api/favorite/item_list/", headers=headers, params=params, timeout=25)
                if resp.status_code != 200:
                    break
                data = resp.json()
                if data.get("status_code", 0) != 0 and data.get("statusCode", 0) != 0:
                    break
                items = data.get("itemList") or data.get("items") or []
                if not items:
                    break
                for item in items:
                    item_id = str(item.get("id") or item.get("aweme_id") or "")
                    if item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        author = item.get("author", {})
                        author_id = author.get("uniqueId") or author.get("unique_id") or "video"
                        post_url = f"https://www.tiktok.com/@{author_id}/video/{item_id}"
                        saved_urls.append(post_url)

                console.print(f"  [bold green][OK] Favorites Page {page}:[/bold green] Found {len(saved_urls)} videos so far...", end="\r")
                has_more = data.get("hasMore") or data.get("has_more")
                next_cursor = data.get("cursor")
                if not has_more or next_cursor is None or str(next_cursor) == str(cursor) or str(next_cursor) == "0":
                    break
                cursor = next_cursor
                page += 1
                time.sleep(1.0)
            except Exception:
                break

    console.print(f"[bold green][OK] Total TikTok saved videos discovered: {len(saved_urls)}[/bold green]")
    return saved_urls

def parse_tiktok_user_data_json(json_input: str) -> list[str]:
    """Parse TikTok data export file."""
    content = ""
    if os.path.isfile(json_input.strip()):
        with open(json_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    else:
        content = json_input.strip()

    if not content:
        console.print("[bold red][-] Empty or missing TikTok data export file.[/bold red]")
        return []

    try:
        data = json.loads(content)
    except Exception as e:
        console.print(f"[bold red][-] Failed to parse JSON content: {e}[/bold red]")
        return []

    urls = []
    seen = set()

    activity = data.get("Activity") or data.get("activity") or {}
    fav_videos = activity.get("Favorite Videos") or activity.get("favorite_videos") or {}
    fav_list = fav_videos.get("FavoriteVideoList") or fav_videos.get("favorite_video_list") or []

    if isinstance(fav_list, list):
        for entry in fav_list:
            if isinstance(entry, dict):
                link = entry.get("Link") or entry.get("link") or entry.get("Url") or entry.get("url")
                if link and link.strip() and link.strip() not in seen:
                    seen.add(link.strip())
                    urls.append(link.strip())

    fav_collections = activity.get("Favorite Collections") or {}
    col_list = fav_collections.get("FavoriteCollectionList") or []
    if isinstance(col_list, list):
        for entry in col_list:
            if isinstance(entry, dict):
                link = entry.get("Link") or entry.get("link")
                if link and link.strip() and link.strip() not in seen:
                    seen.add(link.strip())
                    urls.append(link.strip())

    if not urls:
        raw_text = json.dumps(data)
        found_links = re.findall(
            r"https?://(?:www\.|vm\.|vt\.)?tiktok\.com/(?:@[a-zA-Z0-9_.-]+/video/\d+|[a-zA-Z0-9_.-]+/video/\d+|t/[a-zA-Z0-9]+)",
            raw_text
        )
        for link in found_links:
            if link not in seen:
                seen.add(link)
                urls.append(link)

    console.print(f"[bold green][OK] Extracted {len(urls)} TikTok video URLs from JSON export file.[/bold green]")
    return urls

def download_tiktok_saved_posts(
    cookie_file: str = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    use_aria2: bool = False,
    normalize: bool = False,
    transcode: bool = False,
    proxy: str = None,
    custom_urls: list[str] = None
):
    """Download TikTok saved posts."""
    from features.downloader import download_urls
    target_dir = resolve_collection_target_dir(output_dir, DEFAULT_TIKTOK_SAVED_DIR)
    saved_urls = []
    cookie_path = None

    if custom_urls:
        saved_urls = custom_urls
    else:
        cookie_path = get_effective_tiktok_cookie_file(cookie_file)
        if not cookie_path or not os.path.isfile(cookie_path):
            console.print("[bold yellow][!] Downloading saved videos requires TikTok authentication.[/bold yellow]")
            raw_c = ask_input("[bold cyan]Please paste your TikTok sessionid directly[/bold cyan]")
            if not raw_c:
                console.print("[bold red][-] No cookie provided. Aborting.[/bold red]")
                return
            cookie_path = prepare_tiktok_cookies(raw_c)

        if not cookie_path or not os.path.isfile(cookie_path):
            console.print("[bold red][-] Error: Could not prepare valid TikTok cookies.[/bold red]")
            return

        cj = load_cookie_jar(cookie_path)
        if not cj:
            console.print("[bold red][-] Error: Failed to parse TikTok cookies.[/bold red]")
            return

        session = requests.Session()
        session.cookies.update(cj)
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}

        saved_urls = fetch_tiktok_saved_videos_urls(session)
        if not saved_urls:
            console.print("[bold yellow][!] No saved videos found on TikTok account or session expired.[/bold yellow]")
            console.print("[dim]Note: You can also provide your TikTok user_data.json data export file path.[/dim]")
            return

    pending_urls = run_collection_inventory(
        urls=saved_urls,
        target_dir=target_dir,
        platform_id="tiktok",
        list_filename="saved_tiktok_urls.txt",
        inventory_title="TikTok Saved Videos Status",
        total_label="Total on TikTok Account:",
        all_done_msg="All saved TikTok videos are already downloaded and physically verified on disk!",
    )
    if not pending_urls:
        return

    effective_cookie = cookie_path if not custom_urls else (get_effective_tiktok_cookie_file(cookie_file) or cookie_file)
    already_on_disk = len(saved_urls) - len(pending_urls)
    download_urls(
        pending_urls, output_dir=target_dir, cookie_file=effective_cookie,
        mode=mode, video_quality=video_quality,
        audio_format=audio_format, audio_quality=audio_quality,
        delay=delay,
        use_aria2=use_aria2, normalize=normalize,
        transcode=transcode, proxy=proxy,
        is_bulk=True, initial_skipped=already_on_disk
    )

def fetch_tiktok_reposted_videos_urls(session: requests.Session) -> list[str]:
    """Fetch all reposted video URLs directly from TikTok's Web Feed API."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.tiktok.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    console.print("[bold cyan][*] Fetching reposted videos from your TikTok account...[/bold cyan]")
    sec_uid = None
    try:
        acc_resp = session.get("https://www.tiktok.com/passport/web/account/info/", headers=headers, timeout=12)
        if acc_resp.status_code == 200:
            acc_data = acc_resp.json()
            if acc_data.get("message") == "success" and acc_data.get("data"):
                u_info = acc_data["data"]
                u_name = u_info.get("username") or u_info.get("screen_name") or "User"
                sec_uid = u_info.get("sec_user_id") or u_info.get("sec_uid")
                console.print(f"  [bold green][OK] Connected to TikTok account:[/bold green] [bold cyan]@{u_name}[/bold cyan]")
    except Exception:
        pass

    reposted_urls = []
    seen_ids = set()

    endpoints = [
        "https://www.tiktok.com/api/user/repost/item_list/",
        "https://www.tiktok.com/api/user/repost/feed/",
    ]
    for endpoint in endpoints:
        cursor = 0
        page = 1
        while True:
            params = {
                "aid": "1988",
                "app_name": "tiktok_web",
                "device_platform": "web_pc",
                "count": 30,
                "cursor": cursor,
            }
            if sec_uid:
                params["secUid"] = sec_uid

            try:
                resp = session.get(endpoint, headers=headers, params=params, timeout=25)
                if resp.status_code != 200:
                    break
                data = resp.json()
                if data.get("status_code", 0) != 0 and data.get("statusCode", 0) != 0:
                    break
                items = data.get("itemList") or data.get("items") or data.get("repostList") or []
                if not items:
                    break
                for item in items:
                    aweme = item.get("item") or item.get("aweme") or item
                    item_id = str(aweme.get("id") or aweme.get("aweme_id") or "")
                    if item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        author = aweme.get("author", {})
                        author_id = author.get("uniqueId") or author.get("unique_id") or "video"
                        post_url = f"https://www.tiktok.com/@{author_id}/video/{item_id}"
                        reposted_urls.append(post_url)
                console.print(f"  [bold green][OK] Reposts Page {page}:[/bold green] Found {len(reposted_urls)} reposts so far...", end="\r")
                has_more = data.get("hasMore") or data.get("has_more")
                next_cursor = data.get("cursor")
                if not has_more or next_cursor is None or str(next_cursor) == str(cursor) or str(next_cursor) == "0":
                    break
                cursor = next_cursor
                page += 1
                time.sleep(1.0)
            except Exception:
                break
        if reposted_urls:
            break

    console.print(f"[bold green][OK] Total TikTok reposted videos discovered: {len(reposted_urls)}[/bold green]")
    return reposted_urls

def download_tiktok_reposted_videos(
    cookie_file: str = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    use_aria2: bool = False,
    normalize: bool = False,
    transcode: bool = False,
    proxy: str = None,
):
    """Download all REPOSTED videos from your authenticated TikTok account."""
    from features.downloader import download_urls
    target_dir = resolve_collection_target_dir(output_dir, DEFAULT_TIKTOK_REPOSTS_DIR)

    cookie_path = get_effective_tiktok_cookie_file(cookie_file)
    if not cookie_path or not os.path.isfile(cookie_path):
        console.print("[bold yellow][!] Downloading reposted videos requires TikTok authentication.[/bold yellow]")
        raw_c = ask_input("[bold cyan]Please paste your TikTok sessionid directly[/bold cyan]")
        if not raw_c:
            console.print("[bold red][-] No cookie provided. Aborting.[/bold red]")
            return
        cookie_path = prepare_tiktok_cookies(raw_c)

    if not cookie_path or not os.path.isfile(cookie_path):
        console.print("[bold red][-] Error: Could not prepare valid TikTok cookies.[/bold red]")
        return

    cj = load_cookie_jar(cookie_path)
    if not cj:
        console.print("[bold red][-] Error: Failed to parse TikTok cookies.[/bold red]")
        return

    session = requests.Session()
    session.cookies.update(cj)
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}

    reposted_urls = fetch_tiktok_reposted_videos_urls(session)
    if not reposted_urls:
        console.print("[bold yellow][!] No reposted videos found on TikTok account or session expired.[/bold yellow]")
        return

    pending_urls = run_collection_inventory(
        urls=reposted_urls,
        target_dir=target_dir,
        platform_id="tiktok",
        list_filename="reposted_tiktok_urls.txt",
        inventory_title="TikTok Reposted Videos Status",
        total_label="Total on TikTok Account:",
        all_done_msg="All reposted TikTok videos are already downloaded and physically verified on disk!",
    )
    if not pending_urls:
        return

    already_on_disk = len(reposted_urls) - len(pending_urls)
    download_urls(
        pending_urls, output_dir=target_dir, cookie_file=cookie_path,
        mode=mode, video_quality=video_quality,
        audio_format=audio_format, audio_quality=audio_quality,
        delay=delay,
        use_aria2=use_aria2, normalize=normalize,
        transcode=transcode, proxy=proxy,
        is_bulk=True, initial_skipped=already_on_disk
    )
