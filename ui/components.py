"""TUI menu and dialog components."""
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable

from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from core.constants import (
    A7_BRASS,
    A7_DANGER,
    A7_HAIRLINE,
    A7_MUTED,
    A7_OK,
    A7_SIGNAL,
    A7_TEXT,
)
from ui.theme import (
    BOX_STYLES,
    PLATFORMS_REGISTRY,
    config_mgr,
    console,
    get_key,
    init_windows_terminal,
    normalize_hotkey_char,
    render_screen,
)


@dataclass
class MenuItem:
    key: str
    label: str
    detail: str
    group: str | None = None
    danger: bool = False
    disabled: bool = False
    value: Any = None
    extra: dict | None = None

def show_help_overlay(breadcrumb: str = "Menu", last_lines: int = 0) -> int:
    """Display keyboard shortcuts help screen."""
    help_grid = Table.grid(expand=True, padding=(0, 2))
    help_grid.add_column(style="bold cyan", width=26)
    help_grid.add_column(style="white", ratio=1)
    help_rows = [
        ("[Up / Down] or [W / S]", "Move highlighted selection up or down"),
        ("[Left / Right] or [A / D]", "Move across grid or switch columns"),
        ("[Enter]", "Open or confirm highlighted option"),
        ("[1-9] / [A-Z]", "Jump directly to option by number or hotkey"),
        ("[H] or [?]", "Show or close this Help screen"),
        ("[/]", "Search / filter long option lists"),
        ("[P] / [S] / [O]", "Live Download: [P] Pause, [S] Skip item, [O] Open folder"),
        ("[Esc] / [Q]", "Return to previous menu or quit"),
    ]
    for k_txt, desc_txt in help_rows:
        help_grid.add_row(Text(k_txt, style=f"bold {A7_SIGNAL}"), Text(desc_txt, style=f"{A7_TEXT}"))

    help_panel = Panel(
        help_grid,
        title="KEYBOARD SHORTCUTS & HELP",
        title_align="left",
        box=BOX_STYLES["focus"],
        border_style=A7_SIGNAL,
        padding=(1, 2),
    )
    screen = render_screen(
        f"{breadcrumb}  >  Help",
        help_panel,
        "[Enter / Esc / H / ?] Close Help & Return to Menu",
    )

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

    while True:
        k = get_key()
        if k in ("enter", "space", "esc", "q", "Q", "h", "H", "?", "؟"):
            break

    return lines

def select_menu(
    title: str,
    items: list[MenuItem],
    breadcrumb: str = "Menu",
    default_index: int = 0,
    details_generator: Callable[[MenuItem], Any] | None = None,
    footer_keys: str | None = None,
    allow_filter: bool = False,
    show_details: bool = True,
    banner: Any = None,
) -> Any:
    init_windows_terminal()
    if not items:
        return "cancel"

    if not sys.stdin.isatty():
        if banner:
            console.print(banner)
        table = Table(
            title=f"[bold {A7_SIGNAL}]{title}[/bold {A7_SIGNAL}]" if title else None,
            box=BOX_STYLES["normal"],
            border_style=A7_SIGNAL,
            show_header=True,
            header_style=f"bold {A7_SIGNAL}",
            padding=(0, 1)
        )
        table.add_column("#", justify="left", style=f"bold {A7_BRASS}", width=5)
        table.add_column("Option", style=f"bold {A7_TEXT}", no_wrap=True)
        table.add_column("Description", style="dim")
        for it in items:
            table.add_row(it.key, it.label, it.detail)
        console.print(table)
        choices_keys = [it.key for it in items]
        def_k = items[default_index].key if 0 <= default_index < len(items) else choices_keys[0]
        try:
            picked = Prompt.ask("[bold cyan]Select option[/bold cyan]", choices=choices_keys, default=def_k)
            for it in items:
                if it.key.upper() == picked.upper():
                    return it.value
        except (EOFError, KeyboardInterrupt):
            pass
        return items[default_index].value if 0 <= default_index < len(items) else items[0].value

    cur_idx = default_index if 0 <= default_index < len(items) else 0
    filter_query = ""
    last_lines = 0

    if footer_keys is None:
        has_letters = any(it.key.upper() in ("A", "B") for it in items)
        jump_hint = "[1-9/A/B] Jump" if has_letters else "[1-9] Jump"
        filt_hint = " [/] Filter" if (allow_filter or len(items) > 9) else ""
        footer_keys = f"[Up/Down] Move [Enter] Open {jump_hint}{filt_hint} [H/?] Help [Esc] Back [Q] Quit"

    try:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

        while True:
            if filter_query:
                visible_items = [it for it in items if filter_query.lower() in it.label.lower() or filter_query.lower() in it.detail.lower()]
                if not visible_items:
                    visible_items = items
            else:
                visible_items = items

            if cur_idx >= len(visible_items):
                cur_idx = max(0, len(visible_items) - 1)

            w = console.width
            is_narrow = (w < 76)
            menu_w = max(34, (w - 4) // 2) if not is_narrow else (w - 2)
            det_w = max(34, w - menu_w - 4) if not is_narrow else (w - 2)

            menu_table = Table.grid(expand=True, padding=(0, 0))
            menu_table.add_column(ratio=1)

            cur_grp = None
            for i, it in enumerate(visible_items):
                if it.group and it.group != cur_grp:
                    cur_grp = it.group
                    if i > 0:
                        menu_table.add_row("")
                    menu_table.add_row(Text(cur_grp, style="bold cyan"))

                is_active = (i == cur_idx)
                ptr = "> " if is_active else "  "
                row_text = Text()
                k_style = f"bold {A7_OK}" if is_active else (f"bold {A7_DANGER}" if it.danger else f"dim {A7_MUTED}")
                lbl_style = f"bold {A7_TEXT}" if is_active else (f"dim {A7_DANGER}" if it.danger else (f"dim {A7_MUTED}" if it.disabled else f"{A7_TEXT}"))
                row_text.append(f"{ptr}{it.key:>2}  ", style=k_style)
                row_text.append(it.label, style=lbl_style)
                menu_table.add_row(row_text)

            menu_panel = Panel(
                menu_table,
                title=f"MENU ({len(visible_items)})" if filter_query else "MENU",
                title_align="left",
                box=BOX_STYLES["normal"],
                border_style=A7_SIGNAL,
                width=menu_w if not is_narrow else None
            )

            active_it = visible_items[cur_idx] if visible_items else None
            if details_generator and active_it:
                det_panel = details_generator(active_it)
            elif active_it and show_details:
                det_table = Table.grid(expand=True, padding=(0, 0))
                det_table.add_column(ratio=1)
                det_table.add_row(Text(active_it.label, style=f"bold {A7_TEXT}"))
                det_table.add_row(Text(active_it.detail or "", style=f"dim {A7_MUTED}"))
                if active_it.extra:
                    det_table.add_row("")
                    for k, v in active_it.extra.items():
                        det_table.add_row(Text(f"  {k:<10} {v}", style=f"{A7_BRASS}"))
                det_panel = Panel(
                    det_table,
                    title="DETAILS",
                    title_align="left",
                    box=BOX_STYLES["normal"],
                    border_style=A7_SIGNAL,
                    width=det_w if not is_narrow else None
                )
            else:
                det_panel = None

            if det_panel and not is_narrow:
                body_grid = Table.grid(expand=True)
                body_grid.add_column(ratio=1)
                body_grid.add_column(ratio=1)
                body_grid.add_row(menu_panel, det_panel)
            elif active_it and is_narrow:
                compact_det = Panel(
                    Text.assemble(
                        ("Active: ", f"dim {A7_MUTED}"),
                        (active_it.label, f"bold {A7_SIGNAL}"),
                        ("  -  ", f"dim {A7_MUTED}"),
                        (active_it.detail or "", f"{A7_TEXT}")
                    ),
                    box=BOX_STYLES["normal"],
                    border_style=A7_SIGNAL,
                    padding=(0, 1)
                )
                body_grid = Table.grid(expand=True)
                body_grid.add_column(ratio=1)
                body_grid.add_row(menu_panel)
                body_grid.add_row(compact_det)
            else:
                body_grid = menu_panel

            if banner:
                outer_grid = Table.grid(expand=True)
                outer_grid.add_column(ratio=1)
                outer_grid.add_row(banner)
                outer_grid.add_row(body_grid)
                screen = render_screen(breadcrumb, outer_grid, footer_keys)
            else:
                screen = render_screen(breadcrumb, body_grid, footer_keys)

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
            if key == "up":
                cur_idx = (cur_idx - 1) % len(visible_items)
            elif key == "down":
                cur_idx = (cur_idx + 1) % len(visible_items)
            elif key == "home":
                cur_idx = 0
            elif key == "end":
                cur_idx = len(visible_items) - 1
            elif key == "pageup":
                cur_idx = max(0, cur_idx - 5)
            elif key == "pagedown":
                cur_idx = min(len(visible_items) - 1, cur_idx + 5)
            elif key == "enter":
                if last_lines > 0:
                    sys.stdout.write(f"\033[{last_lines}F\033[0J")
                    sys.stdout.flush()
                return visible_items[cur_idx].value
            elif key == "esc":
                if filter_query:
                    filter_query = ""
                    continue
                if last_lines > 0:
                    sys.stdout.write(f"\033[{last_lines}F\033[0J")
                    sys.stdout.flush()
                for it in visible_items:
                    if it.key.upper() in ("0", "Q") or str(it.value).lower() in ("0", "exit", "back", "cancel"):
                        return it.value
                return "cancel"
            elif key in ("?", "؟", "h", "H") and not any(it.key.upper() == key.upper() for it in visible_items):
                last_lines = show_help_overlay(breadcrumb, last_lines)
                continue
            elif key == "/" and (allow_filter or len(items) > 9):
                if last_lines > 0:
                    sys.stdout.write(f"\033[{last_lines}F\033[0J")
                    sys.stdout.flush()
                last_lines = 0
                sys.stdout.write("\033[?25h")
                sys.stdout.flush()
                q = ask_input("[bold cyan]Search / Filter options[/bold cyan]")
                sys.stdout.write("\033[?25l")
                sys.stdout.flush()
                if q:
                    filter_query = q.strip()
                    cur_idx = 0
                else:
                    filter_query = ""
                continue
            else:
                # Check explicit menu item hotkey.
                matched_item = None
                for it in visible_items:
                    if it.key.upper() == key.upper():
                        matched_item = it
                        break
                if matched_item is not None:
                    if last_lines > 0:
                        sys.stdout.write(f"\033[{last_lines}F\033[0J")
                        sys.stdout.flush()
                    return matched_item.value
                # Handle navigation and quit keys.
                if key in ("k", "w", "W"):
                    cur_idx = (cur_idx - 1) % len(visible_items)
                elif key in ("j", "s", "S"):
                    cur_idx = (cur_idx + 1) % len(visible_items)
                elif key in ("q", "Q"):
                    if filter_query:
                        filter_query = ""
                        continue
                    if last_lines > 0:
                        sys.stdout.write(f"\033[{last_lines}F\033[0J")
                        sys.stdout.flush()
                    for it in visible_items:
                        if it.key.upper() in ("0", "Q") or str(it.value).lower() in ("0", "exit", "back", "cancel"):
                            return it.value
                    return "cancel"
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

def interactive_select(
    title: str,
    options: list[dict],
    default_index: int = 0,
    border_style: str = A7_SIGNAL,
    show_numbers: bool = True,
    breadcrumb: str | None = None
):
    menu_items = []
    for i, opt in enumerate(options):
        k = opt.get("key", str(i + 1))
        t = opt.get("title", "")
        clean_title = re.sub(r"^\[[A-Z0-9_\-/\s]+\]\s*", "", t)
        desc = opt.get("desc", "")
        val = opt.get("value")
        is_danger = any(w in t.lower() or w in str(val).lower() for w in ("reset", "delete", "remove"))
        menu_items.append(MenuItem(
            key=k,
            label=clean_title,
            detail=desc,
            danger=is_danger,
            value=val
        ))

    b_crumb = breadcrumb or title or "Select Option"
    clean_crumb = re.sub(r"^\[[A-Z0-9_\-/\s]+\]\s*", "", b_crumb)
    return select_menu(
        title=title,
        items=menu_items,
        breadcrumb=clean_crumb,
        default_index=default_index,
        allow_filter=(len(menu_items) > 9)
    )

def select_platform_grid(breadcrumb: str = "Settings  >  Cookies  >  Platform", title: str = "PLATFORMS") -> str | None:
    init_windows_terminal()
    if not sys.stdin.isatty():
        choices = [p["hotkey"] for p in PLATFORMS_REGISTRY]
        table = Table(title="[bold cyan]SELECT PLATFORM[/bold cyan]", box=BOX_STYLES["normal"], border_style="cyan")
        table.add_column("#", width=4)
        table.add_column("Platform", width=20)
        for p in PLATFORMS_REGISTRY:
            table.add_row(p["hotkey"], p["name"])
        console.print(table)
        picked = Prompt.ask("Select platform", choices=choices, default="1")
        for p in PLATFORMS_REGISTRY:
            if p["hotkey"].upper() == picked.upper():
                return p["id"]
        return PLATFORMS_REGISTRY[0]["id"]

    cur_idx = 0
    last_lines = 0
    footer_keys = "[Arrows] Move [Enter] Open [1-9/A/B] Jump [H/?] Help [Esc] Back"

    try:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

        while True:
            grid = Table.grid(expand=True, padding=(0, 1))
            grid.add_column(ratio=1)
            grid.add_column(ratio=1)
            grid.add_column(ratio=1)

            for r in range(4):
                row_cells = []
                for c in range(3):
                    idx = r * 3 + c
                    if idx < len(PLATFORMS_REGISTRY):
                        p = PLATFORMS_REGISTRY[idx]
                        is_active = (idx == cur_idx)
                        b = BOX_STYLES["focus"] if is_active else BOX_STYLES["normal"]
                        b_style = f"bold {A7_OK}" if is_active else A7_SIGNAL

                        profs = config_mgr.get_cookie_profiles(p["id"])
                        def_name = config_mgr.get_default_cookie_profile_name(p["id"])
                        if not profs:
                            status_text = Text("no session", style=f"dim {A7_MUTED}")
                        elif len(profs) == 1:
                            h = def_name or profs[0]["name"]
                            status_text = Text(f"{h}  [DEFAULT]", style=f"bold {A7_OK}") if def_name else Text(f"{h}", style=f"{A7_OK}")
                        else:
                            status_text = Text(f"{len(profs)} profiles", style=f"bold {A7_OK}")

                        card_content = Table.grid(expand=True)
                        card_content.add_row(status_text)
                        card_panel = Panel(
                            card_content,
                            title=f"{p['hotkey']}  {p['name']}",
                            title_align="left",
                            box=b,
                            border_style=b_style
                        )
                        row_cells.append(card_panel)
                    else:
                        row_cells.append("")
                grid.add_row(*row_cells)

            outer_panel = Panel(grid, title=title, title_align="left", box=BOX_STYLES["normal"], border_style=A7_SIGNAL)
            screen = render_screen(breadcrumb, outer_panel, footer_keys)

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
            if key == "left":
                cur_idx = (cur_idx - 1) % len(PLATFORMS_REGISTRY)
            elif key in ("right", "l", "d"):
                cur_idx = (cur_idx + 1) % len(PLATFORMS_REGISTRY)
            elif key in ("up", "k", "w"):
                cur_idx = (cur_idx - 3) % len(PLATFORMS_REGISTRY)
            elif key in ("down", "j", "s"):
                cur_idx = (cur_idx + 3) % len(PLATFORMS_REGISTRY)
            elif key in ("?", "؟", "h", "H"):
                last_lines = show_help_overlay(breadcrumb, last_lines)
                continue
            elif key == "enter":
                if last_lines > 0:
                    sys.stdout.write(f"\033[{last_lines}F\033[0J")
                    sys.stdout.flush()
                return PLATFORMS_REGISTRY[cur_idx]["id"]
            elif key in ("esc", "q", "Q"):
                if last_lines > 0:
                    sys.stdout.write(f"\033[{last_lines}F\033[0J")
                    sys.stdout.flush()
                return None
            else:
                for p in PLATFORMS_REGISTRY:
                    if p["hotkey"].upper() == key.upper():
                        if last_lines > 0:
                            sys.stdout.write(f"\033[{last_lines}F\033[0J")
                            sys.stdout.flush()
                        return p["id"]
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

def interactive_confirm(question: str, default: bool = True) -> bool:
    """Prompt user with interactive yes/no dialog."""
    init_windows_terminal()
    if not sys.stdin.isatty():
        try:
            return Confirm.ask(question, default=default)
        except (EOFError, KeyboardInterrupt):
            return default

    current = 0 if default else 1  # 0: Yes, 1: No
    last_lines = 0

    try:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

        while True:
            t_dialog = Table.grid(expand=True, padding=(0, 2))
            t_dialog.add_column(ratio=1)

            q_text = Text(question, style=f"bold {A7_TEXT}")
            t_dialog.add_row(q_text)
            t_dialog.add_row("")

            btn_grid = Table.grid(expand=True, padding=(0, 2))
            btn_grid.add_column(width=22)
            btn_grid.add_column(width=22)
            btn_grid.add_column(ratio=1)

            yes_active = (current == 0)
            no_active = (current == 1)

            yes_btn = Panel(
                Text("[Y] YES", justify="center", style=f"bold {A7_SIGNAL}" if yes_active else f"dim {A7_MUTED}"),
                box=BOX_STYLES["focus"] if yes_active else BOX_STYLES["normal"],
                border_style=f"bold {A7_SIGNAL}" if yes_active else A7_HAIRLINE
            )
            no_btn = Panel(
                Text("[N] NO", justify="center", style=f"bold {A7_SIGNAL}" if no_active else f"dim {A7_MUTED}"),
                box=BOX_STYLES["focus"] if no_active else BOX_STYLES["normal"],
                border_style=f"bold {A7_SIGNAL}" if no_active else A7_HAIRLINE
            )
            btn_grid.add_row(yes_btn, no_btn, "")
            t_dialog.add_row(btn_grid)

            panel_confirm = Panel(
                t_dialog,
                title="CONFIRMATION REQUIRED",
                title_align="left",
                box=BOX_STYLES["normal"],
                border_style=A7_SIGNAL,
                padding=(1, 2)
            )

            screen = render_screen("Confirmation", panel_confirm, "[Left/Right] Move  [Space/Enter] Confirm  [Y/N] Quick Select")

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
            if key in ("left", "right", "up", "down", "tab", "h", "l", "a", "d"):
                current = 1 - current
            elif key in ("y", "Y"):
                current = 0
                break
            elif key in ("n", "N"):
                current = 1
                break
            elif key == "enter":
                break
            elif key in ("esc", "q"):
                current = 1
                break

    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    if last_lines > 0:
        sys.stdout.write(f"\033[{last_lines}F\033[0J")
        sys.stdout.flush()

    res_str = "Yes" if current == 0 else "No"
    style = f"bold {A7_OK}" if current == 0 else f"dim {A7_MUTED}"
    console.print(f"[{A7_TEXT}]{question}:[/] [{style}]{res_str}[/{style}]")
    return current == 0

def pause_prompt(message: str = "Press [Enter] or [Esc] to return to main menu..."):
    """Wait for user to press Enter, Esc, or any key before continuing."""
    if not sys.stdin.isatty():
        return
    console.print(f"[dim]{message}[/dim]")
    while True:
        key = normalize_hotkey_char(get_key())
        if key in ("enter", "space", "esc", "q", "Q", "h", "H", "?", "؟"):
            break

def ask_input(prompt_text: str, default: str = "") -> str | None:
    init_windows_terminal()
    if not sys.stdin.isatty():
        try:
            val = input(f"{prompt_text}: ").strip()
            return val or (default if default else None)
        except (EOFError, KeyboardInterrupt):
            return None

    if default:
        console.print(f"{prompt_text} [dim](Default: {default})[/dim]: ", end="")
    else:
        console.print(f"{prompt_text}: ", end="")
    sys.stdout.flush()

    buf = []
    if os.name == "nt":
        import msvcrt
        while True:
            ch = msvcrt.getwch()
            if ch == "\x1b":  # ESC key
                console.print("[yellow][Operation cancelled by Esc][/yellow]")
                return None
            elif ch in ("\r", "\n"):
                if msvcrt.kbhit():
                    buf.append("\n")
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                else:
                    console.print()
                    res = "".join(buf).strip().strip('"').strip("'")
                    return res if res else (default if default else "")
            elif ch == "\x08":  # Backspace
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif ch == "\x03":  # Ctrl+C
                console.print("[yellow][Operation cancelled][/yellow]")
                return None
            elif ch in ("\x00", "\xe0"):
                # Handle extended key scan codes.
                msvcrt.getwch()
            elif ch >= " " or ch in "\t":
                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    sys.stdout.write("\r\n\033[33m[Operation cancelled by Esc]\033[0m\r\n")
                    sys.stdout.flush()
                    return None
                elif ch in ("\r", "\n"):
                    sys.stdout.write("\r\n")
                    sys.stdout.flush()
                    res = "".join(buf).strip()
                    return res if res else (default if default else "")
                elif ch in ("\x08", "\x7f"):
                    if buf:
                        buf.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                elif ch == "\x03":
                    sys.stdout.write("\r\n")
                    sys.stdout.flush()
                    return None
                elif ch >= " ":
                    buf.append(ch)
                    sys.stdout.write(ch)
                    sys.stdout.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
