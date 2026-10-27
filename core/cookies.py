"""Authentication and cookie profile manager."""
import http.cookiejar
import io
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse

import requests
from rich import box
from rich.table import Table

from core.config import ConfigManager
from core.constants import HEADERS, PLATFORMS_REGISTRY
from core.instances import config_mgr
from ui.components import ask_input, interactive_select
from ui.theme import clear_terminal, console


def clean_dummy_cookie_profiles(cfg: ConfigManager):
    """Clean any orphaned dummy profiles (e.g. named containing default or user)."""
    for plat in PLATFORMS_REGISTRY:
        p_id = plat["id"]
        profs = list(cfg.get_cookie_profiles(p_id))
        for prof in profs:
            p_name = prof.get("name", "").lower()
            if "user" in p_name or "default" in p_name:
                cfg.delete_cookie_profile(p_id, prof["name"])

def sanitize_netscape_cookie_text(content: str) -> str:
    """Ensures Netscape cookie lines adhere strictly to MozillaCookieJar specification."""
    if not content:
        return ""
    lines = content.splitlines()
    cleaned = ["# Netscape HTTP Cookie File", "# https://curl.haxx.se/rfc/cookie_spec.html", ""]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        stripped = stripped.removeprefix("#HttpOnly_")
        if stripped.startswith("#"):
            continue
        parts = stripped.split("\t")
        if len(parts) < 7:
            parts = stripped.split()
        if len(parts) >= 7:
            domain, flag, path, secure, exp, name = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            value = " ".join(parts[6:]) if "\t" not in stripped else "\t".join(parts[6:])
            flag = "TRUE" if domain.startswith(".") else "FALSE"
            secure = "TRUE" if secure.upper() == "TRUE" else "FALSE"
            try:
                exp_int = int(float(exp))
                if exp_int <= 0:
                    exp_int = 2147483647
                exp = str(exp_int)
            except ValueError:
                exp = "2147483647"
            cleaned.append(f"{domain}\t{flag}\t{path}\t{secure}\t{exp}\t{name}\t{value}")
    return "\n".join(cleaned) + "\n"

def sanitize_netscape_cookie_file(file_path: str) -> bool:
    """Format cookie file for MozillaCookieJar compatibility."""
    if not file_path or not os.path.isfile(file_path):
        return False
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        sanitized = sanitize_netscape_cookie_text(raw)
        has_entries = any(
            line.strip() and not line.strip().startswith("#")
            for line in sanitized.splitlines()
        )
        if not has_entries:
            return False
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(sanitized)
        return True
    except Exception:
        return False

def prepare_cookies(cookie_input: str = None, save_profile: bool = True) -> str | None:
    """Prepare Instagram cookie file from input."""
    content = ""
    if cookie_input and os.path.isfile(cookie_input.strip()):
        try:
            with open(cookie_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
        except Exception:
            pass
    elif cookie_input and cookie_input.strip():
        content = cookie_input.strip()
    else:
        return config_mgr.get_effective_cookie_file("instagram") if save_profile else None

    if not content:
        return config_mgr.get_effective_cookie_file("instagram") if save_profile else None

    if content.startswith("# Netscape") or "\tTRUE\t" in content:
        sanitized = sanitize_netscape_cookie_text(content)
        if save_profile:
            config_mgr.add_cookie_profile("instagram", "@account_1", sanitized, set_as_default=True)
            return config_mgr.get_effective_cookie_file("instagram")
        else:
            tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_ig_cookie.txt", encoding="utf-8")
            tf.write(sanitized)
            tf.close()
            return tf.name

    cookies = {}
    if content.startswith("[") or content.startswith("{"):
        try:
            data = json.loads(content)
            if isinstance(data, list):
                for item in data:
                    if "name" in item and "value" in item:
                        cookies[item["name"]] = item["value"]
            elif isinstance(data, dict):
                cookies.update(data)
        except Exception:
            pass

    if not cookies:
        if "=" not in content and len(content) > 15:
            cookies["sessionid"] = content.strip()
        else:
            for part in content.replace("\n", ";").split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()

    if "sessionid" in cookies:
        sid = cookies["sessionid"]
        unquoted = urllib.parse.unquote(sid)
        match = re.match(r"^(\d+):", unquoted)
        if match and "ds_user_id" not in cookies:
            cookies["ds_user_id"] = match.group(1)
        if "sessionid_ss" not in cookies:
            cookies["sessionid_ss"] = sid
    elif "sessionid_ss" in cookies and "sessionid" not in cookies:
        cookies["sessionid"] = cookies["sessionid_ss"]

    if not cookies:
        return config_mgr.get_effective_cookie_file("instagram") if save_profile else None

    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically by Media Bulk Downloader",
        ""
    ]
    now_sec = int(time.time())
    exp_sec = now_sec + (365 * 24 * 3600)
    for k, v in cookies.items():
        clean_v = str(v).replace("\r", "").replace("\n", "").strip()
        lines.append(f".instagram.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f".tiktok.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f".byteoversea.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f"www.tiktok.com\tFALSE\t/\tFALSE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f".youtube.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")

    netscape_text = "\n".join(lines) + "\n"
    if save_profile:
        u_h = f"@{cookies.get('ds_user_id', 'account_1')}"
        config_mgr.add_cookie_profile("instagram", u_h, netscape_text, set_as_default=True)
        temp_path = config_mgr.get_effective_cookie_file("instagram")
        console.print("[bold green][OK] Formatted Netscape cookies saved to configuration.[/bold green]")
        return temp_path
    else:
        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_ig_cookie.txt", encoding="utf-8")
        tf.write(netscape_text)
        tf.close()
        return tf.name

def get_effective_instagram_cookie_file(cookie_file: str = None) -> str | None:
    """Find the best available cookie file for Instagram operations."""
    if cookie_file and os.path.isfile(cookie_file):
        return os.path.abspath(cookie_file)
    cfg_file = config_mgr.get_effective_cookie_file("instagram")
    if cfg_file and os.path.isfile(cfg_file):
        return os.path.abspath(cfg_file)
    return None

def verify_instagram_session(cookie_file: str) -> tuple[bool, str]:
    """Verify if Instagram cookies represent an active logged-in session."""
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return (False, "Could not load cookie file")
    cookie_names = {c.name for c in cj}
    if "sessionid" not in cookie_names:
        return (False, "Missing Instagram sessionid cookie")
    try:
        user = detect_account_username("instagram", cookie_file)
        if user:
            return (True, f"Authenticated as @{user.lstrip('@')}")
        s = requests.Session()
        s.cookies = cj
        csrf = next((c.value for c in cj if c.name == "csrftoken"), "")
        headers = {
            "User-Agent": HEADERS["User-Agent"],
            "X-IG-App-ID": "936619743392459",
            "X-CSRFToken": csrf,
            "Referer": "https://www.instagram.com/",
        }
        resp = s.get("https://i.instagram.com/api/v1/accounts/current_user/?edit=true", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            uname = data.get("user", {}).get("username")
            if uname:
                return (True, f"Authenticated as @{uname}")
        return (True, "Session cookie present (sessionid valid)")
    except Exception as e:
        return (False, f"Connection error: {e}")

def prepare_tiktok_cookies(cookie_input: str = None, save_profile: bool = True) -> str | None:
    """Prepare TikTok cookie file from input."""
    content = ""
    if cookie_input and os.path.isfile(cookie_input.strip()):
        try:
            with open(cookie_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
        except Exception:
            pass
    elif cookie_input and cookie_input.strip():
        content = cookie_input.strip()
    else:
        return config_mgr.get_effective_cookie_file("tiktok") if save_profile else None

    if not content:
        return config_mgr.get_effective_cookie_file("tiktok") if save_profile else None

    cookies = {}
    if content.startswith("# Netscape") or "\tTRUE\t" in content:
        for line in content.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 7 and any(d in parts[0] for d in ("tiktok", "byteoversea")):
                cookies[parts[5]] = parts[6]
    else:
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if "name" in item and "value" in item:
                            cookies[item["name"]] = item["value"]
                elif isinstance(data, dict):
                    cookies.update(data)
            except Exception:
                pass

        if not cookies:
            if "=" not in content and len(content) > 10:
                cookies["sessionid"] = content.strip()
                cookies["sessionid_ss"] = content.strip()
            else:
                for part in content.replace("\n", ";").split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

    if "sessionid" in cookies and "sessionid_ss" not in cookies:
        cookies["sessionid_ss"] = cookies["sessionid"]
    elif "sessionid_ss" in cookies and "sessionid" not in cookies:
        cookies["sessionid"] = cookies["sessionid_ss"]

    if not cookies:
        if content.startswith("# Netscape"):
            if save_profile:
                config_mgr.add_cookie_profile("tiktok", "@account_1", content, set_as_default=True)
                return config_mgr.get_effective_cookie_file("tiktok")
            else:
                tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_tt.txt", encoding="utf-8")
                tf.write(content)
                tf.close()
                return tf.name
        return config_mgr.get_effective_cookie_file("tiktok") if save_profile else None

    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically for TikTok by Media Bulk Downloader",
        ""
    ]
    now_sec = int(time.time())
    exp_sec = now_sec + (365 * 24 * 3600)
    for k, v in cookies.items():
        clean_v = str(v).replace("\r", "").replace("\n", "").strip()
        lines.append(f".tiktok.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f".byteoversea.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f"www.tiktok.com\tFALSE\t/\tFALSE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f".ibytedtos.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")

    netscape_text = "\n".join(lines) + "\n"
    if save_profile:
        u_h = f"@{cookies.get('uid', 'account_1')}"
        config_mgr.add_cookie_profile("tiktok", u_h, netscape_text, set_as_default=True)
        temp_path = config_mgr.get_effective_cookie_file("tiktok")
        console.print("[bold green][OK] TikTok Netscape cookies saved to configuration.[/bold green]")
        return temp_path
    else:
        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_tt.txt", encoding="utf-8")
        tf.write(netscape_text)
        tf.close()
        return tf.name

def get_effective_tiktok_cookie_file(cookie_file: str = None) -> str | None:
    """Find the best available cookie file for TikTok operations."""
    if cookie_file and os.path.isfile(cookie_file):
        return os.path.abspath(cookie_file)
    cfg_file = config_mgr.get_effective_cookie_file("tiktok")
    if cfg_file and os.path.isfile(cfg_file):
        return os.path.abspath(cfg_file)
    return None

def verify_tiktok_session(cookie_file: str) -> tuple[bool, str]:
    """Verify if TikTok cookies represent an active logged-in session."""
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return (False, "Could not load cookie file")
    cookie_names = {c.name for c in cj}
    if not cookie_names.intersection({"sessionid", "sid_tt", "sessionid_ss", "uid_tt"}):
        return (False, "Missing TikTok session cookie (sessionid / sid_tt)")
    try:
        user = detect_account_username("tiktok", cookie_file)
        if user:
            return (True, f"Authenticated as @{user.lstrip('@')}")
        s = requests.Session()
        s.cookies = cj
        resp = s.get(
            "https://www.tiktok.com/passport/web/account/info/",
            headers={"User-Agent": HEADERS["User-Agent"], "Referer": "https://www.tiktok.com/"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("message") == "success" and data.get("data", {}).get("username"):
                uname = data["data"]["username"]
                return (True, f"Authenticated as @{uname}")
        return (True, "Session cookie present (sessionid/sid_tt valid)")
    except Exception as e:
        return (False, f"Connection error: {e}")

def prepare_youtube_cookies(raw_input: str, save_profile: bool = True) -> str | None:
    """Prepare YouTube cookie file from input."""
    if not raw_input or not raw_input.strip():
        return config_mgr.get_effective_cookie_file("youtube") if save_profile else None
    val = raw_input.strip()

    # Parse from file on disk.
    if os.path.isfile(val):
        try:
            with open(val, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if "# Netscape HTTP Cookie File" in content or "\tyoutube.com\t" in content or "\t.youtube.com\t" in content:
                if save_profile:
                    config_mgr.add_cookie_profile("youtube", "@account_1", content, set_as_default=True)
                    return config_mgr.get_effective_cookie_file("youtube")
                else:
                    tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_yt.txt", encoding="utf-8")
                    tf.write(content)
                    tf.close()
                    return tf.name
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    lines = [
                        "# Netscape HTTP Cookie File",
                        "# Converted from JSON export for YouTube",
                        "",
                    ]
                    exp = int(time.time()) + (365 * 24 * 3600)
                    for c in data:
                        dom = c.get("domain", ".youtube.com")
                        name = c.get("name")
                        val_c = c.get("value")
                        if name and val_c:
                            lines.append(f"{dom}\tTRUE\t/\tTRUE\t{exp}\t{name}\t{val_c}")
                    netscape_text = "\n".join(lines) + "\n"
                    if save_profile:
                        config_mgr.add_cookie_profile("youtube", "@account_1", netscape_text, set_as_default=True)
                        return config_mgr.get_effective_cookie_file("youtube")
                    else:
                        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_yt.txt", encoding="utf-8")
                        tf.write(netscape_text)
                        tf.close()
                        return tf.name
            except Exception:
                pass
        except Exception:
            pass

    # Parse raw Netscape content string.
    if "# Netscape" in val or "\tyoutube.com\t" in val or "\t.youtube.com\t" in val:
        if save_profile:
            config_mgr.add_cookie_profile("youtube", "@account_1", val, set_as_default=True)
            return config_mgr.get_effective_cookie_file("youtube")
        else:
            tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_yt.txt", encoding="utf-8")
            tf.write(val)
            tf.close()
            return tf.name

    # Convert key=value cookie header string to Netscape format.
    pairs = [p.strip() for p in val.split(";") if "=" in p]
    if pairs:
        lines = [
            "# Netscape HTTP Cookie File",
            "# Converted from header cookie string for YouTube",
            "",
        ]
        exp = int(time.time()) + (365 * 24 * 3600)
        for pair in pairs:
            k, v = pair.split("=", 1)
            lines.append(f".youtube.com\tTRUE\t/\tTRUE\t{exp}\t{k.strip()}\t{v.strip()}")
        netscape_text = "\n".join(lines) + "\n"
        if save_profile:
            config_mgr.add_cookie_profile("youtube", "@account_1", netscape_text, set_as_default=True)
            return config_mgr.get_effective_cookie_file("youtube")
        else:
            tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_yt.txt", encoding="utf-8")
            tf.write(netscape_text)
            tf.close()
            return tf.name

    return config_mgr.get_effective_cookie_file("youtube") if save_profile else None

def is_authenticated_youtube_cookie_file(cookie_file: str) -> bool:
    """Check if the YouTube cookie file contains actual authenticated login cookies."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return False
    try:
        with open(cookie_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        auth_tokens = ("LOGIN_INFO", "SID", "SSID", "SAPISID", "HSID", "__Secure-1PSID", "__Secure-3PSID")
        return any(tok in content for tok in auth_tokens)
    except Exception:
        return False

def verify_youtube_session(cookie_file: str) -> tuple[bool, str]:
    """Test if YouTube cookie file is valid and authenticated."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return (False, "Cookie file does not exist")
    if not is_authenticated_youtube_cookie_file(cookie_file):
        return (False, "Cookie file does not contain login tokens (visitor only)")
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return (False, "Could not parse cookie jar")

    try:
        session = requests.Session()
        session.cookies.update(cj)
        resp = session.get(
            "https://www.youtube.com/playlist?list=WL",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36"},
            timeout=12
        )
        if resp.status_code == 200:
            if "signin" in resp.url.lower() or "accounts.google.com" in resp.url.lower():
                return (False, "Session expired / redirected to login")
            return (True, "Active authenticated session detected")
        return (False, f"HTTP {resp.status_code}")
    except Exception as e:
        return (False, f"Connection error: {e}")

def get_effective_youtube_cookie_file(explicit_path: str = None) -> str | None:
    """Resolve effective YouTube cookie file from explicit path or config profiles."""
    if explicit_path and os.path.isfile(explicit_path):
        return os.path.abspath(explicit_path)
    from_config = config_mgr.get_effective_cookie_file("youtube")
    if from_config and os.path.isfile(from_config):
        if is_authenticated_youtube_cookie_file(from_config):
            return from_config
    return None

def prepare_x_cookies(raw_input: str = None, save_profile: bool = True) -> str | None:
    """Prepare X (Twitter) cookie file from input."""
    content = ""
    if raw_input and os.path.isfile(raw_input.strip()):
        try:
            with open(raw_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
        except Exception:
            pass
    elif raw_input and raw_input.strip():
        content = raw_input.strip()
    else:
        return config_mgr.get_effective_cookie_file("x") if save_profile else None

    if not content:
        return config_mgr.get_effective_cookie_file("x") if save_profile else None

    cookies = {}
    if "# Netscape" in content or "\tx.com\t" in content or "\ttwitter.com\t" in content:
        for line in content.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 7 and any(d in parts[0] for d in ("x.com", "twitter.com")):
                cookies[parts[5]] = parts[6]
    else:
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if "name" in item and "value" in item:
                            cookies[item["name"]] = item["value"]
                elif isinstance(data, dict):
                    cookies.update(data)
            except Exception:
                pass

        if not cookies:
            if "=" not in content and len(content) >= 20:
                cookies["auth_token"] = content.strip()
            else:
                for part in content.replace("\n", ";").split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

    if not cookies:
        if content.startswith("# Netscape"):
            if save_profile:
                config_mgr.add_cookie_profile("x", "@account_1", content, set_as_default=True)
                return config_mgr.get_effective_cookie_file("x")
            else:
                tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_x.txt", encoding="utf-8")
                tf.write(content)
                tf.close()
                return tf.name
        return config_mgr.get_effective_cookie_file("x") if save_profile else None

    now_sec = int(time.time())
    exp_sec = now_sec + (365 * 24 * 3600)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically for X (Twitter) by Media Bulk Downloader",
        ""
    ]
    for k, v in cookies.items():
        clean_v = str(v).replace("\r", "").replace("\n", "").strip()
        lines.append(f".x.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f".twitter.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f"x.com\tFALSE\t/\tFALSE\t{exp_sec}\t{k}\t{clean_v}")

    netscape_text = "\n".join(lines) + "\n"
    if save_profile:
        config_mgr.add_cookie_profile("x", "@account_1", netscape_text, set_as_default=True)
        temp_path = config_mgr.get_effective_cookie_file("x")
        console.print("[bold green][OK] X (Twitter) Netscape cookies saved to configuration.[/bold green]")
        return temp_path
    else:
        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_x.txt", encoding="utf-8")
        tf.write(netscape_text)
        tf.close()
        return tf.name

def get_effective_x_cookie_file(cookie_file: str = None) -> str | None:
    """Find the best available cookie file for X (Twitter) operations."""
    if cookie_file and os.path.isfile(cookie_file):
        return os.path.abspath(cookie_file)
    cfg_file = config_mgr.get_effective_cookie_file("x")
    if cfg_file and os.path.isfile(cfg_file):
        return os.path.abspath(cfg_file)
    return None

def verify_x_session(cookie_file: str) -> tuple[bool, str]:
    """Verify if X (Twitter) cookies represent an active authenticated session."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return False, "Cookie file does not exist"
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return False, "Could not load cookie jar"
    session = requests.Session()
    session.cookies.update(cj)

    bearer = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    ct0 = ""
    for c in session.cookies:
        if c.name == "ct0":
            ct0 = c.value
            break

    headers = {
        "authorization": f"Bearer {bearer}",
        "x-twitter-active-user": "yes",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }
    if ct0:
        headers["x-csrf-token"] = ct0

    try:
        resp = session.get("https://api.x.com/1.1/account/settings.json", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            sn = data.get("screen_name")
            if sn:
                return True, f"Logged in as @{sn}"
            return True, "Active session detected"
        elif resp.status_code in (401, 403):
            return False, "Session expired or invalid credentials"
    except Exception as e:
        return False, f"Connection error: {e}"

    try:
        r2 = session.get("https://x.com/home", headers={"User-Agent": headers["User-Agent"]}, timeout=8, allow_redirects=False)
        if r2.status_code == 200 and "login" not in r2.url.lower():
            return True, "Active web session detected"
    except Exception:
        pass

    return False, "Unauthenticated session"

def prepare_soundcloud_cookies(raw_input: str = None, save_profile: bool = True) -> str | None:
    """Prepare SoundCloud cookie file from input."""
    content = ""
    if raw_input and os.path.isfile(raw_input.strip()):
        try:
            with open(raw_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
        except Exception:
            pass
    elif raw_input and raw_input.strip():
        content = raw_input.strip()
    else:
        return config_mgr.get_effective_cookie_file("soundcloud") if save_profile else None

    if not content:
        return config_mgr.get_effective_cookie_file("soundcloud") if save_profile else None

    cookies = {}
    if "# Netscape" in content or "\tsoundcloud.com\t" in content:
        for line in content.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 7 and "soundcloud" in parts[0]:
                cookies[parts[5]] = parts[6]
    else:
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if "name" in item and "value" in item:
                            cookies[item["name"]] = item["value"]
                elif isinstance(data, dict):
                    cookies.update(data)
            except Exception:
                pass

        if not cookies:
            if "=" not in content and len(content) >= 15:
                cookies["oauth_token"] = content.strip()
            else:
                for part in content.replace("\n", ";").split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

    if not cookies:
        if content.startswith("# Netscape"):
            if save_profile:
                config_mgr.add_cookie_profile("soundcloud", "@account_1", content, set_as_default=True)
                return config_mgr.get_effective_cookie_file("soundcloud")
            else:
                tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_sc.txt", encoding="utf-8")
                tf.write(content)
                tf.close()
                return tf.name
        return config_mgr.get_effective_cookie_file("soundcloud") if save_profile else None

    now_sec = int(time.time())
    exp_sec = now_sec + (365 * 24 * 3600)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically for SoundCloud by Media Bulk Downloader",
        ""
    ]
    for k, v in cookies.items():
        clean_v = str(v).replace("\r", "").replace("\n", "").strip()
        lines.append(f".soundcloud.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")

    netscape_text = "\n".join(lines) + "\n"
    if save_profile:
        config_mgr.add_cookie_profile("soundcloud", "@account_1", netscape_text, set_as_default=True)
        temp_path = config_mgr.get_effective_cookie_file("soundcloud")
        console.print("[bold green][OK] SoundCloud Netscape cookies saved to configuration.[/bold green]")
        return temp_path
    else:
        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_sc.txt", encoding="utf-8")
        tf.write(netscape_text)
        tf.close()
        return tf.name

def get_effective_soundcloud_cookie_file(cookie_file: str = None) -> str | None:
    """Find the best available cookie file for SoundCloud operations."""
    if cookie_file and os.path.isfile(cookie_file):
        return os.path.abspath(cookie_file)
    cfg_file = config_mgr.get_effective_cookie_file("soundcloud")
    if cfg_file and os.path.isfile(cfg_file):
        return os.path.abspath(cfg_file)
    return None

def verify_soundcloud_session(cookie_file: str) -> tuple[bool, str]:
    """Verify if SoundCloud cookies represent an active authenticated session."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return False, "Cookie file does not exist"
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return False, "Could not load cookie jar"
    oauth_token = None
    for c in cj:
        if c.name == "oauth_token":
            oauth_token = c.value
            break
    if not oauth_token:
        return False, "No oauth_token found in cookies"

    headers = {
        "Authorization": f"OAuth {oauth_token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }
    try:
        resp = requests.get("https://api-v2.soundcloud.com/me", headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            uname = data.get("username") or data.get("permalink")
            if uname:
                return True, f"Logged in as {uname}"
            return True, "Active authenticated session detected"
        elif resp.status_code in (401, 403):
            return False, "oauth_token expired or unauthorized"
    except Exception as e:
        return False, f"Connection error: {e}"
    return True, "oauth_token present"

def prepare_reddit_cookies(raw_input: str = None, save_profile: bool = True) -> str | None:
    """Prepare Reddit cookie file from input."""
    content = ""
    if raw_input and os.path.isfile(raw_input.strip()):
        try:
            with open(raw_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
        except Exception:
            pass
    elif raw_input and raw_input.strip():
        content = raw_input.strip()
    else:
        return config_mgr.get_effective_cookie_file("reddit") if save_profile else None

    if not content:
        return config_mgr.get_effective_cookie_file("reddit") if save_profile else None

    cookies = {}
    if "# Netscape" in content or "\treddit.com\t" in content:
        for line in content.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 7 and "reddit" in parts[0]:
                cookies[parts[5]] = parts[6]
    else:
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if "name" in item and "value" in item:
                            cookies[item["name"]] = item["value"]
                elif isinstance(data, dict):
                    cookies.update(data)
            except Exception:
                pass

        if not cookies:
            if "=" not in content and len(content) >= 15:
                cookies["reddit_session"] = content.strip()
            else:
                for part in content.replace("\n", ";").split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

    if not cookies:
        if content.startswith("# Netscape"):
            if save_profile:
                config_mgr.add_cookie_profile("reddit", "@account_1", content, set_as_default=True)
                return config_mgr.get_effective_cookie_file("reddit")
            else:
                tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_rd.txt", encoding="utf-8")
                tf.write(content)
                tf.close()
                return tf.name
        return config_mgr.get_effective_cookie_file("reddit") if save_profile else None

    now_sec = int(time.time())
    exp_sec = now_sec + (365 * 24 * 3600)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically for Reddit by Media Bulk Downloader",
        ""
    ]
    for k, v in cookies.items():
        clean_v = str(v).replace("\r", "").replace("\n", "").strip()
        lines.append(f".reddit.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")

    netscape_text = "\n".join(lines) + "\n"
    if save_profile:
        config_mgr.add_cookie_profile("reddit", "@account_1", netscape_text, set_as_default=True)
        temp_path = config_mgr.get_effective_cookie_file("reddit")
        console.print("[bold green][OK] Reddit Netscape cookies saved to configuration.[/bold green]")
        return temp_path
    else:
        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_rd.txt", encoding="utf-8")
        tf.write(netscape_text)
        tf.close()
        return tf.name

def get_effective_reddit_cookie_file(cookie_file: str = None) -> str | None:
    """Find the best available cookie file for Reddit operations."""
    if cookie_file and os.path.isfile(cookie_file):
        return os.path.abspath(cookie_file)
    cfg_file = config_mgr.get_effective_cookie_file("reddit")
    if cfg_file and os.path.isfile(cfg_file):
        return os.path.abspath(cfg_file)
    return None

def verify_reddit_session(cookie_file: str) -> tuple[bool, str]:
    """Verify if Reddit cookies represent an active authenticated session."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return False, "Cookie file does not exist"
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return False, "Could not load cookie jar"
    has_session = any(c.name in ("reddit_session", "token") for c in cj)
    if not has_session:
        return False, "No reddit_session cookie found"

    session = requests.Session()
    session.cookies.update(cj)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }
    try:
        r = session.get("https://old.reddit.com/prefs/where/", headers=headers, timeout=8, allow_redirects=False)
        if r.status_code == 200:
            return True, "Active authenticated session detected"
        elif r.status_code in (301, 302, 401, 403):
            return False, "Session expired / redirected to login"
    except Exception:
        pass
    return True, "Session tokens present"

def prepare_facebook_cookies(raw_input: str = None, save_profile: bool = True) -> str | None:
    """Prepare Facebook cookie file from input."""
    content = ""
    if raw_input and os.path.isfile(raw_input.strip()):
        try:
            with open(raw_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
        except Exception:
            pass
    elif raw_input and raw_input.strip():
        content = raw_input.strip()
    else:
        return config_mgr.get_effective_cookie_file("facebook") if save_profile else None

    if not content:
        return config_mgr.get_effective_cookie_file("facebook") if save_profile else None

    cookies = {}
    if "# Netscape" in content or "\tfacebook.com\t" in content:
        for line in content.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 7 and "facebook" in parts[0]:
                cookies[parts[5]] = parts[6]
    else:
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if "name" in item and "value" in item:
                            cookies[item["name"]] = item["value"]
                elif isinstance(data, dict):
                    cookies.update(data)
            except Exception:
                pass

        if not cookies:
            if "=" not in content and ":" in content:
                u_p = content.split(":", 1)
                cookies["c_user"] = u_p[0].strip()
                cookies["xs"] = u_p[1].strip()
            elif "=" not in content and content.strip().isdigit():
                cookies["c_user"] = content.strip()
            else:
                for part in content.replace("\n", ";").split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

    if not cookies:
        if content.startswith("# Netscape"):
            if save_profile:
                config_mgr.add_cookie_profile("facebook", "@account_1", content, set_as_default=True)
                return config_mgr.get_effective_cookie_file("facebook")
            else:
                tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_fb.txt", encoding="utf-8")
                tf.write(content)
                tf.close()
                return tf.name
        return config_mgr.get_effective_cookie_file("facebook") if save_profile else None

    now_sec = int(time.time())
    exp_sec = now_sec + (365 * 24 * 3600)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically for Facebook by Media Bulk Downloader",
        ""
    ]
    for k, v in cookies.items():
        clean_v = str(v).replace("\r", "").replace("\n", "").strip()
        lines.append(f".facebook.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f"www.facebook.com\tFALSE\t/\tFALSE\t{exp_sec}\t{k}\t{clean_v}")

    netscape_text = "\n".join(lines) + "\n"
    if save_profile:
        user_handle = f"@{cookies.get('c_user', 'account_1')}"
        config_mgr.add_cookie_profile("facebook", user_handle, netscape_text, set_as_default=True)
        temp_path = config_mgr.get_effective_cookie_file("facebook")
        console.print("[bold green][OK] Facebook Netscape cookies saved to configuration.[/bold green]")
        return temp_path
    else:
        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_fb.txt", encoding="utf-8")
        tf.write(netscape_text)
        tf.close()
        return tf.name

def get_effective_facebook_cookie_file(cookie_file: str = None) -> str | None:
    """Find the best available cookie file for Facebook operations."""
    if cookie_file and os.path.isfile(cookie_file):
        return os.path.abspath(cookie_file)
    cfg_file = config_mgr.get_effective_cookie_file("facebook")
    if cfg_file and os.path.isfile(cfg_file):
        return os.path.abspath(cfg_file)
    return None

def verify_facebook_session(cookie_file: str) -> tuple[bool, str]:
    """Verify if Facebook cookies represent an active authenticated session."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return False, "Cookie file does not exist"
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return False, "Could not load cookie jar"
    c_user = None
    has_xs = False
    for c in cj:
        if c.name == "c_user":
            c_user = c.value
        elif c.name == "xs":
            has_xs = True

    if not c_user and not has_xs:
        return False, "No c_user or xs cookies found"

    session = requests.Session()
    session.cookies.update(cj)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }
    try:
        r = session.get("https://mbasic.facebook.com/settings", headers=headers, timeout=8, allow_redirects=False)
        if r.status_code == 200:
            return True, f"Active session (User ID: {c_user})" if c_user else "Active Facebook session"
        elif r.status_code in (301, 302):
            loc = r.headers.get("Location", "")
            if "login" in loc.lower():
                return False, "Session expired / redirected to login"
            return True, f"Active session (User ID: {c_user})" if c_user else "Active session detected"
    except Exception:
        pass
    return True, f"Session tokens present (c_user: {c_user})" if c_user else "Session tokens present"

def prepare_pinterest_cookies(raw_input: str = None, save_profile: bool = True) -> str | None:
    """Prepare Pinterest cookie file from input."""
    content = ""
    if raw_input and os.path.isfile(raw_input.strip()):
        try:
            with open(raw_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
        except Exception:
            pass
    elif raw_input and raw_input.strip():
        content = raw_input.strip()
    else:
        return config_mgr.get_effective_cookie_file("pinterest") if save_profile else None

    if not content:
        return config_mgr.get_effective_cookie_file("pinterest") if save_profile else None

    cookies = {}
    if "# Netscape" in content or "\tpinterest.com\t" in content:
        for line in content.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 7 and "pinterest" in parts[0]:
                cookies[parts[5]] = parts[6]
    else:
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if "name" in item and "value" in item:
                            cookies[item["name"]] = item["value"]
                elif isinstance(data, dict):
                    cookies.update(data)
            except Exception:
                pass

        if not cookies:
            if "=" not in content and len(content) >= 15:
                cookies["_pinterest_sess"] = content.strip()
            else:
                for part in content.replace("\n", ";").split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

    if not cookies:
        if content.startswith("# Netscape"):
            if save_profile:
                config_mgr.add_cookie_profile("pinterest", "@account_1", content, set_as_default=True)
                return config_mgr.get_effective_cookie_file("pinterest")
            else:
                tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_pin.txt", encoding="utf-8")
                tf.write(content)
                tf.close()
                return tf.name
        return config_mgr.get_effective_cookie_file("pinterest") if save_profile else None

    now_sec = int(time.time())
    exp_sec = now_sec + (365 * 24 * 3600)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically for Pinterest by Media Bulk Downloader",
        ""
    ]
    for k, v in cookies.items():
        clean_v = str(v).replace("\r", "").replace("\n", "").strip()
        lines.append(f".pinterest.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f"www.pinterest.com\tFALSE\t/\tFALSE\t{exp_sec}\t{k}\t{clean_v}")

    netscape_text = "\n".join(lines) + "\n"
    if save_profile:
        config_mgr.add_cookie_profile("pinterest", "@account_1", netscape_text, set_as_default=True)
        temp_path = config_mgr.get_effective_cookie_file("pinterest")
        console.print("[bold green][OK] Pinterest Netscape cookies saved to configuration.[/bold green]")
        return temp_path
    else:
        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_pin.txt", encoding="utf-8")
        tf.write(netscape_text)
        tf.close()
        return tf.name

def get_effective_pinterest_cookie_file(cookie_file: str = None) -> str | None:
    """Find the best available cookie file for Pinterest operations."""
    if cookie_file and os.path.isfile(cookie_file):
        return os.path.abspath(cookie_file)
    cfg_file = config_mgr.get_effective_cookie_file("pinterest")
    if cfg_file and os.path.isfile(cfg_file):
        return os.path.abspath(cfg_file)
    return None

def verify_pinterest_session(cookie_file: str) -> tuple[bool, str]:
    """Verify if Pinterest cookies represent an active authenticated session."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return False, "Cookie file does not exist"
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return False, "Could not load cookie jar"
    has_sess = any(c.name in ("_pinterest_sess", "_auth") for c in cj)
    if not has_sess:
        return False, "No _pinterest_sess or _auth cookie found"
    return True, "Active Pinterest session tokens present"

def prepare_twitch_cookies(raw_input: str = None, save_profile: bool = True) -> str | None:
    """Prepare Twitch cookie file from input."""
    content = ""
    if raw_input and os.path.isfile(raw_input.strip()):
        try:
            with open(raw_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
        except Exception:
            pass
    elif raw_input and raw_input.strip():
        content = raw_input.strip()
    else:
        return config_mgr.get_effective_cookie_file("twitch") if save_profile else None

    if not content:
        return config_mgr.get_effective_cookie_file("twitch") if save_profile else None

    cookies = {}
    if "# Netscape" in content or "\ttwitch.tv\t" in content:
        for line in content.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 7 and "twitch" in parts[0]:
                cookies[parts[5]] = parts[6]
    else:
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if "name" in item and "value" in item:
                            cookies[item["name"]] = item["value"]
                elif isinstance(data, dict):
                    cookies.update(data)
            except Exception:
                pass

        if not cookies:
            if "=" not in content and len(content) >= 15:
                cookies["auth-token"] = content.strip()
            else:
                for part in content.replace("\n", ";").split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

    if not cookies:
        if content.startswith("# Netscape"):
            if save_profile:
                config_mgr.add_cookie_profile("twitch", "@account_1", content, set_as_default=True)
                return config_mgr.get_effective_cookie_file("twitch")
            else:
                tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_ttv.txt", encoding="utf-8")
                tf.write(content)
                tf.close()
                return tf.name
        return config_mgr.get_effective_cookie_file("twitch") if save_profile else None

    now_sec = int(time.time())
    exp_sec = now_sec + (365 * 24 * 3600)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically for Twitch by Media Bulk Downloader",
        ""
    ]
    for k, v in cookies.items():
        clean_v = str(v).replace("\r", "").replace("\n", "").strip()
        lines.append(f".twitch.tv\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f"www.twitch.tv\tFALSE\t/\tFALSE\t{exp_sec}\t{k}\t{clean_v}")

    netscape_text = "\n".join(lines) + "\n"
    if save_profile:
        login_name = cookies.get("login") or cookies.get("name")
        user_handle = f"@{login_name}" if login_name else "@account_1"
        config_mgr.add_cookie_profile("twitch", user_handle, netscape_text, set_as_default=True)
        temp_path = config_mgr.get_effective_cookie_file("twitch")
        console.print("[bold green][OK] Twitch Netscape cookies saved to configuration.[/bold green]")
        return temp_path
    else:
        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_ttv.txt", encoding="utf-8")
        tf.write(netscape_text)
        tf.close()
        return tf.name

def get_effective_twitch_cookie_file(cookie_file: str = None) -> str | None:
    """Find the best available cookie file for Twitch operations."""
    if cookie_file and os.path.isfile(cookie_file):
        return os.path.abspath(cookie_file)
    cfg_file = config_mgr.get_effective_cookie_file("twitch")
    if cfg_file and os.path.isfile(cfg_file):
        return os.path.abspath(cfg_file)
    return None

def verify_twitch_session(cookie_file: str) -> tuple[bool, str]:
    """Verify if Twitch cookies represent an active authenticated session."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return False, "Cookie file does not exist"
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return False, "Could not load cookie jar"
    token = None
    login_cookie = None
    for c in cj:
        if c.name == "auth-token":
            token = c.value
        elif c.name == "login":
            login_cookie = c.value

    if not token and not login_cookie:
        return False, "No auth-token or login cookie found"

    if token:
        try:
            headers = {"Authorization": f"OAuth {token}"}
            r = requests.get("https://id.twitch.tv/oauth2/validate", headers=headers, timeout=8)
            if r.status_code == 200:
                data = r.json()
                login = data.get("login")
                return True, f"Logged in as @{login}" if login else "Active authenticated Twitch session"
            elif r.status_code == 401:
                return False, "Twitch auth-token expired or invalid"
        except Exception:
            pass

    return True, f"Twitch session token present ({login_cookie or 'auth-token'})"

def prepare_threads_cookies(raw_input: str = None, save_profile: bool = True) -> str | None:
    """Prepare Threads cookie file from input."""
    content = ""
    if raw_input and os.path.isfile(raw_input.strip()):
        try:
            with open(raw_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
        except Exception:
            pass
    elif raw_input and raw_input.strip():
        content = raw_input.strip()
    else:
        th_eff = config_mgr.get_effective_cookie_file("threads")
        if th_eff:
            return th_eff
        return config_mgr.get_effective_cookie_file("instagram") if save_profile else None

    if not content:
        return (config_mgr.get_effective_cookie_file("threads") or config_mgr.get_effective_cookie_file("instagram")) if save_profile else None

    cookies = {}
    if "# Netscape" in content or "\tthreads.net\t" in content or "\tinstagram.com\t" in content:
        for line in content.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 7 and ("threads" in parts[0] or "instagram" in parts[0]):
                cookies[parts[5]] = parts[6]
    else:
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if "name" in item and "value" in item:
                            cookies[item["name"]] = item["value"]
                elif isinstance(data, dict):
                    cookies.update(data)
            except Exception:
                pass

        if not cookies:
            if "=" not in content and len(content) >= 15:
                cookies["sessionid"] = content.strip()
            else:
                for part in content.replace("\n", ";").split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

    if not cookies:
        if content.startswith("# Netscape"):
            if save_profile:
                config_mgr.add_cookie_profile("threads", "@account_1", content, set_as_default=True)
                return config_mgr.get_effective_cookie_file("threads")
            else:
                tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_th.txt", encoding="utf-8")
                tf.write(content)
                tf.close()
                return tf.name
        return config_mgr.get_effective_cookie_file("threads") if save_profile else None

    now_sec = int(time.time())
    exp_sec = now_sec + (365 * 24 * 3600)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically for Threads by Media Bulk Downloader",
        ""
    ]
    for k, v in cookies.items():
        clean_v = str(v).replace("\r", "").replace("\n", "").strip()
        lines.append(f".threads.net\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f"www.threads.net\tFALSE\t/\tFALSE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f".instagram.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")

    netscape_text = "\n".join(lines) + "\n"
    if save_profile:
        user_handle = f"@{cookies.get('ds_user_id', 'account_1')}"
        config_mgr.add_cookie_profile("threads", user_handle, netscape_text, set_as_default=True)
        temp_path = config_mgr.get_effective_cookie_file("threads")
        console.print("[bold green][OK] Threads Netscape cookies saved to configuration.[/bold green]")
        return temp_path
    else:
        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_th.txt", encoding="utf-8")
        tf.write(netscape_text)
        tf.close()
        return tf.name

def get_effective_threads_cookie_file(cookie_file: str = None) -> str | None:
    """Get active Threads cookie file."""
    if cookie_file and os.path.isfile(cookie_file):
        return os.path.abspath(cookie_file)
    cfg_file = config_mgr.get_effective_cookie_file("threads")
    if cfg_file and os.path.isfile(cfg_file):
        return os.path.abspath(cfg_file)
    ig_file = config_mgr.get_effective_cookie_file("instagram")
    if ig_file and os.path.isfile(ig_file):
        return os.path.abspath(ig_file)
    return None

def verify_threads_session(cookie_file: str) -> tuple[bool, str]:
    """Verify if Threads/Instagram cookies represent an active authenticated session."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return False, "Cookie file does not exist"
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return False, "Could not load cookie jar"
    has_sess = any(c.name == "sessionid" for c in cj)
    user_id = None
    for c in cj:
        if c.name in ("ds_user_id", "user_id"):
            user_id = c.value
            break
    if not has_sess and not user_id:
        return False, "No sessionid or ds_user_id cookie found"
    return True, f"Active Threads session (User ID: {user_id})" if user_id else "Active Threads session"

def prepare_spotify_cookies(raw_input: str = None, save_profile: bool = True) -> str | None:
    """Prepare Spotify cookie file from input."""
    content = ""
    if raw_input and os.path.isfile(raw_input.strip()):
        try:
            with open(raw_input.strip(), "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
        except Exception:
            pass
    elif raw_input and raw_input.strip():
        content = raw_input.strip()
    else:
        return config_mgr.get_effective_cookie_file("spotify") if save_profile else None

    if not content:
        return config_mgr.get_effective_cookie_file("spotify") if save_profile else None

    cookies = {}
    if "# Netscape" in content or "\t.spotify.com\t" in content or "\topen.spotify.com\t" in content:
        for line in content.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 7 and "spotify" in parts[0]:
                cookies[parts[5]] = parts[6]
    else:
        if content.startswith("[") or content.startswith("{"):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if "name" in item and "value" in item:
                            cookies[item["name"]] = item["value"]
                elif isinstance(data, dict):
                    cookies.update(data)
            except Exception:
                pass

        if not cookies:
            if "=" not in content and len(content) >= 15:
                cookies["sp_dc"] = content.strip()
            else:
                for part in content.replace("\n", ";").split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

    if not cookies:
        if content.startswith("# Netscape"):
            if save_profile:
                config_mgr.add_cookie_profile("spotify", "@account_1", content, set_as_default=True)
                return config_mgr.get_effective_cookie_file("spotify")
            else:
                tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_sp.txt", encoding="utf-8")
                tf.write(content)
                tf.close()
                return tf.name
        return config_mgr.get_effective_cookie_file("spotify") if save_profile else None

    now_sec = int(time.time())
    exp_sec = now_sec + (365 * 24 * 3600)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated automatically for Spotify by Media Bulk Downloader",
        ""
    ]
    for k, v in cookies.items():
        clean_v = str(v).replace("\r", "").replace("\n", "").strip()
        lines.append(f".spotify.com\tTRUE\t/\tTRUE\t{exp_sec}\t{k}\t{clean_v}")
        lines.append(f"open.spotify.com\tFALSE\t/\tFALSE\t{exp_sec}\t{k}\t{clean_v}")

    netscape_text = "\n".join(lines) + "\n"
    if save_profile:
        config_mgr.add_cookie_profile("spotify", "@account_1", netscape_text, set_as_default=True)
        temp_path = config_mgr.get_effective_cookie_file("spotify")
        console.print("[bold green][OK] Spotify Netscape cookies saved to configuration.[/bold green]")
        return temp_path
    else:
        tf = tempfile.NamedTemporaryFile("w", delete=False, suffix="_sp.txt", encoding="utf-8")
        tf.write(netscape_text)
        tf.close()
        return tf.name

def get_effective_spotify_cookie_file(cookie_file: str = None) -> str | None:
    """Find the best available cookie file for Spotify operations."""
    if cookie_file and os.path.isfile(cookie_file):
        return os.path.abspath(cookie_file)
    cfg_file = config_mgr.get_effective_cookie_file("spotify")
    if cfg_file and os.path.isfile(cfg_file):
        return os.path.abspath(cfg_file)
    return None

def verify_spotify_session(cookie_file: str) -> tuple[bool, str]:
    """Verify if Spotify cookies represent an active authenticated session."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return False, "Cookie file does not exist"
    try:
        with open(cookie_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if "sp_dc" in content:
            return True, "sp_dc verified: Active authenticated Spotify session"
        return False, "No sp_dc session cookie found"
    except Exception as e:
        return False, f"Error reading cookie file: {e}"

def load_cookie_jar(cookie_file: str) -> http.cookiejar.MozillaCookieJar | None:
    """Load Netscape cookie file into requests session."""
    if not cookie_file:
        return None
    # Match by platform name.
    plat = cookie_file.lower().strip()
    if plat in ("instagram", "tiktok", "youtube", "x", "twitter", "soundcloud", "reddit", "facebook", "pinterest", "twitch", "threads", "spotify"):
        cj = config_mgr.get_effective_cookie_jar(plat)
        if cj:
            return cj
    # Load directly from file path.
    if os.path.isfile(cookie_file):
        sanitize_netscape_cookie_file(cookie_file)
        cj = http.cookiejar.MozillaCookieJar(cookie_file)
        try:
            cj.load(ignore_discard=True, ignore_expires=True)
            return cj
        except Exception as e:
            console.print(f"[bold red][-] Could not load cookie jar:[/bold red] {e}")
            return None
    # Parse in-memory Netscape content.
    if "# Netscape" in cookie_file or "\tTRUE\t" in cookie_file or "\tFALSE\t" in cookie_file:
        cj = http.cookiejar.MozillaCookieJar()
        try:
            sanitized = sanitize_netscape_cookie_text(cookie_file)
            cj._really_load(io.StringIO(sanitized), "<string>", ignore_discard=True, ignore_expires=True)
            return cj
        except Exception:
            pass
    # Fallback: parse cookies without saving profile.
    valid_file = prepare_cookies(cookie_file, save_profile=False)
    if valid_file and os.path.isfile(valid_file):
        cj = http.cookiejar.MozillaCookieJar(valid_file)
        try:
            cj.load(ignore_discard=True, ignore_expires=True)
            return cj
        except Exception as e:
            console.print(f"[bold red][-] Could not load cookie jar:[/bold red] {e}")
            return None
    return None

def show_cookie_tutorial(platform: str):
    """Display cookie guide for platform."""
    clear_terminal()
    plat = platform.lower()
    table = Table(
        title=f"[bold cyan][TUTORIAL] HOW TO GET {platform.upper()} CREDENTIALS[/bold cyan]",
        box=box.ASCII,
        border_style="cyan",
        header_style="bold yellow"
    )
    table.add_column("Step", style="bold white", width=8)
    table.add_column("Instructions", style="dim white")

    if plat == "instagram":
        table.add_row("1", "Open Instagram.com in your web browser and ensure you are logged in.")
        table.add_row("2", "Press F12 to open Developer Tools, then navigate to Application (or Storage) -> Cookies -> https://www.instagram.com.")
        table.add_row("3", "Find the cookie named 'sessionid' and copy its Value string.")
        table.add_row("4", "Alternatively, use a browser extension like 'Get cookies.txt LOCALLY' to export cookies.txt.")
        table.add_row("5", "Paste either the sessionid value or the file path directly into the prompt.")
    elif plat == "tiktok":
        table.add_row("1", "Open TikTok.com in your web browser and log in to your account.")
        table.add_row("2", "Press F12 -> Developer Tools -> Application -> Cookies -> https://www.tiktok.com.")
        table.add_row("3", "Locate 'sessionid' (or 'sessionid_ss') and copy its Value.")
        table.add_row("4", "Alternatively, export cookies using 'Get cookies.txt LOCALLY' or 'Cookie-Editor'.")
        table.add_row("5", "Or download your user_data.json data export file from TikTok Privacy settings.")
    elif plat == "youtube":
        table.add_row("1", "Open YouTube.com in your web browser and sign in to your Google/YouTube account.")
        table.add_row("2", "Install the browser extension 'Get cookies.txt LOCALLY' (Chrome, Edge, Firefox).")
        table.add_row("3", "While on YouTube.com, open the extension and click 'Export'.")
        table.add_row("4", "Save the file as 'youtube_cookies.txt' or copy its full path.")
        table.add_row("5", "This allows downloading private playlists (Watch Later 'WL', Liked Videos 'LL', and unlisted videos).")
    elif plat in ("x", "twitter"):
        table.add_row("1", "Open X.com (Twitter) in your web browser and ensure you are logged in.")
        table.add_row("2", "Press F12 to open Developer Tools -> Application (or Storage) -> Cookies -> https://x.com.")
        table.add_row("3", "Find 'auth_token' and copy its Value string (also copy 'ct0' if available).")
        table.add_row("4", "Alternatively, export cookies using browser extension 'Get cookies.txt LOCALLY' or 'Cookie-Editor'.")
        table.add_row("5", "Paste either the auth_token value, 'auth_token=...; ct0=...', or file path directly into the prompt.")
    elif plat in ("sc", "snd", "soundcloud"):
        table.add_row("1", "Open SoundCloud.com in your web browser and ensure you are logged in.")
        table.add_row("2", "Press F12 to open Developer Tools -> Application (or Storage) -> Cookies -> https://soundcloud.com.")
        table.add_row("3", "Find 'oauth_token' and copy its Value string.")
        table.add_row("4", "Alternatively, export cookies using browser extension 'Get cookies.txt LOCALLY' or 'Cookie-Editor'.")
        table.add_row("5", "Paste either oauth_token, 'oauth_token=...; ...', or file path directly into the prompt.")
    elif plat in ("rd", "reddit"):
        table.add_row("1", "Open Reddit.com in your web browser and ensure you are logged in.")
        table.add_row("2", "Press F12 -> Developer Tools -> Application -> Cookies -> https://www.reddit.com.")
        table.add_row("3", "Find 'reddit_session' and copy its Value string.")
        table.add_row("4", "Alternatively, export cookies using browser extension 'Get cookies.txt LOCALLY' or 'Cookie-Editor'.")
        table.add_row("5", "Paste either reddit_session, cookie header string, or file path directly into the prompt.")
    elif plat in ("fb", "facebook"):
        table.add_row("1", "Open Facebook.com in your web browser and ensure you are logged in.")
        table.add_row("2", "Press F12 -> Developer Tools -> Application -> Cookies -> https://www.facebook.com.")
        table.add_row("3", "Find 'c_user' (user ID) and 'xs' (session secret) values.")
        table.add_row("4", "Alternatively, export cookies using browser extension 'Get cookies.txt LOCALLY' or 'Cookie-Editor'.")
        table.add_row("5", "Paste either 'c_user=...; xs=...', 'c_user:xs', or file path directly into the prompt.")
    elif plat in ("pin", "pinterest"):
        table.add_row("1", "Open Pinterest.com in your web browser and ensure you are logged in.")
        table.add_row("2", "Press F12 -> Developer Tools -> Application -> Cookies -> https://www.pinterest.com.")
        table.add_row("3", "Find '_pinterest_sess' and copy its Value string.")
        table.add_row("4", "Alternatively, export cookies using browser extension 'Get cookies.txt LOCALLY' or 'Cookie-Editor'.")
        table.add_row("5", "Paste either '_pinterest_sess' value, cookie header, or file path directly into the prompt.")
    elif plat in ("ttv", "twitch"):
        table.add_row("1", "Open Twitch.tv in your web browser and ensure you are logged in.")
        table.add_row("2", "Press F12 -> Developer Tools -> Application -> Cookies -> https://www.twitch.tv.")
        table.add_row("3", "Find 'auth-token' and copy its Value string.")
        table.add_row("4", "Alternatively, export cookies using browser extension 'Get cookies.txt LOCALLY' or 'Cookie-Editor'.")
        table.add_row("5", "Paste either the auth-token value, cookie string, or file path directly into the prompt.")
    elif plat in ("th", "thread", "threads"):
        table.add_row("1", "Open Threads.net in your web browser and ensure you are logged in.")
        table.add_row("2", "Press F12 -> Developer Tools -> Application -> Cookies -> https://www.threads.net.")
        table.add_row("3", "Find 'sessionid' and 'ds_user_id' values.")
        table.add_row("4", "Alternatively, export cookies using browser extension 'Get cookies.txt LOCALLY' or 'Cookie-Editor'.")
        table.add_row("5", "Note: If you already configured Instagram cookies, Threads can automatically use them!")
    elif plat in ("sp", "spotify"):
        table.add_row("1", "Open open.spotify.com in your web browser and ensure you are logged in.")
        table.add_row("2", "Press F12 -> Developer Tools -> Application -> Cookies -> https://open.spotify.com.")
        table.add_row("3", "Find 'sp_dc' (and optionally 'sp_key') and copy the Value string.")
        table.add_row("4", "Alternatively, export cookies using browser extension 'Get cookies.txt LOCALLY' or 'Cookie-Editor'.")
        table.add_row("5", "Paste either 'sp_dc' value, cookie header, or file path directly into the prompt.")

    console.print()
    console.print(table)
    console.print()

def detect_account_username(platform: str, cookie_file: str) -> str | None:
    """Extract username from cookie session."""
    if not cookie_file or not os.path.isfile(cookie_file):
        return None

    plat = platform.lower().strip()
    cj = load_cookie_jar(cookie_file)
    if not cj:
        return None

    cookie_dict = {c.name: c.value for c in cj}
    s = requests.Session()
    s.cookies.update(cj)

    if plat == "instagram":
        user_id = cookie_dict.get("ds_user_id")
        try:
            h = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "X-IG-App-ID": "936619743392459",
                "X-Requested-With": "XMLHttpRequest"
            }
            r = s.get("https://www.instagram.com/api/v1/accounts/edit/web_form_data/", headers=h, timeout=8)
            if r.status_code == 200:
                data = r.json()
                u = data.get("form_data", {}).get("username")
                if u:
                    return f"@{u}"
        except Exception:
            pass
        if user_id:
            try:
                h = {"User-Agent": "Instagram 219.0.0.12.117 Android"}
                r = s.get(f"https://i.instagram.com/api/v1/users/{user_id}/info/", headers=h, timeout=8)
                if r.status_code == 200:
                    u = r.json().get("user", {}).get("username")
                    if u:
                        return f"@{u}"
            except Exception:
                pass
            return f"@user_{user_id}"

    elif plat == "tiktok":
        try:
            h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = s.get("https://www.tiktok.com/passport/web/account/info/", headers=h, timeout=8)
            if r.status_code == 200:
                u = r.json().get("data", {}).get("username")
                if u:
                    return f"@{u}"
        except Exception:
            pass
        if cookie_dict.get("uid"):
            return f"@user_{cookie_dict.get('uid')}"

    elif plat == "youtube":
        try:
            h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = s.get("https://www.youtube.com", headers=h, timeout=8)
            if r.status_code == 200:
                import re
                m = re.search(r'"USER_NAME":"([^"]+)"', r.text)
                if m and m.group(1):
                    return f"@{m.group(1)}"
                m = re.search(r'"channelName":"([^"]+)"', r.text)
                if m and m.group(1):
                    return f"@{m.group(1)}"
                m = re.search(r'"canonicalChannelUrl":"[^"]*@([^"]+)"', r.text)
                if m and m.group(1):
                    return f"@{m.group(1)}"
        except Exception:
            pass

    elif plat in ("x", "twitter"):
        ct0 = cookie_dict.get("ct0")
        try:
            h = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
            }
            if ct0:
                h["x-csrf-token"] = ct0
            r = s.get("https://api.x.com/1.1/account/settings.json", headers=h, timeout=8)
            if r.status_code == 200:
                sn = r.json().get("screen_name")
                if sn:
                    return f"@{sn}"
        except Exception:
            pass

    elif plat in ("soundcloud", "sc"):
        try:
            r = s.get("https://soundcloud.com/you", allow_redirects=True, timeout=8)
            if r.url and "soundcloud.com/you" not in r.url:
                parts = r.url.rstrip("/").split("/")
                if parts and parts[-1] and parts[-1] != "you":
                    return f"@{parts[-1]}"
        except Exception:
            pass

    elif plat == "reddit":
        try:
            h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = s.get("https://www.reddit.com/api/v1/me.json", headers=h, timeout=8)
            if r.status_code == 200:
                name = r.json().get("name")
                if name:
                    return f"u/{name}"
        except Exception:
            pass

    elif plat == "spotify":
        try:
            h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = s.get("https://open.spotify.com", headers=h, timeout=8)
            if r.status_code == 200:
                import re
                m = re.search(r'"name":"([^"]+)"', r.text)
                if m and m.group(1):
                    return f"@{m.group(1)}"
        except Exception:
            pass

    elif plat in ("twitch", "ttv"):
        login = cookie_dict.get("login") or cookie_dict.get("name")
        if login:
            return f"@{login}"
        try:
            h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = s.get("https://www.twitch.tv", headers=h, timeout=8)
            if r.status_code == 200:
                import re
                m = re.search(r'"login":"([^"]+)"', r.text)
                if m and m.group(1):
                    return f"@{m.group(1)}"
        except Exception:
            pass

    elif plat in ("facebook", "fb"):
        c_user = cookie_dict.get("c_user")
        if c_user:
            return f"@user_{c_user}"

    elif plat == "threads":
        user_id = cookie_dict.get("ds_user_id")
        if user_id:
            return f"@threads_{user_id}"

    elif plat in ("pinterest", "pin"):
        try:
            h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = s.get("https://www.pinterest.com", headers=h, timeout=8)
            if r.url and "pinterest.com" in r.url:
                parts = r.url.rstrip("/").split("/")
                if parts and parts[-1] not in ("www.pinterest.com", "pinterest.com", ""):
                    return f"@{parts[-1]}"
        except Exception:
            pass

    return None

def resolve_cookie_file(platform: str, force_prompt: bool = False, required: bool = True) -> str | None:
    """Resolve active cookie file for platform."""
    plat = platform.lower()
    profiles = config_mgr.get_cookie_profiles(plat)
    default_name = config_mgr.get_default_cookie_profile_name(plat)

    if not force_prompt:
        if default_name:
            for p in profiles:
                if p["name"] == default_name and os.path.isfile(p["file"]):
                    return os.path.abspath(p["file"])
        if len(profiles) == 1 and os.path.isfile(profiles[0]["file"]):
            return os.path.abspath(profiles[0]["file"])
        if not profiles and not required:
            return None

    valid_profiles = [p for p in profiles if os.path.isfile(p["file"])]
    if valid_profiles and (force_prompt or not default_name):
        opts = []
        for i, p in enumerate(valid_profiles, 1):
            opts.append({
                "key": str(i),
                "title": f"Profile: {p['name']}",
                "desc": "[Default Profile]" if p["name"] == default_name else "[Active Profile]",
                "value": p["file"]
            })
        opts.append({"key": str(len(opts) + 1), "title": "[ADD] Add New Profile", "desc": "Paste session token directly", "value": "add"})
        opts.append({"key": "0", "title": "[CANCEL] Cancel / Continue Without", "desc": "Proceed without cookies", "value": "cancel"})
        sel = interactive_select(f"SELECT {platform.upper()} COOKIE PROFILE", opts, default_index=0, border_style="yellow")
        if sel not in ("cancel", "add", None):
            return sel
        if sel in ("cancel", None):
            return None

    if not sys.stdin.isatty():
        return None

    console.print(f"[bold yellow][!] Authentication required for {platform.title()}. No cookies configured.[/bold yellow]")
    show_cookie_tutorial(plat)

    raw_c = ask_input(f"[bold cyan]Paste {platform.title()} session token / cookies string or file path directly[/bold cyan]")
    if not raw_c:
        console.print("[dim]Operation cancelled or continuing without cookies.[/dim]")
        return None

    c_path = None
    if plat == "instagram":
        c_path = prepare_cookies(raw_c, save_profile=False)
    elif plat == "tiktok":
        c_path = prepare_tiktok_cookies(raw_c, save_profile=False)
    elif plat == "youtube":
        c_path = prepare_youtube_cookies(raw_c, save_profile=False)
    elif plat in ("x", "twitter"):
        c_path = prepare_x_cookies(raw_c, save_profile=False)
    elif plat in ("sc", "snd", "soundcloud"):
        c_path = prepare_soundcloud_cookies(raw_c, save_profile=False)
    elif plat in ("rd", "reddit"):
        c_path = prepare_reddit_cookies(raw_c, save_profile=False)
    elif plat in ("fb", "facebook"):
        c_path = prepare_facebook_cookies(raw_c, save_profile=False)
    elif plat in ("pin", "pinterest"):
        c_path = prepare_pinterest_cookies(raw_c, save_profile=False)
    elif plat in ("ttv", "twitch"):
        c_path = prepare_twitch_cookies(raw_c, save_profile=False)
    elif plat in ("th", "thread", "threads"):
        c_path = prepare_threads_cookies(raw_c, save_profile=False)
    elif plat in ("sp", "spotify"):
        c_path = prepare_spotify_cookies(raw_c, save_profile=False)

    if c_path and os.path.isfile(c_path):
        detected_user = detect_account_username(plat, c_path)
        if detected_user:
            clean_user = detected_user if detected_user.startswith("@") else f"@{detected_user}"
            console.print(f"[bold green][OK] Auto-detected account username:[/bold green] [bold cyan]{clean_user}[/bold cyan]")
        else:
            prof_name = ask_input("[bold cyan]Enter account username handle (e.g. @username)[/bold cyan]")
            if not prof_name:
                return os.path.abspath(c_path)
            clean_user = prof_name if prof_name.startswith("@") else f"@{prof_name}"
        with open(c_path, "r", encoding="utf-8", errors="ignore") as f:
            cookie_content = f.read()
        saved_file = config_mgr.save_internal_session(plat, clean_user, cookie_content, set_as_default=True)
        console.print(f"[bold green][OK] Saved and set '{clean_user}' as default {platform.title()} profile.[/bold green]")
        return os.path.abspath(saved_file)
    else:
        console.print("[bold red][-] Failed to parse provided cookies.[/bold red]")
        return None
