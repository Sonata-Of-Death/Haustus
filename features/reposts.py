"""Saved reposts download workflow."""
import os

from core.cookies import (
    resolve_cookie_file,
)
from platforms.instagram import (
    download_instagram_reposted_posts,
    parse_instagram_reposts_json,
)
from platforms.tiktok import (
    download_tiktok_reposted_videos,
)
from platforms.x_twitter import (
    download_x_reposts,
    parse_x_data_archive,
)
from ui.components import (
    ask_input,
    interactive_select,
    pause_prompt,
)
from ui.quality import (
    resolve_output_dir,
    resolve_quality_settings,
)
from ui.theme import (
    clear_terminal,
    console,
)


def dedicated_reposts_menu():
    """Run reposts download menu."""
    while True:
        clear_terminal()
        repost_opts = [
            {"key": "1", "title": "[TIKTOK] Download TikTok Reposted Videos", "desc": "All videos reposted by your authenticated TikTok account", "value": "tiktok"},
            {"key": "2", "title": "[INSTAGRAM] Download Instagram Reposted Posts & Reels", "desc": "All posts & reels reposted by your authenticated Instagram account", "value": "instagram"},
            {"key": "3", "title": "[X / TWITTER] Download X Reposts / Retweets", "desc": "All tweets and videos reposted/retweeted by your account", "value": "x"},
            {"key": "0", "title": "[BACK] Return to Main Menu", "desc": "Return to main menu", "value": "back"},
        ]
        r_pick = interactive_select("REPOSTED MEDIA DOWNLOADER", repost_opts, default_index=0, border_style="cyan")
        if not r_pick or r_pick in ("back", "cancel", "0"):
            break

        if r_pick == "tiktok":
            tt_c = resolve_cookie_file("tiktok", required=True)
            if not tt_c:
                pause_prompt("Press [Enter] or [Esc] to return...")
                continue
            out_dir = resolve_output_dir()
            if not out_dir:
                continue
            mode, quality, af, aq = resolve_quality_settings()
            download_tiktok_reposted_videos(
                cookie_file=tt_c, output_dir=out_dir,
                mode=mode, video_quality=quality, audio_format=af, audio_quality=aq
            )
            pause_prompt("Press [Enter] or [Esc] to return...")

        elif r_pick == "instagram":
            ig_sub_opts = [
                {"key": "1", "title": "Online Account Fetch (Via Session / Cookies)", "desc": "Fetch live reposted reels and posts directly from Instagram", "value": "online"},
                {"key": "2", "title": "Offline Data Export (Via reposts.json / archive)", "desc": "Load reposted posts from your Instagram data export file", "value": "archive"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            ig_mode = interactive_select("INSTAGRAM REPOSTS SOURCE", ig_sub_opts, default_index=0, border_style="cyan")
            if not ig_mode or ig_mode == "cancel":
                continue

            if ig_mode == "online":
                ig_c = resolve_cookie_file("instagram", required=True)
                if not ig_c:
                    pause_prompt("Press [Enter] or [Esc] to return...")
                    continue
                out_dir = resolve_output_dir()
                if not out_dir:
                    continue
                mode, quality, af, aq = resolve_quality_settings()
                download_instagram_reposted_posts(
                    cookie_file=ig_c, output_dir=out_dir,
                    mode=mode, video_quality=quality, audio_format=af, audio_quality=aq
                )
            elif ig_mode == "archive":
                arch_path = ask_input("[bold cyan]Enter path to reposts.json or Instagram data export file[/bold cyan]")
                if arch_path and os.path.isfile(arch_path):
                    custom_urls = parse_instagram_reposts_json(arch_path)
                    if custom_urls:
                        out_dir = resolve_output_dir()
                        if not out_dir:
                            continue
                        mode, quality, af, aq = resolve_quality_settings()
                        download_instagram_reposted_posts(
                            output_dir=out_dir, mode=mode, video_quality=quality,
                            audio_format=af, audio_quality=aq, custom_urls=custom_urls
                        )
                else:
                    console.print("[bold red][-] File not found or cancelled.[/bold red]")
            pause_prompt("Press [Enter] or [Esc] to return...")

        elif r_pick in ("x", "twitter"):
            x_sub_opts = [
                {"key": "1", "title": "Online Account Fetch (Via Session / Cookies)", "desc": "Fetch live reposts/retweets from your authenticated X account", "value": "online"},
                {"key": "2", "title": "Offline Data Export (Via tweets.json / archive)", "desc": "Load retweets from Twitter/X data archive file", "value": "archive"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            x_mode = interactive_select("X REPOSTS SOURCE", x_sub_opts, default_index=0, border_style="cyan")
            if not x_mode or x_mode == "cancel":
                continue

            if x_mode == "online":
                x_c = resolve_cookie_file("x", required=True)
                if not x_c:
                    pause_prompt("Press [Enter] or [Esc] to return...")
                    continue
                out_dir = resolve_output_dir()
                if not out_dir:
                    continue
                mode, quality, af, aq = resolve_quality_settings()
                download_x_reposts(
                    cookie_file=x_c, output_dir=out_dir,
                    mode=mode, video_quality=quality, audio_format=af, audio_quality=aq
                )
            elif x_mode == "archive":
                arch_path = ask_input("[bold cyan]Enter path to tweets.json or Twitter data export file[/bold cyan]")
                if arch_path and os.path.isfile(arch_path):
                    custom_urls = parse_x_data_archive(arch_path, kind="reposts")
                    if custom_urls:
                        out_dir = resolve_output_dir()
                        if not out_dir:
                            continue
                        mode, quality, af, aq = resolve_quality_settings()
                        download_x_reposts(
                            output_dir=out_dir, mode=mode, video_quality=quality,
                            audio_format=af, audio_quality=aq, custom_urls=custom_urls
                        )
                else:
                    console.print("[bold red][-] File not found or cancelled.[/bold red]")
            pause_prompt("Press [Enter] or [Esc] to return...")
