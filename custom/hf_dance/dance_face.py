"""
dance_face.py — Mini Pupper LCD Face Display for Dance Choreography

Cycles through REST → TROT → HOP → FINISHHOP faces on the robot's
LCD display, synced to the song's BPM and genre.

Usage:
    from dance_face import generate_face_cues, DanceFace

    cues = generate_face_cues(bpm=120, duration=180.0, genre="pop")
    df = DanceFace()
    df.start(cues, stop_flag_path="/tmp/minipupper_dance_active")
    # ... dance loop runs ...
    df.stop()
"""

import os
import time
import threading
from enum import Enum
from MangDang.mini_pupper.display import Display

# Lean choreo image directory (relative to this file)
LEAN_IMG_DIR = os.path.dirname(os.path.abspath(__file__))


def _show_on_lcd(img_path: str):
    """Display a static image on the ST7789 LCD, resized and centered."""
    from PIL import Image
    try:
        d = Display()
        w, h = d.disp.width, d.disp.height
        img = Image.open(img_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        thumb = img.copy()
        thumb.thumbnail((w, h), Image.LANCZOS)
        thumb = thumb.transpose(Image.FLIP_LEFT_RIGHT)
        bg = Image.new("RGB", (w, h), (0, 0, 0))
        offset = ((w - thumb.width) // 2, (h - thumb.height) // 2)
        bg.paste(thumb, offset)
        tmp = "/tmp/minipupper_lean_face.png"
        bg.save(tmp)
        d.show_image(tmp)
    except Exception:
        pass



class TiltState:
    """Thread-safe shared roll angle — written by control loop, read by display thread."""
    def __init__(self):
        self.roll_deg = 0.0


LEAN_IMG_NORMAL = "dog_tilt2.webp"
LEAN_IMG_INVERTED = "dog_tilt2inv.webp"


def tilt_display_poller(tilt_state, stop_flag_path):
    """Poll tilt_state roll and update LCD on sign change.

    Pre-processes both images once at startup (resize, flip, cache as PIL Image).
    Reuses a single Display() — no re-init, no file I/O per frame.
    Polls at 12 Hz for tighter tracking.
    """
    from PIL import Image
    d = Display()
    w, h = d.disp.width, d.disp.height

    inv_img = None
    norm_img = None
    for path, target in [
        (os.path.join(LEAN_IMG_DIR, LEAN_IMG_INVERTED), "inv"),
        (os.path.join(LEAN_IMG_DIR, LEAN_IMG_NORMAL), "norm"),
    ]:
        if not os.path.exists(path):
            continue
        img = Image.open(path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        thumb = img.copy()
        thumb.thumbnail((w, h), Image.LANCZOS)
        thumb = thumb.transpose(Image.FLIP_LEFT_RIGHT)
        bg = Image.new("RGB", (w, h), (0, 0, 0))
        offset = ((w - thumb.width) // 2, (h - thumb.height) // 2)
        bg.paste(thumb, offset)
        if target == "inv":
            inv_img = bg
        else:
            norm_img = bg

    if inv_img is None or norm_img is None:
        return

    last_sign = 0
    while os.path.exists(stop_flag_path):
        roll = tilt_state.roll_deg
        sign = 1 if roll > 3 else (-1 if roll < -3 else 0)
        if sign != 0 and sign != last_sign:
            img = inv_img if sign < 0 else norm_img
            try:
                d.disp.display(img)  # direct SPI, no file I/O
            except Exception:
                pass
            last_sign = sign
        time.sleep(0.08)




class BehaviorState(Enum):
    DEACTIVATED = -1
    REST = 0
    TROT = 1
    HOP = 2
    FINISHHOP = 3
    SHUTDOWN = 96
    IP = 97
    TEST = 98
    LOWBATTERY = 99


# The face cycle: calm -> moving -> leap -> landing -> repeat
FACE_CYCLE = [
    BehaviorState.REST,       # calm
    BehaviorState.TROT,       # walking
    BehaviorState.HOP,        # leaping!
    BehaviorState.FINISHHOP,  # landing
]

# Genre -> beats per face change (higher = slower / more relaxed)
GENRE_PACING = {
    "classical":   8,   # slow, graceful
    "jazz":        6,   # smooth
    "chill":       8,   # relaxed
    "reggae":      6,   # laid-back
    "folk":        6,   # unhurried
    "pop":         4,   # energetic 4-beat
    "hiphop":      4,   # bouncy
    "country":     4,   # cheerful
    "disco":       4,   # groovy
    "latin":       3,   # faster 3-beat
    "rock":        2,   # aggressive 2-beat
    "electronic":  2,   # rapid-fire
}
DEFAULT_PACING = 4


def generate_face_cues(bpm: float, duration: float, genre: str = "pop") -> list:
    """
    Generate face-change cues synced to BPM and genre pacing.

    Returns list of (cmd, time_acc, angle, start_time) tuples compatible
    with the dance timetable format.

    Fields:
        cmd        = "display"  (sentinel for the dance loop)
        time_acc   = 0.0        (instant -- no acceleration)
        angle      = float      (BehaviorState.value)
        start_time = float      (seconds from audio start)
    """
    if bpm <= 0:
        bpm = 120

    beat_s = 60.0 / bpm
    pacing = GENRE_PACING.get(genre.lower(), DEFAULT_PACING)
    cycle_len = len(FACE_CYCLE)

    cues = []
    beat_num = 0

    while True:
        t = beat_num * beat_s
        if t > duration:
            break

        if beat_num % pacing == 0:
            idx = (beat_num // pacing) % cycle_len
            state_val = float(FACE_CYCLE[idx].value)
            cues.append(("display", 0.0, state_val, t))

        beat_num += 1

    return cues


def _resolve_state(val: float) -> BehaviorState:
    """Convert a stored float back to a BehaviorState enum member."""
    try:
        return BehaviorState(int(val))
    except (ValueError, TypeError):
        return BehaviorState.REST


class DanceFace:
    """
    Manages the Mini Pupper LCD display during a dance session.

    Runs face changes in a lightweight daemon thread that sleeps until
    each cue's timestamp, then calls Display.show_state().

    The thread checks stop_flag_path on every sleep cycle so it dies
    cleanly when cmd_stop() is invoked.
    """

    def __init__(self):
        self.disp = Display()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -----------------------------------------------------------------
    def start(
        self,
        cues: list,
        audio_delay: float = 0.0,
        stop_flag_path: str = "/tmp/minipupper_dance_active",
    ) -> None:
        """
        Start the face-display thread.

        Args:
            cues: (cmd, time_acc, angle, start_time) tuples from
                  generate_face_cues(), OR simpler (state_val, time) pairs.
            audio_delay: Seconds to offset all cue times by.
            stop_flag_path: Thread stops if this file disappears.
        """
        if not cues:
            return

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(cues, audio_delay, stop_flag_path),
            daemon=True,
        )
        self._thread.start()

    # -----------------------------------------------------------------
    def stop(self) -> None:
        """Signal the face thread to stop and wait up to 2s."""
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    # -----------------------------------------------------------------
    def show_now(self, state_val: int) -> None:
        """Immediately show a face (useful for post-dance)."""
        try:
            self.disp.show_state(_resolve_state(state_val))
        except Exception:
            pass

    # -----------------------------------------------------------------
    #  Internal
    # -----------------------------------------------------------------
    def _run(self, cues: list, audio_delay: float, stop_flag_path: str) -> None:
        t0 = time.time()

        # Normalise to (cmd_or_val, start_time) pairs
        # Supports face cues (cmd="display", angle=state_val) and
        # image cues (cmd="image", angle=image_path)
        pairs = []
        for c in cues:
            if len(c) == 2:
                pairs.append((c[0], c[1]))
            elif len(c) >= 4:
                if isinstance(c[0], str) and c[0] == "image":
                    pairs.append((c[2], c[3]))  # (image_path, start_time)
                else:
                    pairs.append((int(c[2]), c[3]))  # (state_val, start_time)
            else:
                continue

        if not pairs:
            return

        for val_or_path, cue_time in pairs:
            if self._stop.is_set() or not os.path.exists(stop_flag_path):
                break

            elapsed = time.time() - t0
            remaining = audio_delay + cue_time - elapsed

            if remaining > 0:
                while remaining > 0 and not self._stop.is_set() and os.path.exists(stop_flag_path):
                    chunk = min(remaining, 0.5)
                    time.sleep(chunk)
                    remaining -= chunk

            if self._stop.is_set() or not os.path.exists(stop_flag_path):
                break

            try:
                if isinstance(val_or_path, int):
                    self.disp.show_state(_resolve_state(val_or_path))
                else:
                    # Image cue: val_or_path is a file path (relative or absolute)
                    full_path = os.path.join(LEAN_IMG_DIR, val_or_path) if not os.path.isabs(val_or_path) else val_or_path
                    if os.path.exists(full_path):
                        _show_on_lcd(full_path)
            except Exception:
                pass


def face_cues_from_choreography(timed_moves: list, genre: str = "pop") -> list:
    """
    Generate face-change cues from the actual choreography timestamps.

    Instead of synthesizing timestamps from BPM, this uses the start_time
    of every Nth entry in the timed choreography. This naturally tracks
    variable tempo because it follows whatever timing the HF Space baked in.

    Args:
        timed_moves: List of (cmd, duration, angle, start_time) tuples.
        genre: Genre string for pacing selection.

    Returns:
        List of (cmd, time_acc, angle, start_time) tuples in the same
        format as generate_face_cues().
    """
    if not timed_moves or not isinstance(timed_moves, list):
        return []

    pacing = GENRE_PACING.get(genre.lower(), DEFAULT_PACING)
    cycle_len = len(FACE_CYCLE)

    cues = []
    for i, entry in enumerate(timed_moves):
        if len(entry) < 4:
            continue
        if i % pacing == 0:
            face_idx = (i // pacing) % cycle_len
            state_val = float(FACE_CYCLE[face_idx].value)
            # Use the choreography entry's actual start_time
            cues.append(("display", 0.0, state_val, entry[3]))

    return cues
