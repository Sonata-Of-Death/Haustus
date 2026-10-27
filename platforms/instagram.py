"""Instagram media extractor."""
import json
import os
import re
import time

import requests
import yt_dlp

from core.archive import (
    DEFAULT_INSTAGRAM_REPOSTS_DIR,
    DEFAULT_INSTAGRAM_SAVED_DIR,
    DEFAULT_OUTPUT_DIR,
    RESULT_DOWNLOADED,
    RESULT_FAILED,
    RESULT_SKIPPED,
    add_to_archive,
    check_disk_presence,
    download_file,
    find_downloaded_media_file,
    is_archived,
    remove_from_failed_urls,
    sanitize_filename,
    tag_audio_metadata,
)
from core.cookies import get_effective_instagram_cookie_file, load_cookie_jar, prepare_cookies
from core.ytdl_format import (
    get_ydl_format,
)
from platforms.base import resolve_collection_target_dir, run_collection_inventory
from ui.components import ask_input
from ui.theme import console


def has_instagram_video(entry: dict) -> bool:
    """Check if an Instagram entry contains an actual video stream."""
    formats = entry.get("formats") or []
    for f in formats:
        if f.get("vcodec") and f.get("vcodec") != "none":
            return True
        if f.get("ext") in ("mp4", "webm", "mkv", "mov"):
            return True
    return False

def get_instagram_best_image_url(entry: dict) -> str | None:
    """Extract highest resolution Instagram image from thumbnails candidates."""
    thumbnails = entry.get("thumbnails") or []
    valid = [t for t in thumbnails if t.get("url")]
    if not valid:
        return None
    return valid[-1]["url"]

class SilentProbeLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

def extract_instagram_info(url: str, ydl: yt_dlp.YoutubeDL) -> tuple[dict | None, bool]:
    """Extract Instagram post metadata."""
    # Probe with cookies using quiet logger.
    probe_opts = dict(ydl.params)
    probe_opts["logger"] = SilentProbeLogger()
    probe_opts["quiet"] = True
    probe_opts["no_warnings"] = True

    try:
        with yt_dlp.YoutubeDL(probe_opts) as probe_ydl:
            ie = yt_dlp.extractor.get_info_extractor("Instagram")(probe_ydl)
            if ie.suitable(url):
                try:
                    info = ie._real_extract(url)
                    if info:
                        return info, True
                except Exception as e:
                    err_str = str(e).lower()
                    if any(k in err_str for k in ("getaddrinfo", "transport", "connection", "timed out", "timeout")):
                        raise
            try:
                info = probe_ydl.extract_info(url, download=False)
                if info:
                    return info, False
            except Exception as e:
                err_str = str(e).lower()
                if any(k in err_str for k in ("getaddrinfo", "transport", "connection", "timed out", "timeout")):
                    raise
    except Exception as e:
        err_str = str(e).lower()
        if any(k in err_str for k in ("getaddrinfo", "transport", "connection", "timed out", "timeout")):
            raise

    # Fall back to anonymous extraction if authenticated session returns empty response.
    has_cookies = bool(ydl.params.get("cookiefile") or getattr(ydl, "cookiejar", None) or ydl.params.get("cookiesfrombrowser"))
    if has_cookies:
        try:
            anon_opts = dict(ydl.params)
            anon_opts.pop("cookiefile", None)
            anon_opts.pop("cookiejar", None)
            anon_opts.pop("cookiesfrombrowser", None)
            anon_opts["logger"] = SilentProbeLogger()
            anon_opts["quiet"] = True
            anon_opts["no_warnings"] = True
            with yt_dlp.YoutubeDL(anon_opts) as anon_ydl:
                anon_ie = yt_dlp.extractor.get_info_extractor("Instagram")(anon_ydl)
                if anon_ie.suitable(url):
                    try:
                        info = anon_ie._real_extract(url)
                        if info:
                            return info, True
                    except Exception:
                        pass
                info = anon_ydl.extract_info(url, download=False)
                if info:
                    return info, False
        except Exception:
            pass

    return None, False

def process_instagram_post(
    info: dict,
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
    """Process an Instagram post/item (video or photo carousel folder)."""
    post_id = info.get("id") or str(int(time.time()))
    uploader = sanitize_filename(info.get("channel") or info.get("uploader") or "instagram_user")
    title = sanitize_filename(info.get("title") or "")
    caption = info.get("description") or ""

    if is_archived(archive_set, post_id, "instagram", output_dir=output_dir):
        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (Instagram ID: {post_id})[/bold blue]")
        remove_from_failed_urls(output_dir, post_id)
        return RESULT_SKIPPED

    entries = info.get("entries")
    prog_cb = (ydl.params.get("progress_hooks") or [None])[0]

    if entries:
        entries_list = [e for e in entries if e]

        # Extract audio from carousel video entries.
        if mode == "audio":
            video_entries = [e for e in entries_list if has_instagram_video(e)]
            if not video_entries:
                console.print("[bold yellow]  [!] Instagram post is a photo-only carousel (no audio stream found).[/bold yellow]")
                return RESULT_FAILED
            for idx, entry in enumerate(video_entries, 1):
                audio_file = os.path.join(output_dir, f"instagram_{uploader}_{post_id}_audio_{idx:02d}.%(ext)s")
                sub_opts = dict(ydl.params)
                sub_opts.pop("cookiesfrombrowser", None)
                if ydl.cookiejar:
                    sub_opts["cookiejar"] = ydl.cookiejar
                fmt_str, pps = get_ydl_format(mode="audio", audio_format=audio_format, audio_quality=audio_quality)
                sub_opts["format"] = fmt_str
                sub_opts["postprocessors"] = pps
                sub_opts["outtmpl"] = audio_file
                with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                    sub_ydl.process_ie_result(entry, download=True)
            if check_disk_presence(output_dir, post_id):
                add_to_archive(archive_path, post_id, "instagram")
                archive_set.add(f"instagram {post_id}")
                return RESULT_DOWNLOADED
            return RESULT_FAILED

        folder_name = sanitize_filename(f"{uploader}_{post_id}_photos")
        post_folder = os.path.join(output_dir, folder_name)
        os.makedirs(post_folder, exist_ok=True)

        console.print(f"[bold blue]  [FOLDER] Detected Instagram photo carousel ({len(entries_list)} items). Folder: {folder_name}/[/bold blue]")

        if caption.strip():
            try:
                with open(os.path.join(post_folder, "caption.txt"), "w", encoding="utf-8") as f:
                    f.write(caption)
            except Exception:
                pass

        saved_count = 0
        for idx, entry in enumerate(entries_list, 1):
            entry_id = entry.get("id") or f"{post_id}_{idx}"
            if has_instagram_video(entry):
                console.print(f"    [>] [{idx}/{len(entries_list)}] Downloading video in album (with merged audio)...")
                video_outtmpl = os.path.join(post_folder, f"{idx:02d}_{entry_id}.%(ext)s")
                sub_opts = dict(ydl.params)
                sub_opts.pop("cookiesfrombrowser", None)
                if ydl.cookiejar:
                    sub_opts["cookiejar"] = ydl.cookiejar
                fmt_str, pps = get_ydl_format(mode="video", video_quality=video_quality)
                sub_opts["format"] = fmt_str
                if pps:
                    sub_opts["postprocessors"] = pps
                sub_opts["outtmpl"] = video_outtmpl
                sub_opts["ignoreerrors"] = True
                with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                    sub_ydl.process_ie_result(entry, download=True)
                saved_count += 1
            else:
                img_url = get_instagram_best_image_url(entry)
                if img_url:
                    img_path = os.path.join(post_folder, f"{idx:02d}_{entry_id}.jpg")
                    console.print(f"    [>] [{idx}/{len(entries_list)}] Downloading photo {idx:02d}.jpg (max resolution)...")
                    if download_file(img_url, img_path, session, progress_callback=prog_cb):
                        saved_count += 1

        if saved_count > 0 and (check_disk_presence(output_dir, post_id) or check_disk_presence(post_folder, post_id) or any(os.scandir(post_folder))):
            add_to_archive(archive_path, post_id, "instagram")
            archive_set.add(f"instagram {post_id}")
            remove_from_failed_urls(output_dir, post_id)
            console.print(f"[bold green]  [OK] All carousel items saved in: {folder_name}/[/bold green]")
            return RESULT_DOWNLOADED
        else:
            console.print(f"[bold red]  [-] Carousel download incomplete or empty (ID: {post_id})[/bold red]")
            return RESULT_FAILED

    elif not has_instagram_video(info):
        if mode == "audio":
            console.print("[bold yellow]  [!] Instagram post is a photo only (no audio stream available).[/bold yellow]")
            return RESULT_FAILED

        img_url = get_instagram_best_image_url(info)
        if img_url:
            folder_name = sanitize_filename(f"{uploader}_{post_id}_photos")
            post_folder = os.path.join(output_dir, folder_name)
            os.makedirs(post_folder, exist_ok=True)

            console.print(f"[bold blue]  [FOLDER] Instagram single photo. Creating folder: {folder_name}/[/bold blue]")

            if caption.strip():
                try:
                    with open(os.path.join(post_folder, "caption.txt"), "w", encoding="utf-8") as f:
                        f.write(caption)
                except Exception:
                    pass

            img_path = os.path.join(post_folder, f"01_{post_id}.jpg")
            if download_file(img_url, img_path, session, progress_callback=prog_cb) and (check_disk_presence(output_dir, post_id) or check_disk_presence(post_folder, post_id)):
                add_to_archive(archive_path, post_id, "instagram")
                archive_set.add(f"instagram {post_id}")
                remove_from_failed_urls(output_dir, post_id)
                console.print(f"[bold green]  [OK] Photo saved successfully in: {folder_name}/[/bold green]")
                return RESULT_DOWNLOADED
        return RESULT_FAILED

    else:
        embed_meta = ydl.params.get("_embed_metadata", True)
        clean_title = sanitize_filename(title, max_len=140) if title else post_id
        if mode == "audio":
            console.print(f"[bold magenta]  [AUDIO] Extracting Instagram Reel audio ({audio_format.upper()} @ {audio_quality}k)...[/bold magenta]")
            out_file = os.path.join(output_dir, f"instagram_{uploader}_{post_id}_{clean_title}.%(ext)s")
            fmt_str, pps = get_ydl_format(mode="audio", audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_meta)
        else:
            q_label = f"({video_quality}p with merged audio)" if video_quality and video_quality != "best" else "(with merged audio)"
            console.print(f"[bold green]  [VIDEO] Downloading Instagram Reel {q_label}: {title}[/bold green]")
            out_file = os.path.join(output_dir, f"{uploader}_{post_id}_{clean_title}.%(ext)s")
            fmt_str, pps = get_ydl_format(mode="video", video_quality=video_quality, embed_metadata=embed_meta)

        sub_opts = dict(ydl.params)
        sub_opts.pop("cookiesfrombrowser", None)
        if ydl.cookiejar:
            sub_opts["cookiejar"] = ydl.cookiejar
        sub_opts["format"] = fmt_str
        if pps:
            sub_opts["postprocessors"] = pps
        else:
            sub_opts.pop("postprocessors", None)
        if embed_meta:
            sub_opts["writethumbnail"] = True
        sub_opts["outtmpl"] = out_file

        try:
            with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
                sub_ydl.process_ie_result(info, download=True)
        except Exception as e:
            console.print(f"[dim]  [!] Primary download attempt: {e}[/dim]")

        # Retry anonymously if authenticated fetch fails.
        if not check_disk_presence(output_dir, post_id) and (sub_opts.get("cookiejar") or sub_opts.get("cookiefile")):
            console.print("[yellow]  [!] Download failed with cookies (HTTP 403 or stream error). Retrying anonymously...[/yellow]")
            anon_opts = dict(sub_opts)
            anon_opts.pop("cookiejar", None)
            anon_opts.pop("cookiefile", None)
            try:
                with yt_dlp.YoutubeDL(anon_opts) as anon_ydl:
                    anon_ie = yt_dlp.extractor.get_info_extractor("Instagram")(anon_ydl)
                    web_url = info.get("webpage_url") or f"https://www.instagram.com/p/{post_id}/"
                    anon_info = None
                    if anon_ie.suitable(web_url):
                        try:
                            anon_info = anon_ie._real_extract(web_url)
                        except Exception:
                            anon_info = None
                    if not anon_info:
                        anon_info = anon_ydl.extract_info(web_url, download=False)
                    if anon_info:
                        anon_ydl.process_ie_result(anon_info, download=True)
                    else:
                        anon_ydl.process_ie_result(info, download=True)
            except Exception as anon_err:
                console.print(f"[dim]  [!] Anonymous retry note: {anon_err}[/dim]")

        if check_disk_presence(output_dir, post_id):
            if mode == "audio" and embed_meta:
                media_f = find_downloaded_media_file(output_dir, post_id)
                if media_f:
                    tag_audio_metadata(
                        media_f,
                        title=title or f"Instagram Post {post_id}",
                        artist=uploader,
                        album=f"{uploader} - Instagram",
                        cover_url=info.get("thumbnail") if info else None
                    )
            add_to_archive(archive_path, post_id, "instagram")
            archive_set.add(f"instagram {post_id}")
            remove_from_failed_urls(output_dir, post_id)
            return RESULT_DOWNLOADED
        else:
            console.print(f"[bold red]  [-] Reel download failed or empty file (ID: {post_id})[/bold red]")
            return RESULT_FAILED

def download_instagram_stories_or_highlights(
    user_or_url: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    cookie_file: str = None,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    embed_metadata: bool = None,
    kind: str = "stories",
):
    """Download Instagram stories or highlights."""
    from features.downloader import download_urls
    cookie_path = get_effective_instagram_cookie_file(cookie_file) or prepare_cookies(cookie_file, save_profile=False)
    if not cookie_path or not os.path.isfile(cookie_path):
        console.print("[bold yellow][!] Instagram Stories & Highlights require an authenticated session.[/bold yellow]")
        raw_c = ask_input("[bold cyan]Please paste your Instagram sessionid directly[/bold cyan]")
        if not raw_c:
            console.print("[bold red][-] No cookie provided. Aborting Stories/Highlights download.[/bold red]")
            return
        cookie_path = prepare_cookies(raw_c)

    target = user_or_url.strip()
    if target.startswith("http"):
        story_url = target
        m_u = re.search(r"instagram\.com/(?:stories/)?([^/?#]+)", target)
        sub_name = m_u.group(1) if m_u else "stories"
    else:
        clean_user = target.lstrip("@").strip()
        sub_name = clean_user
        if kind == "highlights":
            hl_id = ask_input("[bold cyan]Enter Highlight ID or full Highlight URL (https://www.instagram.com/stories/highlights/...)[/bold cyan]")
            if not hl_id:
                return
            if hl_id.strip().startswith("http"):
                story_url = hl_id.strip()
            else:
                story_url = f"https://www.instagram.com/stories/highlights/{hl_id.strip().strip('/')}/"
        else:
            story_url = f"https://www.instagram.com/stories/{clean_user}/"

    target_dir = os.path.join(output_dir, f"instagram_{sub_name}_{kind}")
    os.makedirs(target_dir, exist_ok=True)
    console.print(f"[bold cyan][*] Fetching Instagram {kind.capitalize()}: {story_url}[/bold cyan]")
    download_urls(
        [story_url],
        output_dir=target_dir,
        cookie_file=cookie_path,
        mode=mode,
        video_quality=video_quality,
        audio_format=audio_format,
        audio_quality=audio_quality,
        delay=delay,
        embed_metadata=embed_metadata,
        is_bulk=True,
    )

def fetch_instagram_saved_posts_urls(session: requests.Session) -> list[str]:
    """Fetch all saved post URLs directly from Instagram's official Web Feed API."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "X-IG-App-ID": "936619743392459",
        "Referer": "https://www.instagram.com/",
    }

    saved_urls = []
    seen_codes = set()
    next_max_id = None
    page = 1

    console.print("[bold cyan][*] Fetching saved posts list from your Instagram account...[/bold cyan]")

    while True:
        url = "https://www.instagram.com/api/v1/feed/saved/posts/"
        params = {}
        if next_max_id:
            params["max_id"] = next_max_id

        try:
            resp = session.get(url, headers=headers, params=params, timeout=25)
            if resp.status_code != 200:
                console.print(f"[bold yellow][!] Warning: Received HTTP {resp.status_code} from Instagram saved API.[/bold yellow]")
                break

            data = resp.json()
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                media = item.get("media", item)
                code = media.get("code")
                if code and code not in seen_codes:
                    seen_codes.add(code)
                    post_url = f"https://www.instagram.com/p/{code}/"
                    saved_urls.append(post_url)

            console.print(f"  [bold green][OK] Page {page}:[/bold green] Found {len(saved_urls)} saved posts so far...", end="\r")

            if not data.get("more_available"):
                break

            next_max_id = data.get("next_max_id")
            if not next_max_id:
                break

            page += 1
            time.sleep(1.0)

        except Exception as e:
            console.print(f"[bold red][-] Error during saved posts pagination:[/bold red] {e}")
            break

    console.print(f"[bold green][OK] Total saved posts discovered: {len(saved_urls)}[/bold green]")
    return saved_urls

def download_instagram_saved_posts(
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
    proxy: str = None
):
    """Download all SAVED posts / reels from your authenticated Instagram account."""
    from features.downloader import download_urls
    cookie_path = get_effective_instagram_cookie_file(cookie_file) or prepare_cookies(cookie_file, save_profile=False)
    if not cookie_path or not os.path.isfile(cookie_path):
        console.print("[bold red][-] Error: A valid cookies file or sessionid is required to access saved posts.[/bold red]")
        return

    cj = load_cookie_jar(cookie_path)
    if not cj:
        console.print("[bold red][-] Error: Failed to parse cookies for saved posts.[/bold red]")
        return

    session = requests.Session()
    session.cookies.update(cj)
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}

    saved_urls = fetch_instagram_saved_posts_urls(session)
    if not saved_urls:
        console.print("[bold yellow][!] No saved posts found or session may be invalid.[/bold yellow]")
        return

    target_dir = resolve_collection_target_dir(output_dir, DEFAULT_INSTAGRAM_SAVED_DIR)
    pending_urls = run_collection_inventory(
        urls=saved_urls,
        target_dir=target_dir,
        platform_id="instagram",
        list_filename="saved_posts_urls.txt",
        inventory_title="Account Saved Posts Status",
        total_label="Total on Instagram Account:",
        all_done_msg="All saved posts are already downloaded and physically verified on disk!",
    )
    if not pending_urls:
        return

    already_on_disk = len(saved_urls) - len(pending_urls)
    download_urls(
        pending_urls, output_dir=target_dir, cookie_file=cookie_path,
        mode=mode, video_quality=video_quality,
        audio_format=audio_format, audio_quality=audio_quality,
        delay=delay,
        use_aria2=use_aria2, normalize=normalize,
        transcode=transcode, proxy=proxy,
        is_bulk=True, initial_skipped=already_on_disk
    )

def parse_instagram_reposts_json(json_input: str) -> list[str]:
    """Parse Instagram reposts archive file."""
    content = ""
    if os.path.isfile(json_input.strip()):
        with open(json_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    else:
        content = json_input.strip()

    if not content:
        console.print("[bold red][-] Empty or missing Instagram data export file.[/bold red]")
        return []

    urls = []
    seen = set()

    def _add_url(u: str):
        if not u:
            return
        m = re.search(r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)", u)
        if m:
            code = m.group(1)
            clean_url = f"https://www.instagram.com/p/{code}/"
            if clean_url not in seen:
                seen.add(clean_url)
                urls.append(clean_url)

    try:
        data = json.loads(content)
        def _walk(node):
            if isinstance(node, dict):
                for k in ("href", "uri", "url", "link"):
                    if k in node and isinstance(node[k], str):
                        _add_url(node[k])
                if "code" in node and isinstance(node["code"], str):
                    clean_url = f"https://www.instagram.com/p/{node['code']}/"
                    if clean_url not in seen:
                        seen.add(clean_url)
                        urls.append(clean_url)
                if "shortcode" in node and isinstance(node["shortcode"], str):
                    clean_url = f"https://www.instagram.com/p/{node['shortcode']}/"
                    if clean_url not in seen:
                        seen.add(clean_url)
                        urls.append(clean_url)
                for v in node.values():
                    _walk(v)
            elif isinstance(node, list):
                for elem in node:
                    _walk(elem)

        _walk(data)
    except Exception:
        pass

    if not urls:
        found_codes = re.findall(r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)", content)
        for code in found_codes:
            clean_url = f"https://www.instagram.com/p/{code}/"
            if clean_url not in seen:
                seen.add(clean_url)
                urls.append(clean_url)

    if urls:
        console.print(f"[bold green][OK][/bold green] Extracted {len(urls)} Instagram repost URLs from archive data.")
    else:
        console.print("[bold yellow][!] No reposted post or reel URLs found in provided Instagram file.[/bold yellow]")

    return urls

def fetch_instagram_reposted_posts_urls(session: requests.Session) -> list[str]:
    """Fetch all reposted post and reel URLs for the authenticated Instagram account."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
    }
    csrf_token = session.cookies.get("csrftoken")
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token

    user_id = session.cookies.get("ds_user_id")
    if not user_id:
        try:
            acc_resp = session.get("https://www.instagram.com/api/v1/accounts/current_user/", headers=headers, timeout=12)
            if acc_resp.status_code == 200:
                user_id = acc_resp.json().get("user", {}).get("pk")
        except Exception:
            pass

    if not user_id:
        console.print("[bold yellow][!] Could not determine Instagram user ID from cookies for reposted posts.[/bold yellow]")
        return []

    console.print("[bold cyan][*] Fetching reposted posts & reels from your Instagram account...[/bold cyan]")
    reposted_urls = []
    seen_codes = set()

    candidate_endpoints = [
        f"https://www.instagram.com/api/v1/feed/user/{user_id}/reposts/",
        f"https://www.instagram.com/api/v1/clips/user/{user_id}/reposts/",
        "https://www.instagram.com/api/v1/feed/reposts_feed/",
    ]

    for endpoint in candidate_endpoints:
        next_max_id = None
        page = 1
        while True:
            params = {}
            if next_max_id:
                params["max_id"] = next_max_id

            try:
                resp = session.get(endpoint, headers=headers, params=params, timeout=25)
                if resp.status_code != 200:
                    break
                data = resp.json()
                items = (
                    data.get("items")
                    or data.get("media_or_ad")
                    or data.get("reposted_media")
                    or data.get("reposts")
                    or []
                )
                if not items and "data" in data and isinstance(data["data"], dict):
                    items = data["data"].get("items") or data["data"].get("user", {}).get("edge_user_reposts", {}).get("edges", [])
                if not items:
                    break

                for item in items:
                    node = item.get("node") if isinstance(item, dict) and "node" in item else item
                    media = node.get("media") or node.get("reposted_media") or node
                    code = media.get("code") or media.get("shortcode")
                    if code and code not in seen_codes:
                        seen_codes.add(code)
                        reposted_urls.append(f"https://www.instagram.com/p/{code}/")

                console.print(f"  [bold green][OK] Reposts Page {page}:[/bold green] Found {len(reposted_urls)} reposted posts so far...", end="\r")

                if not data.get("more_available") and not data.get("has_more"):
                    break
                next_max_id = data.get("next_max_id") or data.get("max_id") or data.get("paging_token")
                if not next_max_id:
                    break
                page += 1
                time.sleep(1.0)
            except Exception:
                break
        if reposted_urls:
            break

    console.print(f"[bold green][OK] Total Instagram reposted posts discovered: {len(reposted_urls)}[/bold green]")
    return reposted_urls

def download_instagram_reposted_posts(
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
    custom_urls: list[str] = None,
):
    """Download Instagram reposted posts."""
    from features.downloader import download_urls
    target_dir = resolve_collection_target_dir(output_dir, DEFAULT_INSTAGRAM_REPOSTS_DIR)

    reposted_urls = []
    cookie_path = None

    if custom_urls:
        reposted_urls = custom_urls
    else:
        cookie_path = get_effective_instagram_cookie_file(cookie_file)
        if not cookie_path or not os.path.isfile(cookie_path):
            console.print("[bold yellow][!] Downloading Instagram Reposts requires authentication.[/bold yellow]")
            raw_c = ask_input("[bold cyan]Please paste your Instagram sessionid directly[/bold cyan]")
            if not raw_c:
                console.print("[bold red][-] No cookie provided. Aborting.[/bold red]")
                return
            cookie_path = prepare_cookies(raw_c)

        if not cookie_path or not os.path.isfile(cookie_path):
            console.print("[bold red][-] Error: Could not prepare valid Instagram cookies.[/bold red]")
            return

        cj = load_cookie_jar(cookie_path)
        if not cj:
            console.print("[bold red][-] Error: Failed to parse Instagram cookies.[/bold red]")
            return

        session = requests.Session()
        session.cookies.update(cj)
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}

        reposted_urls = fetch_instagram_reposted_posts_urls(session)
        if not reposted_urls:
            console.print("[bold yellow][!] No reposted posts retrieved via API or session expired.[/bold yellow]")
            console.print("[dim]Note: You can also provide your Instagram data export file (e.g. reposts.json).[/dim]")
            arch_input = ask_input("[bold cyan]Enter path to Instagram reposts.json file (or press Enter to cancel)[/bold cyan]")
            if arch_input and os.path.isfile(arch_input.strip()):
                reposted_urls = parse_instagram_reposts_json(arch_input.strip())
            if not reposted_urls:
                return

    pending_urls = run_collection_inventory(
        urls=reposted_urls,
        target_dir=target_dir,
        platform_id="instagram",
        list_filename="reposted_instagram_urls.txt",
        inventory_title="Instagram Reposted Posts & Reels Status",
        total_label="Total Reposts on Account:",
        all_done_msg="All Instagram reposts are already downloaded and physically verified on disk!",
    )
    if not pending_urls:
        return

    effective_cookie = cookie_path if not custom_urls else (get_effective_instagram_cookie_file(cookie_file) or cookie_file)
    already_on_disk = len(reposted_urls) - len(pending_urls)
    download_urls(
        pending_urls,
        output_dir=target_dir,
        cookie_file=effective_cookie,
        mode=mode,
        video_quality=video_quality,
        audio_format=audio_format,
        audio_quality=audio_quality,
        delay=delay,
        use_aria2=use_aria2,
        normalize=normalize,
        transcode=transcode,
        proxy=proxy,
        is_bulk=True,
        initial_skipped=already_on_disk
    )
