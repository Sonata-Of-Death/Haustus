"""Creator profile and feed download workflow."""
import os
import re

from core.archive import DEFAULT_OUTPUT_DIR
from core.urls import (
    is_facebook_url,
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
from features.downloader import (
    download_urls,
)
from platforms.instagram import (
    download_instagram_stories_or_highlights,
)
from platforms.pinterest import (
    resolve_pinterest_url,
)
from platforms.reddit import (
    download_reddit_feed,
)
from platforms.spotify import (
    resolve_spotify_url,
)
from platforms.threads import (
    resolve_threads_url,
)
from platforms.twitch import (
    resolve_twitch_url,
)
from platforms.x_twitter import (
    download_x_profile,
)
from ui.components import (
    ask_input,
    interactive_select,
    pause_prompt,
)
from ui.quality import (
    run_preflight_screen,
)
from ui.theme import (
    clear_terminal,
    config_mgr,
    console,
)


def download_profile(
    user_or_url: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    browser: str = None,
    cookie_file: str = None,
    platform: str = "auto",
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
    clip_range: str = None,
    subtitles: bool = False,
    use_archive: bool = None,
):
    """Download all media from an Instagram, TikTok, YouTube, or X profile/channel."""
    target = user_or_url.strip()
    if is_youtube_url(target) or platform == "youtube":
        if not target.startswith("http"):
            clean_user = target.lstrip("@").strip()
            url = f"https://www.youtube.com/@{clean_user}/videos"
            profile_dir = os.path.join(output_dir, f"youtube_{clean_user}")
        else:
            url = target
            profile_dir = output_dir
        console.print(f"[bold cyan]Fetching YouTube Channel media: {url}[/bold cyan]")
        download_urls(
            [url], output_dir=profile_dir, browser=browser, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay,
            use_aria2=use_aria2, normalize=normalize,
            transcode=transcode, proxy=proxy,
            smart_filters=smart_filters, embed_metadata=embed_metadata,
            is_bulk=True, clip_range=clip_range, subtitles=subtitles,
            use_archive=use_archive
        )

    elif is_tiktok_url(target) or platform == "tiktok":
        if not target.startswith("http"):
            clean_user = target.lstrip("@").strip()
            url = f"https://www.tiktok.com/@{clean_user}"
            profile_dir = os.path.join(output_dir, f"tiktok_{clean_user}")
        else:
            url = target
            profile_dir = output_dir
        console.print(f"[bold cyan]Fetching TikTok profile media: {url}[/bold cyan]")
        download_urls(
            [url], output_dir=profile_dir, browser=browser, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay,
            use_aria2=use_aria2, normalize=normalize,
            transcode=transcode, proxy=proxy,
            smart_filters=smart_filters, embed_metadata=embed_metadata,
            is_bulk=True, clip_range=clip_range, subtitles=subtitles,
            use_archive=use_archive
        )

    elif is_x_url(target) or platform in ("x", "twitter"):
        if not target.startswith("http"):
            clean_user = target.lstrip("@").strip()
            url = f"https://x.com/{clean_user}"
            profile_dir = os.path.join(output_dir, f"x_{clean_user}")
        else:
            url = target
            m_user = re.search(r"(?:x\.com|twitter\.com)/([^/?#]+)", url)
            user_sub = m_user.group(1) if m_user else "user"
            profile_dir = os.path.join(output_dir, f"x_{user_sub}")
        console.print(f"[bold cyan]Fetching X (Twitter) profile media: {url}[/bold cyan]")
        download_x_profile(
            url, output_dir=profile_dir, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay,
            use_aria2=use_aria2, normalize=normalize,
            transcode=transcode, proxy=proxy,
            smart_filters=smart_filters, embed_metadata=embed_metadata
        )

    elif is_soundcloud_url(target) or platform in ("sc", "soundcloud"):
        if not target.startswith("http"):
            clean_user = target.lstrip("@").strip()
            url = f"https://soundcloud.com/{clean_user}/tracks"
            profile_dir = os.path.join(output_dir, f"soundcloud_{clean_user}")
        else:
            url = target
            m_user = re.search(r"soundcloud\.com/([^/?#]+)", url)
            user_sub = m_user.group(1) if m_user else "artist"
            profile_dir = os.path.join(output_dir, f"soundcloud_{user_sub}")
        console.print(f"[bold yellow]Fetching SoundCloud artist discography: {url}[/bold yellow]")
        download_urls(
            [url], output_dir=profile_dir, browser=browser, cookie_file=cookie_file,
            mode="audio", video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay,
            use_aria2=use_aria2, normalize=normalize,
            transcode=transcode, proxy=proxy,
            smart_filters=smart_filters, embed_metadata=embed_metadata,
            is_bulk=True, clip_range=clip_range
        )

    elif is_reddit_url(target) or platform in ("rd", "reddit") or target.startswith("r/") or target.startswith("u/"):
        target_feed = target
        if not target.startswith("http") and not target.startswith("r/") and not target.startswith("u/"):
            target_feed = f"r/{target}"
        clean_tag = target_feed.replace("https://www.reddit.com/", "").replace("/", "_").strip("_")
        profile_dir = os.path.join(output_dir, f"reddit_{clean_tag}")
        console.print(f"[bold red]Fetching Reddit feed: {target_feed}[/bold red]")
        download_reddit_feed(
            target_feed, output_dir=profile_dir,
            cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay, smart_filters=smart_filters,
            embed_metadata=embed_metadata
        )

    elif is_facebook_url(target) or platform in ("fb", "facebook"):
        if not target.startswith("http"):
            clean_user = target.lstrip("@").strip()
            url = f"https://www.facebook.com/{clean_user}/videos"
            profile_dir = os.path.join(output_dir, f"facebook_{clean_user}")
        else:
            url = target
            m_user = re.search(r"facebook\.com/([^/?#]+)", url)
            user_sub = m_user.group(1) if m_user else "page"
            profile_dir = os.path.join(output_dir, f"facebook_{user_sub}")
        console.print(f"[bold blue]Fetching Facebook Page / Creator media: {url}[/bold blue]")
        download_urls(
            [url], output_dir=profile_dir, browser=browser, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay,
            use_aria2=use_aria2, normalize=normalize,
            transcode=transcode, proxy=proxy,
            smart_filters=smart_filters, embed_metadata=embed_metadata,
            is_bulk=True, clip_range=clip_range, subtitles=subtitles,
            use_archive=use_archive
        )

    elif is_pinterest_url(target) or platform in ("pin", "pinterest"):
        if not target.startswith("http"):
            clean_user = target.lstrip("@").strip()
            url = f"https://www.pinterest.com/{clean_user}/"
            profile_dir = os.path.join(output_dir, f"pinterest_{clean_user}")
        else:
            url = resolve_pinterest_url(target)
            m_user = re.search(r"pinterest\.[a-z.]+/([^/?#]+)", url)
            user_sub = m_user.group(1) if m_user else "user"
            profile_dir = os.path.join(output_dir, f"pinterest_{user_sub}")
        console.print(f"[bold red]Fetching Pinterest pins / collection: {url}[/bold red]")
        download_urls(
            [url], output_dir=profile_dir, browser=browser, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay,
            use_aria2=use_aria2, normalize=normalize,
            transcode=transcode, proxy=proxy,
            smart_filters=smart_filters, embed_metadata=embed_metadata,
            is_bulk=True
        )

    elif is_twitch_url(target) or platform in ("ttv", "twitch"):
        if not target.startswith("http"):
            clean_user = target.lstrip("@").strip()
            url = f"https://www.twitch.tv/{clean_user}"
            profile_dir = os.path.join(output_dir, f"twitch_{clean_user}")
        else:
            url = resolve_twitch_url(target)
            m_user = re.search(r"twitch\.tv/([A-Za-z0-9_]+)", url)
            user_sub = m_user.group(1) if m_user else "streamer"
            profile_dir = os.path.join(output_dir, f"twitch_{user_sub}")
        console.print(f"[bold magenta]Fetching Twitch Channel / Streamer media: {url}[/bold magenta]")
        download_urls(
            [url], output_dir=profile_dir, browser=browser, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay,
            use_aria2=use_aria2, normalize=normalize,
            transcode=transcode, proxy=proxy,
            smart_filters=smart_filters, embed_metadata=embed_metadata,
            is_bulk=True, clip_range=clip_range, subtitles=subtitles,
            use_archive=use_archive
        )

    elif is_threads_url(target) or platform in ("th", "thread", "threads"):
        if not target.startswith("http"):
            clean_user = target.lstrip("@").strip()
            url = f"https://www.threads.net/@{clean_user}"
            profile_dir = os.path.join(output_dir, f"threads_{clean_user}")
        else:
            url = resolve_threads_url(target)
            m_user = re.search(r"threads\.[a-z.]+/@([^/?#]+)", url)
            user_sub = m_user.group(1) if m_user else "user"
            profile_dir = os.path.join(output_dir, f"threads_{user_sub}")
        console.print(f"[bold cyan]Fetching Threads profile media: {url}[/bold cyan]")
        download_urls(
            [url], output_dir=profile_dir, browser=browser, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay,
            use_aria2=use_aria2, normalize=normalize,
            transcode=transcode, proxy=proxy,
            smart_filters=smart_filters, embed_metadata=embed_metadata,
            is_bulk=True, clip_range=clip_range, subtitles=subtitles,
            use_archive=use_archive
        )

    elif is_spotify_url(target) or platform in ("sp", "spotify"):
        if not target.startswith("http") and not target.startswith("spotify:"):
            clean_user = target.lstrip("@").strip()
            url = f"https://open.spotify.com/artist/{clean_user}"
            profile_dir = os.path.join(output_dir, f"spotify_{clean_user}")
        else:
            url = resolve_spotify_url(target)
            m_user = re.search(r"spotify\.com/(?:artist|playlist|album|show)/([^/?#]+)", url)
            user_sub = m_user.group(1) if m_user else "collection"
            profile_dir = os.path.join(output_dir, f"spotify_{user_sub}")
        console.print(f"[bold green]Fetching Spotify artist/collection media: {url}[/bold green]")
        download_urls(
            [url], output_dir=profile_dir, browser=browser, cookie_file=cookie_file,
            mode="audio", video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay,
            use_aria2=use_aria2, normalize=normalize,
            transcode=transcode, proxy=proxy,
            smart_filters=smart_filters, embed_metadata=embed_metadata,
            is_bulk=True
        )

    else:
        # Handle Instagram posts, reels, stories, or highlights by default.
        if "/stories/highlights/" in target.lower():
            download_instagram_stories_or_highlights(
                target, output_dir=output_dir, cookie_file=cookie_file,
                mode=mode, video_quality=video_quality,
                audio_format=audio_format, audio_quality=audio_quality,
                delay=delay, embed_metadata=embed_metadata, kind="highlights"
            )
            return
        elif "/stories/" in target.lower():
            download_instagram_stories_or_highlights(
                target, output_dir=output_dir, cookie_file=cookie_file,
                mode=mode, video_quality=video_quality,
                audio_format=audio_format, audio_quality=audio_quality,
                delay=delay, embed_metadata=embed_metadata, kind="stories"
            )
            return

        if not target.startswith("http"):
            clean_user = target.lstrip("@").strip()
            url = f"https://www.instagram.com/{clean_user}/reels/"
            profile_dir = os.path.join(output_dir, clean_user)
        else:
            url = target
            profile_dir = output_dir
        console.print(f"[bold cyan]Fetching Instagram profile media: {url}[/bold cyan]")
        download_urls(
            [url], output_dir=profile_dir, browser=browser, cookie_file=cookie_file,
            mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            delay=delay,
            use_aria2=use_aria2, normalize=normalize,
            transcode=transcode, proxy=proxy,
            smart_filters=smart_filters, embed_metadata=embed_metadata,
            is_bulk=True, clip_range=clip_range, subtitles=subtitles,
            use_archive=use_archive
        )

def run_profile_menu():
    """Run creator profile and feed download workflow."""
    clear_terminal()
    user_input = ask_input("[bold green]Enter username or profile/channel URL (e.g. @user, @channel)[/bold green]")
    if not user_input:
        return

    platform = "auto"
    ig_content_type = "reels"
    if not user_input.startswith("http"):
        plat_opts = [
            {"key": "1", "title": "Instagram (Posts & Reels)", "desc": "Reels, posts, and profile media", "value": "instagram"},
            {"key": "2", "title": "Instagram Stories", "desc": "Active 24h stories from @user (requires session cookie)", "value": "instagram_stories"},
            {"key": "3", "title": "Instagram Highlights", "desc": "Archived story highlights from @user (requires session cookie)", "value": "instagram_highlights"},
            {"key": "4", "title": "TikTok", "desc": "Creator videos and photo slideshows", "value": "tiktok"},
            {"key": "5", "title": "YouTube", "desc": "Channel videos, shorts, and livestreams", "value": "youtube"},
            {"key": "6", "title": "X (Twitter)", "desc": "Creator videos, media tweets, and posts", "value": "x"},
            {"key": "7", "title": "SoundCloud", "desc": "Artist discography and tracks", "value": "soundcloud"},
            {"key": "8", "title": "Reddit", "desc": "Subreddit feed or user submissions", "value": "reddit"},
            {"key": "9", "title": "Facebook", "desc": "Public page videos or creator watch channel", "value": "facebook"},
            {"key": "10", "title": "Pinterest", "desc": "User pins, collections, and public boards", "value": "pinterest"},
            {"key": "11", "title": "Twitch", "desc": "Streamer channel videos, clips, and past broadcasts", "value": "twitch"},
            {"key": "12", "title": "Threads", "desc": "Creator profile video and photo posts", "value": "threads"},
            {"key": "13", "title": "Spotify", "desc": "Artist discography, albums, and tracks", "value": "spotify"},
        ]
        platform = interactive_select("SELECT TARGET PLATFORM", plat_opts, default_index=0, border_style="yellow")
        if not platform or platform in ("cancel", "back", "0"):
            return
        if platform == "instagram_stories":
            platform = "instagram"
            ig_content_type = "stories"
        elif platform == "instagram_highlights":
            platform = "instagram"
            ig_content_type = "highlights"

    c_file = config_mgr.get_effective_cookie_file(platform) if platform != "auto" else None
    pf = run_preflight_screen(
        target_label=user_input,
        platform=platform,
        is_single=False,
        cookie_file=c_file,
    )
    if not pf:
        return

    if platform == "instagram" and ig_content_type in ("stories", "highlights"):
        download_instagram_stories_or_highlights(
            user_input,
            output_dir=pf["output_dir"],
            cookie_file=c_file,
            mode=pf["mode"],
            video_quality=pf["video_quality"],
            audio_format=pf["audio_format"],
            audio_quality=pf["audio_quality"],
            embed_metadata=pf["embed_metadata"],
            kind=ig_content_type,
        )
    else:
        download_profile(
            user_input,
            output_dir=pf["output_dir"],
            cookie_file=c_file,
            platform=platform,
            mode=pf["mode"],
            video_quality=pf["video_quality"],
            audio_format=pf["audio_format"],
            audio_quality=pf["audio_quality"],
            smart_filters=pf["smart_filters"],
            embed_metadata=pf["embed_metadata"],
            clip_range=pf["clip_range"],
            subtitles=pf["subtitles"],
        )
    pause_prompt("Press [Enter] or [Esc] to return to main menu...")
