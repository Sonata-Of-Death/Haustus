"""Interactive multi-line URL paste workflow."""
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
    resolve_embed_metadata,
    resolve_output_dir,
    resolve_quality_settings,
)
from ui.theme import (
    clear_terminal,
    config_mgr,
    console,
)


def run_paste_urls_menu():
    """Run interactive URL paste workflow."""
    clear_terminal()
    console.print("[bold cyan]Paste your URLs below (press Enter on empty line or [Esc] to finish/cancel):[/bold cyan]")
    lines = []
    while True:
        line = ask_input(f"URL #{len(lines)+1} (or Enter to finish)")
        if line is None:
            break
        if not line.strip() or line.strip().upper() == "END":
            break
        for sub_line in line.splitlines():
            cleaned_sub = sub_line.strip().strip('"').strip("'")
            if cleaned_sub and cleaned_sub.upper() != "END":
                lines.append(cleaned_sub)
    if not lines:
        return

    out_dir = resolve_output_dir()
    if not out_dir:
        return
    if len(lines) == 1:
        u0 = lines[0]
        plat = "x" if is_x_url(u0) else ("youtube" if is_youtube_url(u0) else ("tiktok" if is_tiktok_url(u0) else ("soundcloud" if is_soundcloud_url(u0) else ("reddit" if is_reddit_url(u0) else ("facebook" if is_facebook_url(u0) else ("pinterest" if is_pinterest_url(u0) else ("twitch" if is_twitch_url(u0) else ("threads" if is_threads_url(u0) else ("spotify" if is_spotify_url(u0) else ("instagram" if is_instagram_url(u0) else None))))))))))
        c_file = config_mgr.get_effective_cookie_file(plat) if plat else None
        mode = config_mgr.get_default_mode()
        if mode:
            mode, quality, af, aq = resolve_quality_settings(mode_override=mode)
        else:
            mode, quality, af, aq = choose_single_video_quality(lines[0], cookie_file=c_file)
    else:
        c_file = None
        mode, quality, af, aq = resolve_quality_settings()

    embed_meta = resolve_embed_metadata()
    download_urls(
        lines, output_dir=out_dir, cookie_file=c_file,
        mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
        embed_metadata=embed_meta, is_bulk=False
    )
    pause_prompt("Press [Enter] or [Esc] to return to main menu...")
