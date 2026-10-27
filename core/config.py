"""Configuration and cookie persistence manager."""
import copy
import http.cookiejar
import io
import json
import os
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional

DEFAULT_CONFIG_FILE = "config.json"

def get_sessions_dir() -> str:
    """Get internal dedicated sessions folder in system temp directory."""
    d = os.path.join(tempfile.gettempdir(), "mbd_sessions")
    os.makedirs(d, exist_ok=True)
    return d

def get_default_desktop_dir() -> str:
    """Get standard user Desktop download destination."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.expanduser("~")
    return os.path.join(desktop, "HaustusDownloads")

class ConfigManager:
    """Persistent configuration manager."""

    def __init__(self, config_path: str = DEFAULT_CONFIG_FILE):
        self.config_path = os.path.abspath(config_path)
        self.data: Dict[str, Any] = self._load()
        self._migrate_legacy_txt_files()

    def _default_state(self) -> Dict[str, Any]:
        default_dir = get_default_desktop_dir()
        return {
            "output_dirs": [default_dir],
            "default_output_dir": default_dir,
            "links_files": [],
            "default_links_file": None,
            "default_mode": None,          # "video" | "audio" | None (prompt each time)
            "default_video_quality": None, # e.g. "best", "1080", "720" | None
            "default_audio_format": None,  # e.g. "mp3", "m4a" | None
            "default_audio_quality": None,
            "default_embed_metadata": True, # e.g. "320", "192" | None
            "default_speed_limit": None,     # str e.g. "5M" | None (unlimited)
            "archive_bulk_mode": "always",       # "always" [default] | "disabled" | "prompt"
            "archive_single_mode": "disabled",   # "disabled" [default] | "always" | "prompt"
            "archive_missing_policy": "prompt",  # "prompt" [default] | "skip" | "redownload"
            "cookies": {
                "instagram": {"profiles": [], "default": None},
                "tiktok": {"profiles": [], "default": None},
                "youtube": {"profiles": [], "default": None},
                "x": {"profiles": [], "default": None},
                "soundcloud": {"profiles": [], "default": None},
                "reddit": {"profiles": [], "default": None},
                "facebook": {"profiles": [], "default": None},
                "pinterest": {"profiles": [], "default": None},
                "twitch": {"profiles": [], "default": None},
                "threads": {"profiles": [], "default": None},
                "spotify": {"profiles": [], "default": None},
            }
        }

    def _migrate_legacy_txt_files(self):
        """Migrate legacy cookie files into config."""
        changed = False

        for plat in ("instagram", "tiktok", "youtube", "x", "soundcloud", "reddit", "facebook", "pinterest", "twitch", "threads", "spotify"):
            for p in self.data.get("cookies", {}).get(plat, {}).get("profiles", []):
                if "file" in p and not p.get("data"):
                    f_path = p.get("file")
                    if f_path and os.path.isfile(f_path):
                        try:
                            with open(f_path, "r", encoding="utf-8", errors="ignore") as f:
                                p["data"] = f.read().strip()
                            changed = True
                        except (IOError, OSError):
                            pass

        legacy_files = [
            "cookies.txt", "instagram_cookies.txt", "tiktok_cookies.txt",
            "youtube_cookies.txt", "x_cookies.txt", "twitter_cookies.txt",
            "soundcloud_cookies.txt", "reddit_cookies.txt", "facebook_cookies.txt",
            "fb_cookies.txt", "pinterest_cookies.txt", "pin_cookies.txt",
            "twitch_cookies.txt", "threads_cookies.txt", "spotify_cookies.txt",
            "sp_cookies.txt", "test_valid_cookies.txt"
        ]
        for c_file in legacy_files:
            if os.path.isfile(c_file):
                try:
                    os.remove(c_file)
                    changed = True
                except (IOError, OSError):
                    pass

        # Clean up legacy .sessions directory if present.
        sessions_dir = os.path.abspath(".sessions")
        if os.path.isdir(sessions_dir):
            try:
                shutil.rmtree(sessions_dir, ignore_errors=True)
                changed = True
            except Exception:
                pass

        # Remove legacy file path references from cookie profiles.
        for plat in ("instagram", "tiktok", "youtube", "x", "soundcloud", "reddit", "facebook", "pinterest", "twitch", "threads", "spotify"):
            for p in self.data.get("cookies", {}).get(plat, {}).get("profiles", []):
                if "file" in p:
                    p.pop("file", None)
                    changed = True

        # Remove test and placeholder profile names left from development.
        dummy_names = {
            "@instagram_user", "@tiktok_user", "@youtube_user", "@x_user",
            "@soundcloud_user", "@reddit_user", "@facebook_user", "@pinterest_user",
            "@twitch_user", "@threads_user", "@spotify_user", "Default Account",
            "@account_1"
        }
        for plat in ("instagram", "tiktok", "youtube", "x", "soundcloud", "reddit", "facebook", "pinterest", "twitch", "threads", "spotify"):
            if plat in self.data.get("cookies", {}):
                profs = self.data["cookies"][plat].get("profiles", [])
                filtered = [p for p in profs if p.get("name") not in dummy_names]
                if len(filtered) != len(profs):
                    self.data["cookies"][plat]["profiles"] = filtered
                    if self.data["cookies"][plat].get("default") in dummy_names:
                        self.data["cookies"][plat]["default"] = filtered[0]["name"] if filtered else None
                    changed = True

        # Remove deprecated notifications key if present.
        if "notifications" in self.data:
            self.data.pop("notifications", None)
            changed = True

        if changed:
            self.save()

    def _load(self) -> Dict[str, Any]:
        if os.path.isfile(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Populate missing default configuration keys.
                base = self._default_state()
                for k, v in base.items():
                    if k not in data:
                        data[k] = v
                    elif isinstance(v, dict):
                        for sub_k, sub_v in v.items():
                            if sub_k not in data[k]:
                                data[k][sub_k] = sub_v
                return data
            except (IOError, OSError, json.JSONDecodeError):
                pass
        state = self._default_state()
        self.save(state)
        return state

    def save(self, data: Optional[Dict[str, Any]] = None):
        if data is not None:
            self.data = data
        try:
            save_data = copy.deepcopy(self.data)
            for plat in save_data.get("cookies", {}).values():
                if isinstance(plat, dict) and "profiles" in plat:
                    for prof in plat["profiles"]:
                        if isinstance(prof, dict):
                            prof.pop("file", None)

            tmp_path = f"{self.config_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            if os.path.isfile(self.config_path):
                os.replace(tmp_path, self.config_path)
            else:
                os.rename(tmp_path, self.config_path)
        except (IOError, OSError):
            pass

    def get_output_dirs(self) -> List[str]:
        dirs = self.data.get("output_dirs", [])
        return [os.path.abspath(d) for d in dirs]

    def get_default_output_dir(self) -> str:
        d = self.data.get("default_output_dir")
        if not d:
            d = get_default_desktop_dir()
            self.data["default_output_dir"] = d
            if d not in self.data["output_dirs"]:
                self.data["output_dirs"].append(d)
            self.save()
        return os.path.abspath(d)

    def add_output_dir(self, path: str, set_as_default: bool = False) -> str:
        norm = os.path.abspath(path.strip())
        os.makedirs(norm, exist_ok=True)
        if norm not in self.data["output_dirs"]:
            self.data["output_dirs"].append(norm)
        if set_as_default:
            self.data["default_output_dir"] = norm
        self.save()
        return norm

    def set_default_output_dir(self, path: str):
        norm = os.path.abspath(path.strip())
        if norm not in self.data["output_dirs"]:
            self.data["output_dirs"].append(norm)
        self.data["default_output_dir"] = norm
        self.save()

    def remove_output_dir(self, path: str):
        norm = os.path.abspath(path.strip())
        self.data["output_dirs"] = [d for d in self.data.get("output_dirs", []) if os.path.abspath(d) != norm]
        if self.data.get("default_output_dir") == norm:
            dirs = self.data["output_dirs"]
            self.data["default_output_dir"] = dirs[0] if dirs else get_default_desktop_dir()
        self.save()

    def get_links_files(self) -> List[str]:
        files = self.data.get("links_files", [])
        return [os.path.abspath(f) for f in files if os.path.isfile(f)]

    def get_default_links_file(self) -> Optional[str]:
        f = self.data.get("default_links_file")
        if f and os.path.isfile(f):
            return os.path.abspath(f)
        return None

    def add_links_file(self, path: str, set_as_default: bool = False) -> Optional[str]:
        norm = os.path.abspath(path.strip())
        if not os.path.isfile(norm):
            return None
        if norm not in self.data.get("links_files", []):
            if "links_files" not in self.data:
                self.data["links_files"] = []
            self.data["links_files"].append(norm)
        if set_as_default:
            self.data["default_links_file"] = norm
        self.save()
        return norm

    def set_default_links_file(self, path: Optional[str]):
        if path is None:
            self.data["default_links_file"] = None
        else:
            norm = os.path.abspath(path.strip())
            if norm not in self.data.get("links_files", []):
                self.data["links_files"].append(norm)
            self.data["default_links_file"] = norm
        self.save()

    def remove_links_file(self, path: str):
        norm = os.path.abspath(path.strip())
        self.data["links_files"] = [f for f in self.data.get("links_files", []) if os.path.abspath(f) != norm]
        if self.data.get("default_links_file") == norm:
            self.data["default_links_file"] = None
        self.save()

    def get_default_mode(self) -> Optional[str]:
        return self.data.get("default_mode")

    def set_default_mode(self, mode: Optional[str]):
        self.data["default_mode"] = mode
        self.save()

    def get_default_video_quality(self) -> Optional[str]:
        return self.data.get("default_video_quality")

    def set_default_video_quality(self, quality: Optional[str]):
        self.data["default_video_quality"] = quality
        self.save()

    def get_default_audio_format(self) -> Optional[str]:
        return self.data.get("default_audio_format")

    def set_default_audio_format(self, fmt: Optional[str]):
        self.data["default_audio_format"] = fmt
        self.save()

    def get_default_audio_quality(self) -> Optional[str]:
        return self.data.get("default_audio_quality")

    def set_default_audio_quality(self, q: Optional[str]):
        self.data["default_audio_quality"] = q
        self.save()

    def get_default_embed_metadata(self) -> Optional[bool]:
        return self.data.get("default_embed_metadata")

    def set_default_embed_metadata(self, val: Optional[bool]):
        self.data["default_embed_metadata"] = val
        self.save()

    def get_default_speed_limit(self) -> Optional[str]:
        return self.data.get("default_speed_limit")

    def set_default_speed_limit(self, val: Optional[str]):
        self.data["default_speed_limit"] = val
        self.save()

    def get_speed_limit_bytes(self) -> Optional[int]:
        """Convert speed limit string (e.g. '5M', '500K') to integer bytes/sec."""
        val = self.get_default_speed_limit()
        if not val or str(val).lower().strip() in ("none", "unlimited", "0"):
            return None
        clean = str(val).strip().upper()
        try:
            if clean.endswith("M") or clean.endswith("MB") or clean.endswith("MIB"):
                num = float(re.sub(r"[A-Z]", "", clean))
                return int(num * 1024 * 1024)
            elif clean.endswith("K") or clean.endswith("KB") or clean.endswith("KIB"):
                num = float(re.sub(r"[A-Z]", "", clean))
                return int(num * 1024)
            elif clean.endswith("G") or clean.endswith("GB"):
                num = float(re.sub(r"[A-Z]", "", clean))
                return int(num * 1024 * 1024 * 1024)
            return int(float(clean))
        except Exception:
            return None

    def get_archive_bulk_mode(self) -> str:
        """Get duplicate check policy for bulk downloads."""
        val = self.data.get("archive_bulk_mode", "always")
        if val not in ("always", "disabled", "prompt"):
            val = "always"
        return val

    def set_archive_bulk_mode(self, mode: str):
        if mode in ("always", "disabled", "prompt"):
            self.data["archive_bulk_mode"] = mode
            self.save()

    def get_archive_single_mode(self) -> str:
        """Get duplicate check policy for single downloads."""
        val = self.data.get("archive_single_mode", "disabled")
        if val not in ("always", "disabled", "prompt"):
            val = "disabled"
        return val

    def set_archive_single_mode(self, mode: str):
        if mode in ("always", "disabled", "prompt"):
            self.data["archive_single_mode"] = mode
            self.save()

    def get_archive_missing_policy(self) -> str:
        """Get policy for missing history files."""
        val = self.data.get("archive_missing_policy", "prompt")
        if val not in ("prompt", "skip", "redownload"):
            val = "prompt"
        return val

    def set_archive_missing_policy(self, policy: str):
        if policy in ("prompt", "skip", "redownload"):
            self.data["archive_missing_policy"] = policy
            self.save()

    def _norm_plat(self, platform: str) -> str:
        p = platform.lower().strip()
        if p in ("x", "twitter"):
            return "x"
        if p in ("sc", "snd", "soundcloud"):
            return "soundcloud"
        if p in ("rd", "reddit"):
            return "reddit"
        if p in ("fb", "facebook"):
            return "facebook"
        if p in ("pin", "pinterest"):
            return "pinterest"
        if p in ("ttv", "twitch"):
            return "twitch"
        if p in ("th", "thread", "threads"):
            return "threads"
        if p in ("sp", "spotify"):
            return "spotify"
        return p

    @staticmethod
    def _normalize_netscape_cookie_str(cookie_data: str) -> str:
        lines = []
        for raw_line in (cookie_data or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                parts = line.split()
            if len(parts) >= 7:
                domain, flag, path, secure, exp, name = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
                value = " ".join(parts[6:]) if "\t" not in line else "\t".join(parts[6:])
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                secure = "TRUE" if secure.upper() == "TRUE" else "FALSE"
                try:
                    exp_int = int(float(exp))
                    if exp_int <= 0:
                        exp_int = 2147483647
                    exp = str(exp_int)
                except ValueError:
                    exp = "2147483647"
                lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{exp}\t{name}\t{value}")
        if lines:
            return "# Netscape HTTP Cookie File\n# https://curl.haxx.se/rfc/cookie_spec.html\n\n" + "\n".join(lines) + "\n"
        return cookie_data.strip() + "\n"

    def _get_or_create_temp_cookie_file(self, platform: str, profile_name: str, cookie_data: str) -> str:
        """Get ephemeral cookie file path."""
        temp_dir = os.path.join(tempfile.gettempdir(), "mbd_cookies")
        os.makedirs(temp_dir, exist_ok=True)
        safe_name = re.sub(r'[\\/*?:"<>|@\s]', "_", profile_name).strip("_").lower()
        if not safe_name:
            safe_name = "default"
        file_path = os.path.join(temp_dir, f"{platform}_{safe_name}.txt")
        try:
            normalized = self._normalize_netscape_cookie_str(cookie_data)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(normalized)
        except Exception:
            pass
        return os.path.abspath(file_path)

    def get_cookie_profiles(self, platform: str) -> List[Dict[str, str]]:
        plat = self._norm_plat(platform)
        profiles = self.data.get("cookies", {}).get(plat, {}).get("profiles", [])
        for p in profiles:
            if "data" in p and p["data"]:
                p["file"] = self._get_or_create_temp_cookie_file(plat, p.get("name", "profile"), p["data"])
        return profiles

    def get_default_cookie_profile_name(self, platform: str) -> Optional[str]:
        plat = self._norm_plat(platform)
        return self.data.get("cookies", {}).get(plat, {}).get("default")

    def get_effective_cookie_data(self, platform: str) -> Optional[str]:
        plat = self._norm_plat(platform)
        profiles = self.data.get("cookies", {}).get(plat, {}).get("profiles", [])
        default_name = self.get_default_cookie_profile_name(plat)

        if default_name:
            for p in profiles:
                if p.get("name") == default_name and p.get("data"):
                    return p["data"]

        for p in profiles:
            if p.get("data"):
                return p["data"]

        return None

    def get_effective_cookie_jar(self, platform: str) -> Optional[http.cookiejar.MozillaCookieJar]:
        data = self.get_effective_cookie_data(platform)
        if not data:
            return None
        cj = http.cookiejar.MozillaCookieJar()
        try:
            normalized = self._normalize_netscape_cookie_str(data)
            cj._really_load(io.StringIO(normalized), "<config.json>", ignore_discard=True, ignore_expires=True)
            return cj
        except Exception:
            return None

    def get_effective_cookie_file(self, platform: str) -> Optional[str]:
        plat = self._norm_plat(platform)
        profiles = self.get_cookie_profiles(plat)
        default_name = self.get_default_cookie_profile_name(plat)

        if default_name:
            for p in profiles:
                if p.get("name") == default_name:
                    if p.get("data"):
                        return self._get_or_create_temp_cookie_file(plat, p["name"], p["data"])
                    elif p.get("file") and os.path.isfile(p["file"]):
                        return os.path.abspath(p["file"])

        for p in profiles:
            if p.get("data"):
                return self._get_or_create_temp_cookie_file(plat, p["name"], p["data"])
            elif p.get("file") and os.path.isfile(p["file"]):
                return os.path.abspath(p["file"])

        return None

    def add_cookie_profile(self, platform: str, name: str, data_or_file: str, set_as_default: bool = False):
        plat = self._norm_plat(platform)
        if "cookies" not in self.data or not isinstance(self.data["cookies"], dict):
            self.data["cookies"] = {
                "instagram": {"profiles": [], "default": None},
                "tiktok": {"profiles": [], "default": None},
                "youtube": {"profiles": [], "default": None},
                "x": {"profiles": [], "default": None},
            }
        if plat not in self.data["cookies"]:
            self.data["cookies"][plat] = {"profiles": [], "default": None}

        cookie_text = ""
        if os.path.isfile(data_or_file):
            try:
                with open(data_or_file, "r", encoding="utf-8", errors="ignore") as f:
                    cookie_text = f.read().strip()
            except Exception:
                cookie_text = ""
        else:
            cookie_text = str(data_or_file).strip()

        profiles = self.data["cookies"][plat]["profiles"]
        profiles = [p for p in profiles if p.get("name", "").lower() != name.lower()]
        new_prof = {
            "name": name.strip(),
            "data": cookie_text
        }
        profiles.append(new_prof)
        self.data["cookies"][plat]["profiles"] = profiles

        if set_as_default or len(profiles) == 1:
            self.data["cookies"][plat]["default"] = name.strip()

        self.save()

    def set_default_cookie_profile(self, platform: str, name: str):
        plat = self._norm_plat(platform)
        if plat in self.data.get("cookies", {}):
            self.data["cookies"][plat]["default"] = name
            self.save()

    def edit_cookie_profile_name(self, platform: str, old_name: str, new_name: str):
        plat = self._norm_plat(platform)
        if plat in self.data.get("cookies", {}):
            for p in self.data["cookies"][plat]["profiles"]:
                if p.get("name") == old_name:
                    p["name"] = new_name.strip()
            if self.data["cookies"][plat].get("default") == old_name:
                self.data["cookies"][plat]["default"] = new_name.strip()
            self.save()

    def delete_cookie_profile(self, platform: str, name: str):
        plat = self._norm_plat(platform)
        if plat in self.data.get("cookies", {}):
            profiles = self.data["cookies"][plat]["profiles"]
            self.data["cookies"][plat]["profiles"] = [p for p in profiles if p.get("name") != name]
            if self.data["cookies"][plat].get("default") == name:
                rem = self.data["cookies"][plat]["profiles"]
                self.data["cookies"][plat]["default"] = rem[0]["name"] if rem else None
            # Remove corresponding temporary cookie file if present.
            safe_name = re.sub(r'[\\/*?:"<>|@\s]', "_", name).strip("_").lower()
            temp_path = os.path.join(tempfile.gettempdir(), "mbd_cookies", f"{plat}_{safe_name}.txt")
            if os.path.isfile(temp_path):
                try:
                    os.remove(temp_path)
                except (IOError, OSError):
                    pass
            self.save()

    def save_internal_session(self, platform: str, username: str, content: str, set_as_default: bool = True) -> str:
        """Save cookie data to config."""
        plat = self._norm_plat(platform)
        clean_user = username if username.startswith("@") else f"@{username}"
        self.add_cookie_profile(plat, clean_user, content, set_as_default=set_as_default)
        return self._get_or_create_temp_cookie_file(plat, clean_user, content)

    def reset_to_defaults(self):
        """Reset all configuration settings to factory default."""
        self.data = self._default_state()
        self.save()
