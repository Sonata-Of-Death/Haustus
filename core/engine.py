"""High-throughput download engine."""
import os
import re
import shutil
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yt_dlp

from .media import MediaMaestro
from .resilience import (
    AdaptiveNetworkManager,
    SessionCheckpointLedger,
)


class TokenBucketLimiter:
    """Non-blocking token-bucket rate limiter per domain."""
    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()

    def acquire(self):
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return
        wait_time = (1.0 - self.tokens) / self.rate
        time.sleep(wait_time)
        self.tokens = 0.0
        self.last_update = time.monotonic()

class HighThroughputEngine:
    """Multi-stream download engine."""

    def __init__(
        self,
        output_dir: str = "downloads",
        cookie_file: Optional[str] = None,
        browser: Optional[str] = None,
        use_aria2: bool = False,
        aria2_connections: int = 16,
        max_workers: int = 6,
        checkpoint_path: str = ".download_checkpoint.json",
        proxy: Optional[str] = None
    ):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        self.use_aria2 = use_aria2 and (shutil.which("aria2c") is not None)
        self.aria2_connections = aria2_connections
        self.max_workers = max_workers
        self.proxy = proxy

        self.network_mgr = AdaptiveNetworkManager(base_delay=1.5, max_delay=45.0)
        self.checkpoint = SessionCheckpointLedger(checkpoint_path)
        self.media_maestro = MediaMaestro()

        self.cookie_file = cookie_file

        # Per-domain token bucket rate limiters.
        self.limiters = {
            "instagram.com": TokenBucketLimiter(rate=2.0, capacity=4.0),
            "tiktok.com": TokenBucketLimiter(rate=3.0, capacity=6.0),
            "youtube.com": TokenBucketLimiter(rate=5.0, capacity=10.0),
        }

    def _get_limiter(self, url: str) -> Optional[TokenBucketLimiter]:
        host = urllib.parse.urlparse(url).netloc.lower()
        for dom, lim in self.limiters.items():
            if dom in host:
                return lim
        return None

    def build_ydl_options(
        self,
        target_dir: str,
        mode: str = "video",
        video_quality: str = "best",
        audio_format: str = "mp3",
        audio_quality: str = "192",
        progress_hook: Optional[Callable[[dict], None]] = None
    ) -> dict:
        """Constructs optimized yt-dlp configuration with optional aria2c transport."""
        ydl_opts: Dict[str, Any] = {
            "outtmpl": os.path.join(target_dir, "%(title).180B.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": False,
            "buffersize": 2 * 1024 * 1024,  # 2 MB buffer.
            "http_chunk_size": 10485760,   # 10 MB chunk range requests.
            "remote_components": ["ejs:github"],
            "js_runtimes": {"node": {}},
        }

        if progress_hook:
            ydl_opts["progress_hooks"] = [progress_hook]

        if self.proxy:
            ydl_opts["proxy"] = self.proxy

        if self.cookie_file and os.path.isfile(self.cookie_file):
            ydl_opts["cookiefile"] = self.cookie_file

        # Use aria2c for segmented multi-connection downloads.
        if self.use_aria2:
            ydl_opts["external_downloader"] = "aria2c"
            ydl_opts["external_downloader_args"] = {
                "default": [
                    f"-s {self.aria2_connections}",
                    f"-x {self.aria2_connections}",
                    "-k 1M",
                    f"-j {self.aria2_connections}",
                    "--summary-interval=0",
                    "--allow-overwrite=true",
                    "--auto-file-renaming=false",
                ]
            }

        if mode == "audio":
            ydl_opts["format"] = "bestaudio/best"
            pref_q = "0" if str(audio_quality).lower() == "best" else str(audio_quality)
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": str(audio_format).lower(),
                "preferredquality": pref_q,
            }]
        else:
            clean_q = str(video_quality).lower().strip()
            h = None
            q_map = {
                "4k": 2160, "2160": 2160, "2160p": 2160,
                "2k": 1440, "1440": 1440, "1440p": 1440,
                "1080": 1080, "1080p": 1080,
                "720": 720, "720p": 720,
                "480": 480, "480p": 480,
                "360": 360, "360p": 360,
            }
            h = q_map.get(clean_q)
            if not h and clean_q.isdigit():
                h = int(clean_q)

            if h:
                ydl_opts["format"] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            else:
                ydl_opts["format"] = "bestvideo+bestaudio/best"
            ydl_opts["merge_output_format"] = "mp4"

        return ydl_opts

    def download_single(
        self,
        url: str,
        target_dir: Optional[str] = None,
        mode: str = "video",
        video_quality: str = "best",
        audio_format: str = "mp3",
        audio_quality: str = "192",
        normalize: bool = False,
        transcode: bool = False,
        progress_hook: Optional[Callable[[dict], None]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Download single URL using optimal backend."""
        dest_dir = os.path.abspath(target_dir or self.output_dir)
        os.makedirs(dest_dir, exist_ok=True)

        limiter = self._get_limiter(url)
        if limiter:
            limiter.acquire()

        ydl_opts = self.build_ydl_options(
            dest_dir, mode=mode, video_quality=video_quality,
            audio_format=audio_format, audio_quality=audio_quality,
            progress_hook=progress_hook
        )

        downloaded_file = None

        def _internal_hook(d):
            nonlocal downloaded_file
            if d.get("status") == "finished":
                downloaded_file = d.get("filename")
            if progress_hook:
                progress_hook(d)

        ydl_opts["progress_hooks"] = [_internal_hook]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                item_id = info.get("id") or url

                if not downloaded_file:
                    target_ext = audio_format if mode == "audio" else "mp4"
                    title = info.get("title", "media")
                    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)[:60]
                    downloaded_file = os.path.join(dest_dir, f"{safe_title}.{target_ext}")

                if downloaded_file and os.path.isfile(downloaded_file):
                    # Apply two-pass EBU R128 loudness normalization.
                    if normalize and mode == "audio":
                        norm_out = str(Path(downloaded_file).with_name(f"norm_{Path(downloaded_file).name}"))
                        if self.media_maestro.normalize_audio(downloaded_file, norm_out, audio_format=audio_format, bitrate=audio_quality):
                            os.replace(norm_out, downloaded_file)

                    # Transcode video using hardware acceleration when requested.
                    if transcode and mode == "video":
                        opt_out = str(Path(downloaded_file).with_name(f"opt_{Path(downloaded_file).name}"))
                        if self.media_maestro.transcode_video(downloaded_file, opt_out):
                            os.replace(opt_out, downloaded_file)


                    # Inject metadata and tags into output file.
                    uploader = info.get("uploader") or info.get("channel") or "Unknown"
                    title = info.get("title") or "Media Item"
                    if mode == "audio":
                        self.media_maestro.tag_audio_file(downloaded_file, title=title, artist=uploader)
                    else:
                        self.media_maestro.tag_mp4_video(downloaded_file, title=title, artist=uploader)

                self.checkpoint.mark_completed(item_id, url)
                return True, downloaded_file

        except Exception as e:
            self.checkpoint.mark_failed(url, str(e))
            return False, None

    def download_batch_parallel(
        self,
        urls: List[str],
        target_dir: Optional[str] = None,
        mode: str = "video",
        video_quality: str = "best",
        audio_format: str = "mp3",
        audio_quality: str = "192",
        normalize: bool = False,
        transcode: bool = False,
        item_callback: Optional[Callable[[str, bool, Optional[str]], None]] = None
    ) -> Dict[str, Any]:
        """Execute batch downloads concurrently."""
        self.checkpoint.initialize_batch(urls)
        queue = self.checkpoint.get_pending_queue()

        succeeded = 0
        failed = 0
        failed_urls = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self.download_single,
                    u, target_dir, mode, video_quality,
                    audio_format, audio_quality, normalize, transcode
                ): u for u in queue
            }

            for fut in as_completed(futures):
                url = futures[fut]
                try:
                    ok, path = fut.result()
                    if ok:
                        succeeded += 1
                    else:
                        failed += 1
                        failed_urls.append(url)
                    if item_callback:
                        item_callback(url, ok, path)
                except Exception:
                    failed += 1
                    failed_urls.append(url)
                    if item_callback:
                        item_callback(url, False, None)

        return {
            "total": len(queue),
            "succeeded": succeeded,
            "failed": failed,
            "failed_urls": failed_urls,
        }
