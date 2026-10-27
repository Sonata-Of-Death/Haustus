"""Single media download workflow."""
from core.constants import A7_SIGNAL
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
from features.downloader import (
    download_urls,
)
from ui.components import (
    ask_input,
    pause_prompt,
)
from ui.quality import (
    choose_single_video_quality,
    resolve_quality_settings,
    run_preflight_screen,
)
from ui.theme import (
    clear_terminal,
    config_mgr,
)


def run_single_video_menu():
    """Run single media download workflow."""
    clear_terminal()
    video_url = ask_input(f"[bold {A7_SIGNAL}]Enter media URL[/bold {A7_SIGNAL}]")
    if not video_url:
        return
    if is_x_url(video_url):
        plat = "x"
    elif is_youtube_url(video_url):
        plat = "youtube"
    elif is_tiktok_url(video_url):
        plat = "tiktok"
    elif is_soundcloud_url(video_url):
        plat = "soundcloud"
    elif is_reddit_url(video_url):
        plat = "reddit"
    elif is_facebook_url(video_url):
        plat = "facebook"
    elif is_pinterest_url(video_url):
        plat = "pinterest"
    elif is_twitch_url(video_url):
        plat = "twitch"
    elif is_threads_url(video_url):
        plat = "threads"
    elif is_spotify_url(video_url):
        plat = "spotify"
    elif is_instagram_url(video_url):
        plat = "instagram"
    else:
        plat = None
    c_file = config_mgr.get_effective_cookie_file(plat) if plat else None

    mode = config_mgr.get_default_mode()
    if mode:
        mode, quality, af, aq = resolve_quality_settings(mode_override=mode)
    else:
        mode, quality, af, aq = choose_single_video_quality(video_url, cookie_file=c_file)

    pf = run_preflight_screen(
        target_label=video_url,
        platform=plat,
        is_single=True,
        single_url=video_url,
        cookie_file=c_file,
        default_mode=mode,
    )
    if not pf:
        return

    # Preserve explicit quality choice.
    final_mode = pf["mode"] or mode
    final_q = pf["video_quality"] if pf["video_quality"] != (config_mgr.get_default_video_quality() or "best") else quality

    download_urls(
        [video_url],
        output_dir=pf["output_dir"],
        cookie_file=c_file,
        mode=final_mode,
        video_quality=final_q,
        audio_format=pf["audio_format"] or af,
        audio_quality=pf["audio_quality"] or aq,
        embed_metadata=pf["embed_metadata"],
        is_bulk=False,
        clip_range=pf["clip_range"],
        subtitles=pf["subtitles"],
    )
    pause_prompt("Press [Enter] or [Esc] to return to main menu...")
