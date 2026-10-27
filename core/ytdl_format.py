"""yt-dlp format string builders."""
def get_ydl_format(
    mode: str = "video",
    video_quality: str = "best",
    audio_format: str = "mp3",
    audio_quality: str = "192",
    embed_metadata: bool = True
) -> tuple[str, list]:
    """Build yt-dlp format string and postprocessors."""
    if mode == "audio":
        pps = []
        preferred_q = "0" if str(audio_quality).lower() == "best" else str(audio_quality)
        pps.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": str(audio_format).lower(),
            "preferredquality": preferred_q,
        })
        if embed_metadata:
            pps.append({"key": "FFmpegMetadata", "add_metadata": True})
            pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
            pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
        return ("bestaudio/best", pps)

    pps = []
    if embed_metadata:
        pps.append({"key": "FFmpegMetadata", "add_metadata": True})
        pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
        pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})

    clean_q = str(video_quality).lower().strip() if video_quality else ""
    h = None
    if clean_q in ("4k", "2160", "2160p"):
        h = 2160
    elif clean_q in ("2k", "1440", "1440p"):
        h = 1440
    elif clean_q in ("1080", "1080p", "fhd"):
        h = 1080
    elif clean_q in ("720", "720p", "hd"):
        h = 720
    elif clean_q in ("480", "480p", "sd"):
        h = 480
    elif clean_q in ("360", "360p", "low"):
        h = 360
    elif clean_q in ("240", "240p"):
        h = 240
    elif clean_q in ("144", "144p"):
        h = 144
    elif clean_q.isdigit():
        h = int(clean_q)

    if h:
        return (f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best", pps)

    return ("bestvideo+bestaudio/best", pps)
