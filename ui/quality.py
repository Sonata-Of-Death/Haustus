"""Quality selectors and pre-flight screen."""
import os
import re
import sys
from datetime import datetime, timedelta

import yt_dlp
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.constants import (
    A7_BRASS,
    A7_HAIRLINE,
    A7_MUTED,
    A7_OK,
    A7_SIGNAL,
    A7_TEXT,
    PLATFORMS_REGISTRY,
)
from core.instances import config_mgr
from ui.components import MenuItem, ask_input, interactive_confirm, interactive_select, select_menu, show_help_overlay
from ui.theme import BOX_STYLES, console, get_key, init_windows_terminal, normalize_hotkey_char, render_screen


def parse_time_range(range_str: str) -> tuple[float, float] | None:
    """Parse time range string into seconds."""
    if not range_str or not isinstance(range_str, str):
        return None
    cleaned = range_str.strip()
    parts = re.split(r"\s*(?:-|to|~)\s*", cleaned, maxsplit=1)
    if len(parts) != 2:
        return None

    def _to_sec(token: str) -> float | None:
        token = token.strip()
        if not token:
            return None
        if re.match(r"^\d+(\.\d+)?$", token):
            return float(token)
        segs = token.split(":")
        if len(segs) == 2:
            try:
                return int(segs[0]) * 60 + float(segs[1])
            except ValueError:
                return None
        elif len(segs) == 3:
            try:
                return int(segs[0]) * 3600 + int(segs[1]) * 60 + float(segs[2])
            except ValueError:
                return None
        return None

    start_s = _to_sec(parts[0])
    end_s = _to_sec(parts[1])
    if start_s is None or end_s is None or start_s < 0 or end_s <= start_s:
        return None
    return (start_s, end_s)

def prompt_time_range(current_range: str = None) -> str | None:
    """Prompt the user for an optional time-range clip (e.g. 01:20-03:45)."""
    console.print("[bold cyan][CLIP] Time-Range Clipping (Partial Video/Audio Download)[/bold cyan]")
    console.print("[dim]Examples: 01:20-03:45  |  00:05:00-00:10:30  |  30-90  |  Leave empty for full media[/dim]")
    raw = ask_input("[bold yellow]Enter time range (start-end) or press Enter for full media[/bold yellow]", default=current_range or "")
    if not raw or not raw.strip():
        return None
    parsed = parse_time_range(raw.strip())
    if not parsed:
        console.print("[bold red][-] Invalid time range format. Keeping full media download.[/bold red]")
        return None
    console.print(f"[bold green][OK] Clip range active:[/bold green] [bold cyan]{raw.strip()} ({parsed[0]:.0f}s -> {parsed[1]:.0f}s)[/bold cyan]")
    return raw.strip()

def estimate_height_size_mb(formats_info: list, height: int, duration: float | None = None) -> str:
    """Estimate file size in MB for a given video height from yt-dlp formats list."""
    if not formats_info:
        return "-"
    best_video_bytes = 0
    best_audio_bytes = 0
    for f in formats_info:
        if not isinstance(f, dict):
            continue
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        f_size = f.get("filesize") or f.get("filesize_approx") or 0
        if not f_size and duration and f.get("tbr"):
            f_size = int((float(f["tbr"]) * 1000 / 8) * float(duration))
        if vcodec and vcodec != "none" and f.get("height") == height:
            if f_size > best_video_bytes:
                best_video_bytes = f_size
        elif (not vcodec or vcodec == "none") and acodec and acodec != "none":
            if f_size > best_audio_bytes:
                best_audio_bytes = f_size

    if best_video_bytes > 0:
        total_bytes = best_video_bytes + (best_audio_bytes if best_audio_bytes > 0 else 0)
        mb = total_bytes / (1024 * 1024)
        if mb >= 1024:
            return f"~{mb / 1024:.2f} GB"
        return f"~{mb:.1f} MB"
    return "-"

def render_media_preview_card(info: dict, url: str = "", platform_name: str = "Media") -> Panel:
    info = info or {}
    title = info.get("title") or url or "Unknown Title"
    uploader = info.get("uploader") or info.get("channel") or info.get("uploader_id") or "-"
    dur = info.get("duration")
    if dur:
        mins, secs = divmod(int(dur), 60)
        hrs, mins = divmod(mins, 60)
        duration_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"
    else:
        duration_str = "-"

    u_date = info.get("upload_date") or ""
    if len(u_date) == 8 and u_date.isdigit():
        upload_date_str = f"{u_date[:4]}-{u_date[4:6]}-{u_date[6:]}"
    else:
        upload_date_str = "-"

    formats_info = info.get("formats") or []
    size_chips = []
    for h in (2160, 1440, 1080, 720, 480, 360):
        sz = estimate_height_size_mb(formats_info, h, duration=dur)
        if sz != "-":
            size_chips.append(f"{h}p ({sz})")

    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(style="bold cyan", width=14)
    grid.add_column(style="white", ratio=1)

    grid.add_row("Title", Text(str(title), style="bold white"))
    grid.add_row("Channel/User", Text(str(uploader), style="yellow"))
    grid.add_row("Platform", Text(str(platform_name), style="cyan"))
    grid.add_row("Duration", Text(duration_str, style="green"))
    grid.add_row("Published", Text(upload_date_str, style="dim white"))
    if size_chips:
        grid.add_row("Est. Sizes", Text("  |  ".join(size_chips), style="bold yellow"))

    return Panel(
        grid,
        title="MEDIA INFO PREVIEW",
        title_align="left",
        box=BOX_STYLES["normal"],
        border_style="cyan",
        padding=(0, 1)
    )

def choose_audio_quality(default_format: str = "mp3", default_quality: str = "192") -> tuple[str, str]:
    init_windows_terminal()
    bitrate_options = [
        ("320", "320 kbps", "Ultra high"),
        ("256", "256 kbps", "Very high"),
        ("192", "192 kbps", "Balanced"),
        ("128", "128 kbps", "Podcasts"),
        ("64",  "64 kbps",  "Voice"),
        ("best", "Best Native", ""),
    ]
    format_options = [
        ("mp3",  "MP3",        "Universal"),
        ("m4a",  "M4A (AAC)",  "Mobile friendly"),
        ("flac", "FLAC",       "Lossless"),
        ("wav",  "WAV",        "Uncompressed"),
        ("opus", "OPUS",       "Ultra efficient"),
    ]

    b_idx = 2
    for i, (b_val, _, _) in enumerate(bitrate_options):
        if b_val == default_quality:
            b_idx = i
            break

    f_idx = 0
    for i, (f_val, _, _) in enumerate(format_options):
        if f_val == default_format.lower():
            f_idx = i
            break

    if not sys.stdin.isatty():
        return bitrate_options[b_idx][0], format_options[f_idx][0]

    bitrate_active = True
    last_lines = 0
    footer_keys = "[Tab] Switch column [Up/Down] Move [Enter] Start [H/?] Help [Esc] Back"

    try:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

        while True:
            cur_fmt_id = format_options[f_idx][0]
            is_lossless = cur_fmt_id in ("flac", "wav")

            t_bit = Table.grid(expand=True, padding=(0, 1))
            t_bit.add_column(width=14)
            t_bit.add_column(ratio=1)

            for i, (b_val, b_lbl, b_desc) in enumerate(bitrate_options):
                ptr = "> " if i == b_idx else "  "
                if is_lossless:
                    st = f"dim {A7_MUTED}"
                    dst = f"dim {A7_MUTED}"
                elif i == b_idx:
                    st = f"bold {A7_SIGNAL}" if bitrate_active else f"bold {A7_TEXT}"
                    dst = f"{A7_BRASS}" if bitrate_active else f"dim {A7_MUTED}"
                else:
                    st = f"{A7_TEXT}" if bitrate_active else f"dim {A7_MUTED}"
                    dst = f"dim {A7_MUTED}"
                t_bit.add_row(Text(f"{ptr}{b_lbl}", style=st), Text(b_desc, style=dst))

            p_bit = Panel(
                t_bit,
                title="1  BITRATE  [ACTIVE]" if (bitrate_active and not is_lossless) else "1  BITRATE",
                title_align="left",
                box=BOX_STYLES["focus"] if (bitrate_active and not is_lossless) else BOX_STYLES["normal"],
                border_style=f"bold {A7_SIGNAL}" if (bitrate_active and not is_lossless) else (A7_HAIRLINE if is_lossless else A7_HAIRLINE)
            )

            t_fmt = Table.grid(expand=True, padding=(0, 1))
            t_fmt.add_column(width=14)
            t_fmt.add_column(ratio=1)
            for i, (f_val, f_lbl, f_desc) in enumerate(format_options):
                ptr = "> " if i == f_idx else "  "
                if i == f_idx:
                    st = f"bold {A7_SIGNAL}" if not bitrate_active else f"bold {A7_TEXT}"
                    dst = f"{A7_BRASS}" if not bitrate_active else f"dim {A7_MUTED}"
                else:
                    st = f"{A7_TEXT}" if not bitrate_active else f"dim {A7_MUTED}"
                    dst = f"dim {A7_MUTED}"
                t_fmt.add_row(Text(f"{ptr}{f_lbl}", style=st), Text(f_desc, style=dst))

            p_fmt = Panel(
                t_fmt,
                title="2  FORMAT  [ACTIVE]" if not bitrate_active else "2  FORMAT",
                title_align="left",
                box=BOX_STYLES["focus"] if not bitrate_active else BOX_STYLES["normal"],
                border_style=f"bold {A7_SIGNAL}" if not bitrate_active else A7_HAIRLINE
            )

            cols = Table.grid(expand=True)
            cols.add_column(ratio=1)
            cols.add_column(ratio=1)
            cols.add_row(p_bit, p_fmt)

            sel_b_label = bitrate_options[b_idx][1] if not is_lossless else "lossless (bitrate ignored)"
            sel_f_label = format_options[f_idx][1]
            out_dir = config_mgr.get_default_output_dir()

            out_text = Text()
            out_text.append(f"{sel_f_label} | {sel_b_label} | cover + tags embedded | {out_dir}\n", style=f"bold {A7_TEXT}")
            if is_lossless:
                out_text.append("FLAC and WAV ignore bitrate; that column is dimmed.", style=f"dim {A7_MUTED}")
            else:
                out_text.append("Audio metadata and thumbnail artwork will be embedded automatically.", style=f"dim {A7_MUTED}")

            p_out = Panel(out_text, title="OUTPUT", title_align="left", box=BOX_STYLES["normal"], border_style=A7_SIGNAL)

            body_grid = Table.grid(expand=True)
            body_grid.add_column(ratio=1)
            body_grid.add_row(cols)
            body_grid.add_row(p_out)

            screen = render_screen("Audio Mode  >  Options", body_grid, footer_keys)

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

            key = normalize_hotkey_char(get_key())
            if key in ("tab", "left", "right", "a", "d"):
                bitrate_active = not bitrate_active
            elif key in ("up", "k", "w"):
                if bitrate_active:
                    b_idx = (b_idx - 1) % len(bitrate_options)
                else:
                    f_idx = (f_idx - 1) % len(format_options)
            elif key in ("down", "j", "s"):
                if bitrate_active:
                    b_idx = (b_idx + 1) % len(bitrate_options)
                else:
                    f_idx = (f_idx + 1) % len(format_options)
            elif key in ("?", "؟", "h", "H"):
                last_lines = show_help_overlay("Audio Mode  >  Options", last_lines)
                continue
            elif key == "enter":
                if last_lines > 0:
                    sys.stdout.write(f"\033[{last_lines}F\033[0J")
                    sys.stdout.flush()
                chosen_b = bitrate_options[b_idx][0]
                chosen_f = format_options[f_idx][0]
                console.print(f"[bold green][OK] Configured Audio Target:[/bold green] [bold cyan]{chosen_f.upper()} @ {chosen_b if chosen_b != 'best' else 'Source Native'} kbps[/bold cyan]\n")
                return chosen_b, chosen_f
            elif key in ("esc", "q", "Q"):
                if last_lines > 0:
                    sys.stdout.write(f"\033[{last_lines}F\033[0J")
                    sys.stdout.flush()
                return default_quality, default_format
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

def choose_bulk_quality() -> tuple[str, str, str, str]:
    options = [
        MenuItem("1", "Best Available [Default]", "Native Max (4K/1080p) - Highest visual fidelity", value="best"),
        MenuItem("2", "1080p Full HD", "Capped at 1080p - Crisp without large 4K file sizes", value="1080"),
        MenuItem("3", "720p HD", "Capped at 720p - High speed, ideal for mobile & laptops", value="720"),
        MenuItem("4", "480p SD", "Capped at 480p - Standard definition, compact storage", value="480"),
        MenuItem("5", "360p Data Saver", "Capped at 360p - Fastest download, lowest storage", value="360"),
        MenuItem("6", "[AUDIO] Audio Only", "Extract audio tracks with custom bitrates (320k-64k)", value="audio"),
    ]

    def _bulk_details(item: MenuItem):
        t = Table.grid(expand=True, padding=(0, 0))
        t.add_column(ratio=1)
        t.add_row(Text(item.label, style="bold white"))
        t.add_row(Text(item.detail, style="dim"))
        t.add_row("")
        t.add_row(Text("Selection Scope", style="bold cyan"))
        t.add_row(Text("  Applies to all items in current batch", style="yellow"))
        t.add_row("")
        t.add_row(Text("Folder", style="bold cyan"))
        t.add_row(Text(f"  {config_mgr.get_default_output_dir()}", style="yellow"))
        return Panel(t, title="SELECTION", title_align="left", box=BOX_STYLES["normal"], border_style="cyan")

    chosen = select_menu(
        title="BULK DOWNLOAD QUALITY SELECTOR",
        items=options,
        breadcrumb="Bulk Download  >  Quality",
        default_index=0,
        details_generator=_bulk_details,
        footer_keys="[Up/Down] Move [Enter] Confirm [1-6] Jump [Esc] Back"
    )

    if chosen == "audio":
        aq, af = choose_audio_quality()
        return "audio", "best", af, aq

    if chosen in ("cancel", "back", "0") or not chosen:
        chosen = "best"

    label = "Best Available" if chosen == "best" else f"{chosen}p"
    console.print(f"[bold green][OK] Bulk video quality applied to all items:[/bold green] [bold cyan]{label}[/bold cyan]\n")
    return "video", chosen, "mp3", "192"

def choose_single_video_quality(url: str, cookie_file: str = None) -> tuple[str, str, str, str]:
    low_url = url.lower()
    if "soundcloud.com" in low_url or "snd.sc" in low_url:
        console.print("[bold yellow][AUDIO] SoundCloud audio track detected.[/bold yellow]")
        aq, af = choose_audio_quality()
        return "audio", "best", af, aq

    if "spotify.com" in low_url or low_url.startswith("spotify:"):
        console.print("[bold green][SPOTIFY] Spotify audio track/collection detected.[/bold green]")
        aq, af = choose_audio_quality()
        return "audio", "best", af, aq

    video_title = None
    uploader = None
    platform_name = "Direct URL"
    duration_val = None
    duration_str = "-"
    upload_date_str = "-"
    formats_info = []
    extracted_info = None

    for p in PLATFORMS_REGISTRY:
        if p["id"] in low_url:
            platform_name = p["name"]
            break

    if any(k in low_url for k in ("youtube.com", "youtu.be")):
        platform_name = "YouTube"

    try:
        inspect_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "remote_components": ["ejs:github"],
            "js_runtimes": {"node": {}},
        }
        if cookie_file and os.path.isfile(cookie_file):
            inspect_opts["cookiefile"] = cookie_file
        with yt_dlp.YoutubeDL(inspect_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                extracted_info = info
                video_title = info.get("title")
                uploader = info.get("uploader") or info.get("channel")
                dur = info.get("duration")
                if dur:
                    duration_val = dur
                    mins, secs = divmod(int(dur), 60)
                    duration_str = f"{mins:02d}:{secs:02d}"
                u_date = info.get("upload_date")
                if u_date and len(u_date) == 8:
                    upload_date_str = f"{u_date[:4]}-{u_date[4:6]}-{u_date[6:]}"
                formats_info = info.get("formats") or []
    except Exception:
        pass

    if extracted_info:
        console.print(render_media_preview_card(extracted_info, url=url, platform_name=platform_name))

    standard_heights = [2160, 1440, 1080, 720, 480, 360]
    height_labels = {
        2160: ("2160p  4K", "VP9 + Opus"),
        1440: ("1440p  2K", "VP9 + Opus"),
        1080: ("1080p  Full HD", "AVC + AAC"),
        720:  ("720p   HD", "AVC + AAC"),
        480:  ("480p   SD", "AVC + AAC"),
        360:  ("360p   Data saver", "AVC + AAC"),
    }

    quality_items = [
        MenuItem("1", "Best available", "auto", extra={"size": "-", "codec": "auto", "res": "best"}, value=("video", "best"))
    ]

    idx = 2
    for h in standard_heights:
        lbl, cdc = height_labels[h]
        sz = estimate_height_size_mb(formats_info, h, duration=duration_val)
        disp_lbl = f"{lbl}  ({sz})" if sz != "-" else lbl
        quality_items.append(MenuItem(
            str(idx),
            disp_lbl,
            cdc,
            extra={"size": sz, "codec": cdc, "res": str(h)},
            value=("video", str(h))
        ))
        idx += 1

    quality_items.append(MenuItem(
        str(idx),
        "[AUDIO] Audio only",
        "next: bitrate",
        extra={"size": "-", "codec": "audio", "res": "audio"},
        value=("audio", "best")
    ))

    def _selection_details(item: MenuItem):
        t = Table.grid(expand=True, padding=(0, 1))
        t.add_column(style=f"dim {A7_MUTED}", width=12)
        t.add_column(style=f"{A7_TEXT}")
        disp_title = video_title or url
        if len(disp_title) > 36:
            disp_title = disp_title[:33] + "..."
        t.add_row("Title", Text(disp_title, style=f"bold {A7_TEXT}"))
        if uploader:
            t.add_row("Channel", Text(uploader, style=f"{A7_BRASS}"))
        t.add_row("Platform", Text(platform_name, style=f"{A7_BRASS}"))
        if duration_str != "-":
            t.add_row("Duration", duration_str)
        if upload_date_str != "-":
            t.add_row("Published", upload_date_str)
        t.add_row("Quality", Text(item.label, style=f"bold {A7_SIGNAL}"))
        if item.extra and item.extra.get("size") and item.extra["size"] != "-":
            t.add_row("Est. Size", item.extra["size"])
        t.add_row("Output", "MP4 merged" if item.value[0] == "video" else "Audio extracted")
        out_f = os.path.basename(config_mgr.get_default_output_dir()) or config_mgr.get_default_output_dir()
        t.add_row("Folder", out_f)
        return Panel(t, title="DETAILS", title_align="left", box=BOX_STYLES["normal"], border_style=A7_SIGNAL)

    chosen_val = select_menu(
        title="QUALITY",
        items=quality_items,
        breadcrumb="Single Video  >  Quality",
        default_index=0,
        details_generator=_selection_details,
        footer_keys="[Up/Down] Move [Enter] Confirm [1-8] Jump [Esc] Back"
    )

    if chosen_val == "cancel" or not chosen_val:
        mode, chosen = "video", "best"
    else:
        mode, chosen = chosen_val

    if mode == "audio":
        aq, af = choose_audio_quality()
        return "audio", "best", af, aq

    label = "Best Available" if chosen == "best" else f"{chosen}p"
    console.print(f"[bold green][OK] Selected video quality:[/bold green] [bold cyan]{label}[/bold cyan]\n")
    return "video", chosen, "mp3", "192"

def prompt_smart_filters() -> dict | None:
    """Prompt the user for optional smart filters (Date, Duration, Item Count)."""
    filter_choice = interactive_select(
        "SMART FILTERS FOR PLAYLISTS & PROFILES",
        [
            {"key": "1", "title": "Download All (No Filters - Default)", "desc": "Download all available items without any restriction", "value": "none"},
            {"key": "2", "title": "Apply Smart Filters", "desc": "Customize Date range, Duration (Shorts/Reels), or Item Count limit", "value": "custom"},
        ],
        default_index=0,
        border_style="cyan"
    )
    if filter_choice in ("none", "cancel", "0", "back"):
        return None

    filters = {}

    date_choice = interactive_select(
        "DATE FILTER",
        [
            {"key": "1", "title": "All Time (No Date Filter - Default)", "desc": "Include posts and videos from any date", "value": "all"},
            {"key": "2", "title": "Last 7 Days", "desc": "Only media uploaded or published within the last 7 days", "value": "7d"},
            {"key": "3", "title": "Last 30 Days", "desc": "Only media uploaded or published within the last 30 days", "value": "30d"},
            {"key": "4", "title": "Custom Date Cutoff", "desc": "Specify custom cutoff date (e.g. YYYYMMDD or YYYY-MM-DD)", "value": "custom"},
        ],
        default_index=0,
        border_style="yellow"
    )
    if date_choice == "7d":
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
        filters["date_after"] = cutoff
        filters["date_label"] = "Last 7 Days"
    elif date_choice == "30d":
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        filters["date_after"] = cutoff
        filters["date_label"] = "Last 30 Days"
    elif date_choice == "custom":
        raw_d = ask_input("[bold yellow]Enter starting date (YYYYMMDD or YYYY-MM-DD)[/bold yellow]")
        if raw_d:
            clean_d = re.sub(r"[^\d]", "", raw_d.strip())
            if len(clean_d) == 8:
                filters["date_after"] = clean_d
                filters["date_label"] = f"After {clean_d}"

    dur_choice = interactive_select(
        "DURATION FILTER",
        [
            {"key": "1", "title": "All Durations (Default)", "desc": "Include short clips, regular videos, and full livestreams", "value": "all"},
            {"key": "2", "title": "Shorts / Reels Only (<= 60 seconds)", "desc": "Only short-form video clips under 1 minute", "value": "shorts"},
            {"key": "3", "title": "Exclude Long Videos (<= 10 minutes)", "desc": "Skip long broadcasts, podcasts, and videos over 10 minutes", "value": "10m"},
            {"key": "4", "title": "Custom Max Duration (seconds)", "desc": "Specify exact maximum duration in seconds", "value": "custom"},
        ],
        default_index=0,
        border_style="yellow"
    )
    if dur_choice == "shorts":
        filters["shorts_only"] = True
        filters["max_duration"] = 60
        filters["dur_label"] = "Shorts / Reels (<= 60s)"
    elif dur_choice == "10m":
        filters["max_duration"] = 600
        filters["dur_label"] = "<= 10 Minutes"
    elif dur_choice == "custom":
        raw_s = ask_input("[bold yellow]Enter maximum duration cap in seconds[/bold yellow]")
        if raw_s and raw_s.strip().isdigit():
            sec_val = int(raw_s.strip())
            filters["max_duration"] = sec_val
            filters["dur_label"] = f"<= {sec_val}s"

    count_choice = interactive_select(
        "ITEM COUNT FILTER",
        [
            {"key": "1", "title": "All Items (No Cap - Default)", "desc": "Download all available videos and posts", "value": "all"},
            {"key": "2", "title": "First 20 Items", "desc": "Cap download batch at the first 20 items", "value": "20"},
            {"key": "3", "title": "First 50 Items", "desc": "Cap download batch at the first 50 items", "value": "50"},
            {"key": "4", "title": "Custom Max Count", "desc": "Specify custom maximum items count", "value": "custom"},
        ],
        default_index=0,
        border_style="yellow"
    )
    if count_choice in ("20", "50"):
        filters["count_limit"] = int(count_choice)
        filters["count_label"] = f"First {count_choice} items"
    elif count_choice == "custom":
        raw_c = ask_input("[bold yellow]Enter maximum number of items to download[/bold yellow]")
        if raw_c and raw_c.strip().isdigit():
            c_val = int(raw_c.strip())
            filters["count_limit"] = c_val
            filters["count_label"] = f"First {c_val} items"

    item_choice = interactive_select(
        "ITEM SELECTION & EXCLUSION FILTER",
        [
            {"key": "1", "title": "All Items [Default]", "desc": "Keep all items matching other filters", "value": "all"},
            {"key": "2", "title": "Specify Items or Range", "desc": "Select specific indices or ranges (e.g. 1, 3, 5-10)", "value": "include"},
            {"key": "3", "title": "Exclude Specific Items", "desc": "Exclude specific video indices (e.g. 2, 4 or ~2, ~4)", "value": "exclude"},
        ],
        default_index=0,
        border_style="yellow"
    )
    if item_choice == "include":
        raw_items = ask_input("[bold yellow]Enter items to include (e.g. 1, 3, 5-8)[/bold yellow]")
        if raw_items and raw_items.strip():
            filters["items"] = raw_items.strip()
            filters["items_label"] = f"Include {raw_items.strip()}"
    elif item_choice == "exclude":
        raw_exc = ask_input("[bold yellow]Enter items to exclude (e.g. 2, 4)[/bold yellow]")
        if raw_exc and raw_exc.strip():
            exc_clean = ",".join(t.strip() if t.strip().startswith("~") else f"~{t.strip()}" for t in raw_exc.split(",") if t.strip())
            filters["items"] = exc_clean
            filters["items_label"] = f"Exclude {raw_exc.strip()}"

    return filters if filters else None

def resolve_embed_metadata() -> bool:
    """Resolve whether cover art and metadata should be embedded into downloaded media."""
    pref = config_mgr.get_default_embed_metadata()
    if pref in (True, "always_yes", "yes"):
        return True
    elif pref in (False, "always_no", "no"):
        return False
    if not sys.stdin.isatty():
        return True
    choice = interactive_select(
        "EMBED METADATA & COVER ART",
        [
            {"key": "1", "title": "Yes (Embed Cover Art & Tags - Recommended)", "desc": "Embed artist, title, album, and thumbnail into downloaded files", "value": True},
            {"key": "2", "title": "No (Raw Media Only)", "desc": "Skip metadata and thumbnail embedding", "value": False},
        ],
        default_index=0,
        border_style="cyan",
    )
    return bool(choice) if choice is not None else True

def resolve_output_dir(prompt_override: bool = False) -> str:
    """Determine destination output directory."""
    default_dir = config_mgr.get_default_output_dir()
    os.makedirs(default_dir, exist_ok=True)
    saved_dirs = config_mgr.get_output_dirs()

    if len(saved_dirs) > 1 and not config_mgr.data.get("default_output_dir"):
        opts = []
        for i, d in enumerate(saved_dirs, 1):
            opts.append({"key": str(i), "title": os.path.basename(d) or d, "desc": d, "value": d})
        opts.append({"key": str(len(opts) + 1), "title": "[CUSTOM] Enter New Folder Path", "desc": "Specify another directory", "value": "custom"})
        sel = interactive_select("SELECT DOWNLOAD DESTINATION DIRECTORY", opts, default_index=0, border_style="cyan")
        if sel != "custom":
            return sel

    console.print(f"[dim][INFO] Default download folder: {default_dir}[/dim]")
    chosen = ask_input("[bold white]Destination directory[/bold white]", default=default_dir)
    if chosen is None:
        return None
    if not chosen:
        chosen = default_dir

    norm_chosen = os.path.abspath(chosen)
    os.makedirs(norm_chosen, exist_ok=True)

    if norm_chosen != default_dir and norm_chosen not in saved_dirs:
        if interactive_confirm(f"Save '{norm_chosen}' for future quick selection?", default=True):
            set_def = interactive_confirm("Set this folder as your primary default?", default=False)
            config_mgr.add_output_dir(norm_chosen, set_as_default=set_def)
            console.print("[bold green][OK] Folder saved to configuration.[/bold green]")

    return norm_chosen

def resolve_links_file() -> str | None:
    """Select links text file for batch operations."""
    def_file = config_mgr.get_default_links_file()
    if def_file and os.path.isfile(def_file):
        console.print(f"[bold green][OK] Using configured default links file:[/bold green] [dim]{def_file}[/dim]")
        return def_file

    saved_files = config_mgr.get_links_files()
    if saved_files:
        opts = []
        for i, f in enumerate(saved_files, 1):
            opts.append({
                "key": str(i),
                "title": os.path.basename(f),
                "desc": f,
                "value": f
            })
        opts.append({"key": str(len(opts) + 1), "title": "[NEW] Enter Another File Path", "desc": "Specify any .txt file", "value": "new"})
        opts.append({"key": "0", "title": "[CANCEL] Cancel", "desc": "Return to menu", "value": "cancel"})
        sel = interactive_select("SELECT LINKS FILE", opts, default_index=0, border_style="green")
        if sel in ("cancel", "0"):
            return None
        if sel != "new":
            return sel

    console.print("[bold cyan]Specify path to your links text file (any name, any location):[/bold cyan]")
    console.print("[dim]Each link must be on a separate line. Mixed Instagram, TikTok, and YouTube URLs supported.[/dim]")
    raw_path = ask_input("[bold green]File path[/bold green]")
    if not raw_path:
        console.print("[bold red][-] No file specified.[/bold red]")
        return None

    norm_path = os.path.abspath(raw_path.strip('\"\''))
    if not os.path.isfile(norm_path):
        console.print(f"[bold red][-] File not found: {norm_path}[/bold red]")
        return None

    if norm_path not in saved_files:
        if interactive_confirm("Save this links file to your quick-access list for future downloads?", default=True):
            set_def = interactive_confirm("Set this file as your default links file (skip asking next time)?", default=False)
            config_mgr.add_links_file(norm_path, set_as_default=set_def)
            console.print("[bold green][OK] Links file saved to configuration.[/bold green]")

    return norm_path

def resolve_quality_settings(mode_override: str = None) -> tuple[str, str, str, str]:
    """Configure video and audio quality preferences."""
    mode = mode_override or config_mgr.get_default_mode()
    v_qual = config_mgr.get_default_video_quality()
    a_fmt = config_mgr.get_default_audio_format()
    a_qual = config_mgr.get_default_audio_quality()

    if not mode:
        mode_opts = [
            {"key": "1", "title": "[VIDEO] Download as Video (with merged audio)", "desc": "MP4 / MKV highest quality", "value": "video"},
            {"key": "2", "title": "[AUDIO] Download as Audio Only", "desc": "MP3, M4A, FLAC, WAV, OPUS", "value": "audio"},
        ]
        mode = interactive_select("SELECT DOWNLOAD TYPE", mode_opts, default_index=0, border_style="cyan")
        if mode == "cancel":
            mode = "video"

    if mode == "audio":
        if not a_qual or not a_fmt:
            prompt_q, prompt_f = choose_audio_quality()
            a_qual = a_qual or prompt_q
            a_fmt = a_fmt or prompt_f
        v_qual = "best"
    else:
        if not v_qual:
            quality_options = [
                {"key": "1", "title": "Best Available (Default)", "desc": "Maximum original resolution (4K / 1080p)", "value": "best"},
                {"key": "2", "title": "4K Ultra HD (2160p)", "desc": "Capped at 3840x2160", "value": "2160"},
                {"key": "3", "title": "2K Quad HD (1440p)", "desc": "Capped at 2560x1440", "value": "1440"},
                {"key": "4", "title": "Full HD (1080p)", "desc": "Standard 1920x1080 (Recommended)", "value": "1080"},
                {"key": "5", "title": "HD (720p)", "desc": "Fast download, 1280x720", "value": "720"},
                {"key": "6", "title": "SD (480p)", "desc": "Low bandwidth, 854x480", "value": "480"},
                {"key": "7", "title": "Low (360p)", "desc": "Smallest file size", "value": "360"},
            ]
            v_qual = interactive_select("SELECT VIDEO RESOLUTION", quality_options, default_index=0, border_style="green")
            if v_qual == "cancel":
                v_qual = "best"
        a_fmt = a_fmt or "mp3"
        a_qual = a_qual or "192"

    return (mode, v_qual, a_fmt, a_qual)

def run_preflight_screen(
    target_label: str,
    platform: str = "auto",
    is_single: bool = False,
    single_url: str = None,
    cookie_file: str = None,
    default_mode: str = None,
) -> dict | None:
    """Display pre-flight inspection and confirmation screen."""
    out_dir = config_mgr.get_default_output_dir()
    os.makedirs(out_dir, exist_ok=True)
    mode = default_mode or config_mgr.get_default_mode() or "video"
    v_qual = config_mgr.get_default_video_quality() or "best"
    a_fmt = config_mgr.get_default_audio_format() or "mp3"
    a_qual = config_mgr.get_default_audio_quality() or "192"
    embed_pref = config_mgr.get_default_embed_metadata()
    embed_meta = False if embed_pref in (False, "always_no", "no") else True
    smart_filters = None
    clip_range = None
    subtitles = False

    if not sys.stdin.isatty():
        return {
            "output_dir": out_dir,
            "mode": mode,
            "video_quality": v_qual,
            "audio_format": a_fmt,
            "audio_quality": a_qual,
            "embed_metadata": embed_meta,
            "smart_filters": smart_filters,
            "clip_range": clip_range,
            "subtitles": subtitles,
        }

    while True:
        q_summary = f"Audio ({a_fmt.upper()} @ {a_qual}k)" if mode == "audio" else (
            "Video (Best Available / 4K)" if v_qual == "best" else f"Video ({v_qual}p Max)"
        )
        filt_summary = "None (All Items)"
        if smart_filters:
            parts = []
            if smart_filters.get("date_label"):
                parts.append(smart_filters["date_label"])
            if smart_filters.get("dur_label"):
                parts.append(smart_filters["dur_label"])
            if smart_filters.get("count_label"):
                parts.append(smart_filters["count_label"])
            if parts:
                filt_summary = " | ".join(parts)

        meta_summary = "Enabled (Cover Art + Tags)" if embed_meta else "Disabled (Raw Media)"
        clip_summary = clip_range if clip_range else "Full Media (No Clip)"
        sub_summary = "Enabled (.srt / .vtt)" if subtitles else "Off"

        items = [
            MenuItem("1", "[START DOWNLOAD NOW]", f"Launch download for {target_label}", group="READY", value="start"),
            MenuItem("F", f"Folder:    {out_dir}", "Change destination folder [F]", group="PRE-FLIGHT CONFIGURATION", value="folder"),
            MenuItem("Q", f"Quality:   {q_summary}", "Change video resolution or audio bitrate [Q]", group="PRE-FLIGHT CONFIGURATION", value="quality"),
            MenuItem("M", f"Metadata:  {meta_summary}", "Toggle cover art & tag embedding [M]", group="PRE-FLIGHT CONFIGURATION", value="metadata"),
            MenuItem("C", f"Clip:      {clip_summary}", "Download a specific time range (e.g. 01:20-03:45) [C]", group="PRE-FLIGHT CONFIGURATION", value="clip"),
            MenuItem("T", f"Subtitles: {sub_summary}", "Toggle downloading/embedding subtitles (.srt/.vtt) [T]", group="PRE-FLIGHT CONFIGURATION", value="subtitles"),
        ]
        if not is_single:
            items.insert(3, MenuItem("S", f"Filters:   {filt_summary}", "Configure Date, Duration, or Count limits [S]", group="PRE-FLIGHT CONFIGURATION", value="filters"))
        items.append(MenuItem("0", "Cancel", "Return to previous menu", group="SYSTEM", danger=True, value="cancel"))

        def _preflight_details(active_item: MenuItem):
            t = Table.grid(expand=True, padding=(0, 1))
            t.add_column(style=f"dim {A7_MUTED}", width=12)
            t.add_column(style=f"{A7_TEXT}", ratio=1)
            t.add_row("Target", Text(str(target_label)[:42], style=f"bold {A7_TEXT}"))
            t.add_row("Platform", Text(str(platform).upper(), style=f"{A7_BRASS}"))
            t.add_row("Folder", Text(os.path.basename(out_dir) or out_dir, style=f"bold {A7_OK}"))
            t.add_row("Quality", Text(q_summary, style=f"bold {A7_SIGNAL}"))
            if not is_single:
                t.add_row("Filters", Text(filt_summary, style=f"{A7_BRASS}"))
            t.add_row("Metadata", Text(meta_summary, style=f"{A7_TEXT}"))
            t.add_row("Clip Range", Text(clip_summary, style=f"{A7_SIGNAL}" if clip_range else f"dim {A7_MUTED}"))
            t.add_row("Subtitles", Text(sub_summary, style=f"bold {A7_OK}" if subtitles else f"dim {A7_MUTED}"))
            return Panel(t, title="PRE-FLIGHT SUMMARY", title_align="left", box=BOX_STYLES["normal"], border_style=A7_SIGNAL)

        choice = select_menu(
            title="UNIFIED PRE-FLIGHT CHECK",
            items=items,
            breadcrumb=f"{target_label[:28]}  >  Pre-Flight",
            default_index=0,
            details_generator=_preflight_details,
            footer_keys="[Enter] Start  [F] Folder  [Q] Quality  [S] Filters  [M] Meta  [C] Clip  [T] Subs  [H/?] Help  [Esc] Cancel"
        )

        if choice in ("cancel", "0", None):
            return None
        elif choice == "start":
            return {
                "output_dir": out_dir,
                "mode": mode,
                "video_quality": v_qual,
                "audio_format": a_fmt,
                "audio_quality": a_qual,
                "embed_metadata": embed_meta,
                "smart_filters": smart_filters,
                "clip_range": clip_range,
                "subtitles": subtitles,
            }
        elif choice == "folder":
            new_dir = resolve_output_dir(prompt_override=True)
            if new_dir:
                out_dir = new_dir
        elif choice == "quality":
            if is_single and single_url:
                mode, v_qual, a_fmt, a_qual = choose_single_video_quality(single_url, cookie_file=cookie_file)
            else:
                mode, v_qual, a_fmt, a_qual = choose_bulk_quality()
        elif choice == "filters":
            smart_filters = prompt_smart_filters()
        elif choice == "metadata":
            embed_meta = not embed_meta
        elif choice == "clip":
            clip_range = prompt_time_range(clip_range)
        elif choice == "subtitles":
            subtitles = not subtitles
