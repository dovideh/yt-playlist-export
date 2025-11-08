#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ytft-export.py

Export YouTube playlists/IDs → FreeTube DB/JSON, Piped JSON/CSV, URL/ID lists
Export YouTube subscriptions → NewPipe subscriptions JSON (via /feed/channels)

Requires:
  - yt-dlp
  - colorama (optional; for colored console output)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from time import time as _time
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

# ---- optional colors ----
try:
    from colorama import init as color_init, Fore
    color_init()
    HAVE_COLOR = True
except Exception:
    HAVE_COLOR = False

import yt_dlp
from yt_dlp.cookies import SUPPORTED_BROWSERS, SUPPORTED_KEYRINGS


# =========================
# Console utils
# =========================

def cprint(head: str, rest: str = "", color: str = "RESET", quiet: bool = False) -> None:
    if quiet:
        return
    if not HAVE_COLOR:
        print(f"{head}{rest}")
        return
    cmap = {"RED": Fore.RED, "GREEN": Fore.GREEN, "YELLOW": Fore.YELLOW, "CYAN": Fore.CYAN, "RESET": Fore.RESET}
    sys.stdout.write(cmap.get(color, Fore.RESET) + head + Fore.RESET)
    if rest:
        print(rest)


# =========================
# Text helpers
# =========================

ZERO_WIDTH = re.compile(r"[\u200B-\u200F\uFEFF]")

def clean_text(s: Any) -> str:
    if s is None:
        return ""
    s = str(s).strip().replace("\u00A0", " ").replace("\u2024", ".")
    return ZERO_WIDTH.sub("", s)

def to_int_str(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"[^\d]", "", str(val))

def sanitize_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")

def now_ms() -> int:
    return int(round(_time() * 1000))


# =========================
# cookiesfrombrowser parsing (shared)
# =========================

_CFB_RE = re.compile(r'''(?x)
    (?P<name>[^+:]+)
    (?:\s*\+\s*(?P<keyring>[^:]+))?
    (?:\s*:\s*(?!:)(?P<profile>.+?))?
    (?:\s*::\s*(?P<container>.+))?
''')

def parse_cookiesfrombrowser_spec(cfb: str) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    Convert "brave:Default" (or similar) to a tuple (name, profile, keyring, container)
    suitable for yt_dlp programmatic options.
    """
    m = _CFB_RE.fullmatch(cfb.strip())
    if not m:
        raise ValueError(f"Invalid cookiesfrombrowser spec: {cfb}")
    name, keyring, profile, container = m.group("name", "keyring", "profile", "container")
    name = name.lower()
    if name not in SUPPORTED_BROWSERS:
        raise ValueError(f'Unsupported browser "{name}". Supported: {", ".join(sorted(SUPPORTED_BROWSERS))}')
    if keyring:
        keyring = keyring.upper()
        if keyring not in SUPPORTED_KEYRINGS:
            raise ValueError(f'Unsupported keyring "{keyring}". Supported: {", ".join(sorted(SUPPORTED_KEYRINGS))}')
    return (name, profile, keyring, container)


# =========================
# Data models (FreeTube)
# =========================

@dataclass
class FreeTubeVideo:
    videoId: str
    title: str = "N/A"
    author: str = "N/A"
    authorId: str = "N/A"
    lengthSeconds: int | str = 0
    published: int | str = 0
    timeAdded: int = 0
    playlistItemId: str = ""
    type: str = "video"

    @staticmethod
    def from_ytdlp_entry(e: Dict[str, Any]) -> "FreeTubeVideo":
        return FreeTubeVideo(
            videoId=clean_text(e.get("id") or "N/A"),
            title=clean_text(e.get("title") or "N/A"),
            author=clean_text(e.get("channel") or e.get("uploader") or "N/A"),
            authorId=clean_text(e.get("channel_id") or e.get("uploader_id") or "N/A"),
            lengthSeconds=int(to_int_str(e.get("duration") or 0) or 0),
            published=int(to_int_str(e.get("timestamp") or 0) or 0),
            timeAdded=now_ms(),
            playlistItemId=str(uuid4()),
        )

    @staticmethod
    def placeholder(video_id: str) -> "FreeTubeVideo":
        return FreeTubeVideo(videoId=video_id, timeAdded=now_ms(), playlistItemId=str(uuid4()))


@dataclass
class FreeTubePlaylist:
    playlistName: str
    protected: bool = False
    description: str = ""
    videos: List[FreeTubeVideo] = None
    _id: str = ""
    createdAt: int = 0
    lastUpdatedAt: int = 0

    @staticmethod
    def new(name: str, description: str = "") -> "FreeTubePlaylist":
        ts = now_ms()
        return FreeTubePlaylist(
            playlistName=name or "Imported Playlist",
            protected=False,
            description=description or "",
            videos=[],
            _id="ft-playlist--" + str(uuid4()),
            createdAt=ts,
            lastUpdatedAt=ts,
        )

    def add_video(self, v: FreeTubeVideo) -> None:
        self.videos.append(v)
        self.lastUpdatedAt = now_ms()

    def to_json_obj(self) -> Dict[str, Any]:
        d = asdict(self)
        d["videos"] = [asdict(v) for v in self.videos]
        return d


# =========================
# yt-dlp client
# =========================

class YTDLPClient:
    def __init__(
        self,
        cookies_file: Optional[str],
        browser_cookies: Optional[str],
        skip_authcheck: bool,
        sleep_requests: Optional[float],
        quiet: bool,
    ) -> None:
        self.quiet = quiet
        self.opts: Dict[str, Any] = {
            "ignoreerrors": "only_download",
            "extract_flat": True,
            "quiet": True,
        }
        if cookies_file:
            self.opts["cookies"] = cookies_file
        else:
            # Use tuple spec programmatically
            self.opts["cookiesfrombrowser"] = parse_cookiesfrombrowser_spec(browser_cookies or "firefox")
        if skip_authcheck:
            self.opts["extractor_args"] = {"youtubetab": {"skip": ["authcheck"]}}
        if sleep_requests is not None:
            self.opts["sleep_interval_requests"] = float(sleep_requests)

    def extract_playlist(self, url: str) -> Dict[str, Any]:
        with yt_dlp.YoutubeDL(self.opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise RuntimeError(f"yt-dlp returned no data for {url}")
            return ydl.sanitize_info(info)

    def extract_video_min(self, video_id: str) -> Dict[str, Any]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            with yt_dlp.YoutubeDL(self.opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return {"id": video_id}
                return ydl.sanitize_info(info)
        except Exception:
            return {"id": video_id}


# =========================
# Inputs
# =========================

YT_ID_RE = re.compile(r"([A-Za-z0-9_-]{10}[AEIMQUYcgkosw048])")

def read_ids_file(path: str) -> List[str]:
    ids: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = YT_ID_RE.search(line)
            if m:
                ids.append(m.group(1))
    return ids


# =========================
# Exporters
# =========================

def freetube_db_path(user_path: Optional[str]) -> str:
    database_name = "playlists.db"
    if user_path:
        if os.path.isfile(user_path) or user_path.lower().endswith((".db", ".json")):
            return user_path
        return os.path.join(user_path, database_name)
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        base = os.path.join(os.getenv("APPDATA") or "", "FreeTube")
    elif sys.platform.startswith("linux"):
        flatpak = os.path.join(home, ".var/app/io.freetubeapp.FreeTube/config/FreeTube")
        base = flatpak if os.path.exists(flatpak) else os.path.join(home, ".config/FreeTube")
    elif sys.platform == "darwin":
        base = os.path.join(home, "Library/Application Support/FreeTube")
    else:
        base = os.path.join(home, ".config/FreeTube")
    return os.path.join(base, database_name)

def ensure_file_exists(path: str) -> None:
    parent = os.path.dirname(path) or "."
    if not os.path.isdir(parent):
        raise FileNotFoundError(f"Parent directory does not exist: {parent}")
    if not os.path.exists(path):
        open(path, "a", encoding="utf-8").close()

def export_freetube_db(pl: FreeTubePlaylist, user_path: Optional[str], quiet: bool) -> str:
    db_path = freetube_db_path(user_path)
    ensure_file_exists(db_path)
    with open(db_path, "a", encoding="utf-8") as f:
        json.dump(pl.to_json_obj(), f, separators=(",", ":"))
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    cprint("✓ ", f"Playlist '{pl.playlistName}' appended to {db_path}", "GREEN", quiet)
    return db_path

def export_freetube_json(pl: FreeTubePlaylist, out_path: str, pretty: bool, quiet: bool) -> str:
    path = out_path or (sanitize_name(pl.playlistName) + ".freetube.json")
    with open(path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(pl.to_json_obj(), f, ensure_ascii=False, indent=2)
        else:
            json.dump(pl.to_json_obj(), f, ensure_ascii=False, separators=(",", ":"))
    cprint("✓ ", f"Wrote FreeTube JSON: {path}", "GREEN", quiet)
    return path

def export_piped_json(playlists: List[Tuple[str, List[str]]], out_path: Optional[str],
                      pretty: bool, quiet: bool) -> str:
    payload = {
        "format": "Piped",
        "version": 1,
        "playlists": [
            {"name": name, "type": "playlist", "visibility": "private",
             "videos": [f"https://youtube.com/watch?v={v}" for v in vids]}
            for (name, vids) in playlists
        ],
    }
    path = out_path or "piped.json"
    with open(path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    cprint("✓ ", f"Wrote Piped JSON: {path}", "GREEN", quiet)
    return path

def export_piped_json_split(playlists: List[Tuple[str, List[str]]], base_out: str,
                            split: int, split_dir: Optional[str], pretty: bool, quiet: bool) -> str:
    base = os.path.splitext(os.path.basename(base_out or "piped.json"))[0]
    outdir = split_dir or os.path.join("chunks", base)
    os.makedirs(outdir, exist_ok=True)
    total = 0
    for name, vids in playlists:
        for i in range(0, len(vids), split):
            chunk = vids[i:i+split]
            payload = {"format": "Piped", "version": 1,
                       "playlists": [{"name": name, "type": "playlist", "visibility": "private",
                                      "videos": [f"https://youtube.com/watch?v={v}" for v in chunk]}]}
            out_name = f"{base}_{sanitize_name(name)}_{(i//split)+1:03}.json"
            path = os.path.join(outdir, out_name)
            with open(path, "w", encoding="utf-8") as f:
                if pretty:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                else:
                    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            total += 1
            if not quiet:
                print(f"  → {path} ({len(chunk)} videos)")
    cprint("✓ ", f"Split Piped JSON finished: {total} files in {outdir}", "GREEN", quiet)
    return outdir

def export_piped_csv(video_ids: Iterable[str], out_path: Optional[str], quiet: bool) -> str:
    path = out_path or "piped.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=",", quotechar='"', lineterminator="\r\n")
        w.writerow(["videoId", "addedAt"])
        for vid in video_ids:
            w.writerow([vid, ""])
    cprint("✓ ", f"Wrote Piped CSV: {path}", "GREEN", quiet)
    return path

def export_urls(video_ids: Iterable[str], out_path: Optional[str], quiet: bool) -> str:
    path = out_path or "urls.txt"
    with open(path, "w", encoding="utf-8") as f:
        for vid in video_ids:
            f.write(f"https://www.youtube.com/watch?v={vid}\n")
    cprint("✓ ", f"Wrote URL list: {path}", "GREEN", quiet)
    return path

def export_ids(video_ids: Iterable[str], out_path: Optional[str], quiet: bool) -> str:
    path = out_path or "ids.txt"
    with open(path, "w", encoding="utf-8") as f:
        for vid in video_ids:
            f.write(f"{vid}\n")
    cprint("✓ ", f"Wrote ID list: {path}", "GREEN", quiet)
    return path


# =========================
# NewPipe subscriptions (yt-dlp /feed/channels)
# =========================

def fetch_subscriptions_via_ytdlp(
    browser_cookies: str | None,
    cookies_file: str | None,
    verbose: bool = False,
) -> list[tuple[str, str]]:
    """
    Use yt-dlp to extract the /feed/channels subscription list for a logged-in account.
    Returns a list of (channel_url, name).
    """
    url = "https://www.youtube.com/feed/channels"
    opts: Dict[str, Any] = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": not verbose,
        "ignoreerrors": "only_download",
        "lazy_playlist": True,
    }
    if cookies_file:
        opts["cookies"] = cookies_file
    elif browser_cookies:
        # IMPORTANT: pass a tuple, not a raw string
        opts["cookiesfrombrowser"] = parse_cookiesfrombrowser_spec(browser_cookies)

    results: list[tuple[str, str]] = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info or "entries" not in info:
            raise RuntimeError("Could not extract subscriptions list (login cookies may be invalid).")
        for e in info.get("entries", []):
            if not e:
                continue
            ch_id = e.get("channel_id") or e.get("id")
            name = e.get("title") or e.get("channel") or "Unknown"
            if not ch_id:
                continue
            ch_url = f"https://www.youtube.com/channel/{ch_id}"
            results.append((ch_url, name))
    return results

def export_newpipe_subscriptions(
    subs: list[tuple[str, str]],
    out_path: str,
    app_ver: str = "0.26.0",
    app_ver_int: int = 1200,
    pretty: bool = False,
    quiet: bool = False,
):
    payload = {
        "app_version": app_ver,
        "app_version_int": app_ver_int,
        "subscriptions": [{"service_id": 0, "url": url, "name": name} for (url, name) in subs],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    cprint("✓ ", f"Wrote NewPipe subscriptions: {out_path} ({len(subs)} channels)", "GREEN", quiet)


# =========================
# Builders
# =========================

def build_freetube_from_entries(info: Dict[str, Any], name: Optional[str], description: str) -> FreeTubePlaylist:
    entries = info.get("entries") or []
    pl_name = name or clean_text(info.get("title") or "") or "Imported Playlist"
    ft = FreeTubePlaylist.new(pl_name, description)
    for e in entries:
        vid = clean_text(e.get("id") or "")
        if not vid:
            continue
        ft.add_video(FreeTubeVideo.from_ytdlp_entry(e))
    return ft

def build_freetube_from_ids(ids: List[str], ytdlp: YTDLPClient,
                            name: str, description: str, quiet: bool) -> FreeTubePlaylist:
    ft = FreeTubePlaylist.new(name or f"Imported IDs ({len(ids)} videos)", description)
    for vid in ids:
        meta = ytdlp.extract_video_min(vid)
        if "id" in meta and meta.get("title") is not None:
            ft.add_video(FreeTubeVideo.from_ytdlp_entry(meta))
        else:
            ft.add_video(FreeTubeVideo.placeholder(vid))
        if not quiet:
            print(f"{vid}  |  {ft.videos[-1].title}  |  {ft.videos[-1].author}")
    return ft


# =========================
# CLI
# =========================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Export YouTube playlists/IDs → FreeTube, Piped, NewPipe")
    # Inputs
    p.add_argument("playlist_url", nargs="*", help="YouTube playlist URL(s)")
    p.add_argument("-f", "--ids-file", help="File with YouTube IDs (one per line)")
    p.add_argument("--name", help="Playlist name (single URL or IDs mode)")
    p.add_argument("--description", default="", help="Playlist description (IDs mode or override)")

    # yt-dlp auth/behavior
    p.add_argument("-c", "--browser-cookies", help='cookiesfrombrowser, e.g. "brave:Default"')
    p.add_argument("--cookies", help="Path to a Netscape cookie file")
    p.add_argument("--skip-authcheck", action="store_true", help="yt-dlp: youtubetab:skip=authcheck")
    p.add_argument("--sleep", type=float, help="Sleep between requests (seconds)")

    # Output type
    p.add_argument("-e", "--export",
                   choices=["freetube-db", "freetube-json", "piped-json", "piped-csv", "urls", "ids", "newpipe-subs"],
                   default="freetube-db", help="Export format")
    p.add_argument("-o", "--output", help="Output path (file). Not used for freetube-db.")
    p.add_argument("--path", help="Override FreeTube playlists.db path (file or dir)")

    # Piped JSON controls
    p.add_argument("--split", type=int, metavar="N", help="Split Piped JSON into chunks of N videos")
    p.add_argument("--split-dir", help="Output directory for split JSON files (default chunks/<basename>)")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs")

    # NewPipe subscriptions
    p.add_argument("--newpipe-version", default="0.19.8", help='NewPipe app_version')
    p.add_argument("--newpipe-version-int", type=int, default=953, help="NewPipe app_version_int")

    # Verbosity
    p.add_argument("-q", "--quiet", action="store_true", help="Reduce log output")
    p.add_argument("--verbose", action="store_true", help="Increase yt-dlp verbosity for debugging")
    return p


# =========================
# Main
# =========================

def main() -> None:
    args = build_parser().parse_args()

    # NewPipe subscriptions export
    if args.export == "newpipe-subs":
        cprint("⋯ ", "Fetching subscriptions via yt-dlp /feed/channels…", "CYAN", args.quiet)
        try:
            subs = fetch_subscriptions_via_ytdlp(
                browser_cookies=args.browser_cookies,
                cookies_file=args.cookies,
                verbose=args.verbose,
            )
        except Exception as e:
            cprint("ERR: ", f"Failed to fetch subscriptions: {e}", "RED")
            sys.exit(1)

        if not subs:
            cprint("WARN: ", "No subscriptions found — ensure cookies are logged in.", "YELLOW", args.quiet)
            sys.exit(2)

        export_newpipe_subscriptions(
            subs=subs,
            out_path=args.output or "newpipe-subscriptions.json",
            app_ver=args.newpipe_version,
            app_ver_int=args.newpipe_version_int,
            pretty=args.pretty,
            quiet=args.quiet,
        )
        return

    # Playlist / IDs exporters
    have_urls = len(args.playlist_url) > 0
    have_ids = bool(args.ids_file)
    # Show help if no input arguments provided
    if not have_urls and not have_ids and args.export != "newpipe-subs":
        build_parser().print_help()
        sys.exit(0)

    if not have_urls and not have_ids:
        cprint("ERR: ", "Provide playlist URL(s) or --ids-file, or use -e newpipe-subs", "RED")
        sys.exit(2)

    ytdlp_client = YTDLPClient(
        cookies_file=args.cookies,
        browser_cookies=args.browser_cookies,
        skip_authcheck=args.skip_authcheck,
        sleep_requests=args.sleep,
        quiet=args.quiet,
    )

    freetube_playlists: List[FreeTubePlaylist] = []
    piped_sets: List[Tuple[str, List[str]]] = []

    if have_ids:
        ids = read_ids_file(args.ids_file)
        if not ids:
            cprint("ERR: ", "No valid YouTube IDs found.", "RED")
            sys.exit(1)
        default_name = args.name or os.path.splitext(os.path.basename(args.ids_file))[0] or f"Imported IDs ({len(ids)})"
        ft = build_freetube_from_ids(ids, ytdlp_client, default_name, args.description, args.quiet)
        freetube_playlists.append(ft)
        piped_sets.append((ft.playlistName, [v.videoId for v in ft.videos]))

    for url in args.playlist_url:
        info = ytdlp_client.extract_playlist(url)
        name = args.name if len(args.playlist_url) == 1 and args.name else None
        ft = build_freetube_from_entries(info, name, args.description)
        freetube_playlists.append(ft)
        piped_sets.append((ft.playlistName, [v.videoId for v in ft.videos]))

    if args.export == "freetube-db":
        for pl in freetube_playlists:
            export_freetube_db(pl, args.path, args.quiet)
        return

    if args.export == "freetube-json":
        if len(freetube_playlists) == 1:
            export_freetube_json(freetube_playlists[0], args.output or "", args.pretty, args.quiet)
        else:
            outdir = args.output or "freetube_json_playlists"
            os.makedirs(outdir, exist_ok=True)
            for pl in freetube_playlists:
                path = os.path.join(outdir, sanitize_name(pl.playlistName) + ".json")
                export_freetube_json(pl, path, args.pretty, args.quiet)
        return

    if args.export == "piped-json":
        if args.split:
            export_piped_json_split(piped_sets, args.output or "piped.json",
                                    args.split, args.split_dir, args.pretty, args.quiet)
        else:
            export_piped_json(piped_sets, args.output or "piped.json", args.pretty, args.quiet)
        return

    if args.export == "piped-csv":
        vids: List[str] = []
        for _, v in piped_sets:
            vids.extend(v)
        export_piped_csv(vids, args.output or "piped.csv", args.quiet)
        return

    if args.export == "urls":
        vids: List[str] = []
        for _, v in piped_sets:
            vids.extend(v)
        export_urls(vids, args.output or "urls.txt", args.quiet)
        return

    if args.export == "ids":
        vids: List[str] = []
        for _, v in piped_sets:
            vids.extend(v)
        export_ids(vids, args.output or "ids.txt", args.quiet)
        return

    cprint("ERR: ", f"Unknown export type: {args.export}", "RED")
    sys.exit(2)

if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        try: sys.stdout.close()
        except Exception: pass
        try: sys.stderr.close()
        except Exception: pass
        sys.exit(0)

