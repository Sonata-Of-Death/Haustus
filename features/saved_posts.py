"""Unified bookmarks download workflow."""
import os

from core.cookies import (
    resolve_cookie_file,
)
from features.downloader import (
    download_urls,
)
from platforms.facebook import (
    download_facebook_saved_videos,
)
from platforms.instagram import (
    download_instagram_saved_posts,
)
from platforms.pinterest import (
    download_pinterest_board,
)
from platforms.reddit import (
    download_reddit_feed,
)
from platforms.soundcloud import (
    download_soundcloud_liked_tracks,
)
from platforms.spotify import (
    download_spotify_playlist,
)
from platforms.threads import (
    download_threads_profile,
)
from platforms.tiktok import (
    download_tiktok_saved_posts,
    parse_tiktok_user_data_json,
)
from platforms.twitch import (
    download_twitch_channel,
)
from platforms.x_twitter import (
    download_x_bookmarks,
    parse_x_data_archive,
)
from platforms.youtube import (
    choose_youtube_playlist_to_download,
)
from ui.components import (
    ask_input,
    interactive_select,
    pause_prompt,
    select_platform_grid,
)
from ui.quality import (
    prompt_smart_filters,
    resolve_embed_metadata,
    resolve_output_dir,
    resolve_quality_settings,
)
from ui.theme import (
    clear_terminal,
    console,
)


def unified_saved_posts_menu():
    """Run saved posts and bookmarks menu."""
    while True:
        clear_terminal()
        s_pick = select_platform_grid(breadcrumb="Library  >  Saved Collections", title="SAVED COLLECTIONS")
        if not s_pick or s_pick in ("back", "cancel", "0"):
            break

        if s_pick == "instagram":
            c_file = resolve_cookie_file("instagram", required=True)
            if not c_file:
                pause_prompt("Press [Enter] to return...")
                continue
            out_dir = resolve_output_dir()
            if not out_dir:
                continue
            mode, quality, af, aq = resolve_quality_settings()
            download_instagram_saved_posts(
                cookie_file=c_file, output_dir=out_dir,
                mode=mode, video_quality=quality, audio_format=af, audio_quality=aq
            )
            pause_prompt("Press [Enter] to return...")

        elif s_pick == "tiktok":
            tt_sub_opts = [
                {"key": "1", "title": "Online Account Fetch (Via Session / Cookies)", "desc": "Fetch live favorites and saved videos directly from TikTok", "value": "online"},
                {"key": "2", "title": "Offline Data Export (Via user_data.json)", "desc": "Load exported favorites from TikTok JSON data backup", "value": "json"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            tt_mode = interactive_select("TIKTOK SAVED SOURCE", tt_sub_opts, default_index=0, border_style="cyan")
            if not tt_mode or tt_mode == "cancel":
                continue

            if tt_mode == "online":
                tt_c = resolve_cookie_file("tiktok", required=True)
                if not tt_c:
                    pause_prompt("Press [Enter] to return...")
                    continue
                out_dir = resolve_output_dir()
                if not out_dir:
                    continue
                mode, quality, af, aq = resolve_quality_settings()
                download_tiktok_saved_posts(
                    cookie_file=tt_c, output_dir=out_dir,
                    mode=mode, video_quality=quality, audio_format=af, audio_quality=aq
                )
            elif tt_mode == "json":
                j_path = ask_input("[bold cyan]Enter path to TikTok user_data.json[/bold cyan]")
                if j_path and os.path.isfile(j_path):
                    custom_urls = parse_tiktok_user_data_json(j_path)
                    if custom_urls:
                        out_dir = resolve_output_dir()
                        if not out_dir:
                            continue
                        mode, quality, af, aq = resolve_quality_settings()
                        download_tiktok_saved_posts(
                            output_dir=out_dir, mode=mode, video_quality=quality,
                            audio_format=af, audio_quality=aq, custom_urls=custom_urls
                        )
                else:
                    console.print("[bold red][-] File not found or cancelled.[/bold red]")
            pause_prompt("Press [Enter] or [Esc] to return...")

        elif s_pick == "youtube":
            yt_c = resolve_cookie_file("youtube", required=False)
            target_url = choose_youtube_playlist_to_download(cookie_file=yt_c)
            if target_url:
                if ("list=WL" in target_url or "list=LL" in target_url) and not yt_c:
                    yt_c = resolve_cookie_file("youtube", required=True)
                    if not yt_c:
                        pause_prompt("Press [Enter] or [Esc] to return...")
                        continue
                out_dir = resolve_output_dir()
                if not out_dir:
                    continue
                mode, quality, af, aq = resolve_quality_settings()
                filters = prompt_smart_filters()
                download_urls(
                    [target_url], output_dir=out_dir, cookie_file=yt_c,
                    mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
                    smart_filters=filters, is_bulk=True
                )
            pause_prompt("Press [Enter] or [Esc] to return...")

        elif s_pick in ("x", "twitter"):
            x_sub_opts = [
                {"key": "1", "title": "Online Account Fetch (Via Session / Cookies)", "desc": "Fetch live bookmarks directly from your authenticated X account", "value": "online"},
                {"key": "2", "title": "Offline Data Export (Via bookmarks.json / archive)", "desc": "Load exported bookmarks from Twitter/X archive file", "value": "archive"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            x_mode = interactive_select("X BOOKMARKS SOURCE", x_sub_opts, default_index=0, border_style="cyan")
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
                download_x_bookmarks(
                    cookie_file=x_c, output_dir=out_dir,
                    mode=mode, video_quality=quality, audio_format=af, audio_quality=aq
                )
            elif x_mode == "archive":
                arch_path = ask_input("[bold cyan]Enter path to bookmarks.json or Twitter data export file[/bold cyan]")
                if arch_path and os.path.isfile(arch_path):
                    custom_urls = parse_x_data_archive(arch_path, kind="bookmarks")
                    if custom_urls:
                        out_dir = resolve_output_dir()
                        if not out_dir:
                            continue
                        mode, quality, af, aq = resolve_quality_settings()
                        download_x_bookmarks(
                            output_dir=out_dir, mode=mode, video_quality=quality,
                            audio_format=af, audio_quality=aq, custom_urls=custom_urls
                        )
                else:
                    console.print("[bold red][-] File not found or cancelled.[/bold red]")
            pause_prompt("Press [Enter] or [Esc] to return...")

        elif s_pick == "soundcloud":
            sc_sub_opts = [
                {"key": "1", "title": "Account Liked Tracks", "desc": "Download all liked tracks from authenticated user account", "value": "likes"},
                {"key": "2", "title": "Custom Artist Liked Tracks", "desc": "Download liked tracks of any public SoundCloud artist / user", "value": "user_likes"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            sc_sub = interactive_select("SOUNDCLOUD SOURCE", sc_sub_opts, default_index=0, border_style="yellow")
            if not sc_sub or sc_sub == "cancel":
                continue
            sc_c = resolve_cookie_file("soundcloud", required=(sc_sub == "likes"))
            if sc_sub == "likes" and not sc_c:
                pause_prompt("Press [Enter] or [Esc] to return...")
                continue
            target_user = None
            if sc_sub == "user_likes":
                target_user = ask_input("[bold cyan]Enter SoundCloud username or profile URL[/bold cyan]")
                if not target_user:
                    continue
            out_dir = resolve_output_dir()
            if not out_dir:
                continue
            mode, quality, af, aq = resolve_quality_settings()
            filters = prompt_smart_filters()
            embed_meta = resolve_embed_metadata()
            download_soundcloud_liked_tracks(
                username_or_url=target_user,
                cookie_file=sc_c,
                output_dir=out_dir,
                audio_format=af,
                audio_quality=aq,
                smart_filters=filters,
                embed_metadata=embed_meta
            )
            pause_prompt("Press [Enter] or [Esc] to return...")

        elif s_pick == "reddit":
            rd_sub_opts = [
                {"key": "1", "title": "Saved Posts (Authenticated Account)", "desc": "Download all bookmarked/saved media from your Reddit account", "value": "saved"},
                {"key": "2", "title": "Upvoted Posts (Authenticated Account)", "desc": "Download all upvoted media submissions from your Reddit account", "value": "upvoted"},
                {"key": "3", "title": "Subreddit Feed", "desc": "Download Hot, New, or Top media from any subreddit (e.g. r/videos)", "value": "subreddit"},
                {"key": "4", "title": "User Submissions", "desc": "Download all media submitted by a specific Reddit user", "value": "user"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            rd_sub = interactive_select("REDDIT MEDIA SOURCE", rd_sub_opts, default_index=0, border_style="red")
            if not rd_sub or rd_sub == "cancel":
                continue

            rd_c = resolve_cookie_file("reddit", required=(rd_sub in ("saved", "upvoted")))
            if rd_sub in ("saved", "upvoted") and not rd_c:
                pause_prompt("Press [Enter] or [Esc] to return...")
                continue

            target_feed = rd_sub
            sort_method = "hot"
            timeframe = "all"

            if rd_sub == "subreddit":
                sub_name = ask_input("[bold cyan]Enter Subreddit name (e.g. videos or r/wallpapers)[/bold cyan]")
                if not sub_name:
                    continue
                target_feed = f"r/{sub_name.replace('r/', '').strip('/')}"
                sort_opts = [
                    {"key": "1", "title": "Hot", "desc": "Currently trending posts in subreddit", "value": "hot"},
                    {"key": "2", "title": "Top (All Time)", "desc": "Highest rated posts of all time", "value": "top_all"},
                    {"key": "3", "title": "Top (This Month)", "desc": "Highest rated posts this month", "value": "top_month"},
                    {"key": "4", "title": "Top (This Week)", "desc": "Highest rated posts this week", "value": "top_week"},
                    {"key": "5", "title": "New", "desc": "Most recently submitted posts", "value": "new"},
                ]
                s_pick_sort = interactive_select("SUBREDDIT SORT METHOD", sort_opts, default_index=0, border_style="yellow")
                if not s_pick_sort:
                    continue
                if s_pick_sort.startswith("top_"):
                    sort_method = "top"
                    timeframe = s_pick_sort.split("_")[1]
                else:
                    sort_method = s_pick_sort

            elif rd_sub == "user":
                u_name = ask_input("[bold cyan]Enter Reddit username (e.g. u/username or username)[/bold cyan]")
                if not u_name:
                    continue
                target_feed = f"u/{u_name.replace('u/', '').strip('/')}"

            out_dir = resolve_output_dir()
            if not out_dir:
                continue
            mode, quality, af, aq = resolve_quality_settings()
            filters = prompt_smart_filters()
            embed_meta = resolve_embed_metadata()
            download_reddit_feed(
                target_feed,
                output_dir=out_dir,
                sort=sort_method,
                timeframe=timeframe,
                cookie_file=rd_c,
                mode=mode,
                video_quality=quality,
                audio_format=af,
                audio_quality=aq,
                smart_filters=filters,
                embed_metadata=embed_meta
            )
            pause_prompt("Press [Enter] or [Esc] to return...")

        elif s_pick == "facebook":
            fb_sub_opts = [
                {"key": "1", "title": "Account Saved Videos", "desc": "Download videos saved in your Facebook account (via cookies)", "value": "saved"},
                {"key": "2", "title": "Page / Creator Videos", "desc": "Download all videos from a public page or creator", "value": "page"},
                {"key": "3", "title": "Direct Video / Reel URL", "desc": "Download specific Facebook watch/reel link", "value": "direct"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            fb_sub = interactive_select("FACEBOOK MEDIA SOURCE", fb_sub_opts, default_index=0, border_style="blue")
            if fb_sub and fb_sub != "cancel":
                fb_c = resolve_cookie_file("facebook", required=(fb_sub == "saved"))
                if fb_sub == "saved" and not fb_c:
                    pause_prompt("Press [Enter] or [Esc] to return...")
                    continue
                out_dir = resolve_output_dir()
                if not out_dir:
                    continue
                mode, quality, af, aq = resolve_quality_settings()
                filters = prompt_smart_filters()
                embed_meta = resolve_embed_metadata()

                if fb_sub == "saved":
                    download_facebook_saved_videos(
                        cookie_file=fb_c, output_dir=out_dir,
                        mode=mode, video_quality=quality,
                        audio_format=af, audio_quality=aq,
                        smart_filters=filters
                    )
                elif fb_sub == "page":
                    p_url = ask_input("[bold cyan]Enter Facebook Page username or URL (e.g. facebook.com/page or page_name)[/bold cyan]")
                    if p_url:
                        if not p_url.startswith("http"):
                            p_url = f"https://www.facebook.com/{p_url.strip('/')}/videos"
                        download_urls(
                            [p_url], output_dir=out_dir, cookie_file=fb_c,
                            mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
                            smart_filters=filters, embed_metadata=embed_meta, is_bulk=True
                        )
                elif fb_sub == "direct":
                    d_url = ask_input("[bold cyan]Enter Facebook video, reel, or watch URL[/bold cyan]")
                    if d_url:
                        download_urls(
                            [d_url], output_dir=out_dir, cookie_file=fb_c,
                            mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
                            smart_filters=filters, embed_metadata=embed_meta, is_bulk=False
                        )
                pause_prompt("Press [Enter] or [Esc] to return...")

        elif s_pick == "pinterest":
            pin_sub_opts = [
                {"key": "1", "title": "Pinterest Board URL", "desc": "Download all pins from a full board / collection", "value": "board"},
                {"key": "2", "title": "User Profile Pins", "desc": "Download pins from a user profile", "value": "user"},
                {"key": "3", "title": "Direct Pin URL (or pin.it)", "desc": "Download single video or photo pin in original resolution", "value": "direct"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            pin_sub = interactive_select("PINTEREST MEDIA SOURCE", pin_sub_opts, default_index=0, border_style="red")
            if pin_sub and pin_sub != "cancel":
                out_dir = resolve_output_dir()
                if not out_dir:
                    continue
                mode, quality, af, aq = resolve_quality_settings()
                filters = prompt_smart_filters()
                embed_meta = resolve_embed_metadata()
                pin_c = resolve_cookie_file("pinterest", required=False)

                if pin_sub == "board":
                    b_url = ask_input("[bold cyan]Enter Pinterest board URL (e.g. pinterest.com/user/board)[/bold cyan]")
                    if b_url:
                        download_pinterest_board(
                            b_url, output_dir=out_dir, cookie_file=pin_c,
                            mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
                            smart_filters=filters
                        )
                elif pin_sub == "user":
                    u_in = ask_input("[bold cyan]Enter Pinterest username or profile URL[/bold cyan]")
                    if u_in:
                        if not u_in.startswith("http"):
                            u_in = f"https://www.pinterest.com/{u_in.strip('/')}/"
                        download_urls(
                            [u_in], output_dir=out_dir, cookie_file=pin_c,
                            mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
                            smart_filters=filters, embed_metadata=embed_meta, is_bulk=True
                        )
                elif pin_sub == "direct":
                    p_url = ask_input("[bold cyan]Enter Pinterest pin URL or pin.it shortlink[/bold cyan]")
                    if p_url:
                        download_urls(
                            [p_url], output_dir=out_dir, cookie_file=pin_c,
                            mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
                            smart_filters=filters, embed_metadata=embed_meta, is_bulk=False
                        )
                pause_prompt("Press [Enter] or [Esc] to return...")

        elif s_pick == "twitch":
            tw_sub_opts = [
                {"key": "1", "title": "Streamer Clips / Archive", "desc": "Download clips from a Twitch channel / streamer", "value": "channel"},
                {"key": "2", "title": "Direct Clip / VOD URL", "desc": "Download specific Twitch clip or video link", "value": "direct"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            tw_sub = interactive_select("TWITCH MEDIA SOURCE", tw_sub_opts, default_index=0, border_style="magenta")
            if tw_sub and tw_sub != "cancel":
                out_dir = resolve_output_dir()
                if not out_dir:
                    continue
                mode, quality, af, aq = resolve_quality_settings()
                filters = prompt_smart_filters()
                embed_meta = resolve_embed_metadata()
                tw_c = resolve_cookie_file("twitch", required=False)

                if tw_sub == "channel":
                    ch_in = ask_input("[bold cyan]Enter Twitch channel / streamer username or URL[/bold cyan]")
                    if ch_in:
                        download_twitch_channel(
                            ch_in, output_dir=out_dir, cookie_file=tw_c,
                            mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
                            smart_filters=filters
                        )
                elif tw_sub == "direct":
                    d_url = ask_input("[bold cyan]Enter Twitch clip or VOD URL[/bold cyan]")
                    if d_url:
                        download_urls(
                            [d_url], output_dir=out_dir, cookie_file=tw_c,
                            mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
                            smart_filters=filters, embed_metadata=embed_meta, is_bulk=False
                        )
                pause_prompt("Press [Enter] or [Esc] to return...")

        elif s_pick == "threads":
            th_sub_opts = [
                {"key": "1", "title": "Creator Profile Media", "desc": "Download all video and photo posts from a Threads profile", "value": "profile"},
                {"key": "2", "title": "Direct Post URL", "desc": "Download a specific Threads video or photo post", "value": "direct"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            th_sub = interactive_select("THREADS MEDIA SOURCE", th_sub_opts, default_index=0, border_style="cyan")
            if th_sub and th_sub != "cancel":
                out_dir = resolve_output_dir()
                if not out_dir:
                    continue
                mode, quality, af, aq = resolve_quality_settings()
                filters = prompt_smart_filters()
                embed_meta = resolve_embed_metadata()
                th_c = resolve_cookie_file("threads", required=False)

                if th_sub == "profile":
                    p_in = ask_input("[bold cyan]Enter Threads username (e.g. @username or username)[/bold cyan]")
                    if p_in:
                        download_threads_profile(
                            p_in, output_dir=out_dir, cookie_file=th_c,
                            mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
                            smart_filters=filters
                        )
                elif th_sub == "direct":
                    d_url = ask_input("[bold cyan]Enter Threads post URL[/bold cyan]")
                    if d_url:
                        download_urls(
                            [d_url], output_dir=out_dir, cookie_file=th_c,
                            mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
                            smart_filters=filters, embed_metadata=embed_meta, is_bulk=False
                        )
                pause_prompt("Press [Enter] or [Esc] to return...")

        elif s_pick == "spotify":
            sp_sub_opts = [
                {"key": "1", "title": "Spotify Playlist or Album URL", "desc": "Download public or private playlist/album in bulk", "value": "playlist"},
                {"key": "2", "title": "Spotify Track URL", "desc": "Download single track with cover art & ID3 tags", "value": "track"},
                {"key": "3", "title": "Spotify Podcast Episode or Show", "desc": "Download podcast episode or series", "value": "podcast"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
            ]
            sp_sub = interactive_select("SPOTIFY MEDIA SOURCE", sp_sub_opts, default_index=0, border_style="green")
            if sp_sub and sp_sub != "cancel":
                out_dir = resolve_output_dir()
                if not out_dir:
                    continue
                mode, quality, af, aq = resolve_quality_settings()
                filters = prompt_smart_filters()
                embed_meta = resolve_embed_metadata()
                sp_c = resolve_cookie_file("spotify", required=False)

                if sp_sub in ("playlist", "podcast"):
                    p_in = ask_input("[bold green]Enter Spotify playlist, album, show, or artist URL[/bold green]")
                    if p_in:
                        download_spotify_playlist(
                            p_in, output_dir=out_dir, cookie_file=sp_c,
                            audio_format=af, audio_quality=aq,
                            smart_filters=filters, embed_metadata=embed_meta
                        )
                elif sp_sub == "track":
                    d_url = ask_input("[bold green]Enter Spotify track URL[/bold green]")
                    if d_url:
                        download_urls(
                            [d_url], output_dir=out_dir, cookie_file=sp_c,
                            mode="audio", audio_format=af, audio_quality=aq,
                            smart_filters=filters, embed_metadata=embed_meta, is_bulk=False
                        )
                pause_prompt("Press [Enter] or [Esc] to return...")
