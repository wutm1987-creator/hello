import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
import threading
import os
import json
import re
from concurrent.futures import ThreadPoolExecutor


NETEASE_APIS = [
    "https://ncmapi.btwoa.com",
    "https://api.toolkal.com",
    "https://ncme.zhenxin.me",
    "https://api.2leo.top",
]
METING_APIS = [
    {"search": "https://api.injahow.cn/meting/", "url": "https://api.injahow.cn/meting/"},
    {"search": "https://meting.qjqq.cn", "url": "https://meting.qjqq.cn"},
    {"search": "https://metingapi.vercel.app/api", "url": "https://metingapi.vercel.app/api"},
    {"search": "https://meting.heheda.top/api", "url": "https://meting.heheda.top/api"},
]

SOURCES = {
    "netease": "网易云",
    "kuwo": "酷我音乐",
    "audius": "Audius",
}

KUWO_SEARCH_URL = "https://search.kuwo.cn/r.s"
KUWO_SONG_URL = "https://antiserver.kuwo.cn/anti.s"

AUDIUS_HOSTS = [
    "https://discoveryprovider.audius.co",
    "https://discoveryprovider2.audius.co",
    "https://discoveryprovider3.audius.co",
    "https://discoveryprovider4.audius.co",
    "https://discoveryprovider5.audius.co",
]

APP_NAME = "FreeMusic"
APP_VERSION = "3.4"
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Music", "FreeMusicDownloads")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".freemusic_config.json")

NETEASE_PLAYLISTS = [
    {"id": "3778678", "name": "热歌榜"},
    {"id": "3779629", "name": "新歌榜"},
    {"id": "2884035", "name": "原创榜"},
    {"id": "19723756", "name": "飙升榜"},
    {"id": "10520166", "name": "抖音榜"},
]


def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()


def get_audius_host():
    for host in AUDIUS_HOSTS:
        try:
            resp = requests.get(
                host + "/v1/tracks/trending",
                params={"limit": 1, "app_name": APP_NAME},
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data.get("data"), list):
                    return host
        except Exception:
            continue
    return None


class NeteaseAPI:
    def __init__(self):
        self.source = "netease"

    def _try_netease_apis(self, path, params, timeout=15):
        for base in NETEASE_APIS:
            try:
                resp = requests.get(base + path, params=params, timeout=timeout)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue
        return None

    def search_tracks(self, query, limit=20):
        data = self._try_netease_apis(
            "/cloudsearch", {"keywords": query, "limit": limit, "type": 1}
        )
        if data:
            songs = data.get("result", {}).get("songs", [])
            if songs:
                return [self._normalize(t) for t in songs]
        data = self._try_netease_apis(
            "/search", {"keywords": query, "limit": limit}
        )
        if data:
            songs = data.get("result", {}).get("songs", [])
            if songs:
                return [self._normalize(t) for t in songs]
        return self._meting_search(query, limit)

    def _meting_search(self, query, limit=20):
        for meting in METING_APIS:
            try:
                resp = requests.get(
                    meting["search"],
                    params={"server": "netease", "type": "search", "id": query},
                    timeout=15,
                    verify=False,
                )
                if resp.status_code == 200:
                    ct = resp.headers.get("Content-Type", "")
                    if "json" in ct or "[" in resp.text[:5]:
                        data = resp.json()
                        if isinstance(data, list):
                            return [self._normalize_meting(t) for t in data[:limit]]
            except Exception:
                continue
        return []

    def get_trending_tracks(self, limit=10):
        playlist_id = NETEASE_PLAYLISTS[0]["id"]
        data = self._try_netease_apis(
            "/playlist/track/all", {"id": playlist_id, "limit": limit}, timeout=20
        )
        if data:
            songs = data.get("songs", [])
            if songs:
                return [self._normalize(t) for t in songs[:limit]]
        data = self._try_netease_apis(
            "/playlist/detail", {"id": playlist_id}, timeout=20
        )
        if data:
            tracks = data.get("playlist", {}).get("tracks", [])
            if tracks:
                return [self._normalize_full(t) for t in tracks[:limit]]
        return self._meting_trending(limit)

    def _meting_trending(self, limit=20):
        for meting in METING_APIS:
            try:
                resp = requests.get(
                    meting["search"],
                    params={"server": "netease", "type": "playlist", "id": NETEASE_PLAYLISTS[0]["id"]},
                    timeout=20,
                    verify=False,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return [self._normalize_meting(t) for t in data[:limit]]
            except Exception:
                continue
        return []

    @staticmethod
    def _is_fragment(item):
        if not item:
            return True
        if item.get("freeTrialInfo") is not None:
            return True
        if item.get("time") and item["time"] < 60000:
            return True
        if item.get("size") and item["size"] < 1000000:
            return True
        return False

    def get_stream_url(self, track_id, title="", artist=""):
        for base in NETEASE_APIS:
            try:
                resp = requests.get(base + "/song/url", params={"id": str(track_id), "level": "exhigh", "randomCNIP": "true"}, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    urls = data.get("data", [])
                    if isinstance(urls, list):
                        for item in urls:
                            if item and item.get("url") and not self._is_fragment(item):
                                return item["url"]
                    elif isinstance(urls, dict) and urls.get("url") and not self._is_fragment(urls):
                        return urls["url"]
            except Exception:
                continue
        for base in NETEASE_APIS:
            try:
                resp = requests.get(base + "/song/url/v1", params={"id": str(track_id), "level": "exhigh", "randomCNIP": "true"}, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    urls = data.get("data", [])
                    if isinstance(urls, list):
                        for item in urls:
                            if item and item.get("url") and not self._is_fragment(item):
                                return item["url"]
            except Exception:
                continue
        for base in NETEASE_APIS:
            try:
                resp = requests.get(base + "/song/url", params={"id": str(track_id), "randomCNIP": "true"}, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    urls = data.get("data", [])
                    if isinstance(urls, list):
                        for item in urls:
                            if item and item.get("url") and not self._is_fragment(item):
                                return item["url"]
            except Exception:
                continue
        for meting in METING_APIS:
            try:
                resp = requests.get(
                    meting["url"],
                    params={"server": "netease", "type": "url", "id": str(track_id)},
                    timeout=15,
                    verify=False,
                    allow_redirects=False,
                )
                if resp.status_code == 302:
                    location = resp.headers.get("Location", "")
                    if location:
                        return location
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if isinstance(data, dict) and data.get("url"):
                            return data["url"]
                    except Exception:
                        pass
            except Exception:
                continue
        if title:
            keyword = (artist + " " + title).strip() if artist else title
            kuwo_api = KuwoAPI()
            results = kuwo_api.search_tracks(keyword, 5)
            for r in results:
                url = kuwo_api.get_stream_url(r["id"])
                if url:
                    return url
        return None

    def get_lrc(self, track_id):
        data = self._try_netease_apis("/lyric", {"id": track_id}, timeout=10)
        if data:
            return data.get("lrc", {}).get("lyric", "")
        for meting in METING_APIS:
            try:
                resp = requests.get(
                    meting["url"],
                    params={"server": "netease", "type": "lrc", "id": str(track_id)},
                    timeout=10,
                    verify=False,
                )
                if resp.status_code == 200:
                    return resp.text
            except Exception:
                continue
        return ""

    def _normalize(self, t):
        artists = t.get("ar", t.get("artists", []))
        artist_name = "/".join(a.get("name", "") for a in artists) if artists else "未知"
        album = t.get("al", t.get("album", {}))
        return {
            "id": str(t.get("id", "")),
            "title": t.get("name", "未知"),
            "artist": artist_name,
            "album": album.get("name", "") if isinstance(album, dict) else "",
            "genre": "",
            "duration": t.get("dt", t.get("duration", 0)) // 1000 if t.get("dt", t.get("duration", 0)) else 0,
            "play_count": 0,
            "source": "netease",
        }

    def _normalize_full(self, t):
        artists = t.get("ar", [])
        artist_name = "/".join(a.get("name", "") for a in artists) if artists else "未知"
        return {
            "id": str(t.get("id", "")),
            "title": t.get("name", "未知"),
            "artist": artist_name,
            "album": t.get("al", {}).get("name", ""),
            "genre": "",
            "duration": t.get("dt", 0) // 1000 if t.get("dt", 0) else 0,
            "play_count": 0,
            "source": "netease",
        }

    def _normalize_meting(self, t):
        track_id = str(t.get("id", ""))
        if t.get("url"):
            match = re.search(r'id=(\d+)', t["url"])
            if match:
                track_id = match.group(1)
        return {
            "id": track_id,
            "title": t.get("name", t.get("title", "未知")),
            "artist": t.get("artist", t.get("author", "未知")),
            "album": t.get("album", ""),
            "genre": "",
            "duration": 0,
            "play_count": 0,
            "source": "netease",
        }


class KuwoAPI:
    def __init__(self):
        self.source = "kuwo"

    def search_tracks(self, query, limit=20):
        return self._search_kuwo(query, limit)

    def _search_kuwo(self, query, limit=20):
        try:
            resp = requests.get(
                KUWO_SEARCH_URL,
                params={
                    "all": query,
                    "ft": "music",
                    "itemset": "web_2013",
                    "client": "kt",
                    "pn": 0,
                    "rn": limit,
                    "rformat": "json",
                    "encoding": "utf8",
                },
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "http://www.kuwo.cn",
                },
            )
            if resp.status_code == 200:
                data = self._parse_kuwo_response(resp.text)
                if data:
                    songs = data.get("abslist", [])
                    results = []
                    for s in songs[:limit]:
                        rid = s.get("MUSICRID", "").replace("MUSIC_", "")
                        results.append({
                            "id": rid,
                            "title": s.get("SONGNAME", "").replace("&nbsp;", " "),
                            "artist": s.get("ARTIST", "").replace("&nbsp;", " ") or "未知",
                            "album": s.get("ALBUM", "").replace("&nbsp;", " "),
                            "genre": "",
                            "duration": 0,
                            "play_count": 0,
                            "source": "kuwo",
                        })
                    return results
        except Exception:
            pass
        return []

    def _parse_kuwo_response(self, text):
        try:
            return json.loads(text)
        except Exception:
            pass
        try:
            import ast
            return ast.literal_eval(text)
        except Exception:
            pass
        try:
            fixed = text.replace("'", '"').replace("True", "true").replace("False", "false").replace("None", "null")
            return json.loads(fixed)
        except Exception:
            pass
        return None

    def get_trending_tracks(self, limit=10):
        import random
        hot_keywords = ["热门歌曲", "华语热歌", "抖音热歌", "流行歌曲", "经典老歌"]
        keyword = random.choice(hot_keywords)
        results = self._search_kuwo(keyword, limit)
        if results:
            return results
        return []

    def get_stream_url(self, track_id):
        rid = str(track_id)
        if not rid.startswith("MUSIC_"):
            rid = "MUSIC_" + rid
        try:
            resp = requests.get(
                KUWO_SONG_URL,
                params={
                    "type": "convert_url3",
                    "rid": rid,
                    "format": "mp3",
                    "response": "url",
                },
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "http://www.kuwo.cn",
                },
            )
            if resp.status_code == 200:
                try:
                    data = json.loads(resp.text)
                    url = data.get("url", "")
                    if url:
                        return url
                except Exception:
                    text = resp.text.strip()
                    if text.startswith("http"):
                        return text
        except Exception:
            pass
        numeric_rid = rid.replace("MUSIC_", "")
        try:
            resp = requests.get(
                "https://www.kuwo.cn/api/v1/www/music/playInfo",
                params={"mid": numeric_rid, "type": "music", "httpsStatus": "1"},
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "http://www.kuwo.cn",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data", {}).get("url"):
                    return data["data"]["url"]
        except Exception:
            pass
        return None


class AudiusAPI:
    def __init__(self):
        self.host = None
        self.app_name = APP_NAME
        self.source = "audius"

    def ensure_host(self):
        if self.host:
            try:
                resp = requests.get(
                    self.host + "/v1/tracks/trending",
                    params={"limit": 1, "app_name": self.app_name},
                    timeout=8,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data.get("data"), list):
                        return True
            except Exception:
                pass
        self.host = get_audius_host()
        return self.host is not None

    def search_tracks(self, query, limit=20):
        if not self.ensure_host():
            return []
        try:
            url = self.host + "/v1/tracks/search"
            params = {"query": query, "limit": limit, "app_name": self.app_name}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                raw = resp.json().get("data", [])
                return [self._normalize(t) for t in raw]
        except Exception:
            pass
        return []

    def get_trending_tracks(self, limit=10):
        if not self.ensure_host():
            return []
        try:
            url = self.host + "/v1/tracks/trending"
            params = {"limit": limit, "app_name": self.app_name}
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                raw = resp.json().get("data", [])
                return [self._normalize(t) for t in raw]
        except Exception:
            pass
        return []

    def get_stream_url(self, track_id):
        if not self.ensure_host():
            return None
        return self.host + "/v1/tracks/" + track_id + "/stream?app_name=" + self.app_name

    def _normalize(self, t):
        return {
            "id": t.get("id", ""),
            "title": t.get("title", "未知"),
            "artist": t.get("user", {}).get("name", "未知"),
            "album": "",
            "genre": t.get("genre", ""),
            "duration": t.get("duration", 0),
            "play_count": t.get("play_count", 0),
            "source": "audius",
        }


class DownloadManager:
    def __init__(self, download_dir=DEFAULT_DOWNLOAD_DIR):
        self.download_dir = download_dir
        self.active_downloads = {}
        self.executor = ThreadPoolExecutor(max_workers=3)
        os.makedirs(self.download_dir, exist_ok=True)

    def download_track(self, track, on_progress=None, on_complete=None, on_error=None):
        track_id = track.get("id", "")
        title = track.get("title", "Unknown")
        artist = track.get("artist", "Unknown")
        source = track.get("source", "netease")
        filename = sanitize_filename(artist + " - " + title) + ".mp3"
        filepath = os.path.join(self.download_dir, filename)

        def _download():
            try:
                stream_url = None
                if source == "netease":
                    api = NeteaseAPI()
                    stream_url = api.get_stream_url(track_id, title, artist)
                elif source == "kuwo":
                    api = KuwoAPI()
                    stream_url = api.get_stream_url(track_id)
                elif source == "audius":
                    api = AudiusAPI()
                    if api.ensure_host():
                        stream_url = api.get_stream_url(track_id)

                if not stream_url:
                    if on_error:
                        on_error(track_id, "无法获取下载链接")
                    return

                resp = requests.get(stream_url, stream=True, timeout=30, verify=False)
                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0

                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and on_progress:
                                progress = downloaded / total_size
                                on_progress(track_id, progress)

                if on_complete:
                    on_complete(track_id, filepath)
            except Exception as e:
                if on_error:
                    on_error(track_id, str(e))

        future = self.executor.submit(_download)
        self.active_downloads[track_id] = future
        return filepath


class MusicApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME + " v" + APP_VERSION + " - 免费音乐搜索下载")
        self.root.geometry("950x720")
        self.root.minsize(800, 600)
        self.root.configure(bg="#1a1a2e")

        self.apis = {
            "netease": NeteaseAPI(),
            "kuwo": KuwoAPI(),
            "audius": AudiusAPI(),
        }
        self.current_source = "netease"
        self.download_mgr = DownloadManager()
        self.tracks = []
        self.config = self._load_config()

        if self.config.get("download_dir"):
            self.download_mgr.download_dir = self.config["download_dir"]
        if self.config.get("source"):
            self.current_source = self.config["source"]

        self._setup_styles()
        self._build_ui()
        self._load_trending()

    def _load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _setup_styles(self):
        self.colors = {
            "bg_dark": "#1a1a2e",
            "bg_medium": "#16213e",
            "bg_light": "#0f3460",
            "accent": "#e94560",
            "accent_hover": "#ff6b81",
            "text_primary": "#ffffff",
            "text_secondary": "#a0a0c0",
            "success": "#2ecc71",
            "warning": "#f39c12",
            "card_bg": "#1e2a4a",
        }

        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Dark.TFrame", background=self.colors["bg_dark"])
        style.configure("Card.TFrame", background=self.colors["card_bg"])
        style.configure("Title.TLabel",
                        background=self.colors["bg_dark"],
                        foreground=self.colors["text_primary"],
                        font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Subtitle.TLabel",
                        background=self.colors["bg_dark"],
                        foreground=self.colors["text_secondary"],
                        font=("Microsoft YaHei UI", 10))
        style.configure("Treeview",
                        background=self.colors["bg_medium"],
                        foreground=self.colors["text_primary"],
                        fieldbackground=self.colors["bg_medium"],
                        font=("Microsoft YaHei UI", 9),
                        rowheight=40)
        style.configure("Treeview.Heading",
                        background=self.colors["bg_light"],
                        foreground=self.colors["text_primary"],
                        font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Treeview",
                  background=[("selected", self.colors["accent"])],
                  foreground=[("selected", self.colors["text_primary"])])
        style.configure("Horizontal.TProgressbar",
                        background=self.colors["accent"],
                        troughcolor=self.colors["bg_medium"])

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, style="Dark.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        header_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        header_frame.pack(fill=tk.X, pady=(0, 15))

        title_label = ttk.Label(header_frame, text="🎵 " + APP_NAME,
                                style="Title.TLabel")
        title_label.pack(side=tk.LEFT)

        subtitle = ttk.Label(header_frame, text="免费音乐搜索下载 · 多平台聚合",
                             style="Subtitle.TLabel")
        subtitle.pack(side=tk.LEFT, padx=(15, 0), pady=(8, 0))

        settings_btn = tk.Button(header_frame, text="⚙ 设置", font=("Microsoft YaHei UI", 9),
                                 bg=self.colors["bg_light"], fg=self.colors["text_primary"],
                                 relief=tk.FLAT, cursor="hand2", command=self._open_settings)
        settings_btn.pack(side=tk.RIGHT, padx=(5, 0))

        source_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        source_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(source_frame, text="音乐来源:", font=("Microsoft YaHei UI", 10),
                 bg=self.colors["bg_dark"], fg=self.colors["text_primary"]).pack(side=tk.LEFT)

        self.source_var = tk.StringVar(value=self.current_source)
        for key, label in SOURCES.items():
            rb = tk.Radiobutton(source_frame, text=label, variable=self.source_var,
                                value=key, font=("Microsoft YaHei UI", 10),
                                bg=self.colors["bg_dark"], fg=self.colors["text_primary"],
                                selectcolor=self.colors["bg_medium"],
                                activebackground=self.colors["bg_dark"],
                                activeforeground=self.colors["accent"],
                                command=self._on_source_change)
            rb.pack(side=tk.LEFT, padx=(10, 0))

        search_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        search_frame.pack(fill=tk.X, pady=(0, 15))

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var,
                                     font=("Microsoft YaHei UI", 12),
                                     bg=self.colors["bg_medium"],
                                     fg=self.colors["text_primary"],
                                     insertbackground=self.colors["text_primary"],
                                     relief=tk.FLAT, width=50)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 10))
        self.search_entry.insert(0, "搜索歌曲、歌手...")
        self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)
        self.search_entry.bind("<Return>", lambda e: self._search())

        self.search_btn = tk.Button(search_frame, text="🔍 搜索", font=("Microsoft YaHei UI", 11, "bold"),
                                    bg=self.colors["accent"], fg=self.colors["text_primary"],
                                    relief=tk.FLAT, cursor="hand2", command=self._search)
        self.search_btn.pack(side=tk.LEFT, ipady=6, ipadx=20)

        trending_btn = tk.Button(search_frame, text="🔥 热门", font=("Microsoft YaHei UI", 10),
                                 bg=self.colors["bg_light"], fg=self.colors["text_primary"],
                                 relief=tk.FLAT, cursor="hand2", command=self._load_trending)
        trending_btn.pack(side=tk.LEFT, ipady=6, ipadx=15, padx=(10, 0))

        list_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("index", "title", "artist", "album", "source_name", "duration")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                                 selectmode="browse")

        self.tree.heading("index", text="#")
        self.tree.heading("title", text="歌曲名称")
        self.tree.heading("artist", text="歌手")
        self.tree.heading("album", text="专辑")
        self.tree.heading("source_name", text="来源")
        self.tree.heading("duration", text="时长")

        self.tree.column("index", width=35, anchor=tk.CENTER)
        self.tree.column("title", width=260, anchor=tk.W)
        self.tree.column("artist", width=130, anchor=tk.W)
        self.tree.column("album", width=130, anchor=tk.W)
        self.tree.column("source_name", width=80, anchor=tk.CENTER)
        self.tree.column("duration", width=60, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self._on_double_click)

        action_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        action_frame.pack(fill=tk.X, pady=(15, 0))

        self.download_btn = tk.Button(action_frame, text="⬇ 下载选中",
                                      font=("Microsoft YaHei UI", 10, "bold"),
                                      bg=self.colors["success"], fg=self.colors["text_primary"],
                                      relief=tk.FLAT, cursor="hand2",
                                      command=self._download_selected)
        self.download_btn.pack(side=tk.LEFT, ipady=5, ipadx=20)

        self.play_btn = tk.Button(action_frame, text="▶ 试听",
                                  font=("Microsoft YaHei UI", 10),
                                  bg=self.colors["bg_light"], fg=self.colors["text_primary"],
                                  relief=tk.FLAT, cursor="hand2",
                                  command=self._play_selected)
        self.play_btn.pack(side=tk.LEFT, padx=(10, 0), ipady=5, ipadx=15)

        self.download_all_btn = tk.Button(action_frame, text="⬇ 全部下载",
                                          font=("Microsoft YaHei UI", 10),
                                          bg=self.colors["bg_light"], fg=self.colors["text_primary"],
                                          relief=tk.FLAT, cursor="hand2",
                                          command=self._download_all)
        self.download_all_btn.pack(side=tk.LEFT, padx=(10, 0), ipady=5, ipadx=15)

        self.status_label = ttk.Label(action_frame, text="就绪",
                                      style="Subtitle.TLabel")
        self.status_label.pack(side=tk.RIGHT)

        progress_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        progress_frame.pack(fill=tk.X, pady=(10, 0))

        self.progress_bar = ttk.Progressbar(progress_frame, style="Horizontal.TProgressbar",
                                            mode="determinate", length=400)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        self.progress_label = ttk.Label(progress_frame, text="",
                                        style="Subtitle.TLabel")
        self.progress_label.pack(anchor=tk.W)

        bottom_frame = ttk.Frame(main_frame, style="Dark.TFrame")
        bottom_frame.pack(fill=tk.X, pady=(10, 0))

        self.download_list_label = ttk.Label(bottom_frame, text="下载记录:",
                                             style="Subtitle.TLabel")
        self.download_list_label.pack(anchor=tk.W)

        self.download_text = tk.Text(bottom_frame, height=4,
                                     bg=self.colors["bg_medium"],
                                     fg=self.colors["text_secondary"],
                                     font=("Microsoft YaHei UI", 9),
                                     relief=tk.FLAT, wrap=tk.WORD)
        self.download_text.pack(fill=tk.X, pady=(5, 0))
        self.download_text.configure(state=tk.DISABLED)

    def _on_source_change(self):
        self.current_source = self.source_var.get()
        self.config["source"] = self.current_source
        self._save_config()
        self._load_trending()

    def _on_search_focus_in(self, event):
        if self.search_var.get() == "搜索歌曲、歌手...":
            self.search_entry.delete(0, tk.END)

    def _on_search_focus_out(self, event):
        if not self.search_var.get().strip():
            self.search_entry.insert(0, "搜索歌曲、歌手...")

    def _set_status(self, msg):
        self.status_label.configure(text=msg)

    def _search(self):
        query = self.search_var.get().strip()
        if not query or query == "搜索歌曲、歌手...":
            messagebox.showinfo("提示", "请输入搜索关键词")
            return

        self._set_status("正在搜索: " + query + "...")
        self.search_btn.configure(state=tk.DISABLED)

        def _search_task():
            try:
                api = self.apis.get(self.current_source)
                if api:
                    results = api.search_tracks(query)
                else:
                    results = []

                def _update():
                    self.tracks = results
                    self._update_tree()
                    self._set_status("搜索完成，找到 " + str(len(results)) + " 首歌曲")
                    self.search_btn.configure(state=tk.NORMAL)

                self.root.after(0, _update)
            except Exception as e:
                self.root.after(0, lambda: self._set_status("搜索失败: " + str(e)))
                self.root.after(0, lambda: self.search_btn.configure(state=tk.NORMAL))

        threading.Thread(target=_search_task, daemon=True).start()

    def _load_trending(self):
        self._set_status("正在加载热门歌曲...")
        source = self.current_source

        def _load_task():
            try:
                api = self.apis.get(source)
                if api:
                    results = api.get_trending_tracks()
                else:
                    results = []

                def _update():
                    self.tracks = results
                    self._update_tree()
                    self._set_status("已加载 " + str(len(results)) + " 首热门歌曲 [" + SOURCES.get(source, source) + "]")

                self.root.after(0, _update)
            except Exception as e:
                self.root.after(0, lambda: self._set_status("加载热门歌曲失败: " + str(e)))

        threading.Thread(target=_load_task, daemon=True).start()

    def _update_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, track in enumerate(self.tracks):
            source_name = SOURCES.get(track.get("source", ""), track.get("source", ""))
            duration = track.get("duration", 0)
            if isinstance(duration, (int, float)) and duration > 0:
                duration_str = "{:d}:{:02d}".format(int(duration // 60), int(duration % 60))
            else:
                duration_str = "--:--"

            self.tree.insert("", tk.END, values=(
                i + 1,
                track.get("title", "未知"),
                track.get("artist", "未知"),
                track.get("album", ""),
                source_name,
                duration_str,
            ))

    def _get_selected_track(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一首歌曲")
            return None
        item = self.tree.item(selection[0])
        index = item["values"][0] - 1
        if 0 <= index < len(self.tracks):
            return self.tracks[index]
        return None

    def _play_selected(self):
        track = self._get_selected_track()
        if not track:
            return

        track_id = track.get("id", "")
        title = track.get("title", "未知")
        artist = track.get("artist", "未知")
        source = track.get("source", self.current_source)

        self._set_status("正在获取试听链接: " + artist + " - " + title + "...")

        def _play_task():
            try:
                stream_url = None
                if source == "netease":
                    api = NeteaseAPI()
                    stream_url = api.get_stream_url(track_id, title, artist)
                elif source == "kuwo":
                    api = KuwoAPI()
                    stream_url = api.get_stream_url(track_id)
                elif source == "audius":
                    api = AudiusAPI()
                    if api.ensure_host():
                        stream_url = api.get_stream_url(track_id)

                if stream_url:
                    self.root.after(0, lambda: self._open_in_browser(stream_url, title))
                else:
                    self.root.after(0, lambda: self._set_status("无法获取试听链接"))
            except Exception as e:
                self.root.after(0, lambda: self._set_status("试听失败: " + str(e)))

        threading.Thread(target=_play_task, daemon=True).start()

    def _open_in_browser(self, url, title):
        import webbrowser
        webbrowser.open(url)
        self._set_status("已在浏览器中打开: " + title)

    def _download_selected(self):
        track = self._get_selected_track()
        if not track:
            return
        self._download_track(track)

    def _download_all(self):
        if not self.tracks:
            messagebox.showinfo("提示", "当前没有可下载的歌曲")
            return

        if not messagebox.askyesno("确认", "确定要下载全部 " + str(len(self.tracks)) + " 首歌曲吗？"):
            return

        for track in self.tracks:
            self._download_track(track)

    def _download_track(self, track):
        track_id = track.get("id", "")
        title = track.get("title", "未知")
        artist = track.get("artist", "未知")

        self._set_status("开始下载: " + artist + " - " + title + "...")
        self.progress_bar["value"] = 0

        def on_progress(tid, progress):
            self.root.after(0, lambda: self._update_download_progress(tid, progress))

        def on_complete(tid, filepath):
            self.root.after(0, lambda: self._on_download_complete(tid, filepath, title))

        def on_error(tid, error):
            self.root.after(0, lambda: self._on_download_error(tid, title, error))

        self.download_mgr.download_track(track, on_progress, on_complete, on_error)

    def _update_download_progress(self, track_id, progress):
        self.progress_bar["value"] = progress * 100
        self.progress_label.configure(text="下载进度: {:.1f}%".format(progress * 100))

    def _on_download_complete(self, track_id, filepath, title):
        self.progress_bar["value"] = 100
        self.progress_label.configure(text="下载完成: " + title)
        self._set_status("下载完成: " + title)

        self.download_text.configure(state=tk.NORMAL)
        self.download_text.insert(tk.END, "✅ " + title + " -> " + filepath + "\n")
        self.download_text.see(tk.END)
        self.download_text.configure(state=tk.DISABLED)

        self.root.after(3000, lambda: self.progress_bar.configure(value=0))

    def _on_download_error(self, track_id, title, error):
        self.progress_bar["value"] = 0
        self.progress_label.configure(text="下载失败: " + title)
        self._set_status("下载失败: " + title + " - " + error)

        self.download_text.configure(state=tk.NORMAL)
        self.download_text.insert(tk.END, "❌ " + title + " - 错误: " + error + "\n")
        self.download_text.see(tk.END)
        self.download_text.configure(state=tk.DISABLED)

    def _on_double_click(self, event):
        self._play_selected()

    def _open_settings(self):
        settings_win = tk.Toplevel(self.root)
        settings_win.title("设置")
        settings_win.geometry("450x420")
        settings_win.configure(bg=self.colors["bg_dark"])
        settings_win.transient(self.root)
        settings_win.grab_set()

        tk.Label(settings_win, text="⚙ 设置", font=("Microsoft YaHei UI", 14, "bold"),
                 bg=self.colors["bg_dark"], fg=self.colors["text_primary"]).pack(pady=(20, 15))

        dir_frame = tk.Frame(settings_win, bg=self.colors["bg_dark"])
        dir_frame.pack(fill=tk.X, padx=30, pady=5)

        tk.Label(dir_frame, text="下载目录:", font=("Microsoft YaHei UI", 10),
                 bg=self.colors["bg_dark"], fg=self.colors["text_primary"]).pack(anchor=tk.W)

        dir_inner = tk.Frame(dir_frame, bg=self.colors["bg_dark"])
        dir_inner.pack(fill=tk.X, pady=(5, 0))

        current_dir = self.download_mgr.download_dir
        dir_var = tk.StringVar(value=current_dir)
        dir_entry = tk.Entry(dir_inner, textvariable=dir_var, font=("Microsoft YaHei UI", 9),
                             bg=self.colors["bg_medium"], fg=self.colors["text_primary"],
                             insertbackground=self.colors["text_primary"], relief=tk.FLAT)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 10))

        def browse_dir():
            d = filedialog.askdirectory(initialdir=dir_var.get())
            if d:
                dir_var.set(d)

        tk.Button(dir_inner, text="浏览", font=("Microsoft YaHei UI", 9),
                  bg=self.colors["bg_light"], fg=self.colors["text_primary"],
                  relief=tk.FLAT, cursor="hand2", command=browse_dir).pack(side=tk.RIGHT)

        info_frame = tk.Frame(settings_win, bg=self.colors["bg_dark"])
        info_frame.pack(fill=tk.X, padx=30, pady=20)

        info_texts = [
            "音乐来源: 网易云/酷我/Audius 多平台聚合",
            "网易云: 中文歌曲丰富，支持搜索+试听+下载",
            "酷我音乐: 中文歌曲丰富，直接通过酷我API获取",
            "Audius: 英文歌曲为主，创作者授权免费分享",
            "请尊重创作者，合理使用音乐作品",
        ]
        for text in info_texts:
            tk.Label(info_frame, text=text, font=("Microsoft YaHei UI", 9),
                     bg=self.colors["bg_dark"], fg=self.colors["text_secondary"]).pack(anchor=tk.W)

        def save_settings():
            new_dir = dir_var.get().strip()
            if new_dir:
                self.download_mgr.download_dir = new_dir
                os.makedirs(new_dir, exist_ok=True)
                self.config["download_dir"] = new_dir
                self._save_config()
            settings_win.destroy()

        btn_frame = tk.Frame(settings_win, bg=self.colors["bg_dark"])
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="保存", font=("Microsoft YaHei UI", 10, "bold"),
                  bg=self.colors["accent"], fg=self.colors["text_primary"],
                  relief=tk.FLAT, cursor="hand2", command=save_settings
                  ).pack(side=tk.LEFT, padx=5, ipady=5, ipadx=30)

        tk.Button(btn_frame, text="取消", font=("Microsoft YaHei UI", 10),
                  bg=self.colors["bg_light"], fg=self.colors["text_primary"],
                  relief=tk.FLAT, cursor="hand2", command=settings_win.destroy
                  ).pack(side=tk.LEFT, padx=5, ipady=5, ipadx=30)


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(default="")
    except Exception:
        pass

    app = MusicApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
