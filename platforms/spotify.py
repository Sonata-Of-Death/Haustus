"""Spotify media extractor."""
import json
import os
import re
import time
from typing import Any

import requests
import yt_dlp

from core.archive import (
    DEFAULT_OUTPUT_DIR,
    RESULT_DOWNLOADED,
    RESULT_FAILED,
    RESULT_SKIPPED,
    add_to_archive,
    extract_url_item_id,
    is_archived,
    sanitize_filename,
    tag_audio_metadata,
)
from ui.theme import FFMPEG_EXE, console


def resolve_spotify_url(url: str) -> str:
    """Resolve Spotify track, album, or playlist URL."""
    clean_url = url.strip()
    if clean_url.lower().startswith("spotify:"):
        parts = clean_url.split(":")
        if len(parts) >= 3:
            clean_url = f"https://open.spotify.com/{parts[1]}/{parts[2]}"
    elif "spotify.link" in clean_url.lower():
        try:
            resp = requests.head(clean_url, allow_redirects=True, timeout=5)
            if resp.url:
                clean_url = resp.url
        except Exception:
            try:
                resp = requests.get(clean_url, allow_redirects=True, timeout=5)
                if resp.url:
                    clean_url = resp.url
            except Exception:
                pass
    if "?" in clean_url:
        clean_url = clean_url.split("?")[0]
    return clean_url

def fetch_spotify_embed_metadata(url: str, session: requests.Session = None) -> dict:
    """Fetch Spotify embed metadata."""
    canonical_url = resolve_spotify_url(url)
    m = re.search(r"/(track|album|playlist|episode|show|artist)/([A-Za-z0-9]+)", canonical_url)
    if not m:
        return {}

    entity_type = m.group(1).lower()
    item_id = m.group(2)

    s = session or requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    embed_url = f"https://open.spotify.com/embed/{entity_type}/{item_id}"
    entity_data = {}
    try:
        r = s.get(embed_url, headers=headers, timeout=12)
        if r.status_code == 200:
            for m_script in re.finditer(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL):
                c = m_script.group(1).strip()
                if '"pageProps"' in c:
                    try:
                        parsed = json.loads(c)
                        entity_data = parsed.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
                        if entity_data:
                            break
                    except Exception:
                        pass
    except Exception:
        pass

    cover_url = None
    images = entity_data.get("visualIdentity", {}).get("image", [])
    if images and isinstance(images, list):
        sorted_imgs = sorted(images, key=lambda x: x.get("maxWidth", 0), reverse=True)
        if sorted_imgs:
            cover_url = sorted_imgs[0].get("url")

    # Fall back to oEmbed endpoint if title or cover image is missing from page data.
    title = entity_data.get("title") or entity_data.get("name")
    if not title or not cover_url:
        try:
            oe_resp = s.get(f"https://open.spotify.com/oembed?url={canonical_url}", headers=headers, timeout=8)
            if oe_resp.status_code == 200:
                oe_json = oe_resp.json()
                if not title:
                    title = oe_json.get("title")
                if not cover_url:
                    cover_url = oe_json.get("thumbnail_url")
        except Exception:
            pass

    artists_list = []
    if "artists" in entity_data and isinstance(entity_data["artists"], list):
        for a in entity_data["artists"]:
            if isinstance(a, dict) and a.get("name"):
                artists_list.append(a["name"])
    subtitle = entity_data.get("subtitle") or ""
    if not artists_list and subtitle:
        artists_list = [s_item.strip() for s_item in subtitle.replace("\xa0", " ").split(",") if s_item.strip()]

    artist_str = ", ".join(artists_list) if artists_list else (subtitle or "Unknown Artist")
    album_name = entity_data.get("album", {}).get("name") if isinstance(entity_data.get("album"), dict) else title

    raw_tracks = entity_data.get("trackList", [])
    track_list = []
    if isinstance(raw_tracks, list):
        for raw_t in raw_tracks:
            if not isinstance(raw_t, dict):
                continue
            t_uri = raw_t.get("uri", "")
            t_id = t_uri.split(":")[-1] if ":" in t_uri else raw_t.get("uid")
            t_title = raw_t.get("title") or raw_t.get("name") or "Track"
            t_sub = raw_t.get("subtitle") or ""
            t_sub_clean = t_sub.replace("\xa0", " ").strip()
            t_artists = t_sub_clean if t_sub_clean else artist_str
            t_preview = raw_t.get("audioPreview", {}).get("url") if isinstance(raw_t.get("audioPreview"), dict) else None
            track_list.append({
                "id": t_id,
                "title": t_title,
                "artist": t_artists,
                "duration": raw_t.get("duration"),
                "preview_url": t_preview,
                "uri": t_uri,
            })

    preview_url = None
    if isinstance(entity_data.get("audioPreview"), dict):
        preview_url = entity_data["audioPreview"].get("url")

    return {
        "type": entity_type,
        "id": item_id,
        "title": title or "Spotify Track",
        "artist": artist_str,
        "album": album_name,
        "release_date": entity_data.get("releaseDate", {}).get("isoString", "") if isinstance(entity_data.get("releaseDate"), dict) else "",
        "duration": entity_data.get("duration"),
        "cover_url": cover_url,
        "preview_url": preview_url,
        "track_list": track_list,
    }

def _download_single_spotify_audio(
    meta: dict,
    output_dir: str,
    ydl: yt_dlp.YoutubeDL,
    audio_format: str,
    audio_quality: str,
    archive_path: str,
    archive_set: set
) -> str:
    """Download matched audio track for Spotify item."""
    title = meta.get("title", "").strip()
    artist = meta.get("artist", "").strip()
    album = meta.get("album", "").strip() or title
    date = meta.get("release_date", "")
    cover_url = meta.get("cover_url")
    item_id = meta.get("id", "")

    safe_title = sanitize_filename(title, max_len=140).strip()
    safe_artist = sanitize_filename(artist, max_len=80).strip()
    base_name = f"{safe_artist} - {safe_title}" if safe_artist else safe_title
    if not base_name:
        base_name = f"spotify_track_{item_id}" if item_id else "spotify_track"

    final_audio_path = os.path.join(output_dir, f"{base_name}.{audio_format}")

    if os.path.isfile(final_audio_path) and os.path.getsize(final_audio_path) > 10000:
        if item_id:
            add_to_archive(archive_path, item_id, "spotify")
            archive_set.add(f"spotify {item_id}")
        return RESULT_SKIPPED

    search_query = f"ytsearch1:{artist} - {title} audio" if artist else f"ytsearch1:{title} audio"

    sub_opts = dict(ydl.params)
    sub_opts.pop("cookiesfrombrowser", None)
    if ydl.cookiejar:
        sub_opts["cookiejar"] = ydl.cookiejar
    if FFMPEG_EXE:
        sub_opts["ffmpeg_location"] = FFMPEG_EXE

    sub_opts["format"] = "bestaudio/best"
    sub_opts["outtmpl"] = os.path.join(output_dir, f"{base_name}.%(ext)s")
    sub_opts["postprocessors"] = [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": audio_format if audio_format in ("mp3", "m4a", "flac", "wav", "opus") else "mp3",
        "preferredquality": audio_quality if audio_quality in ("320", "256", "192", "128", "64") else "320",
    }]
    sub_opts["quiet"] = True
    sub_opts["no_warnings"] = True

    download_ok = False
    try:
        with yt_dlp.YoutubeDL(sub_opts) as audio_ydl:
            ret = audio_ydl.download([search_query])
            if ret == 0:
                download_ok = True
    except Exception:
        download_ok = False

    # Search SoundCloud when YouTube matching yields no file.
    if not download_ok or not os.path.isfile(final_audio_path):
        try:
            sc_query = f"scsearch1:{artist} - {title}"
            with yt_dlp.YoutubeDL(sub_opts) as audio_ydl:
                ret = audio_ydl.download([sc_query])
                if ret == 0:
                    download_ok = True
        except Exception:
            pass

    # Use audio preview when full-length audio matching is unavailable.
    if (not download_ok or not os.path.isfile(final_audio_path)) and meta.get("preview_url"):
        try:
            p_resp = requests.get(meta["preview_url"], timeout=15)
            if p_resp.status_code == 200:
                with open(final_audio_path, "wb") as pf:
                    pf.write(p_resp.content)
                download_ok = True
        except Exception:
            pass

    if os.path.isfile(final_audio_path):
        tag_audio_metadata(final_audio_path, title=title, artist=artist, album=album, date=date, cover_url=cover_url)
        console.print(f"[bold green]  [OK] Spotify audio saved & tagged: {os.path.basename(final_audio_path)}[/bold green]")
        if item_id:
            add_to_archive(archive_path, item_id, "spotify")
            archive_set.add(f"spotify {item_id}")
        return RESULT_DOWNLOADED

    console.print(f"[bold red]  [-] Audio sourcing failed for: {title}[/bold red]")
    return RESULT_FAILED

def process_spotify_item(
    url: str,
    output_dir: str,
    ydl: yt_dlp.YoutubeDL,
    session: requests.Session,
    archive_path: str,
    archive_set: set,
    mode: str = "audio",
    audio_format: str = "mp3",
    audio_quality: str = "320",
    delay: float = 2.0,
    smart_filters: dict = None,
    dashboard: Any = None
) -> str:
    """Process and download Spotify item."""
    plat, item_id = extract_url_item_id(url)
    clean_url = resolve_spotify_url(url)
    meta = fetch_spotify_embed_metadata(clean_url, session=session)
    if not meta or not meta.get("title"):
        console.print(f"[bold red]  [-] Could not extract Spotify metadata for URL: {url}[/bold red]")
        return RESULT_FAILED

    item_type = meta.get("type", "track")

    if item_type in ("album", "playlist", "show") and meta.get("track_list"):
        tracks = meta["track_list"]
        if smart_filters and smart_filters.get("count_limit"):
            tracks = tracks[:smart_filters["count_limit"]]
        col_title = meta.get("title", item_type.title())
        console.print(f"[bold green][*] Spotify {item_type.upper()}: '{col_title}' ({len(tracks)} tracks)[/bold green]")
        if dashboard and tracks:
            queue_items = [
                sanitize_filename(t.get("title") or f"Track {i:02d}", max_len=60)
                for i, t in enumerate(tracks, 1) if t
            ]
            dashboard.init_queue(queue_items)

        s_dl, s_skip, s_fail = 0, 0, 0
        for idx, t in enumerate(tracks, 1):
            t_id = t.get("id") or str(idx)
            t_title = t.get("title") or f"Track {idx}"
            t_artist = t.get("artist") or meta.get("artist", "")
            if dashboard:
                dashboard.set_batch(current=idx, total=len(tracks), done=s_dl, skip=s_skip, fail=s_fail)
                dashboard.start_item(idx, title=f"{t_artist} - {t_title}", platform="Spotify", mode="AUDIO", quality=audio_quality)

            if t_id and is_archived(archive_set, str(t_id), "spotify", output_dir=output_dir, title=t_title):
                console.print(f"[bold blue]  [>>] [SKIPPED] Track {idx}/{len(tracks)} already downloaded ({t_title})[/bold blue]")
                s_skip += 1
                if dashboard:
                    dashboard.finish_item(idx, status="SKIP", done=s_dl, skip=s_skip, fail=s_fail)
                continue

            console.print(f"[dim]--- Spotify Track [{idx}/{len(tracks)}]: {t_artist} - {t_title} ---[/dim]")
            t_meta = {
                "id": t_id,
                "title": t_title,
                "artist": t_artist,
                "album": col_title,
                "release_date": meta.get("release_date"),
                "cover_url": meta.get("cover_url"),
                "preview_url": t.get("preview_url"),
            }
            res = _download_single_spotify_audio(
                t_meta, output_dir, ydl, audio_format, audio_quality,
                archive_path, archive_set
            )
            if res == RESULT_DOWNLOADED:
                s_dl += 1
                if dashboard:
                    dashboard.finish_item(idx, status="DONE", done=s_dl, skip=s_skip, fail=s_fail)
            elif res == RESULT_SKIPPED:
                s_skip += 1
                if dashboard:
                    dashboard.finish_item(idx, status="SKIP", done=s_dl, skip=s_skip, fail=s_fail)
            else:
                s_fail += 1
                if dashboard:
                    dashboard.finish_item(idx, status="FAIL", done=s_dl, skip=s_skip, fail=s_fail)

            if delay > 0 and idx < len(tracks):
                time.sleep(delay)

        return RESULT_DOWNLOADED if (s_fail == 0 or s_dl > 0 or s_skip > 0) else RESULT_FAILED

    t_id = meta.get("id") or item_id
    t_title = meta.get("title", "Track")
    t_artist = meta.get("artist", "")
    if t_id and is_archived(archive_set, t_id, "spotify", output_dir=output_dir, title=t_title):
        console.print(f"[bold blue]  [>>] [SKIPPED] Already downloaded previously (Spotify: {t_title})[/bold blue]")
        return RESULT_SKIPPED

    console.print(f"[bold green]  [SPOTIFY] Downloading audio track ({audio_format.upper()} @ {audio_quality}k): {t_artist} - {t_title}...[/bold green]")
    res = _download_single_spotify_audio(
        meta, output_dir, ydl, audio_format, audio_quality,
        archive_path, archive_set
    )
    return res

def download_spotify_playlist(
    url: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    cookie_file: str = None,
    audio_format: str = "mp3",
    audio_quality: str = "320",
    delay: float = 2.0,
    smart_filters: dict = None,
    embed_metadata: bool = True
) -> int:
    """Download full Spotify playlist, album, show, or artist collection."""
    from features.downloader import download_urls
    clean_url = resolve_spotify_url(url)
    os.makedirs(output_dir, exist_ok=True)
    console.print(f"[bold green][*] Downloading Spotify Collection: {clean_url}[/bold green]")
    console.print(f"[dim][FOLDER] Destination: {os.path.abspath(output_dir)}[/dim]")
    return download_urls(
        [clean_url], output_dir=output_dir, cookie_file=cookie_file,
        mode="audio", audio_format=audio_format, audio_quality=audio_quality,
        delay=delay, smart_filters=smart_filters, embed_metadata=embed_metadata,
        is_bulk=True
    )
