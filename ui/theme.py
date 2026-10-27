"""Theme tokens and terminal helpers."""
import os
import sys
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from core.constants import (
    A7_BRASS,
    A7_DANGER,
    A7_HAIRLINE,
    A7_MUTED,
    A7_OK,
    A7_OPUS,
    A7_SIGNAL,
    A7_TEXT,
    A7_WORLDLINE,
    PLATFORMS_REGISTRY,
)
from core.instances import config_mgr

# Configure UTF-8 console encoding.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (IOError, OSError, AttributeError):
        pass

THEME = Theme({
    "info": f"{A7_BRASS}",
    "ok": f"bold {A7_OK}",
    "done": f"bold {A7_OK}",
    "warn": f"bold {A7_SIGNAL}",
    "error": f"bold {A7_DANGER}",
    "fail": f"bold {A7_DANGER}",
    "audio": f"bold {A7_BRASS}",
    "video": f"bold {A7_SIGNAL}",
    "skip": f"dim {A7_MUTED}",
    "dim": f"dim {A7_MUTED}",
    "accent": f"bold {A7_SIGNAL}",
    "focus": f"bold reverse {A7_SIGNAL}",
})

console = Console(theme=THEME, force_terminal=True, legacy_windows=False)

FFMPEG_EXE = None
try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass

_breadcrumb_stack: list[str] = ["Main Menu"]

def get_box_styles():
    use_ascii = (
        os.environ.get("UI_ASCII", "").strip() == "1"
        or (hasattr(sys.stdout, "encoding") and sys.stdout.encoding and "utf" not in sys.stdout.encoding.lower())
    )
    if use_ascii:
        return {
            "normal": box.ASCII,
            "focus": box.ASCII,
            "double": box.ASCII,
            "heavy": box.ASCII,
            "square": box.ASCII,
        }
    return {
        "normal": box.SQUARE,
        "focus": box.DOUBLE,
        "double": box.DOUBLE,
        "heavy": box.HEAVY,
        "square": box.SQUARE,
    }

def render_tag(tag: str, fixed_width: bool = True) -> Text:
    tag_clean = tag.strip().upper().replace("[", "").replace("]", "")
    padded_map = {
        "INFO": ("[INFO ]", "info"),
        "DONE": ("[DONE ]", "done"),
        "OK":   ("[OK   ]", "ok"),
        "WARN": ("[WARN ]", "warn"),
        "ERROR":("[ERROR]", "error"),
        "FAIL": ("[FAIL ]", "fail"),
        "AUDIO":("[AUDIO]", "audio"),
        "VIDEO":("[VIDEO]", "video"),
        "SKIP": ("[SKIP ]", "skip"),
        "RUN":  ("[RUN  ]", "warn"),
        "WAIT": ("[WAIT ]", "dim"),
        "CONFIRM": ("[CONFIRM]", "error"),
        "ACTIVE":  ("[ACTIVE ]", "accent"),
        "DEFAULT": ("[DEFAULT]", "ok"),
        "PUBLIC":  ("[PUBLIC ]", "warn"),
    }
    unpadded_map = {
        "INFO": ("[INFO]", "info"),
        "DONE": ("[DONE]", "done"),
        "OK":   ("[OK]", "ok"),
        "WARN": ("[WARN]", "warn"),
        "ERROR":("[ERROR]", "error"),
        "FAIL": ("[FAIL]", "fail"),
        "AUDIO":("[AUDIO]", "audio"),
        "VIDEO":("[VIDEO]", "video"),
        "SKIP": ("[SKIP]", "skip"),
        "RUN":  ("[RUN]", "warn"),
        "WAIT": ("[WAIT]", "dim"),
        "CONFIRM": ("[CONFIRM]", "error"),
        "ACTIVE":  ("[ACTIVE]", "accent"),
        "DEFAULT": ("[DEFAULT]", "ok"),
        "PUBLIC":  ("[PUBLIC]", "warn"),
    }
    mapping = padded_map if fixed_width else unpadded_map
    if tag_clean in mapping:
        lbl, st = mapping[tag_clean]
        return Text(lbl, style=st)
    return Text(f"[{tag_clean}]", style=f"bold {A7_SIGNAL}")

def push_breadcrumb(crumb: str):
    _breadcrumb_stack.append(crumb)

def pop_breadcrumb() -> str:
    if len(_breadcrumb_stack) > 1:
        return _breadcrumb_stack.pop()
    return _breadcrumb_stack[0]

def get_current_breadcrumb() -> str:
    return "  >  ".join(_breadcrumb_stack)

def reset_breadcrumb(root: str = "Main Menu"):
    global _breadcrumb_stack
    _breadcrumb_stack = [root]

def render_screen(
    breadcrumb: str,
    body: Any,
    footer_keys: str = "[Up/Down] Move [Enter] Select [Esc] Back",
    status_override: dict | None = None
) -> Table | Panel:
    w = console.width
    if w < 60:
        return Panel(
            Text("Terminal too narrow (< 60 cols). Please enlarge window.", style="bold yellow"),
            box=BOX_STYLES["normal"],
            border_style="yellow"
        )

    head_table = Table.grid(expand=True)
    head_table.add_column(justify="left", ratio=1)
    head_table.add_column(justify="right", width=38)

    crumb_text = Text()
    crumb_text.append("HAUSTUS", style=f"bold {A7_SIGNAL}")
    crumb_text.append("  >  ", style=f"dim {A7_MUTED}")
    crumb_text.append(breadcrumb, style=f"bold {A7_TEXT}")

    chips = Text()
    if FFMPEG_EXE:
        chips.append("FFMPEG ", style=f"dim {A7_MUTED}")
        chips.append("[OK]", style=f"bold {A7_OK}")
    else:
        chips.append("FFMPEG ", style=f"dim {A7_MUTED}")
        chips.append("[MISSING]", style=f"bold {A7_DANGER}")

    chips.append("  ")
    has_any_cookies = any(config_mgr.get_cookie_profiles(p["id"]) for p in PLATFORMS_REGISTRY)
    if has_any_cookies:
        active_handle = None
        for p in PLATFORMS_REGISTRY:
            def_p = config_mgr.get_default_cookie_profile_name(p["id"])
            if def_p:
                active_handle = def_p
                break
        if active_handle:
            chips.append(f"{active_handle}", style=f"bold {A7_OK}")
        else:
            chips.append("SESSION ", style=f"dim {A7_MUTED}")
            chips.append("[ACTIVE]", style=f"bold {A7_OK}")
    else:
        chips.append("SESSION ", style=f"dim {A7_MUTED}")
        chips.append("[PUBLIC]", style=f"bold {A7_BRASS}")

    head_table.add_row(crumb_text, chips)
    header_panel = Panel(head_table, box=BOX_STYLES["normal"], border_style=A7_SIGNAL, padding=(0, 1))

    footer_panel = Panel(
        Text(footer_keys, style=f"dim {A7_MUTED}"),
        box=BOX_STYLES["normal"],
        border_style=A7_HAIRLINE,
        padding=(0, 1)
    )

    screen_grid = Table.grid(expand=True)
    screen_grid.add_column(ratio=1)
    screen_grid.add_row(header_panel)
    screen_grid.add_row(body)
    screen_grid.add_row(footer_panel)
    return screen_grid

def render_banner() -> Panel:
    status_parts = []
    if FFMPEG_EXE:
        status_parts.append(f"[bold {A7_OK}]FFMPEG [OK][/bold {A7_OK}]")
    else:
        status_parts.append(f"[bold {A7_DANGER}]FFMPEG [MISSING][/bold {A7_DANGER}]")

    active_tags = []
    for p in PLATFORMS_REGISTRY:
        if config_mgr.get_cookie_profiles(p["id"]):
            active_tags.append(p["name"])

    if active_tags:
        joined = "/".join(active_tags[:4])
        if len(active_tags) > 4:
            joined += f"+{len(active_tags)-4}"
        status_parts.append(f"[bold {A7_OK}]SESSION [ACTIVE] ({joined})[/bold {A7_OK}]")
    else:
        status_parts.append(f"[dim {A7_BRASS}]SESSION [PUBLIC] (No cookies loaded)[/dim {A7_BRASS}]")

    banner_content = (
        f"[bold {A7_SIGNAL}]┌─┐ ╶─╮[/bold {A7_SIGNAL}]   [dim {A7_MUTED}]A7 · OPUS #{A7_OPUS}[/dim {A7_MUTED}]\n"
        f"[bold {A7_SIGNAL}]├─┤   │[/bold {A7_SIGNAL}]   [bold {A7_TEXT}]HAUSTUS[/bold {A7_TEXT}]\n"
        f"[bold {A7_SIGNAL}]╵ ╵   ╵[/bold {A7_SIGNAL}]   [dim {A7_MUTED}]worldline {A7_WORLDLINE}[/dim {A7_MUTED}]\n\n"
        + "  ".join(status_parts)
    )
    return Panel(banner_content, box=BOX_STYLES["normal"], border_style=A7_SIGNAL, padding=(0, 2))

render_a7_banner = render_banner

def print_banner():
    console.print(render_banner())

def init_windows_terminal():
    """Enable ANSI virtual terminal processing on Windows if supported and set title."""
    if os.name == "nt":
        os.system("")
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW("Haustus")
            kernel32 = ctypes.windll.kernel32
            hStdOut = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode)):
                # Enable virtual terminal processing (0x0004).
                kernel32.SetConsoleMode(hStdOut, mode.value | 0x0004)
        except Exception:
            pass

def clear_terminal():
    """Clear terminal screen and scrollback buffer."""
    if sys.stdout.isatty():
        if os.name == "nt":
            try:
                os.system("cls")
            except (IOError, OSError):
                pass
        try:
            sys.stdout.write("\033[3J\033[2J\033[H")
            sys.stdout.flush()
        except (IOError, OSError):
            pass
        try:
            console.clear(home=True)
        except (IOError, OSError):
            pass

ARABIC_KEY_MAP = {
    "؟": "?",
    "ظ": "/",
    "ض": "q", "َ": "Q",
    "ص": "w", "ً": "W",
    "ث": "e", "ُ": "E",
    "ق": "r", "ٌ": "R",
    "ف": "t",
    "غ": "y", "إ": "Y",
    "ع": "u",
    "ه": "i",
    "خ": "o", "×": "O",
    "ح": "p", "؛": "P",
    "ش": "a", "ِ": "A",
    "س": "s", "ٍ": "S",
    "ي": "d", "]": "D",
    "ب": "f", "[": "F",
    "ا": "h", "أ": "H",
    "ت": "j", "ـ": "J",
    "ن": "k", "،": "K",
    "م": "l",
    "ئ": "z",
    "ء": "x", "ْ": "X",
    "ؤ": "c", "}": "C",
    "ر": "v", "{": "V",
    "لا": "b", "لآ": "B", "لأ": "B",
    "ى": "n", "آ": "N",
    "ة": "m", "’": "M",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
}

def normalize_hotkey_char(ch: str) -> str:
    """Normalize input characters to standard hotkeys."""
    if not ch:
        return ch
    return ARABIC_KEY_MAP.get(ch, ch)

def get_key() -> str:
    """Read single keypress cross-platform."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            mapping = {
                "H": "up", "P": "down", "K": "left", "M": "right",
                "G": "home", "O": "end", "I": "pageup", "Q": "pagedown"
            }
            return mapping.get(ch2, "special")
        elif ch in ("\r", "\n"):
            return "enter"
        elif ch == " ":
            return "space"
        elif ch == "\x1b":
            return "esc"
        elif ch == "\x08":
            return "backspace"
        elif ch == "\t":
            return "tab"
        elif ch == "\x03":
            raise KeyboardInterrupt
        if ch == "ل" and msvcrt.kbhit():
            ch2 = msvcrt.getwch()
            combined = ch + ch2
            if combined in ARABIC_KEY_MAP:
                return ARABIC_KEY_MAP[combined]
            return "g"
        if ch == "ل":
            return "g"
        return normalize_hotkey_char(ch)
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(2)
                if ch2 == "[A":
                    return "up"
                elif ch2 == "[B":
                    return "down"
                elif ch2 == "[C":
                    return "right"
                elif ch2 == "[D":
                    return "left"
                return "esc"
            elif ch in ("\r", "\n"):
                return "enter"
            elif ch == " ":
                return "space"
            elif ch == "\x03":
                raise KeyboardInterrupt
            return normalize_hotkey_char(ch)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def make_progress_bar(percent: float, width: int = 24) -> Text:
    p = max(0.0, min(100.0, float(percent)))
    is_ascii = (os.environ.get("UI_ASCII") == "1")
    filled = int(round((p / 100.0) * width))
    filled = max(0, min(width, filled))
    empty = max(0, width - filled)

    res = Text()
    if is_ascii:
        res.append("=" * filled, style=f"bold {A7_SIGNAL}")
        res.append("-" * empty, style=f"dim {A7_MUTED}")
    else:
        if filled > 0 and filled < width:
            res.append("━" * (filled - 1), style=f"bold {A7_SIGNAL}")
            res.append("╸", style=f"bold {A7_SIGNAL}")
            res.append("─" * empty, style=f"dim {A7_MUTED}")
        elif filled == width:
            res.append("━" * width, style=f"bold {A7_OK}")
        else:
            res.append("─" * width, style=f"dim {A7_MUTED}")

    res.append(f"  {p:>5.1f}%", style=f"bold {A7_TEXT}")
    return res

def print_summary_table(total: int, succeeded: int, skipped: int, failed: int, output_dir: str, failed_urls_list: list | None = None):
    m_grid = Table.grid(expand=True)
    m_grid.add_column(ratio=1)
    m_grid.add_column(ratio=1)
    m_grid.add_column(ratio=1)
    m_grid.add_column(ratio=1)

    p_tot = Panel(Text(str(total), style=f"bold {A7_SIGNAL}", justify="center"), title="TOTAL", title_align="left", box=BOX_STYLES["normal"], border_style=A7_SIGNAL)
    p_don = Panel(Text(str(succeeded), style=f"bold {A7_OK}", justify="center"), title="DONE", title_align="left", box=BOX_STYLES["normal"], border_style=A7_OK)
    p_skp = Panel(Text(str(skipped), style=f"dim {A7_MUTED}", justify="center"), title="SKIPPED", title_align="left", box=BOX_STYLES["normal"], border_style=A7_MUTED)
    fail_style = f"dim {A7_MUTED}" if failed == 0 else f"bold {A7_DANGER}"
    fail_border = A7_MUTED if failed == 0 else A7_DANGER
    p_fai = Panel(Text(str(failed), style=fail_style, justify="center"), title="FAILED", title_align="left", box=BOX_STYLES["normal"], border_style=fail_border)
    m_grid.add_row(p_tot, p_don, p_skp, p_fai)

    issues_text = Text()
    if failed == 0:
        issues_text.append("No failed items.\n", style=f"bold {A7_OK}")
        if skipped > 0:
            issues_text.append("Skipped items were already in history.", style="dim")
        failed_file = os.path.join(output_dir, "failed_urls.txt")
        if os.path.isfile(failed_file) and not failed_urls_list:
            try:
                os.remove(failed_file)
            except OSError:
                pass
    else:
        issues_text.append(f"Encountered {failed} failed or inaccessible item(s).\n", style="bold red")
        if failed_urls_list:
            failed_file = os.path.join(output_dir, "failed_urls.txt")
            try:
                with open(failed_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(failed_urls_list) + "\n")
                issues_text.append(f"Failed URLs saved to: {failed_file}\n", style="yellow")
                issues_text.append("Tip: You can re-run specifically for failed URLs using 'failed_urls.txt'", style="dim")
            except (IOError, OSError):
                pass

    p_iss = Panel(issues_text, title="ISSUES", title_align="left", box=BOX_STYLES["normal"], border_style="cyan")

    dest_grid = Table.grid(expand=True)
    dest_grid.add_column(justify="left", ratio=1)
    dest_grid.add_column(justify="right", width=26)
    dest_path = os.path.abspath(output_dir)
    dest_grid.add_row(dest_path, Text(f"[INFO] {succeeded} files written", style="bold green"))
    p_dst = Panel(dest_grid, title="DESTINATION", title_align="left", box=BOX_STYLES["normal"], border_style="cyan")

    body_grid = Table.grid(expand=True)
    body_grid.add_column(ratio=1)
    body_grid.add_row(m_grid)
    body_grid.add_row(p_iss)
    body_grid.add_row(p_dst)

    screen = render_screen("Download  >  Summary", body_grid, "[Enter] Back to main menu [Esc] Back")
    console.print()
    console.print(screen)
    console.print()

BOX_STYLES = get_box_styles()
