#!/usr/bin/env python3
"""
hf_dance_to_audio.py — Mini Pupper Dance Machine (HF-powered)

Same flow as dance_to_audio.py, but beat detection comes from
Hugging Face (Bedrock510/music-metadata-app Space) instead of local aubio.

HF dependency: Every dance downloads audio, sends a segment to
HF Space for BPM analysis, then generates choreography.

Subcommands:
    search <query>        — Search YouTube, return top results as JSON
    dance <url>           — Download audio, HF analysis, dance (background)
    stop                  — Stop dancing and kill audio immediately
    status                — Check if currently dancing
    execute <state_file>  — Internal: run choreography in subprocess

Usage:
    python3 custom/hf_dance_to_audio.py search "Shape of You Ed Sheeran"
    python3 custom/hf_dance_to_audio.py dance "https://youtube.com/watch?v=..."
    python3 custom/hf_dance_to_audio.py stop
    python3 custom/hf_dance_to_audio.py status
"""

import argparse
import json
import os
# Hugging Face Space for beat analysis
HF_SPACE = os.environ.get("HF_DANCE_SPACE", "grlayndra/pupper-dance-analyzer")
import signal
import subprocess
import sys
import time

# -- HF API -----------------------------------------------------------------

# -- Constants ---------------------------------------------------------------
DANCE_ACTIVE_FLAG = "/tmp/minipupper_dance_active"
AUDIO_PID_FILE = "/tmp/minipupper_dance_audio.pid"
DANCE_PID_FILE = "/tmp/minipupper_dance_pid"
DANCE_STATE_FILE = "/tmp/minipupper_dance_state.json"
MUSIC_ACTIVE_FLAG = "/tmp/minipupper_music_active"
DANCE_RESULT_FILE = "/tmp/minipupper_dance_result.json"
LOG_FILE = "/tmp/minipupper_dance_player.log"
DOWNLOAD_DIR = "/tmp/minipupper_music"
WAV_DIR = "/tmp/minipupper_dance_wav"
CACHE_FILE = "/tmp/minipupper_dance_cache.json"

# -- Logging
# -- Logging -----------------------------------------------------------------

def _log(msg: str):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except OSError:
        pass
    
# -- PID Tracking ------------------------------------------------------------

def _find_dance_pid():
    """Return PID of the dance background process, or None."""
    try:
        if os.path.exists(DANCE_PID_FILE):
            with open(DANCE_PID_FILE) as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
                return pid
            except (OSError, ProcessLookupError):
                pass
            
    except (ValueError, OSError):
        pass
    
    return None

def _find_audio_pid():
    """Return PID of running ffplay (audio playback), or None."""
    try:
        if os.path.exists(AUDIO_PID_FILE):
            with open(AUDIO_PID_FILE) as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
                return pid
            except (OSError, ProcessLookupError):
                pass
            
    except (ValueError, OSError):
        pass
    
    return None

def _stop_audio():
    """Kill audio player and clear flags."""
    pid = _find_audio_pid()
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.2)
                except ProcessLookupError:
                    pass
                    break
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            
        except Exception as e:
            _log(f"Error stopping audio: {e}")
    for f in [AUDIO_PID_FILE, MUSIC_ACTIVE_FLAG]:
        try:
            os.remove(f)
        except OSError:
            pass
        
    _log("Audio stopped.")

# -- Volume Control ----------------------------------------------------------

def _set_music_active(active: bool):
    """Create or remove the music-active flag so the app doesn't mute."""
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
        sys.path.insert(0, "/home/ubuntu/minipupper-app")
        from src.audio.audio_util import set_volume as _av
        _av(pct)
    except Exception:
        pass
    

# -- Task Status Updater (LCD display) ---------------------------------------

def _update_dance_status(phase: str, progress: float, message: str):
    """Update the dance task in tasks.json so the LCD and TaskWatcher show status."""
    try:
        p = "/home/ubuntu/minipupper-app/tasks.json"
        with open(p) as f: data = json.load(f)
        for t in data.get("tasks", {}).values():
            s = t.get("status", "")
            if s in ("pending", "processing", "running") and t.get("action", "").startswith("robot.dance"):
                t["phase"] = phase
                t["progress"] = progress
                t["message"] = message
                t["updatedAt"] = time.time()
                break
        with open(p, "w") as f: json.dump(data, f, indent=2)
    except Exception:
        pass

# -- HF Beat Detection (via Custom HF Space) --------------------------------

def _hf_detect_beats(wav_path: str, genre: str = None) -> dict:
    """
    Analyze WAV file by calling your HF Space for BPM, beat timing, and choreography.
    Returns dict with bpm, synthetic beats, genre, and choreography moves.
    """
    _log(f"HF beat analysis: {wav_path} (genre={genre})")

    # Get full song duration from the original WAV (not just the 5s segment)
    full_duration = 180.0
    try:
        import wave as _wave
        with _wave.open(wav_path, 'rb') as _wf:
            _frames = _wf.getnframes()
            _sr = _wf.getframerate()
            full_duration = _frames / _sr if _sr > 0 else 180.0
        _log(f"Full WAV duration: {full_duration:.1f}s")
    except Exception:
        pass

    _log(f"Calling HF Space via raw API (duration={full_duration:.0f}s)...")
    import requests
    _update_dance_status("uploading", 10, "Uploading audio to Hugging Face Space...")

    # Upload full WAV to Space for variable tempo analysis
    with open(wav_path, "rb") as f:
        upload_resp = requests.post(
            f"https://{HF_SPACE.replace(chr(47), chr(45))}.hf.space/gradio_api/upload",
            files={"files": ("audio.wav", f, "audio/wav")},
            timeout=120,
        )
    upload_data = upload_resp.json()
    uploaded_path = upload_data[0] if isinstance(upload_data, list) else upload_data.get("path")
    _log(f"Uploaded: {uploaded_path}")
    _update_dance_status("analyzing", 30, "Analyzing beats from Hugging Face Space...")

    # Predict using uploaded file path
    t0 = time.time()
    # Build Gradio API data array: [audio_file, genre]
    genre_value = genre if genre else "pop"
    predict_resp = requests.post(
        f"https://{HF_SPACE.replace(chr(47), chr(45))}.hf.space/gradio_api/call/predict",
        json={"data": [
            {"path": uploaded_path, "meta": {"_type": "gradio.FileData"}},
            genre_value,
            full_duration,
        ]},
        timeout=120,
    )
    event_id = predict_resp.json().get("event_id")
    _log(f"Event: {event_id}")

    # Poll for result (SSE streaming - reads line by line, breaks immediately on data)
    deadline = time.time() + 180
    result = None
    try:
        while time.time() < deadline and result is None:
            try:
                r = requests.get(
                    f"https://{HF_SPACE.replace(chr(47), chr(45))}.hf.space/gradio_api/call/predict/{event_id}",
                    headers={"Accept": "text/event-stream"},
                    stream=True,
                    timeout=180,
                )
                for line in r.iter_lines(decode_unicode=True):
                    if line and line.startswith("data:"):
                        raw = line[5:].strip()
                        if raw and raw != "null":
                            elapsed = time.time() - t0
                            _log(f"HF response received in {elapsed:.1f}s")
                            _update_dance_status("choreography", 60, "Generating dance choreography...")
                            result = raw
                            break
                r.close()
            except requests.exceptions.RequestException:
                pass
    except Exception as e:
        _log(f"FATAL poll error: {type(e).__name__}: {e}")
        raise

    result = _parse_hf_result(result or "{}", full_duration)
    result["duration"] = full_duration  # full song duration for choreography scheduling
    return result

GENRE_DISPLAY_NAMES = {
    "rock": "🤘 Rock",
    "classical": "🎵 Classical",
    "pop": "🎤 Pop",
    "jazz": "🎷 Jazz",
    "electronic": "⚡ Electronic",
    "hiphop": "🎧 Hip-Hop",
    "chill": "🌊 Chill",
}

def _parse_hf_result(result_text, duration: float) -> dict:
    """
    Parse JSON response from HF Space.

    Expected Space JSON: {bpm, genre, duration_sec, timed_choreography}
    timed_choreography: [[cmd, duration_sec, angle, start_time_sec], ...]

    Returns dict with genre, genre_display, and timed choreography.
    """
    text = str(result_text)

    # Unwrap Gradio event-stream wrapper
    parsed = {}
    try:
        raw = json.loads(text)
        # Case 1: raw is a list wrapping a JSON string
        if isinstance(raw, list) and len(raw) > 0:
            inner = raw[0]
            if isinstance(inner, str):
                parsed = json.loads(inner)
            elif isinstance(inner, dict):
                parsed = inner
        # Case 2: raw is a dict
        elif isinstance(raw, dict):
            if "data" in raw:
                inner = raw["data"]
                if isinstance(inner, list) and len(inner) > 0:
                    inner_val = inner[0]
                    if isinstance(inner_val, str):
                        parsed = json.loads(inner_val)
                    elif isinstance(inner_val, dict):
                        parsed = inner_val
            else:
                parsed = raw
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        _log(f"HF non-JSON response: {text[:100]}")
        pass

    if not parsed or "error" in parsed:
        return {"error": parsed.get("error", "Could not parse HF Space response")}

    # Extract timed choreography
    raw_choreo = parsed.get("timed_choreography", [])
    if not raw_choreo or not isinstance(raw_choreo, list) or len(raw_choreo) < 4:
        return {"error": "HF Space did not return timed choreography"}

    timed_moves = []
    for entry in raw_choreo:
        if len(entry) >= 4:
            timed_moves.append((
                str(entry[0]),    # cmd
                float(entry[1]),  # time_acc
                entry[2] if entry[2] is not None else None,  # angle
                float(entry[3]),  # start_time
            ))

    # Extract genre
    raw_genre = parsed.get("genre", "pop").lower()
    valid_genres = ("rock", "classical", "pop", "jazz", "electronic", "hiphop", "chill")
    genre = raw_genre if raw_genre in valid_genres else "pop"
    genre_display = GENRE_DISPLAY_NAMES.get(genre, "Pop")

    bpm = parsed.get("bpm") or parsed.get("tempo", 120)
    total_dur = parsed.get("duration_sec", duration)

    _log(f"HF Space: genre={genre_display}, {len(timed_moves)} timed moves, "
         f"BPM={bpm}, total={total_dur:.0f}s")

    return {
        "genre": genre,
        "genre_display": genre_display,
        "timed_choreography": timed_moves,
        "bpm": float(bpm) if bpm else 120,
        "duration": total_dur,
        "source": "hf_space",
    }

def _init_robot():
    """Import robot control functions (no auto-activation)."""
    robot_dir = "/home/ubuntu/minipupper-app/robot"
    if robot_dir not in sys.path:
        sys.path.insert(0, robot_dir)
    from robot_control import _build_movement, run_movement

    return _build_movement, run_movement

def _activate_robot(build_movement, run_movement):
    """Stand the robot up."""
    _log("Activating robot...")
    lib = build_movement("activate", 0.5, None)
    run_movement(lib, timeout=5.0)
    _log("Robot activated.")

def _choreography_loop(build_movement, run_movement,
                       beat_info: dict, timed_choreography: list,
                       wav_file: str, title: str,
                       genre: str = "unknown", genre_display: str = "Generic") -> dict:
    """
    Main dance loop: play audio while executing timed moves.
    timed_choreography: list of (cmd, duration, angle, start_time) tuples.
    Checks DANCE_ACTIVE_FLAG on each iteration for immediate stop.
    Returns result dict.
    """
    bpm = beat_info.get("bpm", 120)

    _log(f"Timed choreography: {len(timed_choreography)} moves, BPM={bpm}")

    # Write active flag
    try:
        open(DANCE_ACTIVE_FLAG, "w").close()
    except OSError:
        pass

    # Set volume
    _set_volume("85%")
    _set_music_active(True)

    # Start audio playback
    # Double-pkill to prevent duplicate ffplay instances (race-safe)
    if wav_file:
        subprocess.run(
            ["pkill", "-f", f"ffplay.*{os.path.basename(wav_file)}"],
            capture_output=True, timeout=3
        )
        time.sleep(0.3)
        subprocess.run(
            ["pkill", "-f", f"ffplay.*{os.path.basename(wav_file)}"],
            capture_output=True, timeout=3
        )
    player = subprocess.Popen(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
         "-af", "volume=0.85", wav_file],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    with open(AUDIO_PID_FILE, "w") as f:
        f.write(str(player.pid))
    _log(f"Audio player PID: {player.pid}")

    # Execute timed moves

    # Sort moves by start_time just in case
    sorted_moves = sorted(timed_choreography, key=lambda m: m[3])
    max_moves = len(sorted_moves)

    # Head pose lookup for gap-filling (holds last pose instead of resetting)
    # Per-move execution: sleep_until each beat, execute one move, repeat.
    # No window batching — each move fires exactly on its beat timestamp,
    # with natural idle in between. Gaps expand/contract with BPM changes.

    audio_start = time.time() + 0.5  # lead-in
    moves_done = 0
    last_attitude = None  # tracks where servos are for snap-free transitions

    for i, move in enumerate(sorted_moves):
        cmd, time_acc, angle, start_time = move
        
        if not os.path.exists(DANCE_ACTIVE_FLAG):
            _log("Dance stopped - abort.")
            break

        # Stop when audio finishes playing
        if player.poll() is not None:
            _log(f"Audio ended at {start_time:.1f}s — stopping dance.")
            break

        # Wall-clock sync: wait for this exact beat time
        target = audio_start + start_time
        now = time.time()
        sleep_time = target - now
        if sleep_time > 0:
            time.sleep(sleep_time)

        # Calculate hold to fill the gap to the next beat
        if i + 1 < len(sorted_moves):
            gap = sorted_moves[i + 1][3] - start_time
            hold = max(gap - time_acc, 0.1)
        else:
            hold = 0.5

        # Build and execute this single move
        try:
            lib = build_movement(cmd, hold, angle, time_acc)
            if lib:
                ok, last_attitude = run_movement(lib, timeout=hold + time_acc + 0.5,
                                                  initial_attitude=last_attitude)
                moves_done += 1
                if moves_done % 20 == 0:
                    _log(f"[{moves_done}/{max_moves}] {start_time:.1f}s")
        except Exception as e:
            _log(f"Move error ({cmd}): {e}")

    _log(f"Dance finished: {moves_done}/{max_moves} moves executed")

    return {
        "ok": True,
        "message": f"Danced to '{title}' - {moves_done} moves at {bpm} BPM ({genre_display})",
        "title": title,
        "bpm": bpm,
        "moves_executed": moves_done,
        "genre": genre,
        "genre_display": genre_display,
        "source": "hf_space",
    }

def _load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_cache(cache: dict):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def _detect_genre_from_url(url: str) -> dict:
    """Detect song genre from YouTube metadata."""
    _log(f'Detecting genre for: {url}')
    try:
        meta = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-playlist", url],
            capture_output=True, text=True, timeout=15,
        )
        if meta.returncode != 0:
            return {"genre": "pop", "genre_display": "Pop"}

        data = json.loads(meta.stdout)
        tags = [t.lower() for t in data.get("tags", []) or []]
        categories = [c.lower() for c in data.get("categories", []) or []]
        channel = (data.get("channel", "") or "").lower()
        title = (data.get("title", "") or "").lower()

        genre_keywords = {
            "rock": ["rock", "metal", "punk", "alternative", "grunge", "hard rock", "indie rock"],
            "classical": ["classical", "orchestra", "symphony", "piano", "violin", "mozart", "beethoven", "bach", "chopin"],
            "jazz": ["jazz", "blues", "bebop", "swing", "smooth jazz"],
            "electronic": ["electronic", "edm", "techno", "house", "dubstep", "trance", "dance", "remix"],
            "hiphop": ["hip hop", "hip-hop", "rap", "r&b", "rnb", "trap", "drill"],
            "chill": ["chill", "ambient", "lo-fi", "lofi", "relax", "mellow", "study"],
        }

        # Score each genre
        scores = {g: 0 for g in genre_keywords}
        for genre, keywords in genre_keywords.items():
            for kw in keywords:
                for tag in tags:
                    if kw in tag:
                        scores[genre] += 10
                for cat in categories:
                    if kw in cat:
                        scores[genre] += 8
                if kw in channel:
                    scores[genre] += 6
                if kw in title:
                    scores[genre] += 4

        best_genre = max(scores, key=scores.get)
        if scores[best_genre] == 0:
            best_genre = "pop"

        _log(f'Detected genre: {best_genre} (scores: {scores})')
        return {"genre": best_genre, "genre_display": GENRE_DISPLAY_NAMES.get(best_genre, "Pop")}
    except Exception as e:
        _log(f'Genre detection error: {e}')
        return {"genre": "pop", "genre_display": "Pop"}


def cmd_search(query: str) -> dict:
    """Search YouTube and return top matches."""
    _log(f"Searching: {query}")
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "-f", "bestaudio/best",
             "--default-search", "ytsearch1",
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
    # Detect genre for top result
    if results:
        genre_info = _detect_genre_from_url(results[0]["url"])
        results[0]["genre"] = genre_info["genre"]
        results[0]["genre_display"] = genre_info["genre_display"]
        _log(f'Top result genre: {genre_info["genre_display"]}')
    return {"ok": True, "results": results, "count": len(results)}

def cmd_dance(url: str, genre_override: str = None, no_activate: bool = False) -> dict:
    """
    Download -> HF beat analysis -> launch background dance -> return.

    1. Download audio (same as dance_to_audio.py)
    2. Convert to WAV
    3. Send 5s segment to Bedrock510 HF Space for BPM
    4. Generate choreography
    5. Launch background subprocess for dance execution
    6. Return immediately
    """
    _log(f"HFDance requested: {url}")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(WAV_DIR, exist_ok=True)

    # Shotgun cleanup: kill any stray audio and previous dance processes
    subprocess.run(["pkill", "-9", "-f", "ffplay"], capture_output=True, timeout=5)
    subprocess.run(["pkill", "-9", "-f", "hf_dance_to_audio.py.*execute"], capture_output=True, timeout=5)

    # Stop any existing dance
    _stop_background_dance()
    _stop_audio()
    for f in [DANCE_ACTIVE_FLAG, DANCE_PID_FILE]:
        try:
            os.remove(f)
        except OSError:
            pass
        
    cache = _load_cache()
    audio_file = cache.get(url)
    if audio_file and os.path.exists(audio_file):
        _log(f"Using cached audio: {audio_file}")
    else:
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
            if line.endswith((".mp3", ".m4a")) and os.path.exists(line):
                audio_file = line
                break
        if not audio_file:
            mp3_files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR)
                         if f.endswith(".mp3")]
            if mp3_files:
                audio_file = max(mp3_files, key=os.path.getmtime)
        if not audio_file or not os.path.exists(audio_file):
            return {"ok": False, "error": "Download completed but output file not found."}
        _log(f"Downloaded: {audio_file} ({os.path.getsize(audio_file)} bytes)")
        cache[url] = audio_file
        _save_cache(cache)

    title = os.path.splitext(os.path.basename(audio_file))[0]

    # Convert to WAV for analysis
    _log("Converting to WAV for analysis...")
    safe_title = title.replace("/", "_").replace(" ", "_")
    wav_path = os.path.join(WAV_DIR, f"{safe_title}.wav")
    if not os.path.exists(wav_path):
        try:
            ffmpeg = subprocess.run(
                ["ffmpeg", "-y", "-i", audio_file,
                 "-ac", "1", "-ar", "22050", "-f", "wav", wav_path],
                capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Audio conversion timed out."}
        if ffmpeg.returncode != 0:
            return {"ok": False, "error": f"Conversion failed: {ffmpeg.stderr.strip()[:300]}"}
    _log(f"WAV ready: {wav_path}")

    # Detect beats + genre + choreography via Hugging Face
    beat_info = _hf_detect_beats(wav_path, genre=genre_override)
    if "error" in beat_info:
        return beat_info
    timed = beat_info.get("timed_choreography")
    if not timed:
        return {"ok": False, "error": "HF Space did not return timed choreography"}

    genre = beat_info.get("genre", "pop")
    genre_display = beat_info.get("genre_display", "Pop")
    _log(f"HF Space: {len(timed)} timed moves, genre: {genre_display}")

    # Save state for background process
    state = {
        "beat_info": beat_info,
        "wav_path": wav_path,
        "title": title,
        "timed_choreography": timed,
        "genre": genre,
        "genre_display": genre_display,
        "no_activate": no_activate,
    }
    with open(DANCE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    # Write pre-start result so caller can mark task completed early
    # Robot hasn't moved yet — choreography is fully ready
    pre_result = {
        "status": "dancing",
        "ok": True,
        "message": f"Dancing to '{title}' ({genre_display})...",
        "title": title,
        "genre": genre,
        "genre_display": genre_display,
        "pid": None,
    }
    with open(DANCE_RESULT_FILE, "w") as f:
        json.dump(pre_result, f, indent=2)

    # Launch dance in background
    script_path = os.path.abspath(__file__)
    proc = subprocess.Popen(
        ["python3", script_path, "execute", DANCE_STATE_FILE],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    with open(DANCE_PID_FILE, "w") as f:
        f.write(str(proc.pid))

    _log(f"Dance background PID: {proc.pid}")

    # Mark the task as processing so cron doesn't re-trigger
    try:
        tasks_path = "/home/ubuntu/minipupper-app/tasks.json"
        with open(tasks_path) as f:
            td = json.load(f)
        for tid, t in td.get("tasks", {}).items():
            if t.get("status") == "pending" and t.get("action", "").startswith("robot.dance"):
                t["status"] = "processing"
                t["phase"] = "dancing"
                t["progress"] = 50
                t["message"] = f"Dancing to '{title}' ({genre_display})..."
                t["result"] = {
                    "summary": f"Dancing to {title}",
                    "title": title,
                    "genre": genre,
                    "genre_display": genre_display,
                }
                t["updatedAt"] = time.time()
                _log(f"Marked task {tid} as processing")
                break
        with open(tasks_path, "w") as f:
            json.dump(td, f, indent=2)
    except Exception as e:
        _log(f"Failed to update tasks.json: {e}")

    return {
        "ok": True,
        "message": f"Dancing to '{title}' ({genre_display})...",
        "title": title,
        "genre": genre,
        "genre_display": genre_display,
        "pid": proc.pid,
        "bpm": beat_info["bpm"],
        "source": "hf_space",
    }

def cmd_execute(state_path: str) -> dict:
    """
    Internal: run the choreography in a subprocess.

    Loads state, activates robot, dances, deactivates, writes result.
    Checks DANCE_ACTIVE_FLAG throughout for immediate stop.
    """
    _log(f"Executing dance from state: {state_path}")
    with open(state_path) as f:
        state = json.load(f)

    beat_info = state["beat_info"]
    wav_path = state["wav_path"]
    title = state["title"]
    timed_choreo = [tuple(m) for m in state.get("timed_choreography", [])]
    genre = state.get("genre", "unknown")
    genre_display = state.get("genre_display", "Generic")
    no_activate = state.get("no_activate", True)

    # Initialize robot
    try:
        build_movement, run_movement = _init_robot()
        if not no_activate:
            _activate_robot(build_movement, run_movement)
    except Exception as e:
        result = {"ok": False, "error": f"Robot init failed: {e}"}
        with open(DANCE_RESULT_FILE, "w") as f:
            json.dump(result, f, indent=2)
        return result

    # Dance!
    try:
        result = _choreography_loop(build_movement, run_movement,
                                     beat_info, timed_choreo, wav_path, title,
                                     genre=genre, genre_display=genre_display)
    except Exception as e:
        result = {"ok": False, "error": f"Dance loop crashed: {e}"}
        _log(f"Dance loop error: {e}")

    result["status"] = "completed"
    result["bpm"] = beat_info.get("bpm", 120)
    result["title"] = title
    result["genre"] = genre
    result["genre_display"] = genre_display
    result["source"] = "hf_space"

    # Deactivate robot (only if we activated it)
    if not no_activate:
        try:
            _log("Deactivating robot...")
            lib = build_movement("deactivate", 0.5, None)
            run_movement(lib, timeout=5.0)
            _log("Robot deactivated.")
        except Exception as e:
            _log(f"Deactivation error: {e}")

    # Write result
    with open(DANCE_RESULT_FILE, "w") as f:
        json.dump(result, f, indent=2)
    _log(f"Result written: {result.get('message', '?')}")

    # Update tasks.json directly so the cron can pick up completion
    try:
        tasks_path = "/home/ubuntu/minipupper-app/tasks.json"
        with open(tasks_path) as f:
            tasks_data = json.load(f)
        for tid, t in tasks_data.get("tasks", {}).items():
            if t.get("status") == "processing" and t.get("action", "").startswith("robot.dance"):
                t["status"] = "completed"
                t["phase"] = "done"
                t["progress"] = 100
                t["message"] = result.get("message", "Dance completed")
                t["result"] = result
                t["updatedAt"] = time.time()
                _log(f"Updated task {tid} to completed")
                break
        with open(tasks_path, "w") as f:
            json.dump(tasks_data, f, indent=2)
    except Exception as e:
        _log(f"Failed to update tasks.json: {e}")

    # Clean up flag files
    for f in [DANCE_ACTIVE_FLAG, DANCE_PID_FILE]:
        try:
            os.remove(f)
        except OSError:
            pass

    # Clear music active flag
    _set_music_active(False)

    return result

def _stop_background_dance():
    """Kill the dance background subprocess immediately."""
    pid = _find_dance_pid()
    if pid is not None:
        _log(f"Killing dance process PID {pid}")
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.2)
                except ProcessLookupError:
                    pass
                    break
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            
        except Exception as e:
            _log(f"Error killing dance process: {e}")

def cmd_stop() -> dict:
    """Stop dancing and audio playback immediately."""
    _log("Stop requested.")

    # FIRST: Remove the active flag — choreography loop checks this
    # on every iteration for immediate abort
    # Kill any stray audio processes (even untracked orphans)
    subprocess.run(["pkill", "-9", "-f", "ffplay"], capture_output=True, timeout=5)
    subprocess.run(["pkill", "-9", "-f", "mpg321"], capture_output=True, timeout=5)

    # Clean up any processing dance task in tasks.json
    try:
        tasks_path = "/home/ubuntu/minipupper-app/tasks.json"
        with open(tasks_path) as f:
            tasks_data = json.load(f)
        for tid, t in list(tasks_data.get("tasks", {}).items()):
            if t.get("status") == "processing" and t.get("action", "").startswith("robot.dance"):
                t["status"] = "stopped"
                t["phase"] = "stopped"
                t["progress"] = 100
                t["message"] = "Dance stopped by user"
                t["updatedAt"] = time.time()
                _log(f"Cleaned up processing dance task: {tid}")
        with open(tasks_path, "w") as f:
            json.dump(tasks_data, f, indent=2)
    except Exception as e:
        _log(f"tasks.json cleanup: {e}")

    # THEN: Deactivate robot BEFORE killing the background process
    # (SIGKILL kills immediately — deactivation won't run in cmd_execute)
    try:
        _log("Deactivating robot...")
    #     subprocess.run(
    #         ["python3", "/home/ubuntu/minipupper-app/robot/robot_control.py", "deactivate"],
    #         capture_output=True, timeout=5.0,
    #     )
    #     _log("Robot deactivated.")
    except Exception as e:
        _log(f"Deactivation error: {e}")

    # THEN: Kill the background process
    _stop_background_dance()

    # THEN: Stop audio
    _stop_audio()

    # Clean up remaining flags
    for f in [DANCE_PID_FILE, DANCE_ACTIVE_FLAG]:
        try:
            os.remove(f)
        except OSError:
            pass
        
    _set_music_active(False)

    _log("Dance stopped.")
    return {"ok": True, "message": "Dance stopped."}

def cmd_status() -> dict:
    """Check dance status."""
    dance_pid = _find_dance_pid()
    audio_pid = _find_audio_pid()
    flag_active = os.path.exists(DANCE_ACTIVE_FLAG)
    result_exists = os.path.exists(DANCE_RESULT_FILE)
    return {
        "ok": True,
        "dancing": dance_pid is not None,
        "dance_pid": dance_pid,
        "audio_pid": audio_pid,
        "flag_active": flag_active,
        "result_ready": result_exists,
    }

# -- CLI ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Mini Pupper Dance Machine (HF-powered)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_search = subparsers.add_parser("search", help="Search YouTube")
    p_search.add_argument("query", nargs="+")

    p_dance = subparsers.add_parser("dance", help="Download audio and dance via HF (background)")
    p_dance.add_argument("url", help="YouTube URL")
    p_dance.add_argument("--genre", "-g", default=None,
                        help="Genre override (rock, classical, pop, jazz, electronic, hiphop, chill)")
    p_dance.add_argument("--no-activate", action="store_true",
                        help="Skip robot activation (assume already standing)")

    p_exec = subparsers.add_parser("execute", help="Internal: run choreography")
    p_exec.add_argument("state_file", help="Dance state JSON path")

    subparsers.add_parser("stop", help="Stop dancing")

    subparsers.add_parser("status", help="Check dance status")

    args = parser.parse_args()

    if args.command == "search":
        result = cmd_search(" ".join(args.query))
    elif args.command == "dance":
        result = cmd_dance(args.url, genre_override=args.genre, no_activate=args.no_activate)
    elif args.command == "execute":
        result = cmd_execute(args.state_file)
    elif args.command == "stop":
        result = cmd_stop()
    elif args.command == "status":
        result = cmd_status()
    else:
        result = {"ok": False, "error": f"Unknown: {args.command}"}

    print(json.dumps(result, indent=2))
    try:
        with open(DANCE_RESULT_FILE, "w") as f:
            json.dump(result, f, indent=2)
    except OSError:
        pass
    
    sys.exit(0 if result.get("ok") else 1)

if __name__ == "__main__":
    main()