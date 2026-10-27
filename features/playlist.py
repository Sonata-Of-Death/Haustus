"""YouTube playlist download workflow."""
from core.cookies import (
    resolve_cookie_file,
)
from features.downloader import (
    download_urls,
)
from platforms.youtube import (
    choose_youtube_playlist_to_download,
)
from ui.components import (
    pause_prompt,
)
from ui.quality import (
    run_preflight_screen,
)
from ui.theme import (
    clear_terminal,
    config_mgr,
)


def run_youtube_playlist_menu():
    """Run YouTube playlist download workflow."""
    clear_terminal()
    c_file = config_mgr.get_effective_cookie_file("youtube")
    pl_url = choose_youtube_playlist_to_download(cookie_file=c_file)
    if not pl_url:
        return
    if ("list=WL" in pl_url or "list=LL" in pl_url) and not c_file:
        c_file = resolve_cookie_file("youtube", required=True)
        if not c_file:
            return

    pf = run_preflight_screen(
        target_label=pl_url,
        platform="youtube",
        is_single=False,
        cookie_file=c_file,
    )
    if not pf:
        return

    download_urls(
        [pl_url],
        output_dir=pf["output_dir"],
        cookie_file=c_file,
        mode=pf["mode"],
        video_quality=pf["video_quality"],
        audio_format=pf["audio_format"],
        audio_quality=pf["audio_quality"],
        smart_filters=pf["smart_filters"],
        embed_metadata=pf["embed_metadata"],
        is_bulk=True,
        clip_range=pf["clip_range"],
        subtitles=pf["subtitles"],
    )
    pause_prompt("Press [Enter] or [Esc] to return to main menu...")
