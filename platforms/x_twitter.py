"""X (Twitter) media extractor."""
import json
import os
import re

import requests
import yt_dlp

from core.archive import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_X_REPOSTS_DIR,
    DEFAULT_X_SAVED_DIR,
    RESULT_DOWNLOADED,
    RESULT_FAILED,
    RESULT_SKIPPED,
    add_to_archive,
    check_disk_presence,
    extract_url_item_id,
    is_archived,
)
from core.cookies import get_effective_x_cookie_file, load_cookie_jar, prepare_x_cookies
from core.ytdl_format import (
    get_ydl_format,
)
from platforms.base import resolve_collection_target_dir, run_collection_inventory
from ui.components import ask_input
from ui.theme import console


def parse_x_data_archive(archive_input: str, kind: str = "bookmarks") -> list[str]:
    """Parse X data export file."""
    content = ""
    if os.path.isfile(archive_input.strip()):
        with open(archive_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    else:
        content = archive_input.strip()

    if not content:
        console.print("[bold red][-] Empty or missing X archive data.[/bold red]")
        return []

    if "=" in content and (content.strip().startswith("window.") or "YTD" in content):
        try:
            content = content.split("=", 1)[1].strip().rstrip(";")
        except Exception:
            pass

    urls = []
    seen = set()

    try:
        data = json.loads(content)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    sub = item.get("bookmark") or item.get("tweet") or item.get("like") or item
                    tid = sub.get("tweetId") or sub.get("id") or sub.get("id_str")
                    if kind == "reposts":
                        full_txt = str(sub.get("full_text") or "")
                        if not (full_txt.startswith("RT @") or "retweeted_status_result" in sub or "retweeted_status_id" in sub):
                            continue
                    if tid and str(tid) not in seen:
                        seen.add(str(tid))
                        urls.append(f"https://x.com/i/status/{tid}")
    except Exception:
        pass

    if not urls:
        found_links = re.findall(r"https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/[a-zA-Z0-9_]+/status/(\d+)", content)
        for tweet_id in found_links:
            if tweet_id not in seen:
                seen.add(tweet_id)
                urls.append(f"https://x.com/i/status/{tweet_id}")

        if not urls:
            found_ids = re.findall(r'"tweetId"\s*:\s*"(\d+)"', content)
            for tweet_id in found_ids:
                if tweet_id not in seen:
                    seen.add(tweet_id)
                    urls.append(f"https://x.com/i/status/{tweet_id}")

    console.print(f"[bold green][OK] Extracted {len(urls)} X tweet URLs from archive data.[/bold green]")
    return urls

def fetch_x_bookmarks_urls(session: requests.Session) -> list[str]:
    """Fetch saved / bookmarked tweets from X account via API."""
    bearer = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    ct0 = ""
    for c in session.cookies:
        if c.name == "ct0":
            ct0 = c.value
            break

    headers = {
        "authorization": f"Bearer {bearer}",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": "https://x.com/i/bookmarks",
    }
    if ct0:
        headers["x-csrf-token"] = ct0

    console.print("[bold cyan][*] Fetching bookmarks from your X (Twitter) account...[/bold cyan]")
    urls = []
    seen = set()

    features = {
        "graphql_timeline_v2_bookmark_timeline": True,
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "responsive_web_graphql_timeline_navigation_enabled": True
    }
    params = {
        "variables": json.dumps({"count": 50, "includePromotedContent": False}),
        "features": json.dumps(features),
    }

    try:
        resp = session.get(
            "https://x.com/i/api/graphql/s-uc-j1rqjA8i-N2gDsc6g/Bookmarks",
            headers=headers,
            params=params,
            timeout=15
        )
        if resp.status_code == 200:
            txt = resp.text
            matches = re.findall(r'"rest_id"\s*:\s*"(\d+)"', txt)
            for m in matches:
                if m not in seen and len(m) >= 15:
                    seen.add(m)
                    urls.append(f"https://x.com/i/status/{m}")
    except Exception:
        pass

    if not urls:
        try:
            home_resp = session.get("https://x.com/i/bookmarks", headers={"User-Agent": headers["User-Agent"]}, timeout=10)
            if home_resp.status_code == 200:
                matches = re.findall(r"/status/(\d+)", home_resp.text)
                for m in matches:
                    if m not in seen:
                        seen.add(m)
                        urls.append(f"https://x.com/i/status/{m}")
        except Exception:
            pass

    return urls

def fetch_x_reposts_urls(session: requests.Session, username: str = None) -> list[str]:
    """Fetch reposted (retweeted) tweets from authenticated user's profile."""
    bearer = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    ct0 = ""
    for c in session.cookies:
        if c.name == "ct0":
            ct0 = c.value
            break

    headers = {
        "authorization": f"Bearer {bearer}",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }
    if ct0:
        headers["x-csrf-token"] = ct0

    console.print("[bold cyan][*] Fetching reposts from your X (Twitter) account...[/bold cyan]")
    urls = []
    seen = set()

    screen_name = username
    if not screen_name:
        try:
            acc_resp = session.get("https://api.x.com/1.1/account/settings.json", headers=headers, timeout=10)
            if acc_resp.status_code == 200:
                screen_name = acc_resp.json().get("screen_name")
        except Exception:
            pass

    if screen_name:
        try:
            tl_resp = session.get(
                f"https://api.x.com/1.1/statuses/user_timeline.json?screen_name={screen_name}&include_rts=1&count=100",
                headers=headers,
                timeout=15
            )
            if tl_resp.status_code == 200:
                items = tl_resp.json()
                if isinstance(items, list):
                    for it in items:
                        rt = it.get("retweeted_status")
                        if rt:
                            orig_id = str(rt.get("id_str") or rt.get("id"))
                            if orig_id and orig_id not in seen:
                                seen.add(orig_id)
                                urls.append(f"https://x.com/i/status/{orig_id}")
        except Exception:
            pass

    return urls

def fetch_x_profile_tweet_urls(screen_name: str, cookie_file: str = None) -> list[str]:
    """Fetch status URLs from an X user profile."""
    clean_user = screen_name.lstrip("@").strip()
    urls = []
    seen = set()

    session = requests.Session()
    if cookie_file and os.path.isfile(cookie_file):
        cj = load_cookie_jar(cookie_file)
        if cj:
            session.cookies.update(cj)

    bearer = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    ct0 = ""
    for c in session.cookies:
        if c.name == "ct0":
            ct0 = c.value
            break

    headers = {
        "authorization": f"Bearer {bearer}",
        "x-twitter-active-user": "yes",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }
    if ct0:
        headers["x-csrf-token"] = ct0

    try:
        resp = session.get(
            f"https://api.x.com/1.1/statuses/user_timeline.json?screen_name={clean_user}&count=50",
            headers=headers,
            timeout=12
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                for t in data:
                    tid = str(t.get("id_str") or t.get("id") or "")
                    if tid and tid not in seen:
                        seen.add(tid)
                        urls.append(f"https://x.com/{clean_user}/status/{tid}")
    except Exception:
        pass

    return urls

def process_x_post(
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
    """Download X (Twitter) post media."""
    plat, post_id = extract_url_item_id(url)
    if not post_id:
        m = re.search(r"status/(\d+)", url)
        if m:
            post_id = m.group(1)

    if post_id and is_archived(archive_set, post_id, "x", output_dir=output_dir):
        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (X ID: {post_id})[/bold blue]")
        return RESULT_SKIPPED

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
        sub_opts["outtmpl"] = os.path.join(output_dir, f"x_%(uploader)s_{post_id or '%(id)s'}_%(title)s.%(ext)s")
        console.print(f"[bold magenta]  [AUDIO] Downloading X audio ({audio_format.upper()} @ {audio_quality}k)...[/bold magenta]")
    else:
        fmt_str, pps = get_ydl_format(mode="video", video_quality=video_quality, embed_metadata=embed_meta)
        sub_opts["format"] = fmt_str
        if pps:
            sub_opts["postprocessors"] = pps
        if embed_meta:
            sub_opts["writethumbnail"] = True
        sub_opts["outtmpl"] = os.path.join(output_dir, f"x_%(uploader)s_{post_id or '%(id)s'}_%(title)s.%(ext)s")
        q_label = f"({video_quality}p)" if video_quality and video_quality != "best" else "(best available)"
        console.print(f"[bold green]  [VIDEO] Downloading X video {q_label}...[/bold green]")

    try:
        with yt_dlp.YoutubeDL(sub_opts) as sub_ydl:
            ret = sub_ydl.download([url])
            if ret == 0 or (post_id and check_disk_presence(output_dir, post_id)):
                if post_id:
                    add_to_archive(archive_path, post_id, "x")
                    archive_set.add(f"x {post_id}")
                return RESULT_DOWNLOADED
            return RESULT_FAILED
    except Exception as e:
        console.print(f"[bold red]  [-] X download error: {e}[/bold red]")
        return RESULT_FAILED

def download_x_bookmarks(
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
    """Download X bookmarked tweets."""
    from features.downloader import download_urls
    target_dir = resolve_collection_target_dir(output_dir, DEFAULT_X_SAVED_DIR)
    saved_urls = []
    cookie_path = None

    if custom_urls:
        saved_urls = custom_urls
    else:
        cookie_path = get_effective_x_cookie_file(cookie_file)
        if not cookie_path or not os.path.isfile(cookie_path):
            console.print("[bold yellow][!] Downloading X Bookmarks requires X authentication.[/bold yellow]")
            raw_c = ask_input("[bold cyan]Please paste your X auth_token directly[/bold cyan]")
            if not raw_c:
                console.print("[bold red][-] No cookie provided. Aborting.[/bold red]")
                return
            cookie_path = prepare_x_cookies(raw_c)

        if not cookie_path or not os.path.isfile(cookie_path):
            console.print("[bold red][-] Error: Could not prepare valid X cookies.[/bold red]")
            return

        cj = load_cookie_jar(cookie_path)
        if not cj:
            console.print("[bold red][-] Error: Failed to parse X cookies.[/bold red]")
            return

        session = requests.Session()
        session.cookies.update(cj)
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}

        saved_urls = fetch_x_bookmarks_urls(session)
        if not saved_urls:
            console.print("[bold yellow][!] No bookmarks retrieved via API or session expired.[/bold yellow]")
            console.print("[dim]Note: You can also provide your Twitter archive file (e.g. bookmarks.json or data/bookmark.js).[/dim]")
            arch_input = ask_input("[bold cyan]Enter path to Twitter archive file (or press Enter to cancel)[/bold cyan]")
            if arch_input and os.path.isfile(arch_input.strip()):
                saved_urls = parse_x_data_archive(arch_input.strip(), kind="bookmarks")
            if not saved_urls:
                return

    pending_urls = run_collection_inventory(
        urls=saved_urls,
        target_dir=target_dir,
        platform_id="x",
        list_filename="saved_x_urls.txt",
        inventory_title="X (Twitter) Bookmarks Status",
        total_label="Total on X Account:",
        all_done_msg="All X bookmarks are already downloaded and physically verified on disk!",
    )
    if not pending_urls:
        return

    effective_cookie = cookie_path if not custom_urls else (get_effective_x_cookie_file(cookie_file) or cookie_file)
    already_on_disk = len(saved_urls) - len(pending_urls)
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

def download_x_reposts(
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
    """Download X reposted media."""
    from features.downloader import download_urls
    target_dir = resolve_collection_target_dir(output_dir, DEFAULT_X_REPOSTS_DIR)
    repost_urls = []
    cookie_path = None

    if custom_urls:
        repost_urls = custom_urls
    else:
        cookie_path = get_effective_x_cookie_file(cookie_file)
        if not cookie_path or not os.path.isfile(cookie_path):
            console.print("[bold yellow][!] Downloading X Reposts requires X authentication.[/bold yellow]")
            raw_c = ask_input("[bold cyan]Please paste your X auth_token directly[/bold cyan]")
            if not raw_c:
                console.print("[bold red][-] No cookie provided. Aborting.[/bold red]")
                return
            cookie_path = prepare_x_cookies(raw_c)

        if not cookie_path or not os.path.isfile(cookie_path):
            console.print("[bold red][-] Error: Could not prepare valid X cookies.[/bold red]")
            return

        cj = load_cookie_jar(cookie_path)
        if not cj:
            console.print("[bold red][-] Error: Failed to parse X cookies.[/bold red]")
            return

        session = requests.Session()
        session.cookies.update(cj)
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}

        repost_urls = fetch_x_reposts_urls(session)
        if not repost_urls:
            console.print("[bold yellow][!] No reposts retrieved via API or session expired.[/bold yellow]")
            console.print("[dim]Note: You can also provide your Twitter archive file (e.g. tweets.json or data/tweets.js).[/dim]")
            arch_input = ask_input("[bold cyan]Enter path to Twitter archive file (or press Enter to cancel)[/bold cyan]")
            if arch_input and os.path.isfile(arch_input.strip()):
                repost_urls = parse_x_data_archive(arch_input.strip(), kind="reposts")
            if not repost_urls:
                return

    pending_urls = run_collection_inventory(
        urls=repost_urls,
        target_dir=target_dir,
        platform_id="x",
        list_filename="reposts_x_urls.txt",
        inventory_title="X (Twitter) Reposts Status",
        total_label="Total Reposts on Account:",
        all_done_msg="All X reposts are already downloaded and physically verified on disk!",
    )
    if not pending_urls:
        return

    effective_cookie = cookie_path if not custom_urls else (get_effective_x_cookie_file(cookie_file) or cookie_file)
    already_on_disk = len(repost_urls) - len(pending_urls)
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

def download_x_profile(
    user_or_url: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    cookie_file: str = None,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    use_aria2: bool = False,
    normalize: bool = False,
    transcode: bool = False,
    proxy: str = None,
    smart_filters: dict = None,
    embed_metadata: bool = None,
):
    """Download tweets / videos from an X (Twitter) profile."""
    from features.bulk_file import download_from_file
    from features.downloader import download_urls
    target = user_or_url.strip()
    clean_user = target.lstrip("@").strip()
    if "/" in clean_user:
        m = re.search(r"(?:x\.com|twitter\.com)/([^/?#]+)", target)
        if m:
            clean_user = m.group(1)

    profile_dir = os.path.join(output_dir, f"x_{clean_user}") if os.path.basename(output_dir) != f"x_{clean_user}" else output_dir
    os.makedirs(profile_dir, exist_ok=True)

    console.print(f"[bold cyan][*] Fetching media from X profile: @{clean_user}...[/bold cyan]")
    c_file = cookie_file or get_effective_x_cookie_file()
    status_urls = fetch_x_profile_tweet_urls(clean_user, cookie_file=c_file)

    if not status_urls:
        console.print(f"[bold yellow][!] Could not retrieve public tweets automatically for @{clean_user} (X requires authentication or session).[/bold yellow]")
        alt_choice = ask_input("[bold cyan]Enter path to links .txt file or paste direct tweet URLs (or press Enter to cancel)[/bold cyan]")
        if alt_choice and os.path.isfile(alt_choice.strip()):
            download_from_file(
                alt_choice.strip(), output_dir=profile_dir, cookie_file=c_file,
                mode=mode, video_quality=video_quality,
                audio_format=audio_format, audio_quality=audio_quality,
                delay=delay, use_aria2=use_aria2, normalize=normalize,
                transcode=transcode, proxy=proxy,
                smart_filters=smart_filters, embed_metadata=embed_metadata
            )
            return
        elif alt_choice and alt_choice.strip().startswith("http"):
            status_urls = [alt_choice.strip()]
        else:
            return

    if smart_filters and smart_filters.get("count_limit"):
        status_urls = status_urls[:smart_filters["count_limit"]]

    download_urls(
        status_urls, output_dir=profile_dir, cookie_file=c_file,
        mode=mode, video_quality=video_quality,
        audio_format=audio_format, audio_quality=audio_quality,
        delay=delay, use_aria2=use_aria2, normalize=normalize,
        transcode=transcode, proxy=proxy,
        smart_filters=smart_filters, embed_metadata=embed_metadata,
        is_bulk=True
    )
