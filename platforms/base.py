"""Base platform extraction helpers."""
import os
import re
from typing import List

from core.archive import (
    DEFAULT_OUTPUT_DIR,
    HISTORY_FILE,
    extract_url_item_id,
    get_archive_set,
    is_archived,
)
from ui.theme import console, print_summary_table


def parse_item_spec(spec: str, total_count: int) -> list[int]:
    """Parse item title, URL, and ID from specification."""
    if not spec or total_count <= 0:
        return list(range(total_count))

    clean = spec.strip()
    clean = re.sub(r"\b(?:exclude|except)\s+", "~", clean, flags=re.IGNORECASE)
    tokens = [t.strip() for t in clean.split(",") if t.strip()]

    included_set = set()
    excluded_set = set()

    for tok in tokens:
        is_exclude = False
        if tok.startswith(("~", "!", "^")):
            is_exclude = True
            tok = tok[1:].strip()
        elif tok.startswith("-") and not (tok.count("-") == 1 and tok[1:].isdigit() and not tok[0].isdigit()):
            is_exclude = True
            tok = tok[1:].strip()

        if "-" in tok:
            parts = tok.split("-", 1)
            try:
                start_i = int(parts[0].strip())
                end_i = int(parts[1].strip())
                if start_i > end_i:
                    start_i, end_i = end_i, start_i
                rng = set(range(max(1, start_i), min(total_count, end_i) + 1))
                if is_exclude:
                    excluded_set.update(rng)
                else:
                    included_set.update(rng)
            except ValueError:
                continue
        elif tok.isdigit():
            val = int(tok)
            if 1 <= val <= total_count:
                if is_exclude:
                    excluded_set.add(val)
                else:
                    included_set.add(val)

    if not included_set:
        candidate_set = set(range(1, total_count + 1))
    else:
        candidate_set = included_set

    final_1based = [i for i in range(1, total_count + 1) if i in candidate_set and i not in excluded_set]
    return [i - 1 for i in final_1based]

def filter_playlist_items(entries: list, spec: str) -> list:
    """Filters a list of collection/playlist entries using an item selection string."""
    if not entries or not spec:
        return entries
    indices = parse_item_spec(spec, len(entries))
    return [entries[i] for i in indices if 0 <= i < len(entries)]

def resolve_collection_target_dir(output_dir: str, default_subdir: str) -> str:
    """Resolve collection output directory."""
    norm_out = os.path.normpath(output_dir)
    if os.path.basename(norm_out).lower() == default_subdir.lower():
        target_dir = norm_out
    elif os.path.isdir(os.path.join(norm_out, default_subdir)):
        target_dir = os.path.join(norm_out, default_subdir)
    elif output_dir == DEFAULT_OUTPUT_DIR:
        target_dir = os.path.join(output_dir, default_subdir)
    else:
        target_dir = output_dir
    os.makedirs(target_dir, exist_ok=True)
    return target_dir

def run_collection_inventory(
    urls: List[str],
    target_dir: str,
    platform_id: str,
    inventory_title: str,
    total_label: str,
    url_list_filename: str = None,
    list_filename: str = None,
    all_done_msg: str = None,
) -> List[str]:
    """Extract collection items and prompt for selection."""
    os.makedirs(target_dir, exist_ok=True)
    fname = list_filename or url_list_filename or f"saved_{platform_id}_urls.txt"
    list_file = os.path.join(target_dir, fname)
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            f.write("\n".join(urls) + "\n")
        console.print(f"[dim]Saved list of URLs written to: {list_file}[/dim]")
    except Exception:
        pass

    archive_path = os.path.join(target_dir, HISTORY_FILE)
    archive_set = get_archive_set(archive_path)

    already_on_disk = 0
    pending_urls = []
    for u in urls:
        plat, iid = extract_url_item_id(u)
        if iid and is_archived(archive_set, iid, plat or platform_id, output_dir=target_dir, prompt_missing=False):
            already_on_disk += 1
        else:
            pending_urls.append(u)

    console.print(f"[bold cyan][INVENTORY] {inventory_title}:[/bold cyan]")
    console.print(f"  {total_label:<30} [bold white]{len(urls)}[/bold white]")
    console.print(f"  Already Archived & On Disk:    [bold green]{already_on_disk}[/bold green]")
    console.print(f"  New / Pending to Download:     [bold yellow]{len(pending_urls)}[/bold yellow]\n")

    if not pending_urls:
        msg = all_done_msg or f"All {platform_id.title()} items are already downloaded and physically verified on disk!"
        console.print(f"[bold green][OK] {msg}[/bold green]")
        console.print(f"[dim]Destination folder: {os.path.abspath(target_dir)}[/dim]\n")
        print_summary_table(
            total=len(urls),
            succeeded=0,
            skipped=len(urls),
            failed=0,
            output_dir=target_dir,
        )
    return pending_urls
