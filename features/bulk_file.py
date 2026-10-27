"""Batch links file download workflow."""
from pathlib import Path

from core.archive import DEFAULT_OUTPUT_DIR
from features.downloader import (
    download_urls,
)
from ui.components import (
    pause_prompt,
)
from ui.quality import (
    resolve_embed_metadata,
    resolve_links_file,
    resolve_output_dir,
    resolve_quality_settings,
)
from ui.theme import (
    clear_terminal,
    console,
)


def download_from_file(
    file_path: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    browser: str = None,
    cookie_file: str = None,
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    delay: float = 2.0,
    use_aria2: bool = False,
    normalize: bool = False,
    transcode: bool = False,
    proxy: str = None,
    smart_filters: dict = None,
    embed_metadata: bool = None,
    is_bulk: bool = False,
    use_archive: bool = None,
):
    """Download URLs from text file."""
    path = Path(file_path)
    if not path.is_file():
        console.print(f"[bold red][-] File not found: {file_path}[/bold red]")
        return

    with open(path, "r", encoding="utf-8") as f:
        urls = f.readlines()

    download_urls(
        urls, output_dir=output_dir, browser=browser, cookie_file=cookie_file,
        mode=mode, video_quality=video_quality,
        audio_format=audio_format, audio_quality=audio_quality,
        delay=delay,
        use_aria2=use_aria2, normalize=normalize,
        transcode=transcode, proxy=proxy,
        smart_filters=smart_filters, embed_metadata=embed_metadata,
        is_bulk=is_bulk, use_archive=use_archive
    )

def run_bulk_file_menu():
    """Run batch links file download workflow."""
    clear_terminal()
    file_path = resolve_links_file()
    if not file_path:
        return
    out_dir = resolve_output_dir()
    if not out_dir:
        return
    embed_meta = resolve_embed_metadata()
    mode, quality, af, aq = resolve_quality_settings()
    download_from_file(
        file_path, output_dir=out_dir,
        mode=mode, video_quality=quality, audio_format=af, audio_quality=aq,
        embed_metadata=embed_meta, is_bulk=False
    )
    pause_prompt("Press [Enter] or [Esc] to return to main menu...")
