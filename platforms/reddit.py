"""Reddit media extractor."""
import html
import json
import os
import re
import time
from datetime import datetime

import requests
import yt_dlp

from core.archive import (
    DEFAULT_OUTPUT_DIR,
    HISTORY_FILE,
    RESULT_DOWNLOADED,
    RESULT_FAILED,
    RESULT_SKIPPED,
    add_to_archive,
    check_disk_presence,
    download_file,
    extract_url_item_id,
    get_archive_set,
    is_archived,
    resolve_archive_policy,
    sanitize_filename,
)
from core.cookies import get_effective_reddit_cookie_file, load_cookie_jar
from core.ytdl_format import (
    get_ydl_format,
)
from ui.components import (
    ask_input,
)
from ui.dashboard import (
    check_cancel_requested,
    interruptible_sleep,
)
from ui.theme import (
    FFMPEG_EXE,
    console,
    print_summary_table,
)


def download_reddit_gallery(
    post_data: dict,
    output_dir: str,
    session: requests.Session,
    archive_path: str = None,
    archive_set: set = None
) -> str:
    """Download Reddit photo gallery."""
    post_id = post_data.get("id")
    subreddit = post_data.get("subreddit") or "reddit"
    author = post_data.get("author") or "user"
    title = post_data.get("title") or "Reddit Gallery"

    folder_name = sanitize_filename(f"reddit_{subreddit}_{post_id}_gallery")
    gallery_dir = os.path.join(output_dir, folder_name)
    os.makedirs(gallery_dir, exist_ok=True)

    media_meta = post_data.get("media_metadata") or {}
    gallery_items = post_data.get("gallery_data", {}).get("items") or []

    ordered_media_ids = []
    if gallery_items:
        ordered_media_ids = [it.get("media_id") for it in gallery_items if it.get("media_id")]
    if not ordered_media_ids:
        ordered_media_ids = list(media_meta.keys())

    console.print(f"[bold blue]  [FOLDER] Detected Reddit photo gallery ({len(ordered_media_ids)} items). Folder: {folder_name}/[/bold blue]")

    meta_info = {
        "id": post_id,
        "title": title,
        "author": author,
        "subreddit": subreddit,
        "permalink": post_data.get("permalink", ""),
        "created_utc": post_data.get("created_utc", 0),
        "score": post_data.get("score", 0),
        "upvote_ratio": post_data.get("upvote_ratio", 0.0),
        "item_count": len(ordered_media_ids),
    }
    try:
        with open(os.path.join(gallery_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta_info, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    saved_count = 0
    for idx, mid in enumerate(ordered_media_ids, 1):
        m_info = media_meta.get(mid, {})
        img_url = None
        s_dict = m_info.get("s", {})
        if s_dict.get("u"):
            img_url = html.unescape(s_dict["u"])
        elif s_dict.get("gif"):
            img_url = html.unescape(s_dict["gif"])
        elif m_info.get("m"):
            ext_val = "png" if "png" in m_info.get("m", "") else "jpg"
            img_url = f"https://i.redd.it/{mid}.{ext_val}"

        if not img_url:
            continue

        ext = "jpg"
        if ".png" in img_url.lower():
            ext = "png"
        elif ".gif" in img_url.lower():
            ext = "gif"
        elif ".webp" in img_url.lower():
            ext = "webp"

        img_filename = f"{idx:02d}_{mid}.{ext}"
        save_path = os.path.join(gallery_dir, img_filename)
        console.print(f"    [>] [{idx}/{len(ordered_media_ids)}] Downloading gallery image {img_filename}...")
        if download_file(img_url, save_path, session):
            saved_count += 1

    if saved_count > 0:
        if post_id and archive_path:
            add_to_archive(archive_path, post_id, "reddit")
            if archive_set is not None:
                archive_set.add(f"reddit {post_id}")
        console.print(f"[bold green]  [OK] All gallery images saved in: {folder_name}/[/bold green]")
        return RESULT_DOWNLOADED
    else:
        console.print(f"[bold red]  [-] Reddit gallery download failed or empty (ID: {post_id})[/bold red]")
        return RESULT_FAILED

def process_reddit_post(
    url_or_data: str | dict,
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
    """Download Reddit post media."""
    post_data = None
    url = ""
    post_id = None
    if isinstance(url_or_data, dict):
        post_data = url_or_data
        url = post_data.get("url") or post_data.get("permalink", "")
        post_id = post_data.get("id")
    else:
        url = str(url_or_data).strip()
        _, post_id = extract_url_item_id(url)

    if post_id and is_archived(archive_set, post_id, "reddit", output_dir=output_dir, mode=mode):
        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (Reddit ID: {post_id})[/bold blue]")
        return RESULT_SKIPPED

    if not post_data:
        json_url = url
        if not json_url.endswith(".json"):
            json_url = json_url.split("?")[0].rstrip("/") + "/.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        try:
            resp = session.get(json_url, headers=headers, timeout=12)
            if resp.status_code == 200:
                raw_json = resp.json()
                if isinstance(raw_json, list) and len(raw_json) > 0:
                    children = raw_json[0].get("data", {}).get("children", [])
                    if children:
                        post_data = children[0].get("data", {})
                        if not post_id:
                            post_id = post_data.get("id")
        except Exception:
            pass

    if post_data and (post_data.get("is_gallery") or post_data.get("media_metadata")):
        return download_reddit_gallery(post_data, output_dir, session, archive_path, archive_set)

    target_media_url = (post_data.get("url_overridden_by_dest") or post_data.get("url")) if post_data else url
    is_img = any(target_media_url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")) or "i.redd.it" in target_media_url

    if is_img and post_data and not post_data.get("is_video"):
        subreddit = post_data.get("subreddit") or "reddit"
        title = post_data.get("title") or "image"
        author = post_data.get("author") or "user"
        ext = target_media_url.split(".")[-1].split("?")[0]
        if len(ext) > 4 or not ext:
            ext = "jpg"
        clean_title = sanitize_filename(title, max_len=140)
        filename = sanitize_filename(f"reddit_{subreddit}_{post_id or 'img'}_{clean_title}.{ext}", max_len=180)
        save_path = os.path.join(output_dir, filename)
        console.print(f"[bold cyan]  [PHOTO] Downloading Reddit photo: {filename}...[/bold cyan]")
        if download_file(target_media_url, save_path, session):
            meta_path = os.path.join(output_dir, sanitize_filename(f"reddit_{subreddit}_{post_id or 'img'}_metadata.json"))
            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "id": post_id,
                        "title": title,
                        "author": author,
                        "subreddit": subreddit,
                        "permalink": post_data.get("permalink", ""),
                        "created_utc": post_data.get("created_utc", 0),
                        "score": post_data.get("score", 0),
                        "source_url": target_media_url,
                    }, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            if post_id:
                add_to_archive(archive_path, post_id, "reddit")
                archive_set.add(f"reddit {post_id}")
            return RESULT_DOWNLOADED
        return RESULT_FAILED

    sub_opts = dict(ydl.params)
    sub_opts.pop("cookiesfrombrowser", None)
    if ydl.cookiejar:
        sub_opts["cookiejar"] = ydl.cookiejar

    embed_meta = ydl.params.get("_embed_metadata", True)
    if mode == "audio":
        fmt_str, pps = get_ydl_format(mode="audio", audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_meta)
        sub_opts["format"] = fmt_str
        sub_opts["postprocessors"] = pps
        if embed_meta:
            sub_opts["writethumbnail"] = True
        sub_opts["outtmpl"] = os.path.join(output_dir, f"reddit_%(subreddit,uploader)s_{post_id or '%(id)s'}_%(title)s.%(ext)s")
        console.print(f"[bold magenta]  [AUDIO] Downloading Reddit audio ({audio_format.upper()} @ {audio_quality}k)...[/bold magenta]")
    else:
        fmt_str, pps = get_ydl_format(mode="video", video_quality=video_quality, embed_metadata=embed_meta)
        sub_opts["format"] = fmt_str
        if pps:
            sub_opts["postprocessors"] = pps
        if embed_meta:
            sub_opts["writethumbnail"] = True
        sub_opts["outtmpl"] = os.path.join(output_dir, f"reddit_%(subreddit,uploader)s_{post_id or '%(id)s'}_%(title)s.%(ext)s")
        q_label = f"({video_quality}p)" if video_quality and video_quality != "best" else "(best available)"
        console.print(f"[bold green]  [VIDEO] Downloading Reddit video {q_label} (with merged audio)...[/bold green]")

    try:
        with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
            ret = sub_ydl.download([url])
            if ret == 0 or (post_id and check_disk_presence(output_dir, post_id)):
                if post_id:
                    add_to_archive(archive_path, post_id, "reddit")
                    archive_set.add(f"reddit {post_id}")
                return RESULT_DOWNLOADED
            return RESULT_FAILED
    except Exception as e:
        console.print(f"[bold red]  [-] Reddit download error: {e}[/bold red]")
        return RESULT_FAILED

def fetch_reddit_feed_posts(
    target: str,
    sort: str = "hot",
    timeframe: str = "all",
    limit: int = 50,
    cookie_file: str = None
) -> list[dict]:
    """Fetch posts from subreddit feed."""
    clean_target = target.strip()
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    if cookie_file and os.path.isfile(cookie_file):
        cj = load_cookie_jar(cookie_file)
        if cj:
            session.cookies.update(cj)

    current_username = None
    if clean_target in ("saved", "upvoted", "user/saved", "user/upvoted"):
        try:
            me_resp = session.get("https://old.reddit.com/api/me.json", headers=headers, timeout=8)
            if me_resp.status_code == 200:
                current_username = me_resp.json().get("data", {}).get("name")
        except Exception:
            pass
        if not current_username:
            current_username = ask_input("[bold cyan]Enter your Reddit username[/bold cyan]")
            if not current_username:
                console.print("[bold red][-] Reddit username required for saved/upvoted posts.[/bold red]")
                return []

    if clean_target in ("saved", "user/saved"):
        base_url = f"https://old.reddit.com/user/{current_username}/saved.json"
    elif clean_target in ("upvoted", "user/upvoted"):
        base_url = f"https://old.reddit.com/user/{current_username}/upvoted.json"
    elif clean_target.startswith("u/") or clean_target.startswith("user/") or "reddit.com/user/" in clean_target:
        u_name = re.sub(r"^(?:https?://[^/]+/)?(?:u|user)/", "", clean_target).strip("/")
        base_url = f"https://old.reddit.com/user/{u_name}/submitted.json?sort={sort}&t={timeframe}"
    else:
        sub_name = re.sub(r"^(?:https?://[^/]+/)?(?:r/)?", "", clean_target).strip("/")
        base_url = f"https://old.reddit.com/r/{sub_name}/{sort}.json?t={timeframe}"

    collected_posts = []
    after_token = None
    max_to_fetch = limit if limit and limit > 0 else 50

    with console.status(f"[bold cyan][*] Querying Reddit API for {clean_target}...[/bold cyan]"):
        while len(collected_posts) < max_to_fetch:
            sep = "&" if "?" in base_url else "?"
            fetch_url = f"{base_url}{sep}limit={min(100, max_to_fetch - len(collected_posts))}"
            if after_token:
                fetch_url += f"&after={after_token}"

            try:
                resp = session.get(fetch_url, headers=headers, timeout=12)
                if resp.status_code != 200:
                    if resp.status_code == 403:
                        console.print("[bold red][!] Reddit blocked anonymous access (HTTP 403). Account cookies are required. Please configure Reddit cookies via settings or --reddit-cookies.[/bold red]")
                    else:
                        console.print(f"[bold red][-] Reddit API error: HTTP {resp.status_code}[/bold red]")
                    break
                data = resp.json()
                children = data.get("data", {}).get("children", [])
                if not children:
                    break

                for child in children:
                    p = child.get("data", {})
                    post_id = p.get("id")
                    if not post_id:
                        continue
                    post_dict = {
                        "id": post_id,
                        "title": p.get("title") or "Untitled Reddit Post",
                        "author": p.get("author") or "unknown",
                        "subreddit": p.get("subreddit") or "",
                        "url": p.get("url") or (f"https://www.reddit.com{p.get('permalink')}" if p.get("permalink") else ""),
                        "permalink": f"https://www.reddit.com{p.get('permalink')}" if p.get("permalink") else "",
                        "is_video": bool(p.get("is_video")),
                        "is_gallery": bool(p.get("is_gallery") or p.get("media_metadata")),
                        "media_metadata": p.get("media_metadata"),
                        "gallery_data": p.get("gallery_data"),
                        "post_hint": p.get("post_hint", ""),
                        "created_utc": p.get("created_utc", 0),
                        "score": p.get("score", 0),
                        "upvote_ratio": p.get("upvote_ratio", 0.0),
                        "domain": p.get("domain", ""),
                        "over_18": p.get("over_18", False),
                        "duration": p.get("media", {}).get("reddit_video", {}).get("duration") if p.get("media") else None,
                    }
                    collected_posts.append(post_dict)
                    if len(collected_posts) >= max_to_fetch:
                        break

                after_token = data.get("data", {}).get("after")
                if not after_token:
                    break
            except Exception as e:
                console.print(f"[bold red][-] Error querying Reddit API: {e}[/bold red]")
                break

    return collected_posts

def download_reddit_feed(
    target: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    sort: str = "hot",
    timeframe: str = "all",
    limit: int = 50,
    cookie_file: str = None,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    smart_filters: dict = None,
    embed_metadata: bool = None
):
    """Download posts from subreddit feed."""
    cookie_file = get_effective_reddit_cookie_file(cookie_file)
    max_count = limit
    if smart_filters and smart_filters.get("count_limit"):
        max_count = smart_filters["count_limit"]

    posts = fetch_reddit_feed_posts(target, sort=sort, timeframe=timeframe, limit=max_count, cookie_file=cookie_file)
    if not posts:
        console.print("[bold yellow][!] No posts found to download.[/bold yellow]")
        return

    console.print(f"[bold green][OK] Found {len(posts)} Reddit posts in feed.[/bold green]")

    filtered_posts = []
    for p in posts:
        if smart_filters:
            if smart_filters.get("date_after"):
                d_after = smart_filters["date_after"]
                try:
                    cutoff_ts = int(time.mktime(datetime.strptime(d_after, "%Y%m%d").timetuple()))
                    if p.get("created_utc", 0) < cutoff_ts:
                        continue
                except Exception:
                    pass
            if smart_filters.get("shorts_only") or smart_filters.get("max_duration"):
                max_sec = 60 if smart_filters.get("shorts_only") else smart_filters.get("max_duration")
                if p.get("duration") and p.get("duration") > max_sec:
                    continue
        filtered_posts.append(p)

    console.print(f"[bold cyan][*] Starting download for {len(filtered_posts)} Reddit items...[/bold cyan]")

    use_archive = resolve_archive_policy(is_bulk=True)
    archive_path = os.path.join(output_dir, HISTORY_FILE)
    if use_archive:
        archive_set = get_archive_set(archive_path)
    else:
        archive_set = set()

    session = requests.Session()
    if cookie_file and os.path.isfile(cookie_file):
        cj = load_cookie_jar(cookie_file)
        if cj:
            session.cookies.update(cj)

    fmt_str, pps = get_ydl_format(mode=mode, video_quality=video_quality, audio_format=audio_format, audio_quality=audio_quality, embed_metadata=embed_metadata)
    ydl_opts = {
        "format": fmt_str,
        "merge_output_format": "mp4",
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
    }
    if pps:
        ydl_opts["postprocessors"] = pps
    if FFMPEG_EXE:
        ydl_opts["ffmpeg_location"] = FFMPEG_EXE
    if cookie_file and os.path.isfile(cookie_file):
        ydl_opts["cookiefile"] = cookie_file

    successful, skipped, failed = 0, 0, 0
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for idx, post in enumerate(filtered_posts, 1):
            if check_cancel_requested():
                break
            console.print(f"[bold cyan][{idx}/{len(filtered_posts)}] Processing Reddit Post:[/bold cyan] {post.get('title')}")
            res = process_reddit_post(
                post, output_dir, ydl, session, archive_path, archive_set,
                mode=mode, video_quality=video_quality,
                audio_format=audio_format, audio_quality=audio_quality
            )
            if res == RESULT_DOWNLOADED:
                successful += 1
            elif res == RESULT_SKIPPED:
                skipped += 1
            else:
                failed += 1

            if delay > 0 and idx < len(filtered_posts):
                if interruptible_sleep(delay):
                    break

    print_summary_table(len(filtered_posts), successful, skipped, failed, output_dir)
