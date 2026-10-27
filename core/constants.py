"""Global constants, network headers, and platform registry."""
APP_NAME = "Haustus"
APP_TITLE = "HAUSTUS"
APP_DESCRIPTION = "Haustus - Bulk Media & Audio Downloader"

# Terminal palette and UI theme tokens.
A7_SIGNAL = "#E87A24"
A7_FILAMENT = "#FFB47A"
A7_MUTED = "#9A9187"
A7_OK = "#4E9A7F"
A7_DANGER = "#DC5A44"
A7_BRASS = "#C8A96E"
A7_TEXT = "#EAE3D5"
A7_HAIRLINE = "#332E2A"
A7_SURFACE = "#1B1917"
A7_WORLDLINE = "1.0"
A7_OPUS = "01"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PLATFORMS_REGISTRY = [
    {
        "id": "instagram",
        "name": "Instagram",
        "hotkey": "1",
        "cookie_field": "sessionid",
        "desc": "Photos, Reels, Stories & Saved posts",
        "saved_label": "Saved Posts & Reels",
        "color": "cyan",
    },
    {
        "id": "tiktok",
        "name": "TikTok",
        "hotkey": "2",
        "cookie_field": "sessionid",
        "desc": "Videos, Slideshows & Favorites",
        "saved_label": "Saved / Favorite Videos",
        "color": "magenta",
    },
    {
        "id": "youtube",
        "name": "YouTube",
        "hotkey": "3",
        "cookie_field": "cookies.txt",
        "desc": "Videos, Shorts, Audio & Playlists",
        "saved_label": "Private Playlists (WL / LL)",
        "color": "red",
    },
    {
        "id": "x",
        "name": "X (Twitter)",
        "hotkey": "4",
        "cookie_field": "auth_token",
        "desc": "Tweets, Videos & Bookmarks",
        "saved_label": "Bookmarks & Saved Media",
        "color": "blue",
    },
    {
        "id": "soundcloud",
        "name": "SoundCloud",
        "hotkey": "5",
        "cookie_field": "oauth_token",
        "desc": "HQ Audio Tracks, Sets & Likes",
        "saved_label": "Liked Tracks & Sets",
        "color": "yellow",
    },
    {
        "id": "reddit",
        "name": "Reddit",
        "hotkey": "6",
        "cookie_field": "reddit_session",
        "desc": "Posts, Videos, Galleries & Subreddits",
        "saved_label": "Saved Posts & Upvoted Media",
        "color": "red",
    },
    {
        "id": "facebook",
        "name": "Facebook",
        "hotkey": "7",
        "cookie_field": "c_user/xs",
        "desc": "Public Videos, Reels & Saved items",
        "saved_label": "Saved Videos & Pages",
        "color": "blue",
    },
    {
        "id": "pinterest",
        "name": "Pinterest",
        "hotkey": "8",
        "cookie_field": "_pinterest_sess",
        "desc": "Pins, High-Res Images & Boards",
        "saved_label": "Saved Pins & Boards",
        "color": "red",
    },
    {
        "id": "twitch",
        "name": "Twitch",
        "hotkey": "9",
        "cookie_field": "auth-token",
        "desc": "Clips, VODs & Highlights",
        "saved_label": "Channel Clips & VODs",
        "color": "magenta",
    },
    {
        "id": "threads",
        "name": "Threads",
        "hotkey": "A",
        "cookie_field": "sessionid",
        "desc": "Text, Images & Videos from creators",
        "saved_label": "User Profile Media",
        "color": "cyan",
    },
    {
        "id": "spotify",
        "name": "Spotify",
        "hotkey": "B",
        "cookie_field": "sp_dc",
        "desc": "Tracks, Playlists & Albums metadata",
        "saved_label": "Playlists & Saved Music",
        "color": "green",
    },
]
