#!/usr/bin/env python3
"""
play_audio.py — Mini Pupper Music Player

Searches YouTube, downloads audio, and plays through the speaker.

Subcommands:
    search <query>   — Search YouTube, return top 3 results as JSON
    play <url>       — Download audio from URL and play via mpg321
    stop             — Kill current playback
    status           — Check if music is currently playing

Output is always JSON for the agent to parse.

PID/PATH files:
    /tmp/minipupper_music_player.pid   — PID of running mpg321
    /tmp/minipupper_music_active       — Flag: music is active (app checks before muting)

Usage:
    python3 custom/play_audio.py search "Shape of You Ed Sheeran"
    python3 custom/play_audio.py play "https://youtube.com/watch?v=..."
    python3 custom/play_audio.py stop
    python3 custom/play_audio.py status
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time

PID_FILE = "/tmp/minipupper_music_player.pid"
MUSIC_ACTIVE_FLAG = "/tmp/minipupper_music_active"
LOG_FILE = "/tmp/minipupper_music_player.log"
DOWNLOAD_DIR = "/tmp/minipupper_music"
CACHE_FILE = "/tmp/minipupper_music_cache.json"

AUTO_STOP = True


def _log(msg: str):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def _find_player_pid():
    """Return PID of running mpg321, or None."""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
                return pid
            except (OSError, ProcessLookupError):
                pass
    except (ValueError, OSError):
        pass
    try:
        out = subprocess.run(
            ["pgrep", "-f", "mpg321 .*minipupper_music"],
            capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            return int(out.stdout.strip().split("\n")[0])
    except Exception:
        pass
    return None


def _set_music_active(active: bool):
    """Create or remove the music-active flag file so the app doesn't mute."""
    if active:
        try:
            open(MUSIC_ACTIVE_FLAG, "w").close()
        except OSError:
            pass
    else:
        try:
            os.remove(MUSIC_ACTIVE_FLAG)
        except OSError:
            pass


def _set_volume(pct: str = "85%"):
    """Set speaker volume via shared audio_util (auto-detects card)."""
    try:
        import sys
        sys.path.insert(0, "/home/ubuntu/minipupper-app")
        from src.audio.audio_util import set_volume
        set_volume(pct)
    except Exception:
        pass


def _start_player(filepath: str) -> dict:
    """Launch mpg321 in background, write PID, return result dict."""
    try:
        player = subprocess.Popen(
            ["mpg321", "-q", "-o", "alsa", "-a", "default", filepath],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "mpg321 not found. Install: apt install mpg321"}

    with open(PID_FILE, "w") as f:
        f.write(str(player.pid))

    _log(f"Player PID: {player.pid}")

    # Signal the app to keep volume up while music plays
    _set_music_active(True)
    _set_volume("85%")

    title = os.path.splitext(os.path.basename(filepath))[0]
    return {
        "ok": True,
        "message": f"Now playing: {title}",
        "title": title,
        "pid": player.pid,
        "file": filepath,
        "size_bytes": os.path.getsize(filepath),
    }


def _stop_playback():
    """Kill any currently running mpg321 and clear the music-active flag."""
    pid = _find_player_pid()
    if pid is None:
        _set_music_active(False)
        return {"ok": True, "message": "No music currently playing."}

    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(0.2)
            except ProcessLookupError:
                break
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    except Exception as e:
        return {"ok": False, "message": f"Failed to stop playback: {e}"}

    try:
        os.remove(PID_FILE)
    except OSError:
        pass

    _set_music_active(False)
    return {"ok": True, "message": "Music stopped."}


def _load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def _clean_uncached_files(cache: dict):
    cached_files = set(cache.values())
    for f in os.listdir(DOWNLOAD_DIR):
        fpath = os.path.join(DOWNLOAD_DIR, f)
        if fpath not in cached_files and f.endswith(".mp3"):
            try:
                os.remove(fpath)
                _log(f"Cleaned uncached file: {f}")
            except OSError:
                pass


def cmd_search(query: str) -> dict:
    """Search YouTube and return top matches."""
    _log(f"Searching: {query}")

    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "-f", "bestaudio/best",
             "--default-search", "ytsearch5",
             "--print", "%(id)s\t%(title)s\t%(duration)s\t%(channel)s", query],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Search timed out after 30 seconds."}
    except FileNotFoundError:
        return {"ok": False, "error": "yt-dlp not found."}

    if result.returncode != 0:
        return {"ok": False, "error": f"Search failed: {result.stderr.strip()[:500]}"}

    results = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip() or "\t" not in line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            vid, title, dur = parts[0], parts[1], parts[2]
            channel = parts[3] if len(parts) > 3 else ""
            try:
                dur = int(dur)
            except ValueError:
                dur = 0
            results.append({
                "id": vid, "title": title, "channel": channel,
                "duration": dur,
                "url": f"https://youtube.com/watch?v={vid}",
            })

    if not results:
        return {"ok": False, "error": "No results found."}

    return {"ok": True, "results": results[:3], "count": min(len(results), 3)}


def cmd_play(url: str) -> dict:
    """Download audio from URL and play through speaker."""
    _log(f"Playing: {url}")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Shotgun cleanup: kill any stray ffplay/mpg321 before starting
    subprocess.run(["pkill", "-9", "-f", "ffplay"], capture_output=True, timeout=5)
    subprocess.run(["pkill", "-9", "-f", "mpg321"], capture_output=True, timeout=5)

    if AUTO_STOP:
        stop_result = _stop_playback()
        if not stop_result["ok"]:
            return stop_result

    cache = _load_cache()

    # Cached path
    if url in cache:
        cached_file = cache[url]
        if os.path.exists(cached_file):
            _log(f"Using cached file: {cached_file}")
            result = _start_player(cached_file)
            result["cached"] = True
            result["message"] = f"Now playing (cached): {result['title']}"
            return result
        else:
            del cache[url]
            _log(f"Removed stale cache entry: {url}")

    _clean_uncached_files(cache)

    _log("Downloading audio...")
    try:
        dl = subprocess.run(
            ["yt-dlp", "-f", "bestaudio/best", "--extract-audio",
             "--audio-format", "mp3", "--audio-quality", "0",
             "-o", f"{DOWNLOAD_DIR}/%(title)s.%(ext)s", "--no-playlist",
             "--print", "after_move:filename", url],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Download timed out after 120 seconds."}

    if dl.returncode != 0:
        return {"ok": False, "error": f"Download failed: {dl.stderr.strip()[:500]}"}

    audio_file = None
    for line in dl.stdout.strip().split("\n"):
        line = line.strip()
        if line.endswith(".mp3") and os.path.exists(line):
            audio_file = line
            break
    if not audio_file:
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(".mp3"):
                audio_file = os.path.join(DOWNLOAD_DIR, f)
                break

    if not audio_file or not os.path.exists(audio_file):
        return {"ok": False, "error": "Download completed but output file not found."}

    _log(f"Downloaded: {audio_file} ({os.path.getsize(audio_file)} bytes)")
    cache[url] = audio_file
    _save_cache(cache)

    return _start_player(audio_file)


def cmd_stop() -> dict:
    """Stop playback."""
    return _stop_playback()


def cmd_status() -> dict:
    """Check if music is playing."""
    pid = _find_player_pid()
    active = os.path.exists(MUSIC_ACTIVE_FLAG)
    return {
        "ok": True,
        "playing": pid is not None,
        "pid": pid,
        "flag_active": active,
    }


def main():
    parser = argparse.ArgumentParser(description="Mini Pupper Music Player")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_search = subparsers.add_parser("search", help="Search YouTube")
    p_search.add_argument("query", nargs="+")

    p_play = subparsers.add_parser("play", help="Download and play audio")
    p_play.add_argument("url", help="YouTube URL")

    subparsers.add_parser("stop", help="Stop playback")
    subparsers.add_parser("status", help="Check playback status")

    args = parser.parse_args()

    if args.command == "search":
        result = cmd_search(" ".join(args.query))
    elif args.command == "play":
        result = cmd_play(args.url)
    elif args.command == "stop":
        result = cmd_stop()
    elif args.command == "status":
        result = cmd_status()
    else:
        result = {"ok": False, "error": f"Unknown: {args.command}"}

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
