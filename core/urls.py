"""URL matching and platform classification."""
def is_instagram_url(url: str) -> bool:
    """Check if a URL belongs to Instagram."""
    return "instagram.com" in url.lower()

def is_tiktok_url(url: str) -> bool:
    """Check if a URL belongs to TikTok."""
    return any(d in url.lower() for d in ("tiktok.com", "douyin.com", "tiktokv.com"))

def is_youtube_url(url: str) -> bool:
    """Check if a URL belongs to YouTube."""
    return any(d in url.lower() for d in ("youtube.com", "youtu.be"))

def is_x_url(url: str) -> bool:
    """Check if a URL belongs to X (Twitter)."""
    return any(d in url.lower() for d in ("x.com", "twitter.com"))

def is_soundcloud_url(url: str) -> bool:
    """Check if a URL belongs to SoundCloud."""
    return any(d in url.lower() for d in ("soundcloud.com", "snd.sc"))

def is_reddit_url(url: str) -> bool:
    """Check if a URL belongs to Reddit."""
    return any(d in url.lower() for d in ("reddit.com", "redd.it", "v.redd.it"))

def is_facebook_url(url: str) -> bool:
    """Check if a URL belongs to Facebook."""
    return any(d in url.lower() for d in ("facebook.com", "fb.watch", "fb.com", "m.facebook.com", "web.facebook.com"))

def is_pinterest_url(url: str) -> bool:
    """Check if a URL belongs to Pinterest."""
    return any(d in url.lower() for d in ("pinterest.com", "pin.it", "pinterest.co", "pinimg.com"))

def is_twitch_url(url: str) -> bool:
    """Check if a URL belongs to Twitch."""
    return any(d in url.lower() for d in ("twitch.tv", "clips.twitch.tv"))

def is_threads_url(url: str) -> bool:
    """Check if a URL belongs to Threads."""
    return any(d in url.lower() for d in ("threads.net", "threads.com"))

def is_spotify_url(url: str) -> bool:
    """Check if a URL belongs to Spotify."""
    u = url.lower().strip()
    return any(d in u for d in ("open.spotify.com", "spotify.com", "spotify.link")) or u.startswith("spotify:")
