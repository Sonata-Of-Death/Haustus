"""Live download progress dashboard."""
import os
import re
import subprocess
import sys
import threading
import time

from rich.console import Console
from rich.panel import Panel
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
from ui.components import interactive_confirm
from ui.theme import BOX_STYLES, console, make_progress_bar, normalize_hotkey_char


class SkipItemRequested(Exception):
    """Raised when the user presses [S] in the live dashboard to skip the active item."""
    pass

class YtdlQuietLogger:
    """Quiet logger for yt-dlp."""
    def __init__(self, dashboard=None):
        self.dashboard = dashboard

    def debug(self, msg: str):
        pass

    def info(self, msg: str):
        if not msg:
            return
        clean = msg.strip()
        if clean.startswith("[download]") or "ETA" in clean:
            return
        if self.dashboard and clean:
            self.dashboard.add_log("[INFO]", clean)

    def warning(self, msg: str):
        if not msg:
            return
        clean = msg.strip()
        if clean.startswith("[download]") or "--paths is ignored" in clean:
            return
        if self.dashboard and clean:
            self.dashboard.add_log("[WARN]", clean)

    def error(self, msg: str):
        if not msg:
            return
        clean = msg.strip()
        if "JSONDecodeError" in clean or "Failed to parse JSON" in clean:
            return
        if self.dashboard and clean:
            self.dashboard.add_log("[FAIL]", clean)

def check_cancel_requested() -> bool:
    """Check if Esc key was pressed. If so, prompt confirmation before aborting."""
    if os.name == "nt":
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch == "\x1b":  # ESC key
                console.print("[bold yellow][!] [ESC] Detected: Process pause / abort requested.[/bold yellow]")
                while msvcrt.kbhit():
                    msvcrt.getwch()
                if interactive_confirm("Are you sure you want to abort the current download process?", default=False):
                    console.print("[bold red][CANCELLED] Download aborted by user.[/bold red]")
                    return True
                else:
                    console.print("[bold green][RESUMING] Download continuing...[/bold green]\n")
    return False

def interruptible_sleep(duration: float) -> bool:
    """Sleep with cancellation check. Returns True if cancelled."""
    if duration <= 0:
        return False
    step = 0.1
    elapsed = 0.0
    while elapsed < duration:
        if check_cancel_requested():
            return True
        time.sleep(min(step, duration - elapsed))
        elapsed += step
    return False

class RichLiveDownloadDashboard:
    """Live download progress dashboard."""
    def __init__(self, console_inst: Console):
        self.console = console_inst
        self._lock = threading.RLock()
        self._progress = None
        self._queue = []
        self._current_filename = None
        self._current_title = None
        self._platform = ""
        self._mode = "VIDEO"
        self._quality = "best"
        self._total_items = 1
        self._current_item_idx = 1
        self._done_count = 0
        self._skip_count = 0
        self._fail_count = 0
        self._speed_str = "--.- MB/s"
        self._eta_str = "--:--"
        self._batch_eta_str = "--:--"
        self._batch_start_time = 0.0
        self._size_str = "- / -"
        self._percent = 0.0
        self._stage = "download"
        self._logs = []
        self._last_lines = 0
        self._last_render_time = 0.0
        self._orig_print = None
        self._in_capture = False
        self._output_dir = None
        self._paused = False
        self._skip_current = False
        self._last_calc_speed = 0.0
        self._last_bytes = 0
        self._last_time = 0.0
        self._running = False

    def set_output_dir(self, output_dir: str):
        with self._lock:
            self._output_dir = output_dir

    def open_output_folder(self) -> bool:
        target = self._output_dir
        if not target or not os.path.isdir(target):
            self.add_log("[WARN]", "Output folder not available yet")
            self.refresh(force=True)
            return False
        try:
            abs_target = os.path.abspath(target)
            if os.name == "nt" and hasattr(os, "startfile"):
                os.startfile(abs_target)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", abs_target])
            else:
                subprocess.Popen(["xdg-open", abs_target])
            self.add_log("[INFO]", f"Opened folder: {os.path.basename(abs_target) or abs_target}")
            self.refresh(force=True)
            return True
        except Exception as e:
            self.add_log("[WARN]", f"Could not open folder: {e}")
            self.refresh(force=True)
            return False

    def request_skip(self):
        with self._lock:
            self._skip_current = True

    def poll_live_keys(self):
        """Non-blocking hotkey handler for [P] Pause/Resume, [S] Skip, [O] Open folder."""
        if self._skip_current:
            self._skip_current = False
            raise SkipItemRequested("Skipped by user hotkey [S]")

        if os.name != "nt" or not sys.stdin.isatty():
            return

        import msvcrt
        while msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                if msvcrt.kbhit():
                    msvcrt.getwch()
                continue
            low = normalize_hotkey_char(ch).lower()
            if low == "s":
                self._skip_current = False
                self.add_log("[SKIP]", "Skipping current item ([S] pressed)...")
                self.refresh(force=True)
                raise SkipItemRequested("Skipped by user hotkey [S]")
            elif low == "o":
                self.open_output_folder()
            elif low == "p":
                self._paused = not self._paused
                if self._paused:
                    self.add_log("[WARN]", "PAUSED - Press [P] to resume or [S] to skip")
                    self.refresh(force=True)
                    while self._paused:
                        time.sleep(0.1)
                        if msvcrt.kbhit():
                            pch = msvcrt.getwch()
                            if pch in ("\x00", "\xe0"):
                                if msvcrt.kbhit():
                                    msvcrt.getwch()
                                continue
                            plow = normalize_hotkey_char(pch).lower()
                            if plow == "p":
                                self._paused = False
                                self.add_log("[INFO]", "Resumed download")
                                self.refresh(force=True)
                                break
                            elif plow == "s":
                                self._paused = False
                                self.add_log("[SKIP]", "Skipping current item ([S] pressed)...")
                                self.refresh(force=True)
                                raise SkipItemRequested("Skipped by user hotkey [S]")
                            elif plow == "o":
                                self.open_output_folder()
                            elif pch == "\x03":
                                self._paused = False
                                raise KeyboardInterrupt()

    def init_queue(self, urls_or_titles: list):
        with self._lock:
            self._queue = [{"title": str(u), "status": "WAIT", "url": str(u)} for u in urls_or_titles]
            self._total_items = max(1, len(urls_or_titles))
            self._current_item_idx = 1
            self._done_count = 0
            self._skip_count = 0
            self._fail_count = 0
            self._paused = False
            self._skip_current = False
            self._batch_start_time = time.time()
            self._batch_eta_str = "--:--"

    def set_batch(self, current: int, total: int, done: int = 0, skip: int = 0, fail: int = 0):
        with self._lock:
            self._current_item_idx = current
            self._total_items = max(1, total)
            self._done_count = done
            self._skip_count = skip
            self._fail_count = fail

    def start_item(self, index: int, title: str = "", platform: str = "", mode: str = "VIDEO", quality: str = "best"):
        with self._lock:
            self._skip_current = False
            self._current_item_idx = index
            self._current_title = title or self._current_title
            self._platform = platform or self._platform
            self._mode = mode.upper() if mode else "VIDEO"
            self._quality = quality or "best"
            self._item_start_time = time.time()
            self._stage = "download"
            self._percent = 0.0
            self._speed_str = "--.- MB/s"
            self._eta_str = "--:--"
            self._size_str = "- / -"
            if 0 <= index - 1 < len(self._queue):
                self._queue[index - 1]["status"] = "RUN"
                if title:
                    self._queue[index - 1]["title"] = title

    def set_stage(self, stage: str):
        with self._lock:
            self._stage = stage.lower()

    def finish_item(self, index: int, status: str = "DONE", log_msg: str = "", done: int | None = None, skip: int | None = None, fail: int | None = None):
        with self._lock:
            if 0 <= index - 1 < len(self._queue):
                self._queue[index - 1]["status"] = status
            if done is not None:
                self._done_count = done
            elif status == "DONE":
                self._done_count += 1

            if skip is not None:
                self._skip_count = skip
            elif status == "SKIP":
                self._skip_count += 1

            if fail is not None:
                self._fail_count = fail
            elif status == "FAIL":
                self._fail_count += 1

            if log_msg:
                tag = f"[{status}]"
                self.add_log(tag, log_msg)
            self._update_batch_eta(pct=100.0)
        self.refresh(force=True)

    def _update_batch_eta(self, pct: float = 0.0):
        cur = self._current_item_idx
        tot = max(1, self._total_items)
        completed_fraction = (cur - 1 + (pct / 100.0)) / tot if tot > 0 else 0.0
        now = time.time()
        b_start = getattr(self, "_batch_start_time", 0.0)
        if b_start > 0 and completed_fraction > 0.005 and (now - b_start) > 1.0:
            elapsed_b = now - b_start
            est_total = elapsed_b / completed_fraction
            rem_b = max(0, est_total - elapsed_b)
            b_mins, b_secs = divmod(int(rem_b), 60)
            b_hrs, b_mins = divmod(b_mins, 60)
            if b_hrs > 0:
                self._batch_eta_str = f"{b_hrs:02d}:{b_mins:02d}:{b_secs:02d}"
            else:
                self._batch_eta_str = f"{b_mins:02d}:{b_secs:02d}"
        else:
            self._batch_eta_str = "--:--"

    def add_log(self, tag: str, message: str):
        with self._lock:
            self._logs.append((tag, message))
            if len(self._logs) > 3:
                self._logs.pop(0)

    def start(self):
        with self._lock:
            self._running = True
            if not self._batch_start_time:
                self._batch_start_time = time.time()
            if sys.stdout.isatty() and self._orig_print is None:
                self._orig_print = self.console.print
                def _intercept_print(*args, **kwargs):
                    if self._in_capture or not self._running:
                        if self._orig_print is not None:
                            return self._orig_print(*args, **kwargs)
                        return
                    if not args:
                        return
                    parts = []
                    for a in args:
                        if isinstance(a, str):
                            parts.append(a)
                        elif hasattr(a, "plain"):
                            parts.append(str(a.plain))
                        else:
                            parts.append(str(a))
                    clean = re.sub(r"\[/?[a-zA-Z0-9_ #]+\]", "", " ".join(parts)).strip()
                    if clean and not clean.startswith("===") and not clean.startswith("---"):
                        tag = "[INFO]"
                        if "[OK]" in clean or "[+]" in clean:
                            tag = "[OK]"
                        elif "[-]" in clean or "[ERROR]" in clean or "error" in clean.lower() or "failed" in clean.lower():
                            tag = "[FAIL]"
                        elif "[!]" in clean or "[WARN]" in clean or "warning" in clean.lower():
                            tag = "[WARN]"
                        elif "[SKIPPED]" in clean or "[>>]" in clean:
                            tag = "[SKIP]"
                        clean_msg = re.sub(r"^(\[[^\]]+\]\s*)+", "", clean).strip()
                        self.add_log(tag, clean_msg or clean)
                        self.refresh()
                    return
                self.console.print = _intercept_print

    def stop(self):
        with self._lock:
            self._running = False
            self._paused = False
            self._skip_current = False
            if self._orig_print is not None:
                self.console.print = self._orig_print
                self._orig_print = None
            if self._last_lines > 0 and sys.stdout.isatty():
                sys.stdout.write(f"\033[{self._last_lines}F\033[0J")
                sys.stdout.flush()
                self._last_lines = 0
            self._progress = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def hook(self, d: dict):
        self.poll_live_keys()
        status = d.get("status")

        if status == "downloading":
            raw_fn = d.get("filename") or "media_stream"
            fn_base = os.path.basename(raw_fn)

            downloaded = d.get("downloaded_bytes", 0) or 0
            total = d.get("total_bytes")
            is_estimate = False
            if not total:
                total = d.get("total_bytes_estimate")
                if total:
                    is_estimate = True
                elif d.get("info_dict"):
                    total = d["info_dict"].get("filesize") or d["info_dict"].get("filesize_approx")
                    if total:
                        is_estimate = True

            now = time.time()

            speed_val = d.get("speed")
            speed_str = None
            if speed_val and speed_val > 0:
                self._last_calc_speed = speed_val
                if speed_val >= 1024 * 1024:
                    speed_str = f"{speed_val / (1024 * 1024):.1f} MB/s"
                elif speed_val >= 1024:
                    speed_str = f"{speed_val / 1024:.1f} KB/s"
                else:
                    speed_str = f"{speed_val:.0f} B/s"
            elif d.get("_speed_str"):
                raw_s = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", str(d.get("_speed_str"))).strip()
                raw_s = raw_s.replace("KiB/s", " KB/s").replace("MiB/s", " MB/s").replace("GiB/s", " GB/s")
                raw_s = re.sub(r"\s+", " ", raw_s).strip()
                if raw_s:
                    speed_str = raw_s

            if not speed_str:
                if self._last_time > 0 and now > self._last_time:
                    dt = now - self._last_time
                    db = downloaded - self._last_bytes
                    if dt >= 0.3 and db >= 0:
                        self._last_calc_speed = db / dt
                        self._last_bytes = downloaded
                        self._last_time = now
                else:
                    self._last_bytes = downloaded
                    self._last_time = now

                calc_spd = getattr(self, "_last_calc_speed", 0.0)
                if calc_spd > 0:
                    if calc_spd >= 1024 * 1024:
                        speed_str = f"{calc_spd / (1024 * 1024):.1f} MB/s"
                    elif calc_spd >= 1024:
                        speed_str = f"{calc_spd / 1024:.1f} KB/s"
                    else:
                        speed_str = f"{calc_spd:.0f} B/s"
                else:
                    item_start = getattr(self, "_item_start_time", 0.0)
                    if item_start > 0 and (now - item_start) > 0.2 and downloaded > 0:
                        overall_spd = downloaded / (now - item_start)
                        self._last_calc_speed = overall_spd
                        if overall_spd >= 1024 * 1024:
                            speed_str = f"{overall_spd / (1024 * 1024):.1f} MB/s"
                        elif overall_spd >= 1024:
                            speed_str = f"{overall_spd / 1024:.1f} KB/s"
                        else:
                            speed_str = f"{overall_spd:.0f} B/s"
                    else:
                        speed_str = "--.- MB/s"

            eta_val = d.get("eta")
            eta_str = None
            if eta_val is not None and eta_val >= 0:
                mins, secs = divmod(int(eta_val), 60)
                hrs, mins = divmod(mins, 60)
                if hrs > 0:
                    eta_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
                else:
                    eta_str = f"{mins:02d}:{secs:02d}"
            elif d.get("_eta_str"):
                raw_eta = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", str(d.get("_eta_str"))).strip()
                if raw_eta and raw_eta != "--:--":
                    eta_str = raw_eta

            if not eta_str:
                calc_spd = getattr(self, "_last_calc_speed", 0.0)
                if calc_spd > 0 and total and total > downloaded:
                    calc_eta = int((total - downloaded) / calc_spd)
                    mins, secs = divmod(max(0, calc_eta), 60)
                    hrs, mins = divmod(mins, 60)
                    if hrs > 0:
                        eta_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
                    else:
                        eta_str = f"{mins:02d}:{secs:02d}"
                else:
                    eta_str = "--:--"

            def _fmt_sz(b):
                if b >= 1024 * 1024 * 1024:
                    return f"{b / (1024 * 1024 * 1024):.1f} GB"
                if b >= 1024 * 1024:
                    return f"{b / (1024 * 1024):.1f} MB"
                if b >= 1024:
                    return f"{b / 1024:.1f} KB"
                return f"{b:.0f} B"

            pct = 0.0
            raw_pct = d.get("_percent_str")
            if raw_pct:
                clean_pct = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", str(raw_pct)).strip()
                m = re.search(r"([\d.]+)%", clean_pct)
                if m:
                    try:
                        pct = float(m.group(1))
                    except ValueError:
                        pct = 0.0

            if total and total > 0:
                calc_pct = (downloaded / total) * 100.0
                if pct <= 0.0 or calc_pct > pct:
                    pct = calc_pct
                pfx = "~" if is_estimate else ""
                sz_str = f"{_fmt_sz(downloaded)} / {pfx}{_fmt_sz(total)}"
            elif pct > 0.0 and downloaded > 0:
                est_total = downloaded / (pct / 100.0)
                sz_str = f"{_fmt_sz(downloaded)} / ~{_fmt_sz(est_total)}"
            else:
                if downloaded > 0:
                    sz_str = f"{_fmt_sz(downloaded)} / Unknown"
                else:
                    sz_str = "- / -"

            pct = max(0.0, min(100.0, pct))

            info_dict = d.get("info_dict") or {}
            vid_title = info_dict.get("title")

            with self._lock:
                self._current_filename = fn_base
                if vid_title:
                    self._current_title = vid_title
                    if 0 <= self._current_item_idx - 1 < len(self._queue):
                        self._queue[self._current_item_idx - 1]["title"] = vid_title
                self._speed_str = speed_str
                self._eta_str = eta_str
                self._size_str = sz_str
                self._percent = pct
                self._stage = "download"

                self._update_batch_eta(pct=pct)

        elif status == "finished":
            with self._lock:
                self._percent = 100.0
                self._stage = "merge"
                self._speed_str = "Finished"
                self._eta_str = "00:00"

        self.refresh()

    def postprocessor_hook(self, d: dict):
        self.poll_live_keys()
        status = d.get("status")
        postprocessor = str(d.get("postprocessor", ""))
        with self._lock:
            if status == "started":
                if any(k in postprocessor for k in ("Merger", "Fixup", "ExtractAudio", "VideoRemuxer", "Remuxer")):
                    self._stage = "merge"
                    self._percent = 100.0
                    self._speed_str = "Merging..."
                    self._eta_str = "00:00"
                    self.add_log("[INFO]", "Merging media streams (ffmpeg)...")
                elif any(k in postprocessor for k in ("Metadata", "Thumb", "EmbedSubtitle", "AtomicParsley")):
                    self._stage = "tag"
                    self._percent = 100.0
                    self._speed_str = "Tagging..."
                    self._eta_str = "00:00"
                    self.add_log("[INFO]", "Embedding metadata & artwork...")
            elif status == "finished":
                info = d.get("info_dict") or {}
                final_f = info.get("_filename") or info.get("filepath")
                if final_f:
                    self._current_filename = os.path.basename(final_f)
        self.refresh()

    def refresh(self, force: bool = False):
        if not sys.stdout.isatty():
            return

        now = time.time()
        if not force and (now - self._last_render_time < 0.08):
            return

        with self._lock:
            screen = self._build_screen()
            self._in_capture = True
            try:
                with self.console.capture() as cap:
                    self.console.print(screen)
            finally:
                self._in_capture = False
            rendered_text = cap.get()
            lines = rendered_text.count("\n")

            if self._last_lines > 0:
                out_buf = f"\033[{self._last_lines}F\033[0J" + rendered_text
            else:
                out_buf = rendered_text

            sys.stdout.write(out_buf)
            sys.stdout.flush()
            self._last_lines = lines
            self._last_render_time = now

    def _build_screen(self):
        w = self.console.width
        is_narrow = (w < 76)
        b_box = BOX_STYLES["normal"]

        head_table = Table.grid(expand=True)
        head_table.add_column(justify="left", ratio=1)
        head_table.add_column(justify="right", width=26)

        run_state = ("Paused [P]", f"bold {A7_SIGNAL}") if self._paused else ("Running", f"bold {A7_TEXT}")
        crumb = Text.assemble(
            ("HAUSTUS", f"bold {A7_SIGNAL}"),
            ("  >  ", f"dim {A7_MUTED}"),
            ("Download", f"dim {A7_MUTED}"),
            ("  >  ", f"dim {A7_MUTED}"),
            run_state
        )
        chips = Text.assemble(
            ("DONE ", f"dim {A7_MUTED}"),
            (f"{self._done_count}  ", f"bold {A7_OK}"),
            ("SKIP ", f"dim {A7_MUTED}"),
            (f"{self._skip_count}  ", f"dim {A7_MUTED}"),
            ("FAIL ", f"dim {A7_MUTED}"),
            (f"{self._fail_count}", f"bold {A7_DANGER}" if self._fail_count > 0 else f"dim {A7_MUTED}")
        )
        head_table.add_row(crumb, chips)
        p_head = Panel(head_table, box=b_box, border_style=A7_SIGNAL, padding=(0, 1))

        cur = self._current_item_idx
        tot = max(1, self._total_items)
        batch_pct = ((cur - 1 + (self._percent / 100.0)) / tot) * 100.0 if tot > 0 else 0.0
        batch_pct = max(0.0, min(100.0, batch_pct))

        b_width = max(16, w - 24)
        batch_table = Table.grid(expand=True)
        batch_table.add_column(ratio=1)
        batch_table.add_row(make_progress_bar(batch_pct, width=b_width))

        batch_title = f"BATCH   {cur} of {tot}   {batch_pct:.0f}%"
        if tot > 1 and getattr(self, "_batch_eta_str", "--:--") != "--:--":
            batch_title += f"   [Total ETA: {self._batch_eta_str}]"

        p_batch = Panel(
            batch_table,
            title=batch_title,
            title_align="left",
            box=b_box,
            border_style=A7_SIGNAL,
            padding=(0, 1)
        )

        c_table = Table.grid(expand=True, padding=(0, 0))
        c_table.add_column(ratio=1)

        disp_title = self._current_title or self._current_filename or f"Item {cur:02d}"
        max_title_len = 34 if not is_narrow else (w - 10)
        if len(disp_title) > max_title_len:
            disp_title = disp_title[:max_title_len - 3] + "..."
        c_table.add_row(Text(disp_title, style=f"bold {A7_TEXT}"))

        mode_tag = f"[{self._mode}]" if self._mode else "[VIDEO]"
        q_lbl = self._quality or "best"
        plat_lbl = self._platform or ""
        info_t = Text.assemble((f"{mode_tag} ", f"bold {A7_BRASS}"), (f"{q_lbl}  ", f"{A7_SIGNAL}"), (plat_lbl, f"dim {A7_MUTED}"))
        c_table.add_row(info_t)
        c_table.add_row("")

        item_bar_w = 20 if not is_narrow else max(16, w - 20)
        c_table.add_row(make_progress_bar(self._percent, width=item_bar_w))

        if tot > 1 and getattr(self, "_batch_eta_str", "--:--") != "--:--":
            metrics_t = Text.assemble(
                ("Speed  ", f"dim {A7_MUTED}"),
                (f"{self._speed_str:<9}", f"bold {A7_TEXT}"),
                ("ETA ", f"dim {A7_MUTED}"),
                (f"{self._eta_str:<6}", f"bold {A7_TEXT}"),
                ("Total ETA ", f"dim {A7_MUTED}"),
                (self._batch_eta_str, f"bold {A7_SIGNAL}")
            )
        else:
            metrics_t = Text.assemble(
                ("Speed  ", f"dim {A7_MUTED}"),
                (f"{self._speed_str:<12}", f"bold {A7_TEXT}"),
                ("ETA   ", f"dim {A7_MUTED}"),
                (self._eta_str, f"bold {A7_TEXT}")
            )
        c_table.add_row(metrics_t)

        size_t = Text.assemble(("Size   ", f"dim {A7_MUTED}"), (self._size_str, f"{A7_TEXT}"))
        c_table.add_row(size_t)

        stg = (self._stage or "download").lower()
        x_dl = "x" if stg in ("download", "merge", "tag", "done") else " "
        x_mg = "x" if stg in ("merge", "tag", "done") else " "
        x_tg = "x" if stg in ("tag", "done") else " "

        stage_t = Text.assemble(
            ("Stage  ", f"dim {A7_MUTED}"),
            (f"[{x_dl}]", f"bold {A7_OK}" if x_dl == "x" else f"dim {A7_MUTED}"),
            (" Download ", f"{A7_TEXT}" if x_dl == "x" else f"dim {A7_MUTED}"),
            (f"[{x_mg}]", f"bold {A7_OK}" if x_mg == "x" else f"dim {A7_MUTED}"),
            (" Merge\n       ", f"{A7_TEXT}" if x_mg == "x" else f"dim {A7_MUTED}"),
            (f"[{x_tg}]", f"bold {A7_OK}" if x_tg == "x" else f"dim {A7_MUTED}"),
            (" Tag", f"{A7_TEXT}" if x_tg == "x" else f"dim {A7_MUTED}")
        )
        c_table.add_row(stage_t)

        p_current = Panel(
            c_table,
            title="CURRENT",
            title_align="left",
            box=b_box,
            border_style=A7_SIGNAL,
            padding=(0, 1)
        )

        if not is_narrow:
            q_table = Table.grid(expand=True, padding=(0, 0))
            q_table.add_column(ratio=1)

            visible_count = 8
            q_len = len(self._queue)
            cur_q_idx = max(0, min(q_len - 1, cur - 1)) if q_len > 0 else 0
            start_q = max(0, min(cur_q_idx - 3, q_len - visible_count))
            end_q = min(q_len, start_q + visible_count)

            visible_queue = self._queue[start_q:end_q] if self._queue else []
            if not visible_queue:
                q_table.add_row(Text(f"[RUN ] Item {cur:02d}", style=f"bold {A7_SIGNAL}"))
                for _ in range(visible_count - 1):
                    q_table.add_row("")
            else:
                for it in visible_queue:
                    st = it.get("status", "WAIT")
                    t_str = it.get("title") or it.get("url") or "Item"
                    if len(t_str) > 26:
                        t_str = t_str[:23] + "..."
                    row_t = Text()
                    if st == "DONE":
                        row_t.append("[DONE] ", style=f"bold {A7_OK}")
                        row_t.append(t_str, style=f"dim {A7_TEXT}")
                    elif st == "SKIP":
                        row_t.append("[SKIP] ", style=f"dim {A7_MUTED}")
                        row_t.append(t_str, style=f"dim {A7_MUTED}")
                    elif st == "FAIL":
                        row_t.append("[FAIL] ", style=f"bold {A7_DANGER}")
                        row_t.append(t_str, style=f"dim {A7_DANGER}")
                    elif st == "RUN":
                        row_t.append("[RUN ] ", style=f"bold {A7_SIGNAL}")
                        row_t.append(t_str, style=f"bold {A7_TEXT}")
                    else:
                        row_t.append("[WAIT] ", style=f"dim {A7_MUTED}")
                        row_t.append(t_str, style=f"dim {A7_MUTED}")
                    q_table.add_row(row_t)
                while len(visible_queue) < visible_count:
                    q_table.add_row("")
                    visible_queue.append({})

            p_queue = Panel(
                q_table,
                title="QUEUE",
                title_align="left",
                box=b_box,
                border_style=A7_SIGNAL,
                padding=(0, 1)
            )

            mid_grid = Table.grid(expand=True)
            mid_grid.add_column(ratio=1)
            mid_grid.add_column(ratio=1)
            mid_grid.add_row(p_queue, p_current)
        else:
            mid_grid = p_current

        log_table = Table.grid(expand=True, padding=(0, 0))
        log_table.add_column(ratio=1)
        disp_logs = self._logs[-3:] if self._logs else [("[INFO]", "Ready to process stream")]
        while len(disp_logs) < 3:
            disp_logs.insert(0, ("", ""))
        for tag, msg in disp_logs:
            if not tag and not msg:
                log_table.add_row("")
                continue
            lt = Text()
            tag_style = f"bold {A7_OK}" if "OK" in tag or "DONE" in tag else (f"bold {A7_DANGER}" if "FAIL" in tag else (f"bold {A7_SIGNAL}" if "WARN" in tag else f"bold {A7_BRASS}"))
            lt.append(f"{tag:<7} ", style=tag_style)
            max_log_len = w - 16
            if len(msg) > max_log_len:
                msg = msg[:max_log_len - 3] + "..."
            lt.append(msg, style=f"dim {A7_TEXT}")
            log_table.add_row(lt)

        p_log = Panel(
            log_table,
            title="LOG",
            title_align="left",
            box=b_box,
            border_style=A7_SIGNAL,
            padding=(0, 1)
        )

        p_foot = Panel(
            Text("[P] Pause/Resume  [S] Skip Item  [O] Open Folder  [Ctrl+C] Stop after current item", style=f"dim {A7_MUTED}"),
            box=b_box,
            border_style=A7_HAIRLINE,
            padding=(0, 1)
        )

        screen = Table.grid(expand=True)
        screen.add_column(ratio=1)
        screen.add_row(p_head)
        screen.add_row(p_batch)
        screen.add_row(mid_grid)
        screen.add_row(p_log)
        screen.add_row(p_foot)
        return screen
