# yt-playlist-export

Utilities to **export YouTube data using `yt-dlp`** into formats you actually use:

* **FreeTube** playlists (append to `playlists.db` or standalone JSON)
* **Piped** import (JSON and CSV, optional chunk split)
* **URL / ID lists**
* **NewPipe** subscriptions JSON (from your `/feed/channels`)

> Works with private playlists/channels via `--cookies` or `--browser-cookies` (programmatic `cookiesfrombrowser`).

---

## Features

### Exports

* **FreeTube (append to DB)**
  Append one or more playlists (or an ID list) into FreeTube’s line-delimited `playlists.db`.

* **FreeTube (standalone JSON)**
  Same structure as above, but written to a file for manual import/inspection.

* **Piped (JSON)**
  `{"format":"Piped","version":1,"playlists":[{ name, type, visibility, videos: [urls] }]}`

  * **Split mode:** chunk large playlists into many files with `--split N`.

* **Piped (CSV)**
  Minimal CSV: `videoId,addedAt` for quick bulk adds.

* **NewPipe subscriptions**
  Export your **subscriptions** as NewPipe JSON (`newpipe-subscriptions-YYYY-MM-DD.json`) using **`/feed/channels`**.

  * No HTML scraping, no OPML endpoint required.
  * Requires valid login cookies.

* **URL / ID lists**
  Flat text files (`urls.txt`, `ids.txt`) for pipelines or custom tooling.

### Inputs

* **Playlist URL(s)** (public/private if cookies provided)
* **ID file** (`--ids-file`) with one YouTube video ID per line (tolerates lines like `youtube <id>`)

### Auth / Cookies

* **`--cookies`**: Netscape cookie file path
* **`--browser-cookies`**: `cookiesfrombrowser` like `"brave:Default"`, correctly passed to `yt-dlp` as a tuple
* **`--skip-authcheck`**: skip yt-dlp auth check for `youtube:tab` extractors when needed

### Ergonomics

* **`--pretty`** JSON
* **`--sleep`** between requests to avoid rate-limits
* **`--verbose`** to see `yt-dlp` chatter
* **Atomic-ish writes** for crash-safe `--out` paths (when applicable in some flows)
* Clean, deterministic file naming and chunking

---

## Install

```bash
python -m pip install yt-dlp colorama
# or uv/pipx/poetry as you prefer
```

Place the script anywhere on your PATH (e.g. `yt-playlist-export.py`) and make it executable.

---

## Quick Start

### 1) Export **NewPipe subscriptions** (uses `/feed/channels`)

```bash
python yt-playlist-export.py \
  --browser-cookies "brave:Default" \
  -e newpipe-subs \
  -o newpipe-subscriptions-2025-11-10.json \
  --pretty
```

* Requires you’re logged into YouTube in the specified browser/profile.
* You can also use `--cookies /path/to/cookies.txt` instead.

### 2) Export a **YouTube playlist → FreeTube DB**

```bash
python yt-playlist-export.py \
  --browser-cookies "brave:Default" \
  -e freetube-db \
  "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx" 
```

This appends to your OS-specific FreeTube `playlists.db` (auto-located).
Override with `--path /path/to/FreeTube/playlists.db` or `--path /dir/` to create if missing.

### 3) Export a **YouTube playlist → FreeTube JSON**

```bash
python yt-playlist-export.py \
  --cookies cookies.txt \
  -e freetube-json \
  -o my_playlist.freetube.json \
  "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx"
```

### 4) Export a **YouTube playlist → Piped JSON** (single file)

```bash
python yt-playlist-export.py \
  --browser-cookies "brave:Default" \
  -e piped-json \
  -o playlist-piped.json \
  "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx" \
  --pretty
```

### 5) Export a **YouTube playlist → Piped JSON (split into chunks of 500)**

```bash
python yt-playlist-export.py \
  --browser-cookies "brave:Default" \
  -e piped-json \
  --split 500 \
  -o my_piped.json \
  --split-dir ./chunks \
  "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx"
```

Outputs: `./chunks/my_piped_<sanitized-name>_001.json`, `..._002.json`, etc.

### 6) Export **IDs file → FreeTube / Piped / lists**

Given `ids.txt`:

```
dQw4w9WgXcQ
youtube 1DxWY0nLEF0
```

* **FreeTube JSON**:

  ```bash
  python yt-playlist-export.py -f ids.txt -e freetube-json --name "Imported IDs" -o imported.freetube.json --pretty
  ```

* **Piped CSV**:

  ```bash
  python yt-playlist-export.py -f ids.txt -e piped-csv -o imported.csv
  ```

* **URLs**:

  ```bash
  python yt-playlist-export.py -f ids.txt -e urls -o urls.txt
  ```

---

## CLI

```text
usage: yt-playlist-export.py [-h] [-f IDS_FILE] [--name NAME] [--description DESCRIPTION]
                      [-c BROWSER_COOKIES] [--cookies COOKIES] [--skip-authcheck] [--sleep SLEEP]
                      [-e {freetube-db,freetube-json,piped-json,piped-csv,urls,ids,newpipe-subs}]
                      [-o OUTPUT] [--path PATH] [--split N] [--split-dir SPLIT_DIR] [--pretty]
                      [--newpipe-version NEWPIPE_VERSION] [--newpipe-version-int NEWPIPE_VERSION_INT]
                      [-q] [--verbose]
                      [playlist_url ...]
```

**Inputs**

* `playlist_url ...`           One or more YouTube playlist URLs
* `-f, --ids-file FILE`        Text file with video IDs (one per line; also accepts lines like `youtube <id>`)
* `--name NAME`                Override/assign playlist name (single URL or IDs mode)
* `--description TEXT`         Optional description

**Auth / yt-dlp**

* `-c, --browser-cookies "brave:Default"`  Use logged-in browser cookies (programmatic tuple)
* `--cookies PATH`                          Netscape cookie file
* `--skip-authcheck`                        `youtubetab:skip=authcheck` for certain private listings
* `--sleep SECS`                            Sleep between requests

**Exports**

* `-e, --export`     `freetube-db | freetube-json | piped-json | piped-csv | urls | ids | newpipe-subs`
* `-o, --output`     Output file (not used for `freetube-db`)
* `--path PATH`      Override FreeTube `playlists.db` (file OR directory)

**Piped JSON**

* `--split N`        Chunk size (e.g. 500)
* `--split-dir DIR`  Where to put the chunks (default `chunks/<basename>`)
* `--pretty`         Pretty JSON

**NewPipe**

* `--newpipe-version`     String, default `0.26.0`
* `--newpipe-version-int` Int, default `1200`

**Misc**

* `-q, --quiet`      Reduce logging
* `--verbose`        More `yt-dlp` logging

---

## Output Formats

### FreeTube playlist JSON (single object, used for DB and file export)

```json
{
  "playlistName": "My Playlist",
  "protected": false,
  "description": "",
  "videos": [
    {
      "videoId": "1DxWY0nLEF0",
      "title": "10 Most Effective Pushup Variations You Really Need",
      "author": "CHRIS HERIA",
      "authorId": "@CHRISHERIA",
      "lengthSeconds": 724,
      "published": 0,
      "timeAdded": 1731048855213,
      "playlistItemId": "uuid-…",
      "type": "video"
    }
  ],
  "_id": "ft-playlist--uuid…",
  "createdAt": 1731048855213,
  "lastUpdatedAt": 1731048855213
}
```

### Piped JSON

```json
{
  "format": "Piped",
  "version": 1,
  "playlists": [
    {
      "name": "My Playlist",
      "type": "playlist",
      "visibility": "private",
      "videos": [
        "https://youtube.com/watch?v=1DxWY0nLEF0",
        "https://youtube.com/watch?v=WzFMnRUzYog"
      ]
    }
  ]
}
```

### NewPipe subscriptions

```json
{
  "app_version": "0.26.0",
  "app_version_int": 1200,
  "subscriptions": [
    {
      "service_id": 0,
      "url": "https://www.youtube.com/channel/UC-0igYFlnYv1XCF7wk30BTg",
      "name": "Ace"
    }
  ]
}
```

---

## Notes & Gotchas

* **Cookies:**

  * For `--browser-cookies`, use strings like `"brave:Default"`, `"firefox:default-release"`, `"chromium:Default"`
  * Internally, the script converts to the **tuple** format `yt-dlp` expects.
  * If you see “failed to load cookies”, confirm the profile name and that you’re logged in.

* **Private / unlisted:**
  Use cookies. Consider `--skip-authcheck` if yt-dlp complains for certain tabs.

* **Rate limits:**
  Use `--sleep 0.5` (or similar) for large exports.

* **FreeTube DB path:**
  Auto-detected per OS. Override with `--path /path/to/playlists.db` or a directory to create one.

* **yt-dlp version:**
  Keep it current. Old versions can fail on `/feed/channels` or playlist tabs.

---

## Examples

* Multiple playlists → FreeTube JSON directory:

  ```bash
  python yt-playlist-export.py \
    --browser-cookies "firefox:default-release" \
    -e freetube-json \
    -o ./ft_json \
    --pretty \
    "https://www.youtube.com/playlist?list=PL1..." \
    "https://www.youtube.com/playlist?list=PL2..."
  ```

* One playlist → Piped JSON (split, pretty):

  ```bash
  python yt-playlist-export.py \
    --cookies cookies.txt \
    -e piped-json \
    -o piped_export.json \
    --split 500 \
    --pretty \
    "https://www.youtube.com/playlist?list=PL..."
  ```

* IDs file → URL list:

  ```bash
  python yt-playlist-export.py -f ids.txt -e urls -o urls.txt
  ```

---

## License

MIT (or your preferred license — add a `LICENSE` file).

---

## Changelog (high-level)

* Add NewPipe subscriptions export via `/feed/channels` (no OPML scraping)
* Robust `cookiesfrombrowser` parsing → correct programmatic tuple
* Piped JSON split + dir controls
* FreeTube DB append + standalone JSON
* IDs-file workflow; placeholder entries on partial failures
* Pretty JSON, sleep, verbose, quiet modes

## Dependencies

yt-playlist-export is using [yt-dlp](https://github.com/yt-dlp) under the hood.

## Keywords

YouTube export playlist. YouTube export Watch later list. YouTube export liked videos. YouTube export playlist to CSV. YouTube export playlist to JSON. YouTube export private playlist.
