"""Settings and account credentials menu."""
import os
import sys
import time

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.config import ConfigManager
from core.constants import (
    A7_BRASS,
    A7_DANGER,
    A7_MUTED,
    A7_OK,
    A7_SIGNAL,
    A7_TEXT,
)
from core.cookies import (
    detect_account_username,
    prepare_cookies,
    prepare_facebook_cookies,
    prepare_pinterest_cookies,
    prepare_reddit_cookies,
    prepare_soundcloud_cookies,
    prepare_spotify_cookies,
    prepare_threads_cookies,
    prepare_tiktok_cookies,
    prepare_twitch_cookies,
    prepare_x_cookies,
    prepare_youtube_cookies,
    show_cookie_tutorial,
    verify_facebook_session,
    verify_instagram_session,
    verify_pinterest_session,
    verify_reddit_session,
    verify_soundcloud_session,
    verify_spotify_session,
    verify_threads_session,
    verify_tiktok_session,
    verify_twitch_session,
    verify_x_session,
    verify_youtube_session,
)
from ui.components import (
    ask_input,
    interactive_confirm,
    interactive_select,
    pause_prompt,
    select_platform_grid,
)
from ui.theme import (
    BOX_STYLES,
    PLATFORMS_REGISTRY,
    clear_terminal,
    console,
    get_key,
    init_windows_terminal,
    render_screen,
)


def manage_cookies_menu(cfg: ConfigManager):
    """Submenu for multi-profile cookie management."""
    while True:
        clear_terminal()
        plat = select_platform_grid(breadcrumb="Settings  >  Cookies  >  Platform", title="SELECT PLATFORM")
        if not plat or plat in ("back", "cancel", "0"):
            break

        while True:
            profiles = cfg.get_cookie_profiles(plat)
            def_name = cfg.get_default_cookie_profile_name(plat)
            def_str = f"default: {def_name}" if def_name else "no default"
            p_title = f"{plat.upper()} PROFILES ({len(profiles)} active, {def_str})"

            act_opts = [
                {"key": "1", "title": "[ADD] Add New Cookie Profile", "desc": "Import from file path or paste token directly", "value": "add"},
                {"key": "2", "title": "[DEFAULT] Set Default Profile", "desc": "Choose which profile to use automatically", "value": "set_default"},
                {"key": "3", "title": "[EDIT] Rename / Edit Profile", "desc": "Rename existing profile", "value": "edit"},
                {"key": "4", "title": "[DELETE] Delete Cookie Profile", "desc": "Remove profile and its stored cookies", "value": "delete"},
                {"key": "5", "title": "[VERIFY] Verify Session Validity", "desc": "Test connection and authentication status", "value": "verify"},
                {"key": "6", "title": "[TUTORIAL] View How-To Guide", "desc": "Step-by-step retrieval instructions", "value": "tutorial"},
                {"key": "0", "title": "[BACK] Back to Platforms", "desc": "Return to platform selection", "value": "back"},
            ]
            act = interactive_select(
                p_title,
                act_opts,
                default_index=0,
                border_style=A7_SIGNAL,
                breadcrumb=f"Settings  >  Cookies  >  {plat.title()}"
            )
            if act in ("back", "cancel", "0"):
                break

            if act == "add":
                console.print(f"[bold cyan]Paste your {plat.title()} session token / cookie string directly below:[/bold cyan]")
                console.print("[dim](No file needed. The session is saved internally in isolated program storage)[/dim]")
                raw_c = ask_input("> ")
                if not raw_c:
                    continue
                c_path = None
                if plat == "instagram":
                    c_path = prepare_cookies(raw_c, save_profile=False)
                elif plat == "tiktok":
                    c_path = prepare_tiktok_cookies(raw_c, save_profile=False)
                elif plat == "youtube":
                    c_path = prepare_youtube_cookies(raw_c, save_profile=False)
                elif plat in ("x", "twitter"):
                    c_path = prepare_x_cookies(raw_c, save_profile=False)
                elif plat in ("sc", "snd", "soundcloud"):
                    c_path = prepare_soundcloud_cookies(raw_c, save_profile=False)
                elif plat in ("rd", "reddit"):
                    c_path = prepare_reddit_cookies(raw_c, save_profile=False)
                elif plat in ("fb", "facebook"):
                    c_path = prepare_facebook_cookies(raw_c, save_profile=False)
                elif plat in ("pin", "pinterest"):
                    c_path = prepare_pinterest_cookies(raw_c, save_profile=False)
                elif plat in ("ttv", "twitch"):
                    c_path = prepare_twitch_cookies(raw_c, save_profile=False)
                elif plat in ("th", "thread", "threads"):
                    c_path = prepare_threads_cookies(raw_c, save_profile=False)
                elif plat in ("sp", "spotify"):
                    c_path = prepare_spotify_cookies(raw_c, save_profile=False)

                if c_path and os.path.isfile(c_path):
                    console.print(f"[dim][*] Fetching account details from {plat}...[/dim]")
                    detected_user = detect_account_username(plat, c_path)
                    if detected_user:
                        clean_user = detected_user
                        console.print(f"[bold green][OK] Detected account handle:[/bold green] [bold cyan]{clean_user}[/bold cyan]")
                    else:
                        clean_user = f"@{plat}_{len(profiles)+1}"
                        console.print(f"[bold green][OK] Profile registered as:[/bold green] [bold cyan]{clean_user}[/bold cyan]")

                    set_def = interactive_confirm("Set as default profile for this platform?", default=True)

                    with open(c_path, "r", encoding="utf-8", errors="ignore") as f:
                        cookie_content = f.read()
                    cfg.save_internal_session(plat, clean_user, cookie_content, set_as_default=set_def)
                    try:
                        os.remove(c_path)
                    except Exception:
                        pass
                    console.print(f"[bold green][OK] Added profile '{clean_user}' successfully.[/bold green]")
                else:
                    console.print("[bold red][-] Failed to parse cookies.[/bold red]")

            elif act == "set_default":
                if not profiles:
                    console.print("[yellow][!] No profiles configured yet.[/yellow]")
                    continue
                p_opts = [{"key": str(i), "title": p["name"], "desc": "[Default Profile]" if p["name"] == def_name else "[Active Profile]", "value": p["name"]} for i, p in enumerate(profiles, 1)]
                p_opts.append({"key": "0", "title": "[CANCEL] Cancel", "desc": "Cancel", "value": "cancel"})
                chosen = interactive_select("SELECT DEFAULT PROFILE", p_opts, default_index=0, border_style="green")
                if chosen not in ("cancel", "0"):
                    cfg.set_default_cookie_profile(plat, chosen)
                    console.print(f"[bold green][OK] Default profile set to: {chosen}[/bold green]")

            elif act == "edit":
                if not profiles:
                    console.print("[yellow][!] No profiles configured yet.[/yellow]")
                    continue
                p_opts = [{"key": str(i), "title": p["name"], "desc": "[Default Profile]" if p["name"] == def_name else "[Active Profile]", "value": p["name"]} for i, p in enumerate(profiles, 1)]
                p_opts.append({"key": "0", "title": "[CANCEL] Cancel", "desc": "Cancel", "value": "cancel"})
                chosen = interactive_select("SELECT PROFILE TO RENAME", p_opts, default_index=0, border_style="yellow")
                if chosen not in ("cancel", "0"):
                    new_n = ask_input("[bold cyan]Enter new account handle (@username)[/bold cyan]", default=chosen)
                    if new_n and new_n != chosen:
                        clean_n = new_n if new_n.startswith("@") else f"@{new_n}"
                        cfg.edit_cookie_profile_name(plat, chosen, clean_n)
                        console.print(f"[bold green][OK] Renamed '{chosen}' to '{clean_n}'.[/bold green]")

            elif act == "delete":
                if not profiles:
                    console.print("[yellow][!] No profiles configured yet.[/yellow]")
                    continue
                p_opts = [{"key": str(i), "title": p["name"], "desc": "[Default Profile]" if p["name"] == def_name else "[Active Profile]", "value": p["name"]} for i, p in enumerate(profiles, 1)]
                p_opts.append({"key": "0", "title": "[CANCEL] Cancel", "desc": "Cancel", "value": "cancel"})
                chosen = interactive_select("SELECT PROFILE TO DELETE", p_opts, default_index=0, border_style="red")
                if chosen not in ("cancel", "0"):
                    if interactive_confirm(f"Are you sure you want to delete profile '{chosen}'?", default=False):
                        cfg.delete_cookie_profile(plat, chosen)
                        console.print(f"[bold green][OK] Profile '{chosen}' deleted.[/bold green]")

            elif act == "verify":
                if not profiles:
                    console.print("[yellow][!] No profiles configured yet.[/yellow]")
                    continue
                console.print(f"[bold cyan][*] Verifying {plat.upper()} profiles...[/bold cyan]")
                for p in profiles:
                    f = p["file"]
                    if not os.path.isfile(f):
                        console.print(f"  Profile '{p['name']}': [bold red]Session file missing[/bold red]")
                        continue
                    if plat == "instagram":
                        ok, msg = verify_instagram_session(f)
                    elif plat == "tiktok":
                        ok, msg = verify_tiktok_session(f)
                    elif plat == "youtube":
                        ok, msg = verify_youtube_session(f)
                    elif plat in ("x", "twitter"):
                        ok, msg = verify_x_session(f)
                    elif plat in ("sc", "snd", "soundcloud"):
                        ok, msg = verify_soundcloud_session(f)
                    elif plat in ("rd", "reddit"):
                        ok, msg = verify_reddit_session(f)
                    elif plat in ("fb", "facebook"):
                        ok, msg = verify_facebook_session(f)
                    elif plat in ("pin", "pinterest"):
                        ok, msg = verify_pinterest_session(f)
                    elif plat in ("ttv", "twitch"):
                        ok, msg = verify_twitch_session(f)
                    elif plat in ("th", "thread", "threads"):
                        ok, msg = verify_threads_session(f)
                    elif plat in ("sp", "spotify"):
                        ok, msg = verify_spotify_session(f)
                    st = "[bold green][ACTIVE][/bold green]" if ok else "[bold yellow][FAILED][/bold yellow]"
                    console.print(f"  Profile '{p['name']}': {st} - {msg}")
                pause_prompt("Press [Enter] to continue...")

            elif act == "tutorial":
                show_cookie_tutorial(plat)
                pause_prompt("Press [Enter] to return...")

def manage_quality_menu(cfg: ConfigManager):
    """Submenu for pre-configuring default mode and qualities."""
    while True:
        clear_terminal()
        cur_mode = cfg.get_default_mode() or "Prompt Every Time"
        cur_v_q = cfg.get_default_video_quality() or "Prompt Every Time"
        cur_a_fmt = cfg.get_default_audio_format() or "Prompt Every Time"
        cur_a_q = cfg.get_default_audio_quality() or "Prompt Every Time"

        q_opts = [
            {"key": "1", "title": f"Default Download Mode: [{cur_mode.upper()}]", "desc": "Video, Audio, or Prompt Each Time", "value": "mode"},
            {"key": "2", "title": f"Default Video Quality: [{cur_v_q}]", "desc": "Best, 4K, 2K, 1080p, 720p, etc.", "value": "video_quality"},
            {"key": "3", "title": f"Default Audio Format: [{cur_a_fmt.upper()}]", "desc": "MP3, M4A, FLAC, WAV, OPUS", "value": "audio_fmt"},
            {"key": "4", "title": f"Default Audio Bitrate: [{cur_a_q}k]", "desc": "320k, 256k, 192k, 128k, 64k", "value": "audio_q"},
            {"key": "5", "title": "[CLEAR] Clear All Quality Defaults", "desc": "Revert to prompting every time", "value": "clear"},
            {"key": "0", "title": "[BACK] Return to Settings", "desc": "Go back", "value": "back"},
        ]
        q_sel = interactive_select("DEFAULT QUALITY & FORMAT PREFERENCES", q_opts, default_index=0, border_style="green")
        if q_sel in ("back", "cancel", "0"):
            break

        if q_sel == "mode":
            m_opts = [
                {"key": "1", "title": "Prompt Every Time (Default)", "desc": "Ask video or audio on each download", "value": "ask"},
                {"key": "2", "title": "Video Mode Always", "desc": "Download video with merged audio directly", "value": "video"},
                {"key": "3", "title": "Audio Mode Always", "desc": "Download audio only directly", "value": "audio"},
            ]
            m_pick = interactive_select("SELECT DEFAULT MODE", m_opts, default_index=0, border_style=A7_SIGNAL)
            if m_pick != "cancel":
                cfg.set_default_mode(None if m_pick == "ask" else m_pick)
                console.print("[bold green][OK] Mode preference updated.[/bold green]")

        elif q_sel == "video_quality":
            vq_opts = [
                {"key": "1", "title": "Prompt Every Time (Default)", "desc": "Ask resolution for each download", "value": "ask"},
                {"key": "2", "title": "Best Available (Native Max 4K/1080p)", "desc": "Always best quality without asking", "value": "best"},
                {"key": "3", "title": "4K Ultra HD (2160p)", "desc": "Cap at 4K", "value": "2160"},
                {"key": "4", "title": "2K Quad HD (1440p)", "desc": "Cap at 1440p", "value": "1440"},
                {"key": "5", "title": "Full HD (1080p)", "desc": "Cap at 1080p standard", "value": "1080"},
                {"key": "6", "title": "HD (720p)", "desc": "Cap at 720p", "value": "720"},
                {"key": "7", "title": "SD (480p)", "desc": "Cap at 480p", "value": "480"},
                {"key": "8", "title": "Data Saver (360p)", "desc": "Cap at 360p", "value": "360"},
            ]
            vq_pick = interactive_select("SELECT DEFAULT VIDEO QUALITY", vq_opts, default_index=0, border_style="green")
            if vq_pick != "cancel":
                cfg.set_default_video_quality(None if vq_pick == "ask" else vq_pick)
                console.print("[bold green][OK] Video quality preference updated.[/bold green]")

        elif q_sel == "audio_fmt":
            af_opts = [
                {"key": "1", "title": "Prompt Every Time", "desc": "Ask container format each time", "value": "ask"},
                {"key": "2", "title": "MP3", "desc": "Universal compatibility", "value": "mp3"},
                {"key": "3", "title": "M4A (AAC)", "desc": "Apple / modern compatibility", "value": "m4a"},
                {"key": "4", "title": "FLAC", "desc": "Lossless studio quality", "value": "flac"},
                {"key": "5", "title": "WAV", "desc": "Uncompressed lossless", "value": "wav"},
                {"key": "6", "title": "OPUS", "desc": "Ultra efficient modern codec", "value": "opus"},
            ]
            af_pick = interactive_select("SELECT DEFAULT AUDIO FORMAT", af_opts, default_index=0, border_style="magenta")
            if af_pick != "cancel":
                cfg.set_default_audio_format(None if af_pick == "ask" else af_pick)
                console.print("[bold green][OK] Audio format preference updated.[/bold green]")

        elif q_sel == "audio_q":
            aq_opts = [
                {"key": "1", "title": "Prompt Every Time", "desc": "Ask bitrate each time", "value": "ask"},
                {"key": "2", "title": "320 kbps (Audiophile Extreme)", "desc": "Maximum bitrate", "value": "320"},
                {"key": "3", "title": "256 kbps (Studio Quality)", "desc": "Very high fidelity", "value": "256"},
                {"key": "4", "title": "192 kbps (Standard High Quality)", "desc": "Balanced (Recommended)", "value": "192"},
                {"key": "5", "title": "128 kbps (Standard Quality)", "desc": "Compact file size", "value": "128"},
                {"key": "6", "title": "64 kbps (Voice / Podcast Saver)", "desc": "Smallest file size", "value": "64"},
            ]
            aq_pick = interactive_select("SELECT DEFAULT AUDIO BITRATE", aq_opts, default_index=0, border_style="magenta")
            if aq_pick != "cancel":
                cfg.set_default_audio_quality(None if aq_pick == "ask" else aq_pick)
                console.print("[bold green][OK] Audio bitrate preference updated.[/bold green]")

        elif q_sel == "clear":
            cfg.set_default_mode(None)
            cfg.set_default_video_quality(None)
            cfg.set_default_audio_format(None)
            cfg.set_default_audio_quality(None)
            console.print("[bold green][OK] All quality defaults cleared. Program will prompt on each run.[/bold green]")

def manage_folders_menu(cfg: ConfigManager):
    """Submenu for download destination folders."""
    while True:
        clear_terminal()
        def_dir = cfg.get_default_output_dir()
        dirs = cfg.get_output_dirs()

        f_opts = [
            {"key": "1", "title": "[ADD] Add New Download Folder", "desc": "Register another destination path", "value": "add"},
            {"key": "2", "title": "[DEFAULT] Set Default Download Folder", "desc": "Select which folder is used by default", "value": "set_default"},
            {"key": "3", "title": "[REMOVE] Remove Download Folder", "desc": "Remove from registered list", "value": "remove"},
            {"key": "0", "title": "[BACK] Return to Settings", "desc": "Go back", "value": "back"},
        ]
        f_title = f"DESTINATION FOLDERS ({len(dirs)} saved, default: {os.path.basename(def_dir) or def_dir})"
        f_pick = interactive_select(f_title, f_opts, default_index=0, border_style=A7_SIGNAL, breadcrumb="Settings  >  Folders")
        if f_pick in ("back", "cancel", "0"):
            break

        if f_pick == "add":
            raw_p = ask_input("[bold cyan]Enter new directory path[/bold cyan]")
            if raw_p:
                norm_p = os.path.abspath(raw_p.strip('\"\''))
                set_def = interactive_confirm("Set as default download folder?", default=False)
                cfg.add_output_dir(norm_p, set_as_default=set_def)
                console.print(f"[bold green][OK] Registered folder: {norm_p}[/bold green]")
                time.sleep(0.5)

        elif f_pick == "set_default":
            if not dirs:
                continue
            d_opts = [{"key": str(i), "title": os.path.basename(d) or d, "desc": d, "value": d} for i, d in enumerate(dirs, 1)]
            d_opts.append({"key": "0", "title": "[CANCEL] Cancel", "desc": "Cancel", "value": "cancel"})
            chosen = interactive_select("SELECT DEFAULT FOLDER", d_opts, default_index=0, border_style=A7_OK, breadcrumb="Settings  >  Folders  >  Set Default")
            if chosen not in ("cancel", "0"):
                cfg.set_default_output_dir(chosen)
                console.print(f"[bold {A7_OK}][OK] Default folder set to: {chosen}[/bold {A7_OK}]")
                time.sleep(0.5)

        elif f_pick == "remove":
            if len(dirs) <= 1:
                console.print(f"[{A7_MUTED}][!] Cannot remove the only remaining destination folder.[/{A7_MUTED}]")
                pause_prompt("Press [Enter] to continue...")
                continue
            d_opts = [{"key": str(i), "title": os.path.basename(d) or d, "desc": d, "value": d} for i, d in enumerate(dirs, 1)]
            d_opts.append({"key": "0", "title": "[CANCEL] Cancel", "desc": "Cancel", "value": "cancel"})
            chosen = interactive_select("SELECT FOLDER TO REMOVE", d_opts, default_index=0, border_style=A7_DANGER, breadcrumb="Settings  >  Folders  >  Remove")
            if chosen not in ("cancel", "0"):
                cfg.remove_output_dir(chosen)
                console.print(f"[bold green][OK] Removed: {chosen}[/bold green]")
                time.sleep(0.5)

def manage_links_files_menu(cfg: ConfigManager):
    """Submenu for registered links files."""
    while True:
        clear_terminal()
        def_file = cfg.get_default_links_file()
        files = cfg.get_links_files()
        def_name = os.path.basename(def_file) if def_file else "None"

        l_opts = [
            {"key": "1", "title": "[ADD] Add / Register Links File", "desc": "Register any .txt links file on disk", "value": "add"},
            {"key": "2", "title": "[DEFAULT] Set Default Links File", "desc": "Set primary file for automatic bulk downloading", "value": "set_default"},
            {"key": "3", "title": "[CLEAR-DEF] Clear Default Selection", "desc": "Prompt for file choice instead of using default", "value": "clear_default"},
            {"key": "4", "title": "[REMOVE] Remove from Registered List", "desc": "Remove file from quick-access list", "value": "remove"},
            {"key": "0", "title": "[BACK] Return to Settings", "desc": "Go back", "value": "back"},
        ]
        l_title = f"LINKS FILES ({len(files)} registered, default: {def_name})"
        l_pick = interactive_select(l_title, l_opts, default_index=0, border_style=A7_SIGNAL, breadcrumb="Settings  >  Links Files")
        if l_pick in ("back", "cancel", "0"):
            break

        if l_pick == "add":
            raw_f = ask_input(f"[bold {A7_SIGNAL}]Enter path to links text file[/bold {A7_SIGNAL}]")
            if raw_f:
                norm_f = os.path.abspath(raw_f.strip('\"\''))
                if os.path.isfile(norm_f):
                    set_def = interactive_confirm("Set as default links file?", default=False)
                    cfg.add_links_file(norm_f, set_as_default=set_def)
                    console.print(f"[bold {A7_OK}][OK] Registered: {norm_f}[/bold {A7_OK}]")
                    time.sleep(0.5)
                else:
                    console.print(f"[bold {A7_DANGER}][-] File not found: {norm_f}[/bold {A7_DANGER}]")
                    pause_prompt("Press [Enter] to continue...")

        elif l_pick == "set_default":
            if not files:
                console.print(f"[{A7_MUTED}][!] No links files registered yet.[/{A7_MUTED}]")
                pause_prompt("Press [Enter] to continue...")
                continue
            fl_opts = [{"key": str(i), "title": os.path.basename(f), "desc": f, "value": f} for i, f in enumerate(files, 1)]
            fl_opts.append({"key": "0", "title": "[CANCEL] Cancel", "desc": "Cancel", "value": "cancel"})
            chosen = interactive_select("SELECT DEFAULT LINKS FILE", fl_opts, default_index=0, border_style=A7_OK, breadcrumb="Settings  >  Links Files  >  Set Default")
            if chosen not in ("cancel", "0"):
                cfg.set_default_links_file(chosen)
                console.print(f"[bold {A7_OK}][OK] Default links file set to: {chosen}[/bold {A7_OK}]")
                time.sleep(0.5)

        elif l_pick == "clear_default":
            cfg.set_default_links_file(None)
            console.print(f"[bold {A7_OK}][OK] Default links file cleared. Program will prompt next time.[/bold {A7_OK}]")
            time.sleep(0.5)

        elif l_pick == "remove":
            if not files:
                console.print(f"[{A7_MUTED}][!] No files registered.[/{A7_MUTED}]")
                pause_prompt("Press [Enter] to continue...")
                continue
            fl_opts = [{"key": str(i), "title": os.path.basename(f), "desc": f, "value": f} for i, f in enumerate(files, 1)]
            fl_opts.append({"key": "0", "title": "[CANCEL] Cancel", "desc": "Cancel", "value": "cancel"})
            chosen = interactive_select("SELECT FILE TO REMOVE", fl_opts, default_index=0, border_style=A7_DANGER, breadcrumb="Settings  >  Links Files  >  Remove")
            if chosen not in ("cancel", "0"):
                cfg.remove_links_file(chosen)
                console.print(f"[bold {A7_OK}][OK] Removed: {chosen}[/bold {A7_OK}]")
                time.sleep(0.5)

def manage_metadata_menu(cfg: ConfigManager):
    """Submenu for Auto Metadata & Cover Art embedding configuration."""
    status_msg = ""
    while True:
        clear_terminal()
        cur = cfg.get_default_embed_metadata()
        if cur is True:
            cur_desc = "Always Yes"
        elif cur is False:
            cur_desc = "Always No"
        else:
            cur_desc = "Prompt Each Time"

        meta_opts = [
            {"key": "1", "title": "Prompt Every Time [Default]", "desc": "Ask before starting each download batch", "value": "prompt"},
            {"key": "2", "title": "Always Yes", "desc": "Automatically embed cover art & tags into all audio/video without prompting", "value": "always_yes"},
            {"key": "3", "title": "Always No", "desc": "Never embed cover art or metadata (fastest raw files)", "value": "always_no"},
            {"key": "0", "title": "[BACK] Return to Settings Menu", "desc": "Save and return", "value": "back"},
        ]
        bc = f"Settings  >  Metadata{f'  ({status_msg})' if status_msg else ''}"
        pick = interactive_select(
            f"AUTO METADATA CONFIGURATION [Current: {cur_desc}]",
            meta_opts,
            default_index=0,
            border_style=A7_SIGNAL,
            breadcrumb=bc
        )
        if pick in ("back", "cancel", "0"):
            break

        if pick == "prompt":
            cfg.set_default_embed_metadata(None)
            status_msg = "[OK] Set to: Prompt each time"
        elif pick == "always_yes":
            cfg.set_default_embed_metadata(True)
            status_msg = "[OK] Set to: Always embed"
        elif pick == "always_no":
            cfg.set_default_embed_metadata(False)
            status_msg = "[OK] Set to: Never embed"

def manage_speed_limiter_menu(cfg: ConfigManager):
    """Submenu for Bandwidth & Download Speed Limiter configuration."""
    status_msg = ""
    while True:
        clear_terminal()
        cur_spd = cfg.get_default_speed_limit() or "Unlimited"
        spd_opts = [
            {"key": "1", "title": "Unlimited [Default]", "desc": "Maximum bandwidth speed (no throttle)", "value": "unlimited"},
            {"key": "2", "title": "2 MB/s", "desc": "Throttle download speed to 2 Megabytes / second", "value": "2M"},
            {"key": "3", "title": "5 MB/s", "desc": "Throttle download speed to 5 Megabytes / second", "value": "5M"},
            {"key": "4", "title": "10 MB/s", "desc": "Throttle download speed to 10 Megabytes / second", "value": "10M"},
            {"key": "5", "title": "Custom Limit", "desc": "Specify custom rate limit (e.g. 500K, 3M, 15M)", "value": "custom"},
            {"key": "0", "title": "[BACK] Return to Settings Menu", "desc": "Save and return", "value": "back"},
        ]
        bc = f"Settings  >  Speed Limiter{f'  ({status_msg})' if status_msg else ''}"
        pick = interactive_select(
            f"BANDWIDTH SPEED LIMITER [Current: {cur_spd}]",
            spd_opts,
            default_index=0,
            border_style=A7_SIGNAL,
            breadcrumb=bc
        )
        if pick in ("back", "cancel", "0"):
            break

        if pick == "unlimited":
            cfg.set_default_speed_limit(None)
            status_msg = "[OK] Speed limit: Unlimited"
        elif pick in ("2M", "5M", "10M"):
            cfg.set_default_speed_limit(pick)
            status_msg = f"[OK] Speed limit: {pick}/s"
        elif pick == "custom":
            val = ask_input("[bold green]Enter custom speed limit (e.g. 500K, 2M, 8M)[/bold green]")
            if val and val.strip():
                clean_val = val.strip().upper()
                cfg.set_default_speed_limit(clean_val)
                status_msg = f"[OK] Speed limit: {clean_val}"

def manage_archive_menu(cfg: ConfigManager):
    """Submenu for Download History & Duplicate Detection preferences."""
    status_msg = ""
    while True:
        clear_terminal()
        cur_bulk = cfg.get_archive_bulk_mode()
        cur_single = cfg.get_archive_single_mode()
        cur_miss = cfg.get_archive_missing_policy()

        bulk_desc = {"always": "Always Active [Default]", "disabled": "Disabled", "prompt": "Prompt Each Time"}.get(cur_bulk, cur_bulk)
        single_desc = {"disabled": "Disabled [Default]", "always": "Always Active", "prompt": "Prompt Each Time"}.get(cur_single, cur_single)
        miss_desc = {"prompt": "Prompt Each Time [Default]", "skip": "Keep Deleted (Skip)", "redownload": "Always Re-download"}.get(cur_miss, cur_miss)

        arch_opts = [
            {"key": "1", "title": f"Bulk & Collections History [{bulk_desc}]", "desc": "Playlists, channels, profiles, saved media, reposts (.download_history.txt)", "value": "bulk"},
            {"key": "2", "title": f"Single & Direct Downloads History [{single_desc}]", "desc": "Single video download, direct URL paste, links files", "value": "single"},
            {"key": "3", "title": f"Missing / Deleted File Policy [{miss_desc}]", "desc": "Behavior when an item is in history but its file was deleted from disk", "value": "missing"},
            {"key": "0", "title": "[BACK] Return to Settings Menu", "desc": "Save and return", "value": "back"},
        ]
        bc = f"Settings  >  History{f'  ({status_msg})' if status_msg else ''}"
        pick = interactive_select(
            "DOWNLOAD HISTORY & ARCHIVE SETTINGS",
            arch_opts,
            default_index=0,
            border_style=A7_SIGNAL,
            breadcrumb=bc
        )
        if pick in ("back", "cancel", "0"):
            break

        if pick == "bulk":
            sub_opts = [
                {"key": "1", "title": "Always Active [Default]", "desc": "Automatically record and skip previously downloaded collection items", "value": "always"},
                {"key": "2", "title": "Disabled", "desc": "Do not check or record download history for bulk collections", "value": "disabled"},
                {"key": "3", "title": "Prompt Each Time", "desc": "Ask before starting each collection/channel/playlist task", "value": "prompt"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Keep current setting", "value": "cancel"},
            ]
            sub_pick = interactive_select("BULK DOWNLOADS HISTORY MODE", sub_opts, default_index=0, border_style=A7_SIGNAL, breadcrumb="Settings  >  History  >  Bulk")
            if sub_pick not in ("cancel", "back", "0"):
                cfg.set_archive_bulk_mode(sub_pick)
                status_msg = f"[OK] Bulk history: {sub_pick}"

        elif pick == "single":
            sub_opts = [
                {"key": "1", "title": "Disabled [Default]", "desc": "Do not skip single video or direct URL downloads based on history", "value": "disabled"},
                {"key": "2", "title": "Always Active", "desc": "Check and skip single downloads if already recorded in history", "value": "always"},
                {"key": "3", "title": "Prompt Each Time", "desc": "Ask before downloading single videos or direct links", "value": "prompt"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Keep current setting", "value": "cancel"},
            ]
            sub_pick = interactive_select("SINGLE DOWNLOADS HISTORY MODE", sub_opts, default_index=0, border_style=A7_SIGNAL, breadcrumb="Settings  >  History  >  Single")
            if sub_pick not in ("cancel", "back", "0"):
                cfg.set_archive_single_mode(sub_pick)
                status_msg = f"[OK] Single history: {sub_pick}"

        elif pick == "missing":
            sub_opts = [
                {"key": "1", "title": "Prompt Each Time [Default]", "desc": "Ask whether to re-download or keep deleted when missing file detected", "value": "prompt"},
                {"key": "2", "title": "Keep Deleted (Always Skip)", "desc": "Assume deleted files were removed intentionally and never re-download", "value": "skip"},
                {"key": "3", "title": "Always Re-download", "desc": "Automatically re-download missing files without asking", "value": "redownload"},
                {"key": "0", "title": "[BACK] Cancel", "desc": "Keep current setting", "value": "cancel"},
            ]
            sub_pick = interactive_select("MISSING / DELETED FILE POLICY", sub_opts, default_index=0, border_style=A7_SIGNAL, breadcrumb="Settings  >  History  >  Missing Policy")
            if sub_pick not in ("cancel", "back", "0"):
                cfg.set_archive_missing_policy(sub_pick)
                status_msg = f"[OK] Missing policy: {sub_pick}"

def render_current_settings_panel(cfg: ConfigManager, print_to_console: bool = True):
    t_stor = Table.grid(expand=True, padding=(0, 1))
    t_stor.add_column(style=f"dim {A7_MUTED}", width=16)
    t_stor.add_column(style=f"{A7_TEXT}")
    t_stor.add_row("Primary folder", cfg.get_default_output_dir())
    t_stor.add_row("Links files", f"{len(cfg.get_links_files())} registered")
    t_stor.add_row("Default mode", cfg.get_default_mode() or "Prompt each time")
    t_stor.add_row("Video quality", cfg.get_default_video_quality() or "Prompt each time")
    af = (cfg.get_default_audio_format() or "Prompt").upper()
    aq = cfg.get_default_audio_quality()
    t_stor.add_row("Audio preset", f"{af} ({aq}k)" if aq else af)
    p_stor = Panel(t_stor, title="STORAGE", title_align="left", box=BOX_STYLES["normal"], border_style=A7_SIGNAL)

    t_beh = Table.grid(expand=True, padding=(0, 1))
    t_beh.add_column(style=f"dim {A7_MUTED}", width=16)
    t_beh.add_column(style=f"{A7_TEXT}")
    m_val = cfg.get_default_embed_metadata()
    m_str = "Always embed" if m_val is True else ("Never embed" if m_val is False else "Prompt every time")
    t_beh.add_row("Metadata", m_str)
    t_beh.add_row("Speed limit", cfg.get_default_speed_limit() or "Unlimited")
    t_beh.add_row("History bulk", cfg.get_archive_bulk_mode().capitalize())
    t_beh.add_row("History single", cfg.get_archive_single_mode().capitalize())
    t_beh.add_row("Missing file", cfg.get_archive_missing_policy().capitalize())
    p_beh = Panel(t_beh, title="BEHAVIOUR", title_align="left", box=BOX_STYLES["normal"], border_style=A7_SIGNAL)

    top_grid = Table.grid(expand=True)
    top_grid.add_column(ratio=1)
    top_grid.add_column(ratio=1)
    top_grid.add_row(p_stor, p_beh)

    active_count = sum(1 for p in PLATFORMS_REGISTRY if cfg.get_cookie_profiles(p["id"]))
    t_acc = Table.grid(expand=True, padding=(0, 1))
    t_acc.add_column(ratio=1)
    t_acc.add_column(ratio=1)
    t_acc.add_column(ratio=1)
    t_acc.add_column(ratio=1)

    acc_items = []
    for p in PLATFORMS_REGISTRY:
        profs = cfg.get_cookie_profiles(p["id"])
        def_p = cfg.get_default_cookie_profile_name(p["id"])
        if profs:
            handle = def_p or profs[0]["name"]
            acc_items.append(f"{p['name']} [{handle}]")
        else:
            acc_items.append(f"{p['name']} [--]")

    for r in range(3):
        row_c = acc_items[r*4 : (r+1)*4]
        while len(row_c) < 4:
            row_c.append("")
        t_acc.add_row(*row_c)

    p_acc = Panel(
        t_acc,
        title=f"ACCOUNTS   {active_count} of {len(PLATFORMS_REGISTRY)} signed in",
        title_align="left",
        box=BOX_STYLES["normal"],
        border_style=A7_SIGNAL
    )

    combined = Table.grid(expand=True)
    combined.add_column(ratio=1)
    combined.add_row(top_grid)
    combined.add_row(p_acc)

    if print_to_console:
        console.print(top_grid)
        console.print(p_acc)
    return combined

def manage_configuration_menu(cfg: ConfigManager):
    init_windows_terminal()
    settings_actions = [
        {"key": "1", "label": "Cookies", "desc": "Accounts & session cookies for 11 platforms", "danger": False},
        {"key": "2", "label": "Quality", "desc": "Default mode, video quality, audio format & bitrate", "danger": False},
        {"key": "3", "label": "Folders", "desc": "Destination directories & default output folder", "danger": False},
        {"key": "4", "label": "Links files", "desc": "Registered .txt links lists for quick batch download", "danger": False},
        {"key": "5", "label": "Metadata", "desc": "Cover art and ID3 metadata tags embedding preferences", "danger": False},
        {"key": "6", "label": "Speed", "desc": "Bandwidth speed limiter & rate throttling", "danger": False},
        {"key": "7", "label": "History", "desc": "Download history tracking & duplicate skipping", "danger": False},
        {"key": "8", "label": "Guides", "desc": "Platform cookie extraction step-by-step tutorials", "danger": False},
        {"key": "0", "label": "Back", "desc": "Return to Main Navigation Menu", "danger": False},
        {"key": "9", "label": "Reset", "desc": "Reset all configuration settings to factory defaults", "danger": True},
    ]

    if not sys.stdin.isatty():
        render_current_settings_panel(cfg, print_to_console=True)
        return

    cur_act = 0
    last_lines = 0
    footer_keys = "[Arrows/WASD] Move  [Enter] Select  [1-9/0] Jump  [?] Help  [Esc] Back"

    try:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

        while True:
            settings_summary = render_current_settings_panel(cfg, print_to_console=False)

            t_act = Table.grid(expand=True, padding=(0, 1))
            for _ in range(5):
                t_act.add_column(ratio=1)

            for row_idx in range(2):
                row_cells = []
                for col_idx in range(5):
                    idx = row_idx * 5 + col_idx
                    if idx < len(settings_actions):
                        act = settings_actions[idx]
                        is_active = (idx == cur_act)
                        ptr = "> " if is_active else "  "
                        if act.get("danger"):
                            if is_active:
                                cell_text = Text(f"{ptr}[{act['key']}] {act['label']} [CONFIRM]", style=f"bold {A7_DANGER}")
                            else:
                                cell_text = Text(f"{ptr}[{act['key']}] {act['label']}", style=f"dim {A7_DANGER}")
                        else:
                            if is_active:
                                cell_text = Text(f"{ptr}[{act['key']}] {act['label']}", style=f"bold {A7_SIGNAL}")
                            else:
                                cell_text = Text(f"{ptr}[{act['key']}] {act['label']}", style=f"{A7_TEXT}")
                        row_cells.append(cell_text)
                    else:
                        row_cells.append("")
                t_act.add_row(*row_cells)

            active_item = settings_actions[cur_act]
            desc_text = Text.assemble(
                ("Selected: ", f"dim {A7_MUTED}"),
                (f"[{active_item['key']}] {active_item['label']}", f"bold {A7_SIGNAL}"),
                ("  -  ", f"dim {A7_MUTED}"),
                (active_item["desc"], f"{A7_BRASS}" if active_item.get("danger") else f"{A7_TEXT}")
            )

            act_box = Table.grid(expand=True)
            act_box.add_column(ratio=1)
            act_box.add_row(t_act)
            act_box.add_row("")
            act_box.add_row(desc_text)

            p_act = Panel(
                act_box,
                title="ACTIONS",
                title_align="left",
                box=BOX_STYLES["focus"],
                border_style=A7_SIGNAL
            )

            body_grid = Table.grid(expand=True)
            body_grid.add_column(ratio=1)
            body_grid.add_row(settings_summary)
            body_grid.add_row(p_act)

            screen = render_screen("Settings", body_grid, footer_keys)

            with console.capture() as cap:
                console.print(screen)

            rendered_text = cap.get()
            lines = rendered_text.count("\n")

            if last_lines > 0:
                out_buf = f"\033[{last_lines}F\033[0J" + rendered_text
            else:
                out_buf = rendered_text

            sys.stdout.write(out_buf)
            sys.stdout.flush()
            last_lines = lines

            key = get_key()
            if key in ("right", "d", "l", "tab"):
                cur_act = (cur_act + 1) % len(settings_actions)
            elif key in ("left", "a", "h"):
                cur_act = (cur_act - 1) % len(settings_actions)
            elif key in ("down", "s", "j"):
                if cur_act < 5:
                    cur_act = cur_act + 5
                else:
                    cur_act = cur_act - 5
            elif key in ("up", "w", "k"):
                if cur_act >= 5:
                    cur_act = cur_act - 5
                else:
                    cur_act = cur_act + 5
            elif key in ("esc", "q", "Q"):
                if last_lines > 0:
                    sys.stdout.write(f"\033[{last_lines}F\033[0J")
                    sys.stdout.flush()
                break
            elif key == "?":
                if last_lines > 0:
                    sys.stdout.write(f"\033[{last_lines}F\033[0J")
                    sys.stdout.flush()
                last_lines = 0
                help_grid = Table.grid(expand=True, padding=(0, 2))
                help_grid.add_column(style="bold cyan", width=18)
                help_grid.add_column(style="white")
                help_grid.add_row("[Arrows] / [WASD]", "Navigate between settings actions")
                help_grid.add_row("[Enter] / [Space]", "Open selected configuration submenu")
                help_grid.add_row("[1-9] / [0]", "Jump directly to numbered action")
                help_grid.add_row("[Esc] / [Q]", "Return to Main Menu")
                help_grid.add_row("[?]", "Show this help screen")
                console.print(Panel(help_grid, title="SETTINGS SHORTCUTS", box=BOX_STYLES["focus"], border_style=A7_SIGNAL))
                pause_prompt("Press [Enter] or [Esc] to resume...")
                continue
            else:
                selected_key = None
                if key in ("enter", "space"):
                    selected_key = settings_actions[cur_act]["key"]
                else:
                    for idx, act in enumerate(settings_actions):
                        if act["key"] == key:
                            selected_key = key
                            cur_act = idx
                            break

                if selected_key is None:
                    continue

                if last_lines > 0:
                    sys.stdout.write(f"\033[{last_lines}F\033[0J")
                    sys.stdout.flush()
                last_lines = 0

                if selected_key in ("0", "back"):
                    break
                elif selected_key == "1":
                    manage_cookies_menu(cfg)
                elif selected_key == "2":
                    manage_quality_menu(cfg)
                elif selected_key == "3":
                    manage_folders_menu(cfg)
                elif selected_key == "4":
                    manage_links_files_menu(cfg)
                elif selected_key == "5":
                    manage_metadata_menu(cfg)
                elif selected_key == "6":
                    manage_speed_limiter_menu(cfg)
                elif selected_key == "7":
                    manage_archive_menu(cfg)
                elif selected_key == "8":
                    plat_choice = select_platform_grid(breadcrumb="Settings  >  Tutorials", title="SELECT TUTORIAL")
                    if plat_choice:
                        show_cookie_tutorial(plat_choice)
                        pause_prompt()
                elif selected_key == "9":
                    if interactive_confirm("Are you sure you want to RESET all configuration settings?", default=False):
                        cfg.reset_to_defaults()
                        console.print("[bold green][OK] Configuration reset to defaults.[/bold green]")
                        pause_prompt()

                clear_terminal()
                last_lines = 0

    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
