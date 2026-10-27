"""Audio extraction and mastering workflow."""
from core.cookies import (
    resolve_cookie_file,
)
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
from features.bulk_file import (
    download_from_file,
)
from features.downloader import (
    download_urls,
)
from features.profile import (
    download_profile,
)
from platforms.soundcloud import (
    download_soundcloud_liked_tracks,
)
from platforms.spotify import (
    download_spotify_playlist,
)
from platforms.youtube import (
    choose_youtube_playlist_to_download,
)
from ui.components import (
    ask_input,
    interactive_select,
    pause_prompt,
)
from ui.quality import (
    prompt_smart_filters,
    resolve_embed_metadata,
    resolve_links_file,
    resolve_output_dir,
    resolve_quality_settings,
)
from ui.theme import (
    clear_terminal,
    config_mgr,
)


def run_audio_mode_menu():
    """Run audio-only extraction menu."""
    clear_terminal()
    audio_source_options = [
        {"key": "1", "title": "Single Video URL as Audio", "desc": "Extract audio track from any video or audio URL", "value": "1"},
        {"key": "2", "title": "Bulk from Links File as Audio", "desc": "Extract audio from all URLs in any links .txt file", "value": "2"},
        {"key": "3", "title": "Full YouTube Playlist as Audio", "desc": "Download entire playlist as separate audio tracks", "value": "3"},
        {"key": "4", "title": "Channel / Profile as Audio", "desc": "Download all videos from a creator as audio", "value": "4"},
        {"key": "5", "title": "SoundCloud Track, Set, or Likes as Audio", "desc": "Download SoundCloud tracks, playlists, or liked tracks", "value": "5"},
        {"key": "6", "title": "Spotify Track, Album, or Playlist as Audio", "desc": "Download Spotify tracks, playlists, or albums with cover art & ID3 tags", "value": "6"},
        {"key": "0", "title": "[BACK] Return to Main Menu", "desc": "Cancel and go back", "value": "back"},
    ]
    sub_c = interactive_select(
        "[AUDIO] DEDICATED AUDIO DOWNLOAD MODE",
        audio_source_options,
        default_index=0,
        border_style="magenta"
    )
    if not sub_c or sub_c in ("back", "cancel", "0"):
        return

    if sub_c == "1":
        url = ask_input("[bold green]Enter media URL to extract audio[/bold green]")
        if not url:
            return
        out_dir = resolve_output_dir()
        if not out_dir:
            return
        _, _, af, aq = resolve_quality_settings(mode_override="audio")
        plat = "x" if is_x_url(url) else ("youtube" if is_youtube_url(url) else ("tiktok" if is_tiktok_url(url) else ("soundcloud" if is_soundcloud_url(url) else ("reddit" if is_reddit_url(url) else ("facebook" if is_facebook_url(url) else ("pinterest" if is_pinterest_url(url) else ("twitch" if is_twitch_url(url) else ("threads" if is_threads_url(url) else ("spotify" if is_spotify_url(url) else ("instagram" if is_instagram_url(url) else None))))))))))
        c_file = config_mgr.get_effective_cookie_file(plat) if plat else None
        embed_meta = resolve_embed_metadata()
        download_urls([url], output_dir=out_dir, cookie_file=c_file, mode="audio", audio_format=af, audio_quality=aq, embed_metadata=embed_meta, is_bulk=False)
    elif sub_c == "2":
        f_path = resolve_links_file()
        if not f_path:
            return
        out_dir = resolve_output_dir()
        if not out_dir:
            return
        _, _, af, aq = resolve_quality_settings(mode_override="audio")
        embed_meta = resolve_embed_metadata()
        download_from_file(f_path, output_dir=out_dir, mode="audio", audio_format=af, audio_quality=aq, embed_metadata=embed_meta, is_bulk=False)
    elif sub_c == "3":
        c_file = config_mgr.get_effective_cookie_file("youtube")
        pl_url = choose_youtube_playlist_to_download(cookie_file=c_file)
        if not pl_url:
            return
        if ("list=WL" in pl_url or "list=LL" in pl_url) and not c_file:
            c_file = resolve_cookie_file("youtube", required=True)
            if not c_file:
                return
        out_dir = resolve_output_dir()
        if not out_dir:
            return
        _, _, af, aq = resolve_quality_settings(mode_override="audio")
        filters = prompt_smart_filters()
        embed_meta = resolve_embed_metadata()
        download_urls([pl_url], output_dir=out_dir, cookie_file=c_file, mode="audio", audio_format=af, audio_quality=aq, smart_filters=filters, embed_metadata=embed_meta, is_bulk=True)
    elif sub_c == "4":
        user_in = ask_input("[bold green]Enter username or channel URL[/bold green]")
        if not user_in:
            return
        out_dir = resolve_output_dir()
        if not out_dir:
            return
        _, _, af, aq = resolve_quality_settings(mode_override="audio")
        filters = prompt_smart_filters()
        embed_meta = resolve_embed_metadata()
        download_profile(user_in, output_dir=out_dir, mode="audio", audio_format=af, audio_quality=aq, smart_filters=filters, embed_metadata=embed_meta)
    elif sub_c == "5":
        sc_opts = [
            {"key": "1", "title": "Single Track URL", "desc": "Download a single track from SoundCloud", "value": "single"},
            {"key": "2", "title": "Playlist / Set URL", "desc": "Download an entire playlist / album set as audio", "value": "set"},
            {"key": "3", "title": "User Liked Tracks", "desc": "Download all liked tracks of a user or artist", "value": "likes"},
            {"key": "0", "title": "[BACK] Cancel", "desc": "Back", "value": "cancel"},
        ]
        sc_pick = interactive_select("SOUNDCLOUD AUDIO DOWNLOAD", sc_opts, default_index=0, border_style="yellow")
        if not sc_pick or sc_pick == "cancel":
            return
        if sc_pick == "single":
            s_url = ask_input("[bold yellow]Enter SoundCloud track URL[/bold yellow]")
            if not s_url:
                return
            out_dir = resolve_output_dir()
            if not out_dir:
                return
            _, _, af, aq = resolve_quality_settings(mode_override="audio")
            c_file = config_mgr.get_effective_cookie_file("soundcloud")
            embed_meta = resolve_embed_metadata()
            download_urls([s_url], output_dir=out_dir, cookie_file=c_file, mode="audio", audio_format=af, audio_quality=aq, embed_metadata=embed_meta, is_bulk=False)
        elif sc_pick == "set":
            s_url = ask_input("[bold yellow]Enter SoundCloud set / playlist URL[/bold yellow]")
            if not s_url:
                return
            out_dir = resolve_output_dir()
            if not out_dir:
                return
            _, _, af, aq = resolve_quality_settings(mode_override="audio")
            c_file = config_mgr.get_effective_cookie_file("soundcloud")
            filters = prompt_smart_filters()
            embed_meta = resolve_embed_metadata()
            download_urls([s_url], output_dir=out_dir, cookie_file=c_file, mode="audio", audio_format=af, audio_quality=aq, smart_filters=filters, embed_metadata=embed_meta, is_bulk=True)
        elif sc_pick == "likes":
            u_in = ask_input("[bold yellow]Enter SoundCloud username or profile URL (leave empty for authenticated account)[/bold yellow]")
            if u_in is None:
                return
            c_file = resolve_cookie_file("soundcloud", required=(not bool(u_in)))
            if not u_in and not c_file:
                return
            out_dir = resolve_output_dir()
            if not out_dir:
                return
            _, _, af, aq = resolve_quality_settings(mode_override="audio")
            filters = prompt_smart_filters()
            embed_meta = resolve_embed_metadata()
            download_soundcloud_liked_tracks(username_or_url=u_in or None, cookie_file=c_file, output_dir=out_dir, audio_format=af, audio_quality=aq, smart_filters=filters, embed_metadata=embed_meta)
    elif sub_c == "6":
        sp_url = ask_input("[bold green]Enter Spotify track, album, playlist, episode, or show URL[/bold green]")
        if not sp_url:
            return
        out_dir = resolve_output_dir()
        if not out_dir:
            return
        _, _, af, aq = resolve_quality_settings(mode_override="audio")
        c_file = config_mgr.get_effective_cookie_file("spotify")
        filters = prompt_smart_filters()
        embed_meta = resolve_embed_metadata()
        download_spotify_playlist(sp_url, output_dir=out_dir, cookie_file=c_file, audio_format=af, audio_quality=aq, smart_filters=filters, embed_metadata=embed_meta)

    pause_prompt("Press [Enter] or [Esc] to return to main menu...")
