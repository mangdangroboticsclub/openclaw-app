# Mini Pupper Dance Machine 🕺

Make your robot dog dance to any song on YouTube! It analyzes the beat, picks genre-appropriate moves, plays the music through its speaker, and cycles faces on its LCD — all automatically.

## Quick Start (Two-Turn Flow)

### Turn 1 — Search

Tell your robot to search:

> **"Dance to Bohemian Rhapsody"**

I'll search YouTube and return the search result ("I found Queen – Bohemian Rhapsody (Official Video Remastered) for you, should I dance to it?)."

### Turn 2 — Confirm

> **"Yes sure dance to it"**

That's it. The robot will:
1. Download the song
2. Analyze the beat (via Hugging Face)
3. Detect the genre
4. Generate choreography (seeded from song URL — same song = same dance)
5. Activate, play music, and dance synchronized to the beat
6. Cool down automatically when the song ends
7. Or you can stop the dance and audio process by directly telling the robot "Stop"

> **⏱️ Setup takes about 30-50 seconds** (download + analysis), then the show starts.

---

## Direct Commands

| You say | What happens |
|---------|-------------|
| `robot.dance <youtube_url>` | Skip search, go straight to dancing |
| `robot.dance <url> --genre rock` | Override genre detection |
| `robot.stop_dance` | Stop everything immediately |
| `robot.classify_dance <url>` | Test genre detection without dancing |
| `robot.genre <url>` | Same as classify |

---

## What Happens Behind the Scenes

1. **Download** — MP3 downloaded from YouTube via yt-dlp
2. **Convert** — MP3 → WAV (wave audio)
3. **Beat Analysis** — WAV uploaded to Hugging Face Space → librosa detects BPM, beat timing, and energy per beat
4. **Genre Detection** — YouTube metadata (tags, title, channel) is scanned to classify genre
5. **Choreography** — Seed based on song URL → deterministic RNG picks moves from the genre's move pool
6. **Execution** — Robot activates → ffplay plays audio → movement commands fire at beat timestamps → LCD cycles through REST→TROT→HOP→FINISHHOP faces
7. **Cooldown** — When audio ends (or ALSA goes silent), robot deactivates automatically

---

## Supported Genres (11)

| Genre | Vibe |
|-------|-------|
| 🚨 **Rock** | Headbang, robot bouncing, lean forward and head tilt |
| 🍵 **Classical** | Slow and graceful - bows, squat, elegant body circular move |
| 🏤 **Pop** | Energetic — twerks, swagger, wiggles, stepping |
| 🌀 **Lean** | Special mode — full-body sustained leans with tilt LCD face |
| 🏧 **Hip-Hop** | Bouncy — front kicks, leg lifts, head nods |
| 🕺 **Disco** | Groovy — shoulder shrugs, head ellipses, assertive looks to the right |
| ⚡ **Electronic** | Fast rhythmic — seeking scans (looking right and left), sharp looking up, wiggle butt to the right |
| 🍷 **Jazz** | Smooth — cool looking upper-left, right shoulder shrugs, downward gaze |
| 💃 **Latin** | Passionate — butt shrugs, body rows, left hip wiggles |
| 🌴 **Reggae*� | Laid-back — chill elevation, left butt shrugs, relaxed looking lower-left |
| 🪕 2**Folk** | Organic — look lower-right, left shoulder shrugs, looking left |


---

## Stopping / Troubleshooting

| Problem | Fix |
|---------|------|
| Music won't stop | Say **"stop dancing"** or **"stop the music"** or **stop** |
| Robot not moving | Make sure the robot is on a flat surface and powered |
| Dance looks wrong genre | Override with `robot.dance <url> --genre rock` |
| Audio cuts out early | Check speaker volume, robot may have auto-muted |

---

## Limitations

- **YouTube only** — currently supports YouTube URLs via yt-dll
- **Requires internet** — HF Space beat analysis needs internet access
- **~20–30s cold start** — download + HF analysis take time before dancing begins
- **YouTube authentication** — `cookies.txt` must be maintained for yt-dlp downloads (cookies expire and need periodic renewal)
- **Audio sync** — beat timing is computed upfront (not live), so variable-tempo songs may drift
- **One dance at a time** — concurrent dances are not supported
