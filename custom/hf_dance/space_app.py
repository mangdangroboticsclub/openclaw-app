"""
Pupper Dance Analyzer — HF Space for Mini Pupper Beat Timing

Accepts full audio clips + song duration, performs real beat detection
via librosa, and returns timed beat slots with energy-based time_acc.

No genre knowledge, no choreography — just timing.
The Pi handles genre-specific move selection.

API:
    POST (audio, duration_sec) → {bpm, duration_sec, beat_slots[]}

beat_slots: [{start_time: float, time_acc: float, local_bpm: float}, ...]
"""

import json
import gradio as gr
import numpy as np
import librosa



def analyze_audio(audio, duration_sec: float = 180.0):
    """Analyze audio for BPM + beat timing + energy-based time_acc.

    Args:
        audio: numpy audio tuple (sr, y) from Gradio.
        duration_sec: Total song duration in seconds.

    Returns:
        JSON dict with bpm, duration_sec, and beat_slots array.
    """
    if audio is None:
        return json.dumps({"error": "No audio provided"})
    try:
        sr, y = audio
    except (TypeError, ValueError) as e:
        return json.dumps({"error": f"Invalid audio format: {e}"})
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    if np.max(np.abs(y)) > 0:
        y = y / np.max(np.abs(y))
    total_duration = max(10.0, min(float(duration_sec), 600.0))

    try:
        # --- 1. Onset strength envelope ---
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)

        # --- 2. Dual-bias beat tracking ---
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_env, sr=sr, units="frames"
        )

        candidates = []
        for start_bpm in (60, 120):
            t, b = librosa.beat.beat_track(
                onset_envelope=onset_env, sr=sr, units="frames",
                start_bpm=start_bpm
            )
            bpm = float(np.round(
                t.item() if hasattr(t, "item") else t, 1
            ))
            b_set = set(b[::2])
            hits = sum(1 for o in onset_frames
                       if any(abs(o - bf) <= 3 for bf in b_set))
            score = hits / max(len(onset_frames), 1)
            candidates.append((score, bpm, b))
            print(f"[Space]  start_bpm={start_bpm} -> BPM={bpm:.0f}, "
                  f"onset alignment={score:.2f} (/{len(onset_frames)} onsets)")

        candidates.sort(key=lambda x: x[0], reverse=True)
        bpm_global, beat_frames = candidates[0][1], candidates[0][2]
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        print(f"[Space] Winner: {len(beat_times)} beats at ~{bpm_global:.0f} BPM")

        # --- 3. Per-beat BPM from inter-beat-intervals ---
        beat_count = len(beat_times)
        bpm_per_beat = []
        for i in range(beat_count - 1):
            ibi = beat_times[i + 1] - beat_times[i]
            bpm_per_beat.append(60.0 / ibi if ibi > 0.01 else bpm_global)
        bpm_per_beat.append(bpm_per_beat[-1] if bpm_per_beat else bpm_global)

        window = max(3, beat_count // 30)
        smooth_kernel = np.ones(window) / window
        bpm_smooth = np.convolve(bpm_per_beat, smooth_kernel, mode="same").tolist()

        # --- 4. RMS energy envelope ---
        frame_length = 2048
        hop_length = 512
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
        rms_min, rms_max = float(np.min(rms)), float(np.max(rms))
        rms_norm = ((rms - rms_min) / (rms_max - rms_min + 1e-10)).tolist() if rms_max > rms_min else [0.5] * len(rms)

        # --- 5. Build beat slots ---
        beat_slots = []
        for slot_idx in range(0, beat_count, 2):
            beat_time = beat_times[slot_idx]
            if beat_time > total_duration:
                break

            local_bpm = bpm_smooth[min(slot_idx, beat_count - 1)]

            rms_at_beat = float(np.interp(beat_time, rms_times, rms_norm))
            energy_acc = 0.25 if rms_at_beat > 0.3 else 0.6
            bpm_acc = 0.25 if local_bpm > 109 else 0.5
            time_acc = max(bpm_acc, energy_acc)

            beat_slots.append({
                "start_time": round(beat_time, 3),
                "time_acc": time_acc,
                "local_bpm": round(local_bpm, 1),
            })

        print(f"[Space] Generated {len(beat_slots)} beat slots")

        result = {
            "bpm": bpm_global,
            "duration_sec": round(total_duration, 1),
            "beat_slots": beat_slots,
        }
        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Analysis failed: {str(e)}"})


DESCRIPTION = "# Pupper Dance Analyzer\n\nUpload full audio + song duration. Returns BPM and timed beat slots."

iface = gr.Interface(
    fn=analyze_audio,
    inputs=[
        gr.Audio(type="numpy", label="Upload Full Song Audio"),
        gr.Number(value=180.0, minimum=10.0, maximum=600.0, step=5.0,
                  label="Song Duration (seconds)"),
    ],
    outputs=gr.Textbox(label="Analysis Results (JSON)", lines=15),
    description=DESCRIPTION,
    api_name="predict",
)

if __name__ == "__main__":
    iface.launch(show_error=True)
